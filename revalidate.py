import pandas as pd
import requests
import json
import time

AMAP_KEY = "b6410cb1a118bad10e6d1161d6e896f7"

def geocode(address, city="重庆"):
    url = "https://restapi.amap.com/v3/geocode/geo"
    params = {"address": address, "city": city, "key": AMAP_KEY}
    resp = requests.get(url, params=params, timeout=10)
    data = resp.json()
    if data.get("status") == "1" and data.get("geocodes"):
        geo = data["geocodes"][0]
        return {
            "status": "OK",
            "formatted": geo.get("formatted_address", ""),
            "district": geo.get("district", ""),
            "location": geo["location"],
            "level": geo.get("level", "")
        }
    return {"status": "FAIL", "formatted": "", "district": "", "location": "", "level": ""}

# 读取修正表
df = pd.read_excel("/root/projects/navigate/地址修正表.xlsx", engine="openpyxl")
fix_col = df.columns[-1]

print("=" * 60)
print(" 重新验证修正后的地址")
print("=" * 60)

fail_count = 0
ok_count = 0
wrong_count = 0

# 对每行：如果有修正地址则用修正地址，否则保持原始
for i, row in df.iterrows():
    fix_addr = row[fix_col]
    if pd.notna(fix_addr) and str(fix_addr).strip():
        addr = str(fix_addr).strip()
    else:
        addr = row["原始地址"]

    result = geocode(addr)
    tag = f"[{i+1}/{len(df)}]"

    if result["status"] == "OK":
        in_changshou = "长寿" in result["district"] or "长寿" in result["formatted"]
        # 检查if only matched to district level
        is_vague = result["formatted"].rstrip() == "重庆市长寿区"

        if not in_changshou:
            print(f"  {tag} [区域不符] {addr}")
            print(f"        -> {result['formatted']} ({result['district']})")
            wrong_count += 1
            df.at[i, "匹配状态"] = "区域不符"
        elif is_vague:
            print(f"  {tag} [仍模糊] {addr}")
            print(f"        -> {result['formatted']}")
            fail_count += 1
            df.at[i, "匹配状态"] = "定位模糊"
        else:
            print(f"  {tag} [OK] {addr}")
            print(f"        -> {result['formatted']} [{result['location']}]")
            ok_count += 1
            df.at[i, "匹配状态"] = "匹配成功"
    else:
        print(f"  {tag} [FAIL] {addr}")
        fail_count += 1
        df.at[i, "匹配状态"] = "匹配失败"

    # 更新坐标和匹配结果
    df.at[i, "高德匹配结果"] = result["formatted"]
    df.at[i, "坐标"] = result["location"]
    time.sleep(0.15)

print(f"\n{'=' * 60}")
print(f" 验证结果")
print(f"{'=' * 60}")
print(f" 匹配成功: {ok_count}")
print(f" 仍有问题: {fail_count}")
print(f" 区域不符: {wrong_count}")
print(f"{'=' * 60}")

# 保存更新后的表
df.to_excel("/root/projects/navigate/地址修正表.xlsx", index=False, engine="openpyxl")

# 同时生成最终确认的地址列表（用于路线规划）
final_rows = []
for _, row in df.iterrows():
    fix_addr = row[fix_col]
    if pd.notna(fix_addr) and str(fix_addr).strip():
        addr = str(fix_addr).strip()
    else:
        addr = row["原始地址"]
    final_rows.append({
        "地址": addr,
        "高德匹配": row["高德匹配结果"],
        "坐标": row["坐标"],
        "状态": row["匹配状态"]
    })

final_df = pd.DataFrame(final_rows)
final_df.to_excel("/root/projects/navigate/最终地址列表.xlsx", index=False, engine="openpyxl")

print(f"\n已更新: 地址修正表.xlsx")
print(f"已生成: 最终地址列表.xlsx")
