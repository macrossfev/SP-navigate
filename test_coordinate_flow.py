#!/usr/bin/env python3
"""Test script to verify coordinate flow."""

import sys
import pandas as pd
sys.path.insert(0, 'src')

# 模拟用户上传的 Excel 数据
test_data = {
    "地址": [
        "重庆市长寿区寿城水岸",
        "重庆市长寿区凤城街道",
        "重庆市长寿区菩提街道"
    ]
}
df = pd.DataFrame(test_data)

print("=" * 60)
print("步骤 1: 模拟用户上传 Excel")
print("=" * 60)
print(df)
print()

# 模拟步骤 2: 地址验证
import subprocess
import json

AMAP_KEY = "de9b271958d5cf291a018d5e95f7e53d"

def geocode_address(address, city="重庆"):
    """Geocode using curl."""
    url = "https://restapi.amap.com/v3/geocode/geo"
    cmd = [
        "curl", "-s", "-G", url,
        "--data-urlencode", f"address={address}",
        "--data-urlencode", f"key={AMAP_KEY}",
        "--data-urlencode", "output=json",
        "--data-urlencode", f"city={city}"
    ]
    
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
    data = json.loads(result.stdout)
    
    if data.get("status") == "1" and data.get("geocodes"):
        geo = data["geocodes"][0]
        return {
            "status": "OK",
            "input": address,
            "location": geo.get("location", ""),
            "formatted": geo.get("formatted_address", "")
        }
    return {"status": "FAIL", "input": address, "location": ""}

print("=" * 60)
print("步骤 2: 地址验证（调用高德 API）")
print("=" * 60)

results = []
for addr in df["地址"]:
    result = geocode_address(addr)
    results.append(result)
    if result.get("status") == "OK":
        print(f"✓ {addr} -> {result['location']}")
    else:
        print(f"✗ {addr} -> Failed")

# 创建 validated_df（带坐标）
def create_validated_dataframe(df, results):
    validated_df = df.copy()
    validated_df["经度"] = None
    validated_df["纬度"] = None
    validated_df["地理编码状态"] = "未验证"
    
    for i, result in enumerate(results):
        if i < len(validated_df):
            if result and result.get("location"):
                lng, lat = result["location"].split(",")
                validated_df.at[i, "经度"] = float(lng)
                validated_df.at[i, "纬度"] = float(lat)
                validated_df.at[i, "地理编码状态"] = "成功"
            else:
                validated_df.at[i, "地理编码状态"] = "失败"
    
    return validated_df

validated_df = create_validated_dataframe(df, results)

print()
print("=" * 60)
print("验证后的 DataFrame (st.session_state.validated_df)")
print("=" * 60)
print(validated_df)
print()

# 模拟步骤 4: build_config_for_planner
print("=" * 60)
print("步骤 4: 模拟 build_config_for_planner")
print("=" * 60)

from navigate.core.models import Point
import hashlib

points = []
geocode_count = 0
from_excel_count = 0

for idx, row in validated_df.iterrows():
    addr = str(row.get("地址", "")).strip()
    lng, lat = None, None
    
    # 检查是否有坐标（从步骤 2 保存的）
    if "经度" in row and "纬度" in row:
        lng_val = row.get("经度")
        lat_val = row.get("纬度")
        if pd.notna(lng_val) and pd.notna(lat_val) and lng_val != 0.0 and lat_val != 0.0:
            lng, lat = float(lng_val), float(lat_val)
            from_excel_count += 1
            print(f"✓ [{from_excel_count}] {addr[:35]} -> {lat:.6f}, {lng:.6f} (from DataFrame)")
    
    # 如果没有坐标，调用地理编码
    if lng is None or lat is None:
        result = geocoder.geocode(addr)
        if result:
            lng, lat = result
            geocode_count += 1
            print(f"✓ [{geocode_count}] {addr[:35]} -> {lat:.6f}, {lng:.6f} (geocoded)")
        else:
            # Fallback
            addr_hash = hashlib.md5(addr.encode('utf-8')).hexdigest()
            lat_offset = (int(addr_hash[:4], 16) / 65535 - 0.5) * 0.5
            lng_offset = (int(addr_hash[4:8], 16) / 65535 - 0.5) * 0.5
            lng = 107.081 + lng_offset
            lat = 29.857 + lat_offset
            print(f"~ {addr[:35]} -> {lat:.6f}, {lng:.6f} (fallback)")
    
    points.append(Point(id=str(idx), name=addr, lng=lng, lat=lat, metadata={"address": addr}))

print()
print("=" * 60)
print("最终点位坐标")
print("=" * 60)
for i, p in enumerate(points):
    print(f"[{i+1}] {p.name[:35]} -> Lng: {p.lng:.6f}, Lat: {p.lat:.6f}")

print()
print("=" * 60)
print("测试结果")
print("=" * 60)
print(f"从 DataFrame 获取坐标：{from_excel_count} 个")
print(f"地理编码获取坐标：{geocode_count} 个")
print(f"使用近似坐标：{len(points)-from_excel_count-geocode_count} 个")

# 验证寿城水岸的坐标
shoucheng = points[0]
expected_lng, expected_lat = 107.068400, 29.848574
if abs(shoucheng.lng - expected_lng) < 0.001 and abs(shoucheng.lat - expected_lat) < 0.001:
    print(f"\n✅ 寿城水岸坐标正确！({shoucheng.lng:.6f}, {shoucheng.lat:.6f})")
else:
    print(f"\n❌ 寿城水岸坐标错误！")
    print(f"   期望：{expected_lng:.6f}, {expected_lat:.6f}")
    print(f"   实际：{shoucheng.lng:.6f}, {shoucheng.lat:.6f}")
