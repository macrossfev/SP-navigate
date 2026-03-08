# SP-navigate

**Multi-point route planning and scheduling optimization system**

多点位路线规划与调度优化系统 —— 基于 TSP 算法和聚类策略的智能路径规划工具

---

## 📋 目录

- [功能特性](#-功能特性)
- [应用场景](#-应用场景)
- [快速开始](#-快速开始)
- [配置说明](#-配置说明)
- [命令行使用](#-命令行使用)
- [架构设计](#-架构设计)
- [算法说明](#-算法说明)
- [输出格式](#-输出格式)
- [示例：水质采样路线规划](#-示例水质采样路线规划)
- [开发计划](#-开发计划)
- [许可证](#-许可证)

---

## ✨ 功能特性

### 核心功能
- **多点路径规划**：支持数十至数百个点位的智能路线规划
- **多策略支持**：TSP（旅行商问题）算法 + 聚类分析策略
- **智能拆分**：根据时间/距离约束自动拆分为多天行程
- **约束条件**：支持每日最大时长、最大点数、停留时间等约束
- **多格式导出**：JSON、Excel、Word 文档、HTML 地图

### 技术特性
- **距离计算**：支持高德地图 API 实时路况 / 半正矢公式直线距离
- **地理编码**：地址名称自动转换为经纬度坐标
- **数据匹配**：Excel 数据与 survey 数据模糊匹配
- **可视化**：生成每日路线 HTML 地图，支持交互式查看
- **配置灵活**：YAML 配置文件 + 命令行参数覆盖

---

## 🎯 应用场景

| 场景 | 描述 |
|------|------|
| 水质采样 | 规划多个采样点的最优路线，生成采样计划 |
| 物流配送 | 多点配送路线优化，降低运输成本 |
| 设备巡检 | 规划设备巡检路线，提高工作效率 |
| 市场调研 | 多点位调研路线规划 |
| 邮政快递 | 快递网点路径优化 |

---

## 🚀 快速开始

### 安装依赖

```bash
pip install pandas openpyxl xlrd pyyaml requests folium python-docx
```

### 安装为命令行工具（可选）

```bash
pip install -e .
```

### 基本使用流程

1. **准备数据**：Excel 文件包含点位地址列表
2. **编写配置**：YAML 格式配置文件（参考 `presets/water_sampling/config.yaml`）
3. **运行规划**：
   ```bash
   python -m navigate plan --config your_config.yaml
   ```
4. **查看结果**：输出目录包含 Excel、Word、HTML 地图等文件

---

## ⚙️ 配置说明

### 配置文件结构

```yaml
# 起点配置
base_point:
  name: "起点地址名称"
  lng: 107.081        # 可选，如不填将自动地理编码
  lat: 29.857

# 策略配置
strategy:
  name: cluster       # tsp 或 cluster
  options:
    cluster_method: centroid  # centroid 或 chain
    outlier_threshold_km: 5.0 # 异常点距离阈值
    tsp_2opt_iterations: 1000 # 2-opt 优化迭代次数

# 约束条件
constraints:
  max_daily_hours: 6.0        # 每日最大工作时长（小时）
  max_daily_points: 10        # 每日最大点数
  min_daily_points: 1         # 每日最小点数
  stop_time_per_point_min: 15 # 每点停留时间（分钟）
  roundtrip_overhead_min: 60  # 往返额外时间（分钟）
  max_daily_distance_km: 200  # 每日最大行驶距离（0 表示不限制）

# 距离计算配置
distance:
  provider: haversine   # haversine（直线距离）或 amap（高德 API）
  avg_speed_kmh: 35.0   # 平均速度（km/h）
  amap_key: YOUR_KEY    # 高德 API Key（使用 amap 时需要）

# 数据源配置
data:
  points:
    file: points.xlsx
    format: excel
    column_mapping:
      name: "地址"
      coordinates: "坐标"
  
  survey:  # 可选，附加数据
    file: survey.xls
    match_key: "小区名称"
    match_mode: fuzzy

# 输出配置
export:
  output_dir: ./output
  formats:
    - type: json
    - type: excel
    - type: docx
    - type: map
```

---

## 💻 命令行使用

### 运行路线规划

```bash
# 基本用法
python -m navigate plan --config config.yaml

# 指定输出标签
python -m navigate plan --config config.yaml --tag tsp_result

# 覆盖配置参数
python -m navigate plan --config config.yaml --set constraints.max_daily_points=8
```

### 多策略对比

```bash
# 对比 TSP 和聚类策略
python -m navigate compare --config config.yaml

# 指定策略列表
python -m navigate compare --config config.yaml --strategies tsp,cluster
```

### 查看帮助

```bash
python -m navigate --help
python -m navigate plan --help
python -m navigate compare --help
```

---

## 🏗️ 架构设计

```
SP-navigate/
├── src/navigate/
│   ├── core/              # 核心模块
│   │   ├── planner.py     # 主规划器
│   │   ├── models.py      # 数据模型
│   │   └── config.py      # 配置管理
│   │
│   ├── strategies/        # 策略模块
│   │   ├── base.py        # 策略基类
│   │   ├── tsp.py         # TSP 策略
│   │   ├── cluster.py     # 聚类策略
│   │   └── registry.py    # 策略注册
│   │
│   ├── distance/          # 距离计算
│   │   ├── haversine.py   # 半正矢公式
│   │   ├── amap.py        # 高德 API
│   │   └── base.py        # 距离提供者基类
│   │
│   ├── geocoding/         # 地理编码
│   │   ├── amap.py        # 高德地理编码
│   │   └── base.py        # 编码基类
│   │
│   ├── constraints/       # 约束条件
│   │   ├── distance.py    # 距离约束
│   │   ├── time.py        # 时间约束
│   │   └── count.py       # 数量约束
│   │
│   ├── io/                # 输入输出
│   │   ├── loaders/       # 数据加载器
│   │   └── exporters/     # 结果导出器
│   │
│   └── cli.py             # 命令行接口
│
├── presets/               # 预设配置
├── tests/                 # 测试用例
└── pyproject.toml         # 项目配置
```

---

## 🧮 算法说明

### TSP 策略（Traveling Salesman Problem）

**流程**：
1. **最近邻启发式**：从起点开始，每次选择最近的未访问点
2. **2-opt 优化**：通过交换路径边来优化总距离
3. **按约束拆分**：根据时间/距离限制将全局路径拆分为多天

**适用场景**：点位分布较均匀，追求全局最优路径

### 聚类策略（Clustering）

**两种模式**：
- **centroid（质心法）**：基于质心的最远点优先种子 + 质心吸引
- **chain（链式法）**：从基点开始的贪心链式聚类

**流程**：
1. **异常点检测**：识别距离其他点过远的异常点
2. **聚类分组**：将点位分为若干组（每组不超过最大点数）
3. **组内优化**：对每组内部进行路径优化

**适用场景**：点位分布有明显聚集特征，如城市不同区域

---

## 📤 输出格式

### JSON 格式
```json
{
  "strategy_name": "TSP",
  "total_days": 5,
  "total_points": 42,
  "days": [
    {
      "day": 1,
      "points": [...],
      "drive_distance_km": 85.3,
      "drive_time_min": 145.2,
      "total_time_hours": 4.5
    }
  ]
}
```

### Excel 格式
- 每日路线明细
- 包含点位名称、坐标、联系方式等
- 支持自定义列配置

### Word 文档
- 格式化报告文档
- 包含每日路线详情
- 可嵌入地图图片

### HTML 地图
- 交互式地图展示
- 每日路线独立文件
- 支持缩放、点击查看详情

---

## 📝 示例：水质采样路线规划

### 项目背景
重庆市长寿区二次供水水质采样计划，需规划 42 个采样点的最优路线。

### 约束条件
- 每日工作时间不超过 6 小时
- 每日采样点不超过 5 个
- 每个采样点停留 15 分钟
- 往返额外时间 155 分钟

### 配置示例
```yaml
base_point:
  name: "中共重庆市自来水有限公司委员会"

strategy:
  name: cluster
  options:
    cluster_method: centroid
    outlier_threshold_km: 5.0

constraints:
  max_daily_hours: 6.0
  max_daily_points: 5
  stop_time_per_point_min: 15
  roundtrip_overhead_min: 155

distance:
  provider: haversine
  avg_speed_kmh: 35.0

data:
  points:
    file: 最终地址列表.xlsx
    column_mapping:
      name: "地址"

export:
  output_dir: ./output/water_sampling
  formats:
    - type: excel
    - type: docx
    - type: map
```

### 运行命令
```bash
python -m navigate plan --config presets/water_sampling/config.yaml
```

### 输出结果
```
output/water_sampling/
├── config_used.yaml          # 使用的配置
├── plan_result.json          # JSON 结果
├── plan_summary.xlsx         # Excel 汇总表
├── report.docx               # Word 报告
└── html/
    ├── day_1.html            # 第 1 天路线地图
    ├── day_2.html
    └── ...
```

---

## 📅 开发计划

- [ ] 支持更多距离提供者（Google Maps、百度地图）
- [ ] 添加遗传算法、模拟退火等优化算法
- [ ] 支持实时交通路况
- [ ] Web 界面
- [ ] 多点并发路径规划
- [ ] 车辆路径问题（VRP）支持

---

## 📄 许可证

MIT License

---

## 👥 作者

macrossfev

---

## 🙏 致谢

- 高德地图 API 提供距离计算和地理编码服务
- Folium 库提供地图可视化功能
- Python-docx 库提供 Word 文档生成功能
