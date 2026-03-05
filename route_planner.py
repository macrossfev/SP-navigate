import requests
import folium
import json

AMAP_KEY = "b6410cb1a118bad10e6d1161d6e896f7"

# ========== 1. 地理编码：地址 -> 坐标 ==========
def geocode(address, city="重庆"):
    """使用高德地理编码 API 将地址转为经纬度"""
    url = "https://restapi.amap.com/v3/geocode/geo"
    params = {
        "address": address,
        "city": city,
        "key": AMAP_KEY
    }
    resp = requests.get(url, params=params, timeout=10)
    data = resp.json()

    if data.get("status") == "1" and data.get("geocodes"):
        location = data["geocodes"][0]["location"]  # "lng,lat"
        lng, lat = location.split(",")
        formatted = data["geocodes"][0].get("formatted_address", address)
        print(f"  [OK] {address}")
        print(f"       -> {formatted}")
        print(f"       -> 坐标: {lng}, {lat}")
        return float(lng), float(lat)
    else:
        print(f"  [FAIL] 未找到: {address}")
        print(f"         返回: {data}")
        return None, None

# ========== 2. 路径规划：高德驾车路线 ==========
def get_driving_route(origin, destination):
    """
    使用高德驾车路径规划 API
    origin/destination: (lng, lat)
    """
    url = "https://restapi.amap.com/v3/direction/driving"
    params = {
        "origin": f"{origin[0]},{origin[1]}",
        "destination": f"{destination[0]},{destination[1]}",
        "key": AMAP_KEY,
        "extensions": "all",
        "strategy": 0  # 速度优先
    }
    resp = requests.get(url, params=params, timeout=15)
    data = resp.json()

    if data.get("status") != "1":
        print(f"  路径规划失败: {data.get('info', '未知错误')}")
        return None

    route = data["route"]
    paths = route["paths"][0]  # 取第一条路线
    distance = int(paths["distance"])  # 米
    duration = int(paths["duration"])  # 秒
    steps = paths["steps"]

    # 提取路线坐标点
    polyline_points = []
    for step in steps:
        points = step["polyline"].split(";")
        for p in points:
            lng, lat = p.split(",")
            polyline_points.append((float(lng), float(lat)))

    return {
        "distance_m": distance,
        "distance_km": round(distance / 1000, 2),
        "duration_s": duration,
        "duration_min": round(duration / 60, 1),
        "polyline": polyline_points,
        "steps": steps
    }

# ========== 3. 生成地图 ==========
def create_map(waypoints, names, routes, output_file="route_map.html"):
    """生成 folium 可视化地图"""
    center_lng = sum(w[0] for w in waypoints) / len(waypoints)
    center_lat = sum(w[1] for w in waypoints) / len(waypoints)

    m = folium.Map(location=[center_lat, center_lng], zoom_start=13,
                   tiles="https://webrd02.is.autonavi.com/appmaptile?lang=zh_cn&size=1&scale=1&style=8&x={x}&y={y}&z={z}",
                   attr="高德地图")

    # 添加标记点
    colors = ["green", "orange", "red"]
    labels = ["起点", "途经点", "终点"]
    icons = ["play", "info-sign", "flag"]
    for i, (wp, name) in enumerate(zip(waypoints, names)):
        idx = min(i, len(colors) - 1)
        if i == 0:
            idx = 0
        elif i == len(waypoints) - 1:
            idx = 2
        else:
            idx = 1
        folium.Marker(
            location=[wp[1], wp[0]],  # folium 用 [lat, lng]
            popup=f"<b>{labels[idx]}: {name}</b>",
            tooltip=f"{labels[idx]}: {name}",
            icon=folium.Icon(color=colors[idx], icon=icons[idx])
        ).add_to(m)

    # 绘制路线
    route_colors = ["blue", "red"]
    for i, route in enumerate(routes):
        if route:
            route_coords = [[p[1], p[0]] for p in route["polyline"]]  # [lat, lng]
            folium.PolyLine(
                locations=route_coords,
                weight=5,
                color=route_colors[i % len(route_colors)],
                opacity=0.8,
                tooltip=f"第{i+1}段路线"
            ).add_to(m)

    m.save(output_file)
    print(f"\n地图已保存: {output_file}")

# ========== 主程序 ==========
if __name__ == "__main__":
    places = [
        "重庆大学城地铁站",
        "重庆市清泽水质检测有限公司",
        "国家城市供水水质监测网重庆监测站"
    ]

    print("=" * 55)
    print(" 路线规划 — 基于高德地图 API")
    print("=" * 55)

    # 第一步：测试 API Key
    print("\n[0/3] 测试 API Key...")
    test_resp = requests.get("https://restapi.amap.com/v3/config/district",
                              params={"key": AMAP_KEY, "keywords": "重庆"}, timeout=10)
    test_data = test_resp.json()
    if test_data.get("status") == "1":
        print("  [OK] API Key 有效")
    else:
        print(f"  [FAIL] API Key 无效: {test_data.get('info')}")
        exit(1)

    # 第二步：地理编码
    print("\n[1/3] 地理编码...")
    waypoints = []
    for place in places:
        lng, lat = geocode(place)
        if lng is None:
            print(f"\n无法找到 '{place}'，请检查地址。")
            exit(1)
        waypoints.append((lng, lat))

    # 第三步：分段路径规划
    print("\n[2/3] 路径规划...")
    routes = []
    total_distance = 0
    total_duration = 0

    for i in range(len(waypoints) - 1):
        print(f"\n  第{i+1}段: {places[i]} -> {places[i+1]}")
        route = get_driving_route(waypoints[i], waypoints[i+1])
        if route:
            print(f"    距离: {route['distance_km']} 公里")
            print(f"    时间: {route['duration_min']} 分钟")
            total_distance += route["distance_m"]
            total_duration += route["duration_s"]
            routes.append(route)
        else:
            routes.append(None)

    # 汇总
    print(f"\n{'=' * 55}")
    print(f" 路线规划结果")
    print(f"{'=' * 55}")
    print(f" 起点:     {places[0]}")
    print(f" 途经:     {places[1]}")
    print(f" 终点:     {places[2]}")
    print(f"{'=' * 55}")
    print(f" 总距离:   {round(total_distance / 1000, 2)} 公里")
    print(f" 预计时间: {round(total_duration / 60, 1)} 分钟")
    print(f"{'=' * 55}")

    # 第四步：生成地图
    print("\n[3/3] 生成地图...")
    create_map(waypoints, places, routes, "/root/route_map.html")
    print(f"\n完成！请在浏览器中打开 /root/route_map.html 查看路线地图。")
