import pandas as pd
import requests
import json
import time

AMAP_KEY = "b6410cb1a118bad10e6d1161d6e896f7"
CITY = "重庆"
DISTRICT = "长寿区"

def poi_search(keyword, city=CITY):
    """使用高德 POI 搜索 API"""
    url = "https://restapi.amap.com/v3/place/text"
    params = {
        "keywords": keyword,
        "city": city,
        "citylimit": "true",
        "key": AMAP_KEY,
        "offset": 5,
        "extensions": "all"
    }
    resp = requests.get(url, params=params, timeout=10)
    data = resp.json()

    if data.get("status") == "1" and data.get("pois"):
        # 优先找长寿区的结果
        for poi in data["pois"]:
            if "长寿" in poi.get("adname", "") or "长寿" in poi.get("address", ""):
                return {
                    "status": "OK",
                    "name": poi["name"],
                    "address": poi.get("address", ""),
                    "location": poi["location"],
                    "district": poi.get("adname", ""),
                    "type": poi.get("type", "")
                }
        # 没有长寿区的就返回第一个
        poi = data["pois"][0]
        return {
            "status": "OK_OTHER",
            "name": poi["name"],
            "address": poi.get("address", ""),
            "location": poi["location"],
            "district": poi.get("adname", ""),
            "type": poi.get("type", "")
        }
    return {"status": "FAIL"}

def geocode(address, city=CITY):
    """地理编码 API"""
    url = "https://restapi.amap.com/v3/geocode/geo"
    params = {"address": address, "city": city, "key": AMAP_KEY}
    resp = requests.get(url, params=params, timeout=10)
    data = resp.json()
    if data.get("status") == "1" and data.get("geocodes"):
        geo = data["geocodes"][0]
        formatted = geo.get("formatted_address", "")
        if formatted.rstrip() != "重庆市长寿区" and "长寿" in formatted:
            return {
                "status": "OK",
                "formatted": formatted,
                "location": geo["location"],
                "district": geo.get("district", "")
            }
    return {"status": "FAIL"}

# 读取修正表
df = pd.read_excel("/root/projects/navigate/地址修正表.xlsx", engine="openpyxl")
fix_col = df.columns[-1]

# 找出有问题的行
problem_indices = []
for i, row in df.iterrows():
    status = row["匹配状态"]
    if status in ["匹配失败", "定位模糊", "区域不符"]:
        problem_indices.append(i)

print("=" * 60)
print(" POI 搜索修复有问题的���址")
print("=" * 60)
print(f" 待处理: {len(problem_indices)} 个\n")

fixed = 0
still_fail = []

for idx in problem_indices:
    row = df.loc[idx]
    # 确定搜索关键词
    fix_addr = row[fix_col]
    if pd.notna(fix_addr) and str(fix_addr).strip():
        full_addr = str(fix_addr).strip()
    else:
        full_addr = row["原始地址"]

    # 提取关键词（去掉"重庆市长寿区"前缀）
    keyword = full_addr.replace("重庆市长寿区", "").replace("重庆市", "").strip()

    print(f"[{idx+1}] 搜索: {keyword}")

    # 先尝试 POI 搜索
    result = poi_search(f"长寿区{keyword}")
    time.sleep(0.15)

    if result["status"] == "OK":
        print(f"  [POI OK] {result['name']}")
        print(f"    地址: {result['address']}")
        print(f"    坐标: {result['location']}")
        print(f"    区域: {result['district']}")
        df.at[idx, "高德匹配结果"] = f"{result['name']} ({result['address']})"
        df.at[idx, "坐标"] = result["location"]
        df.at[idx, "匹配状态"] = "匹配成功"
        fixed += 1
    elif result["status"] == "OK_OTHER":
        # 找到了但不在长寿区，再用原名试一次
        result2 = poi_search(keyword)
        time.sleep(0.15)
        if result2["status"] == "OK":
            print(f"  [POI OK] {result2['name']}")
            print(f"    地址: {result2['address']}")
            print(f"    坐标: {result2['location']}")
            df.at[idx, "高德匹配结果"] = f"{result2['name']} ({result2['address']})"
            df.at[idx, "坐标"] = result2["location"]
            df.at[idx, "匹配状态"] = "匹配成功"
            fixed += 1
        else:
            print(f"  [非长寿区] {result['name']} -> {result['district']}")
            still_fail.append((idx, full_addr, f"定位到{result['district']}: {result['name']}"))
    else:
        # POI 也找不到，尝试简化关键词再搜
        # 去掉路号等细节
        simple_keywords = [
            keyword,
            keyword.split("号")[-1] if "号" in keyword else keyword,
            keyword.replace("小区", ""),
        ]
        found = False
        for sk in simple_keywords[1:]:
            if not sk.strip():
                continue
            result3 = poi_search(f"长寿{sk.strip()}")
            time.sleep(0.15)
            if result3["status"] == "OK":
                print(f"  [POI OK - 简化搜索] {result3['name']}")
                print(f"    地址: {result3['address']}")
                print(f"    坐标: {result3['location']}")
                df.at[idx, "高德匹配结果"] = f"{result3['name']} ({result3['address']})"
                df.at[idx, "坐标"] = result3["location"]
                df.at[idx, "匹配状态"] = "匹配成功"
                fixed += 1
                found = True
                break
        if not found:
            print(f"  [FAIL] 未找到")
            still_fail.append((idx, full_addr, "POI搜索无结果"))

print(f"\n{'=' * 60}")
print(f" 结果")
print(f"{'=' * 60}")
print(f" 修复成功: {fixed} 个")
print(f" 仍然失败: {len(still_fail)} 个")

if still_fail:
    print(f"\n--- 仍然失败的地址 ---")
    for idx, addr, reason in still_fail:
        print(f"  [{idx+1}] {addr} — {reason}")

# 保存
df.to_excel("/root/projects/navigate/地址修正表.xlsx", index=False, engine="openpyxl")

# 重新生成最终列表
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
print(f"已更新: 最终地址列表.xlsx")
