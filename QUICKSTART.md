# SP-navigate 快速入门指南

## 🚀 5 分钟快速开始

### 方式一：Web 界面 (推荐)

**1. 安装依赖**

```bash
cd /home/macrossfev/SP-navigate
pip install -r requirements.txt
```

**2. 启动 Web 应用**

```bash
# Linux/Mac
bash run_web.sh

# 或直接运行
streamlit run app.py
```

**3. 访问应用**

打开浏览器访问：`http://localhost:8501`

**4. 使用步骤**
1. 上传 Excel 文件 (包含"地址"列)
2. 选择规划策略 (推荐：隔夜住宿模式)
3. 配置参数 (每日工时、点数等)
4. 点击"运行路线规划"
5. 查看结果并下载

---

### 方式二：命令行

**1. 准备数据**

创建 Excel 文件 `points.xlsx`，包含以下列：
- `地址` (必需): 采样点地址名称
- `坐标` (可选): 经纬度，格式 "106.123,29.456"

**2. 编辑配置**

编辑 `presets/overnight_sampling/config.yaml`:
```yaml
base_point:
  name: "你的公司名称"

constraints:
  overnight_threshold_km: 80.0  # 超过 80 公里启用隔夜模式
  max_daily_hours: 10.0
  single_day_max_hours: 6.0

data:
  points:
    file: /path/to/your/points.xlsx
```

**3. 运行规划**

```bash
python -m navigate plan --config presets/overnight_sampling/config.yaml
```

**4. 查看结果**

输出目录 (`output/overnight_sampling/`):
- `plan_result.json` - JSON 格式结果
- `plan_summary.xlsx` - Excel 汇总表
- `html/day_1.html`, `day_2.html`... - 每日路线地图

---

## 📋 配置说明

### 核心参数

| 参数 | 说明 | 推荐值 |
|------|------|--------|
| `overnight_threshold_km` | 隔夜距离阈值 (公里) | 80 |
| `max_daily_hours` | 隔夜行程每日最大工时 | 10 |
| `single_day_max_hours` | 单日往返最大工时 | 6 |
| `max_daily_points` | 每日最大采样点数 | 5 |
| `stop_time_per_point_min` | 每点停留时间 (分钟) | 15 |

### 策略选择

| 策略 | 适用场景 |
|------|----------|
| `overnight` | 混合模式，自动判断远近 (推荐) |
| `tsp` | 全部单日往返，短距离多点 |
| `cluster` | 按区域聚类，适合分散点位 |

---

## 🗺️ 结果解读

### 行程类型

**单日往返 (single_day) 🚗**
```
公司 → 点位 A → 点位 B → 点位 C → 公司
```

**隔夜住宿 (overnight) 🏨**
```
Day 1: 公司 → 点位 A → 点位 B → 酒店 🏨
Day 2: 酒店 → 点位 C → 点位 D → 公司
```

### 输出文件说明

| 文件 | 内容 | 用途 |
|------|------|------|
| `plan_result.json` | 完整规划数据 | 程序处理 |
| `plan_summary.xlsx` | 可读表格 | 打印/分发 |
| `report.docx` | Word 报告 | 汇报文档 |
| `html/day_X.html` | 交互式地图 | 路线导航 |

---

## ❓ 常见问题

### Q: 如何修改隔夜阈值？
A: 编辑配置文件中的 `overnight_threshold_km`，或在 Web 界面调整滑块。

### Q: 如何更换起点/公司？
A: 修改配置文件中 `base_point.name`，或在 Web 界面输入框修改。

### Q: 可以使用高德地图实时路况吗？
A: 可以。配置文件中设置 `distance.provider: amap` 并填写 API Key。

### Q: 住宿点如何选择？
A: 系统自动选择采样点集群中心附近的住宿点。

### Q: 如何查看历史规划？
A: 结果文件保存在 `output/` 目录，可按时间整理。

---

## 🔧 高级用法

### 命令行参数覆盖

```bash
# 修改隔夜阈值
python -m navigate plan --config config.yaml \
  --set constraints.overnight_threshold_km=100

# 修改每日最大点数
python -m navigate plan --config config.yaml \
  --set constraints.max_daily_points=8

# 指定输出标签
python -m navigate plan --config config.yaml --tag v2
```

### 多策略对比

```bash
python -m navigate compare --config config.yaml \
  --strategies overnight,tsp,cluster
```

---

## 📞 技术支持

- GitHub: https://github.com/macrossfev/SP-navigate
- 问题反馈：提交 Issue
