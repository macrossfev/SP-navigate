import pandas as pd
import requests
import json
import math
import time
import folium
from itertools import combinations

AMAP_KEY = "b6410cb1a118bad10e6d1161d6e896f7"
BASE_POINT_NAME = "中共重庆市自来水有限公司委员会"
MAX_DAILY_SECONDS = 4 * 3600  # 4小时
MAX_DAILY_POINTS = 5          # 每天最多5个点位
STOP_TIME_SECONDS = 15 * 60   # 每个点位停留15分钟（采样时间）
ROUNDTRIP_OVERHEAD_SECONDS = 155 * 60  # 往返起点(南岸)到长寿区固定开销约155分钟

# ========== 工具函数 ==========

def haversine(coord1, coord2):
    """计算两点间球面距离（公里）"""
    lat1, lon1 = coord1
    lat2, lon2 = coord2
    R = 6371
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon/2)**2
    c = 2 * math.asin(math.sqrt(a))
    return R * c

def estimate_drive_time(dist_km):
    """估算驾车时间（秒），按城市平均35km/h"""
    return dist_km / 35 * 3600

def geocode(address):
    url = "https://restapi.amap.com/v3/geocode/geo"
    params = {"address": address, "city": "重庆", "key": AMAP_KEY}
    resp = requests.get(url, params=params, timeout=10)
    data = resp.json()
    if data.get("status") == "1" and data.get("geocodes"):
        loc = data["geocodes"][0]["location"]
        lng, lat = loc.split(",")
        return float(lng), float(lat)
    return None, None

def get_driving_route(origin, destination, retries=3):
    """高德驾车路径规划，返回距离(m)、时间(s)、路线坐标"""
    url = "https://restapi.amap.com/v3/direction/driving"
    params = {
        "origin": f"{origin[0]},{origin[1]}",
        "destination": f"{destination[0]},{destination[1]}",
        "key": AMAP_KEY,
        "extensions": "all",
        "strategy": 0
    }
    for attempt in range(retries):
        try:
            resp = requests.get(url, params=params, timeout=15)
            data = resp.json()
            if data.get("status") != "1":
                return None
            paths = data["route"]["paths"][0]
            distance = int(paths["distance"])
            duration = int(paths["duration"])
            polyline_points = []
            for step in paths["steps"]:
                for p in step["polyline"].split(";"):
                    lng, lat = p.split(",")
                    polyline_points.append((float(lng), float(lat)))
            return {"distance_m": distance, "duration_s": duration, "polyline": polyline_points}
        except Exception as e:
            if attempt < retries - 1:
                time.sleep(2)
            else:
                print(f"      API请求失败: {e}")
                return None

# ========== 1. 加载数据 ==========

def load_points():
    """加载所有点位"""
    df = pd.read_excel("/root/projects/navigate/最终地址列表.xlsx", engine="openpyxl")
    points = []
    for _, row in df.iterrows():
        coord_str = str(row["坐标"]).strip()
        if not coord_str or coord_str == "nan":
            continue
        lng, lat = coord_str.split(",")
        points.append({
            "name": row["地址"],
            "lng": float(lng),
            "lat": float(lat)
        })
    return points

# ========== 2. TSP 求解 ==========

def build_distance_matrix(points):
    """构建距离矩阵（基于Haversine）"""
    n = len(points)
    dist = [[0.0] * n for _ in range(n)]
    for i in range(n):
        for j in range(i+1, n):
            d = haversine(
                (points[i]["lat"], points[i]["lng"]),
                (points[j]["lat"], points[j]["lng"])
            )
            dist[i][j] = d
            dist[j][i] = d
    return dist

def nearest_neighbor_tsp(dist_matrix, start=0):
    """最近邻启发式求解TSP"""
    n = len(dist_matrix)
    visited = [False] * n
    route = [start]
    visited[start] = True

    for _ in range(n - 1):
        current = route[-1]
        best_next = -1
        best_dist = float('inf')
        for j in range(n):
            if not visited[j] and dist_matrix[current][j] < best_dist:
                best_dist = dist_matrix[current][j]
                best_next = j
        route.append(best_next)
        visited[best_next] = True

    return route

def two_opt_improve(route, dist_matrix, max_iterations=1000):
    """2-opt局部优化"""
    n = len(route)
    improved = True
    iteration = 0

    while improved and iteration < max_iterations:
        improved = False
        iteration += 1
        for i in range(1, n - 1):
            for j in range(i + 1, n):
                # 计算交换前后的距离差
                d_before = dist_matrix[route[i-1]][route[i]] + dist_matrix[route[j]][route[(j+1) % n]]
                d_after = dist_matrix[route[i-1]][route[j]] + dist_matrix[route[i]][route[(j+1) % n]]
                if d_after < d_before:
                    route[i:j+1] = reversed(route[i:j+1])
                    improved = True

    return route

# ========== 3. 多天拆分 ==========

def split_into_days(route_indices, points, dist_matrix, base_idx):
    """
    将路线拆分为多天
    约束：每天不超过 MAX_DAILY_SECONDS 且不超过 MAX_DAILY_POINTS 个点
    每天：base -> 若干点 -> base
    往返起点到长��区的时间作为固定开销，剩余时间用于点位间驾驶+停留
    """
    visit_points = [i for i in route_indices if i != base_idx]

    # 每天可用于点位间驾驶+停留的时间
    available_seconds = MAX_DAILY_SECONDS - ROUNDTRIP_OVERHEAD_SECONDS

    days = []
    current_day = []
    current_time = 0  # 当天点位间驾驶+停留已用时间

    for pt_idx in visit_points:
        if not current_day:
            # 第一个点，只计停留时间
            current_day.append(pt_idx)
            current_time = STOP_TIME_SECONDS
        else:
            # 检查点位数限制
            if len(current_day) >= MAX_DAILY_POINTS:
                days.append(current_day)
                current_day = [pt_idx]
                current_time = STOP_TIME_SECONDS
                continue

            # 从上一个点到当前点的驾驶时间
            prev_idx = current_day[-1]
            drive_dist = dist_matrix[prev_idx][pt_idx]
            drive_time = estimate_drive_time(drive_dist)

            new_total = current_time + drive_time + STOP_TIME_SECONDS

            if new_total <= available_seconds:
                current_day.append(pt_idx)
                current_time = new_total
            else:
                days.append(current_day)
                current_day = [pt_idx]
                current_time = STOP_TIME_SECONDS

    if current_day:
        days.append(current_day)

    return days

# ========== 4. 高德实际路线计算 ==========

def calculate_actual_routes(days, points, base_point):
    """调用高德API计算每天的实际驾车路线"""
    all_day_routes = []

    for day_idx, day_points in enumerate(days):
        print(f"\n  第{day_idx+1}天: {len(day_points)}个点位")
        day_route_data = {
            "day": day_idx + 1,
            "point_count": len(day_points),
            "segments": [],
            "total_distance_m": 0,
            "total_duration_s": 0,
            "stop_time_s": len(day_points) * STOP_TIME_SECONDS,
            "points": []
        }

        # 构建当天的完整路线: base -> p1 -> p2 -> ... -> base
        waypoints = [base_point] + [points[i] for i in day_points] + [base_point]
        day_route_data["points"] = [p["name"] for p in waypoints]

        for i in range(len(waypoints) - 1):
            origin = (waypoints[i]["lng"], waypoints[i]["lat"])
            dest = (waypoints[i+1]["lng"], waypoints[i+1]["lat"])
            route = get_driving_route(origin, dest)
            time.sleep(0.5)

            if route:
                day_route_data["segments"].append(route)
                day_route_data["total_distance_m"] += route["distance_m"]
                day_route_data["total_duration_s"] += route["duration_s"]
                print(f"    {waypoints[i]['name'][:15]}... -> {waypoints[i+1]['name'][:15]}... "
                      f"| {round(route['distance_m']/1000,1)}km {round(route['duration_s']/60,1)}min")
            else:
                day_route_data["segments"].append(None)
                print(f"    {waypoints[i]['name'][:15]}... -> {waypoints[i+1]['name'][:15]}... | 路线获取失败")

        total_with_stops = day_route_data["total_duration_s"] + day_route_data["stop_time_s"]
        day_route_data["total_time_with_stops_s"] = total_with_stops

        print(f"    ---")
        print(f"    驾车: {round(day_route_data['total_distance_m']/1000,1)}km "
              f"{round(day_route_data['total_duration_s']/60,1)}min")
        print(f"    停留: {round(day_route_data['stop_time_s']/60,1)}min")
        print(f"    合计: {round(total_with_stops/3600,1)}小时")

        all_day_routes.append(day_route_data)

    return all_day_routes

# ========== 5. 生成地图 ==========

def create_day_map(day_idx, day_route, points, base_point, output_dir):
    """为每一天生成单独的地图"""
    all_coords = [(base_point["lng"], base_point["lat"])]
    for seg in day_route["segments"]:
        if seg:
            all_coords.extend(seg["polyline"])

    center_lng = sum(c[0] for c in all_coords) / len(all_coords)
    center_lat = sum(c[1] for c in all_coords) / len(all_coords)

    m = folium.Map(
        location=[center_lat, center_lng],
        zoom_start=13,
        tiles="https://webrd02.is.autonavi.com/appmaptile?lang=zh_cn&size=1&scale=1&style=8&x={x}&y={y}&z={z}",
        attr="高德地图"
    )

    # 起点/终点标记
    folium.Marker(
        location=[base_point["lat"], base_point["lng"]],
        popup=f"<b>起点/终点: {base_point['name']}</b>",
        tooltip="起点/终点",
        icon=folium.Icon(color="green", icon="home")
    ).add_to(m)

    # 途经点标记
    point_names = day_route["points"][1:-1]  # 去掉首尾base
    waypoint_coords = []
    for seg in day_route["segments"][:-1]:  # 每段终点就是途经点
        if seg and seg["polyline"]:
            last = seg["polyline"][-1]
            waypoint_coords.append(last)

    for i, (name, coord) in enumerate(zip(point_names, waypoint_coords)):
        folium.Marker(
            location=[coord[1], coord[0]],
            popup=f"<b>第{i+1}站: {name}</b>",
            tooltip=f"第{i+1}站: {name}",
            icon=folium.Icon(color="blue", icon="info-sign")
        ).add_to(m)

    # 绘制路线
    colors = ["blue", "red", "green", "purple", "orange", "darkred", "darkblue", "cadetblue"]
    for i, seg in enumerate(day_route["segments"]):
        if seg:
            route_coords = [[p[1], p[0]] for p in seg["polyline"]]
            folium.PolyLine(
                locations=route_coords,
                weight=4,
                color=colors[i % len(colors)],
                opacity=0.8
            ).add_to(m)

    filepath = f"{output_dir}/第{day_idx+1}天路线图.html"
    m.save(filepath)
    return filepath

# ========== 主程序 ==========

if __name__ == "__main__":
    print("=" * 60)
    print(" 多天路线规划 — 基于高德地图 API")
    print("=" * 60)

    # 1. 加载数据
    print("\n[1/5] 加载点位数据...")
    points = load_points()
    print(f"  已加载 {len(points)} 个点位")

    # 获取起点坐标
    print(f"  获取起点坐标: {BASE_POINT_NAME}")
    base_lng, base_lat = geocode(BASE_POINT_NAME)
    if base_lng is None:
        print("  起点地理编码失败！")
        exit(1)
    base_point = {"name": BASE_POINT_NAME, "lng": base_lng, "lat": base_lat}
    print(f"  起点坐标: {base_lng}, {base_lat}")

    # 将起点加入点位列表（索引0）
    all_points = [base_point] + points
    base_idx = 0

    # 2. 构建距离矩阵
    print(f"\n[2/5] 构建距离矩阵 ({len(all_points)}x{len(all_points)})...")
    dist_matrix = build_distance_matrix(all_points)
    print("  完成")

    # 3. TSP 求解
    print("\n[3/5] TSP 求解最优路线...")
    route = nearest_neighbor_tsp(dist_matrix, start=base_idx)
    print(f"  最近邻初始路线总距离: {sum(dist_matrix[route[i]][route[i+1]] for i in range(len(route)-1)):.1f} km")

    route = two_opt_improve(route, dist_matrix)
    total_dist = sum(dist_matrix[route[i]][route[i+1]] for i in range(len(route)-1))
    print(f"  2-opt 优化后总距离: {total_dist:.1f} km")

    # 4. 拆分多天
    print(f"\n[4/5] 按每天{MAX_DAILY_SECONDS//3600}小时拆分路线...")
    print(f"  每个点位停留时间: {STOP_TIME_SECONDS//60} 分钟")
    days = split_into_days(route, all_points, dist_matrix, base_idx)
    print(f"  拆分为 {len(days)} 天")

    for i, day in enumerate(days):
        day_names = [all_points[idx]["name"].replace("重庆市长寿区", "") for idx in day]
        print(f"\n  第{i+1}天 ({len(day)}个点): {', '.join(day_names[:5])}{'...' if len(day_names) > 5 else ''}")

    # 5. 高德实际路线
    print(f"\n[5/5] 调用高德API计算实际驾车路线...")
    day_routes = calculate_actual_routes(days, all_points, base_point)

    # 生成地图
    print(f"\n生成地图...")
    output_dir = "/root/projects/navigate"
    for i, dr in enumerate(day_routes):
        filepath = create_day_map(i, dr, all_points, base_point, output_dir)
        print(f"  {filepath}")

    # 汇总报告
    print(f"\n{'=' * 60}")
    print(f" 路线规划汇总")
    print(f"{'=' * 60}")
    print(f" 总点位数: {len(points)}")
    print(f" 总天数:   {len(days)}")
    print(f" 起点/终点: {BASE_POINT_NAME}")
    print(f" 每点停留: {STOP_TIME_SECONDS//60} 分钟")
    print(f"{'=' * 60}")

    grand_total_dist = 0
    grand_total_time = 0

    for dr in day_routes:
        total_h = round(dr["total_time_with_stops_s"] / 3600, 1)
        dist_km = round(dr["total_distance_m"] / 1000, 1)
        grand_total_dist += dr["total_distance_m"]
        grand_total_time += dr["total_time_with_stops_s"]
        flag = " !!超时" if dr["total_time_with_stops_s"] > MAX_DAILY_SECONDS else ""
        print(f" 第{dr['day']}天: {dr['point_count']}个点 | {dist_km}km | {total_h}小时{flag}")

    print(f"{'=' * 60}")
    print(f" 总计: {round(grand_total_dist/1000,1)}km | {round(grand_total_time/3600,1)}小时")
    print(f"{'=' * 60}")

    # 保存详细报告
    report = {
        "base_point": BASE_POINT_NAME,
        "total_points": len(points),
        "total_days": len(days),
        "stop_time_per_point_min": STOP_TIME_SECONDS // 60,
        "max_daily_hours": MAX_DAILY_SECONDS // 3600,
        "days": []
    }
    for i, (day_indices, dr) in enumerate(zip(days, day_routes)):
        day_info = {
            "day": i + 1,
            "point_count": len(day_indices),
            "points": dr["points"],
            "drive_distance_km": round(dr["total_distance_m"] / 1000, 1),
            "drive_time_min": round(dr["total_duration_s"] / 60, 1),
            "stop_time_min": round(dr["stop_time_s"] / 60, 1),
            "total_time_hours": round(dr["total_time_with_stops_s"] / 3600, 1)
        }
        report["days"].append(day_info)

    with open(f"{output_dir}/路线规划报告.json", "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    # 生成 Excel 报告
    excel_rows = []
    for i, (day_indices, dr) in enumerate(zip(days, day_routes)):
        for j, pt_name in enumerate(dr["points"]):
            role = "起点" if j == 0 else ("返回" if j == len(dr["points"])-1 else f"第{j}站")
            excel_rows.append({
                "天数": f"第{i+1}天",
                "顺序": role,
                "地点": pt_name,
                "当天总距离(km)": round(dr["total_distance_m"]/1000, 1) if j == 0 else "",
                "当天总时间(小时)": round(dr["total_time_with_stops_s"]/3600, 1) if j == 0 else ""
            })

    excel_df = pd.DataFrame(excel_rows)
    excel_df.to_excel(f"{output_dir}/路线规划表.xlsx", index=False, engine="openpyxl")

    print(f"\n报告已保存:")
    print(f"  - {output_dir}/路线规划报告.json")
    print(f"  - {output_dir}/路线规划表.xlsx")
    print(f"\n完成！")
