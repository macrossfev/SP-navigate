import pandas as pd
import json

# 读取验证结果
with open("/root/projects/navigate/validate_result.json", "r", encoding="utf-8") as f:
    data = json.load(f)

rows = []
for r in data["results"]:
    if r["status"] == "FAIL":
        category = "匹配失败"
    elif r["status"] == "OK" and r["input"] == "中共重庆市自来水有限公司委员会":
        continue  # 跳过起点
    elif r["status"] == "OK":
        # 检查是否定位模糊（formatted 只到区级）
        formatted = r.get("formatted", "")
        inp = r.get("input", "")
        district = r.get("district", "")

        # 区域不符
        if "长寿" not in district and "长寿" not in formatted:
            category = "区域不符"
        # 定位模糊：formatted 以"重庆市长寿区"结尾，没有更具体的信息
        elif formatted.rstrip() in ["重庆市长寿区", "重庆市长寿区 "]:
            category = "定位模糊"
        else:
            category = "匹配成功"
    else:
        category = r["status"]

    rows.append({
        "原始地址": r["input"],
        "高德匹配结果": r.get("formatted", ""),
        "坐标": r.get("location", ""),
        "匹配状态": category,
        "修正地址（请填写）": ""
    })

# 按状态排序：失败 > 区域不符 > 模糊 > 成功
order = {"匹配失败": 0, "区域不符": 1, "定位模糊": 2, "匹配成功": 3}
rows.sort(key=lambda x: order.get(x["匹配状态"], 99))

df = pd.DataFrame(rows)
output_path = "/root/projects/navigate/地址修正表.xlsx"
df.to_excel(output_path, index=False, engine="openpyxl")

# 统计
from collections import Counter
counts = Counter(r["匹配状态"] for r in rows)
print(f"已生成: {output_path}")
print(f"总计: {len(rows)} 条")
for k in ["匹配失败", "区域不符", "定位模糊", "匹配成功"]:
    print(f"  {k}: {counts.get(k, 0)} 条")
print(f"\n请修正「匹配失败」「区域不符」「定位模糊」的地址，填入最后一列「修正地址（请填写）」")
