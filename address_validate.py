import pandas as pd
import requests
import time
import json

AMAP_KEY = "b6410cb1a118bad10e6d1161d6e896f7"
CITY = "重庆"
DISTRICT = "长寿区"
PREFIX = f"重庆市{DISTRICT}"

# ========== 1. 读取并清洗数据 ==========
def load_and_clean(filepath):
    """读取 Excel 并提取、清洗地址"""
    df = pd.read_excel(filepath)
    # 第二列是小区名
    col_name = df.columns[1]
    names = df[col_name].dropna().tolist()

    cleaned = []
    for name in names:
        name = str(name).strip()
        if not name or name == "nan":
            continue
        # 去除备注信息（包含"联系"、"老师"等）
        if "联系" in name or "老师" in name or "电话" in name:
            continue
        # 清理特殊字符
        name = name.replace(".", "·").replace("  ", " ").strip()
        cleaned.append(name)

    return cleaned

# ========== 2. 地理编码验证 ==========
def geocode(address, city=CITY):
    """使用高德 API 地理编码"""
    url = "https://restapi.amap.com/v3/geocode/geo"
    params = {
        "address": address,
        "city": city,
        "key": AMAP_KEY
    }
    resp = requests.get(url, params=params, timeout=10)
    data = resp.json()

    if data.get("status") == "1" and data.get("geocodes"):
        geo = data["geocodes"][0]
        location = geo["location"]
        formatted = geo.get("formatted_address", "")
        district = geo.get("district", "")
        level = geo.get("level", "")
        return {
            "status": "OK",
            "input": address,
            "formatted": formatted,
            "district": district,
            "location": location,
            "level": level
        }
    else:
        return {
            "status": "FAIL",
            "input": address,
            "formatted": "",
            "district": "",
            "location": "",
            "level": ""
        }

# ========== 主程序 ==========
if __name__ == "__main__":
    filepath = "/root/projects/navigate/postion.xls"

    print("=" * 60)
    print(" 地址清洗与高德匹配验证")
    print("=" * 60)

    # 读取清洗
    print("\n[1/3] 读取并清洗数据...")
    raw_names = load_and_clean(filepath)
    print(f"  有效点位: {len(raw_names)} 个")

    # 加上起点/返回点
    base_point = "中共重庆市自来水有限公司委员会"

    # 构建带前缀的完整地址
    all_addresses = [base_point]  # 起点
    address_map = {}  # 原始名 -> 完整地址
    for name in raw_names:
        full_addr = f"{PREFIX}{name}"
        address_map[name] = full_addr
        all_addresses.append(full_addr)

    print(f"  总计验证: {len(all_addresses)} 个地址（含起点）")

    # 批量验证
    print("\n[2/3] 批量地理编码验证...")
    results_ok = []
    results_fail = []
    results_wrong_district = []

    for i, addr in enumerate(all_addresses):
        result = geocode(addr)
        tag = f"[{i+1}/{len(all_addresses)}]"

        if result["status"] == "OK":
            # 检查是否在长寿区（起点除外）
            if i > 0 and "长寿" not in result["district"] and "长寿" not in result["formatted"]:
                results_wrong_district.append(result)
                print(f"  {tag} [区域不符] {addr}")
                print(f"        -> {result['formatted']} ({result['district']})")
            else:
                results_ok.append(result)
                print(f"  {tag} [OK] {addr}")
                print(f"        -> {result['formatted']}")
        else:
            results_fail.append(result)
            print(f"  {tag} [FAIL] {addr}")

        time.sleep(0.15)  # 控制请求频率

    # 汇总报告
    print(f"\n{'=' * 60}")
    print(f" 验证结果汇总")
    print(f"{'=' * 60}")
    print(f" 匹配成功:   {len(results_ok)} 个")
    print(f" 匹配失败:   {len(results_fail)} 个")
    print(f" 区域不符:   {len(results_wrong_district)} 个")
    print(f"{'=' * 60}")

    if results_fail:
        print(f"\n--- 匹配失败的地址 ---")
        for r in results_fail:
            print(f"  × {r['input']}")

    if results_wrong_district:
        print(f"\n--- 区域不符的地址（未定位到长寿区）---")
        for r in results_wrong_district:
            print(f"  ! {r['input']}")
            print(f"    -> 实际定位: {r['formatted']} ({r['district']})")

    # 保存结果
    print("\n[3/3] 保存结果...")
    all_results = results_ok + results_fail + results_wrong_district
    output = {
        "base_point": base_point,
        "total": len(all_addresses),
        "ok": len(results_ok),
        "fail": len(results_fail),
        "wrong_district": len(results_wrong_district),
        "results": all_results
    }
    with open("/root/projects/navigate/validate_result.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    # 同时保存为易读的文本
    with open("/root/projects/navigate/validate_report.txt", "w", encoding="utf-8") as f:
        f.write("地址匹配验证报告\n")
        f.write("=" * 60 + "\n\n")
        f.write(f"匹配成功: {len(results_ok)} 个\n")
        f.write(f"匹配失败: {len(results_fail)} 个\n")
        f.write(f"区域不符: {len(results_wrong_district)} 个\n\n")

        f.write("--- 匹配成功 ---\n")
        for r in results_ok:
            f.write(f"  ✓ {r['input']} -> {r['formatted']} [{r['location']}]\n")

        if results_fail:
            f.write("\n--- 匹配失败 ---\n")
            for r in results_fail:
                f.write(f"  × {r['input']}\n")

        if results_wrong_district:
            f.write("\n--- 区域不符 ---\n")
            for r in results_wrong_district:
                f.write(f"  ! {r['input']} -> {r['formatted']} ({r['district']})\n")

    print(f"  结果已保存:")
    print(f"    - /root/projects/navigate/validate_result.json")
    print(f"    - /root/projects/navigate/validate_report.txt")
    print(f"\n完成！请查看失败和区域不符的地址，手动修正后重新验证。")
