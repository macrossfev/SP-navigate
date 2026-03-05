import json
import requests
import time
import os
import subprocess
import folium
from folium import DivIcon
import pandas as pd

AMAP_KEY = "b6410cb1a118bad10e6d1161d6e896f7"
OUTPUT_DIR = "/root/projects/navigate/route_images"
HTML_DIR = "/root/projects/navigate/route_images/html"
os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(HTML_DIR, exist_ok=True)

# 读取路线规划数据
with open("/root/projects/navigate/路线规划报告.json", "r", encoding="utf-8") as f:
    report = json.load(f)

# 读取地址坐标
addr_df = pd.read_excel("/root/projects/navigate/最终地址列表.xlsx", engine="openpyxl")
addr_coords = {}
for _, row in addr_df.iterrows():
    addr = str(row["地址"]).strip()
    coord = str(row["坐标"]).strip()
    if coord and coord != "nan":
        addr_coords[addr] = coord  # "lng,lat"


def get_driving_polyline(origin_lng, origin_lat, dest_lng, dest_lat):
    """获取驾车路线的坐标点，返回 [(lat, lng), ...]"""
    url = "https://restapi.amap.com/v3/direction/driving"
    params = {
        "origin": f"{origin_lng},{origin_lat}",
        "destination": f"{dest_lng},{dest_lat}",
        "key": AMAP_KEY,
        "extensions": "all",
        "strategy": 0
    }
    try:
        resp = requests.get(url, params=params, timeout=15)
        data = resp.json()
        if data.get("status") != "1":
            return []
        paths = data["route"]["paths"][0]
        points = []
        for step in paths["steps"]:
            for p in step["polyline"].split(";"):
                lng, lat = p.split(",")
                points.append((float(lat), float(lng)))
        return points
    except Exception as e:
        print(f"    API错误: {e}")
        return []


def create_day_map(day_num, sampling_points, coord_list, route_points, filename_html):
    """
    用 folium 生成带清晰标注的地图
    sampling_points: [{"name": "xxx", "short": "xxx"}, ...]
    coord_list: [(lat, lng), ...]  每个采样点的坐标
    route_points: [(lat, lng), ...]  驾车路线的全部坐标点
    """
    # 计算地图中心
    avg_lat = sum(c[0] for c in coord_list) / len(coord_list)
    avg_lng = sum(c[1] for c in coord_list) / len(coord_list)

    m = folium.Map(
        location=[avg_lat, avg_lng],
        zoom_start=14,
        tiles="https://webrd02.is.autonavi.com/appmaptile?lang=zh_cn&size=1&scale=2&style=8&x={x}&y={y}&z={z}",
        attr="高德地图",
        width="100%",
        height="100%",
    )

    # 绘制驾车路线
    if route_points:
        folium.PolyLine(
            locations=route_points,
            weight=5,
            color="#0066FF",
            opacity=0.8,
        ).add_to(m)

    # 添加每个采样点的标注
    for i, (sp, coord) in enumerate(zip(sampling_points, coord_list)):
        num = i + 1
        short_name = sp["short"]

        # 圆形编号标记
        icon_html = f'''<div style="
            background-color: {"#00AA00" if num == 1 else "#CC0000" if num == len(sampling_points) else "#0066FF"};
            color: white;
            border-radius: 50%;
            width: 28px; height: 28px;
            display: flex; align-items: center; justify-content: center;
            font-size: 14px; font-weight: bold;
            border: 2px solid white;
            box-shadow: 0 2px 6px rgba(0,0,0,0.4);
        ">{num}</div>'''

        folium.Marker(
            location=[coord[0], coord[1]],
            icon=DivIcon(
                icon_size=(28, 28),
                icon_anchor=(14, 14),
                html=icon_html,
            ),
        ).add_to(m)

        # 名称标签（紧贴标记右侧）
        label_html = f'''<div style="
            background: rgba(255,255,255,0.92);
            border: 1px solid #666;
            border-radius: 3px;
            padding: 2px 6px;
            font-size: 12px;
            font-weight: bold;
            color: #333;
            white-space: nowrap;
            box-shadow: 0 1px 3px rgba(0,0,0,0.3);
        ">{num}.{short_name}</div>'''

        folium.Marker(
            location=[coord[0], coord[1]],
            icon=DivIcon(
                icon_size=(200, 24),
                icon_anchor=(-18, 12),
                html=label_html,
            ),
        ).add_to(m)

    # 自动适配所有点的范围（增大padding确保标签不被裁切）
    if coord_list:
        m.fit_bounds(coord_list, padding=(60, 60))

    m.save(filename_html)

    # 注入CSS确保地图填满整个视口，无滚动条
    with open(filename_html, "r", encoding="utf-8") as f:
        html_content = f.read()
    css_inject = "<style>html,body{margin:0;padding:0;width:100%;height:100%;overflow:hidden;}.folium-map{position:absolute;top:0;left:0;right:0;bottom:0;}</style>"
    html_content = html_content.replace("</head>", css_inject + "</head>")
    with open(filename_html, "w", encoding="utf-8") as f:
        f.write(html_content)

    return filename_html


def html_to_png(html_path, png_path):
    """用 chromium 无头模式将 HTML 截图为 PNG"""
    cmd = [
        "chromium", "--headless", "--no-sandbox",
        "--disable-gpu", "--disable-software-rasterizer",
        f"--screenshot={png_path}",
        "--window-size=1200,800",
        "--virtual-time-budget=5000",
        f"file://{html_path}"
    ]
    result = subprocess.run(cmd, capture_output=True, timeout=60)
    return os.path.exists(png_path)


# ========== 主程序 ==========

print(f"\n生成 {report['total_days']} 天的导航轨迹图（采样点间路线，带标注）...\n")

for day_info in report["days"]:
    day_num = day_info["day"]
    points = day_info["points"]
    print(f"第{day_num}天 ({day_info['point_count']}个点)...")

    # 跳过首尾基地点，只取采样点
    sampling_points_names = points[1:-1]
    sampling_points = []
    coord_list = []  # [(lat, lng), ...]

    for pt_name in sampling_points_names:
        coord = addr_coords.get(pt_name)
        if coord:
            lng, lat = coord.split(",")
            coord_list.append((float(lat), float(lng)))
            short = pt_name.replace("重庆市长寿区", "").replace("重庆市", "")
            sampling_points.append({"name": pt_name, "short": short})

    if len(coord_list) < 2:
        print(f"  [SKIP] 坐标不足")
        continue

    # 获取每段驾车路线
    all_route_points = []
    for i in range(len(coord_list) - 1):
        o_lat, o_lng = coord_list[i]
        d_lat, d_lng = coord_list[i + 1]
        segment = get_driving_polyline(o_lng, o_lat, d_lng, d_lat)
        all_route_points.extend(segment)
        time.sleep(0.5)

    # 生成 HTML 地图
    html_path = f"{HTML_DIR}/第{day_num}天导航轨迹图.html"
    create_day_map(day_num, sampling_points, coord_list, all_route_points, html_path)

    # 截图为 PNG
    png_path = f"{OUTPUT_DIR}/第{day_num}天导航轨迹图.png"
    success = html_to_png(html_path, png_path)

    if success:
        size_kb = os.path.getsize(png_path) // 1024
        print(f"  [OK] {png_path} ({size_kb}KB)")
    else:
        print(f"  [FAIL] 截图失败")

    time.sleep(0.3)

print(f"\n完成！轨迹图保存在: {OUTPUT_DIR}/")
