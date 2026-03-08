# SP-navigate 开发文档

**多点位路线规划与调度优化系统**

版本：1.0.0  
最后更新：2026-03-08

---

## 📋 目录

1. [项目概述](#项目概述)
2. [系统架构](#系统架构)
3. [核心模块](#核心模块)
4. [数据流程](#数据流程)
5. [API 集成](#api 集成)
6. [配置说明](#配置说明)
7. [部署指南](#部署指南)
8. [故障排查](#故障排查)
9. [版本历史](#版本历史)

---

## 项目概述

### 功能特性

- **多点路径规划**：支持数十至数百个点位的智能路线规划
- **多策略支持**：
  - TSP（旅行商问题）算法
  - 聚类分析策略
  - 隔夜住宿混合模式
- **智能拆分**：根据时间/距离约束自动拆分为多天行程
- **地理编码**：高德地图 API 地址→坐标转换
- **多格式导出**：JSON、Excel、Word 文档、HTML 地图

### 应用场景

| 场景 | 描述 |
|------|------|
| 水质采样 | 规划多个采样点的最优路线，生成采样计划 |
| 物流配送 | 多点配送路线优化，降低运输成本 |
| 设备巡检 | 规划设备巡检路线，提高工作效率 |
| 市场调研 | 多点位调研路线规划 |

---

## 系统架构

### 目录结构

```
SP-navigate/
├── src/navigate/
│   ├── core/
│   │   ├── planner.py        # 主规划器
│   │   ├── models.py         # 数据模型 (Point, DayPlan, PlanResult)
│   │   └── config.py         # 配置管理
│   │
│   ├── strategies/
│   │   ├── base.py           # 策略基类
│   │   ├── tsp.py            # TSP 策略
│   │   ├── cluster.py        # 聚类策略
│   │   ├── overnight.py      # 隔夜住宿策略
│   │   └── registry.py       # 策略注册表
│   │
│   ├── distance/
│   │   ├── base.py           # 距离提供者基类
│   │   ├── haversine.py      # 半正矢公式（直线距离）
│   │   └── amap.py           # 高德地图 API（驾车路线）
│   │
│   ├── geocoding/
│   │   ├── base.py           # 地理编码基类
│   │   └── amap.py           # 高德地理编码
│   │
│   ├── io/
│   │   ├── loaders/          # 数据加载器
│   │   └── exporters/        # 结果导出器
│   │       ├── json_exporter.py
│   │       ├── excel_exporter.py
│   │       ├── docx_exporter.py
│   │       └── map_exporter.py
│   │
│   └── cli.py                # 命令行接口
│
├── app.py                    # Streamlit Web 应用
├── requirements.txt          # Python 依赖
├── pyproject.toml           # 项目配置
└── presets/                  # 预设配置
    └── overnight_sampling/
        └── config.yaml
```

### 技术栈

| 组件 | 技术 |
|------|------|
| 后端核心 | Python 3.9+ |
| Web 界面 | Streamlit |
| 数据处理 | Pandas, OpenPyXL |
| 地图可视化 | Folium |
| 文档生成 | python-docx |
| 地理服务 | 高德地图 Web API |

---

## 核心模块

### 1. 数据模型 (models.py)

```python
@dataclass
class Point:
    """采样点"""
    id: str
    name: str          # 地址名称
    lng: float         # 经度
    lat: float         # 纬度
    metadata: dict     # 附加信息

@dataclass
class DayPlan:
    """每日行程"""
    day: int
    points: List[Point]
    drive_distance_km: float
    drive_time_min: float
    stop_time_min: float
    total_time_hours: float
    trip_type: TripType  # SINGLE_DAY / OVERNIGHT
    hotel: Optional[HotelInfo]

@dataclass
class PlanResult:
    """规划结果"""
    strategy_name: str
    days: List[DayPlan]
    all_points: List[Point]
```

### 2. 策略模块

#### TSP 策略 (tsp.py)
- 最近邻启发式算法
- 2-opt 局部优化
- 按约束拆分多天

#### 聚类策略 (cluster.py)
- 质心法 (centroid)
- 链式法 (chain)
- 异常点检测

#### 隔夜住宿策略 (overnight.py)
- 自动判断远近点位
- 近距离：单日往返
- 远距离：隔夜住宿（2 天）

### 3. 导出器

| 导出器 | 格式 | 说明 |
|--------|------|------|
| JsonExporter | .json | 完整规划数据 |
| ExcelExporter | .xlsx | 可读性好的表格 |
| DocxExporter | .docx | Word 格式报告（含地图） |
| MapExporter | .html/.png | 交互式地图 |

---

## 数据流程

### 完整流程

```
┌─────────────────┐
│ 步骤 1: 上传 Excel │
│ - 包含"地址"列    │
│ - 可选：经度/纬度 │
└────────┬────────┘
         │
         ↓
┌─────────────────┐
│ 步骤 2: 地址验证 │ ← 关键！地理编码在此执行
│ - 调用高德 API   │
│ - 保存坐标到 DF  │
└────────┬────────┘
         │
         ↓ st.session_state.validated_df
         │ (包含经度、纬度列)
         ↓
┌─────────────────┐
│ 步骤 3: 修正表   │ (可选)
│ - 上传修正地址  │
│ - 合并数据      │
└────────┬────────┘
         │
         ↓
┌─────────────────┐
│ 步骤 4: 生成规划 │
│ - 使用 validated_df│
│ - 优先用已有坐标 │
│ - 失败则地理编码 │
└────────┬────────┘
         │
         ↓
┌─────────────────┐
│ 步骤 5: 查看结果 │
│ - 展示每日行程  │
│ - 下载 Excel/Word│
└─────────────────┘
```

### 坐标来源优先级

```python
# build_config_for_planner 中的逻辑
if "经度" in row and "纬度" in row:
    if 坐标有效：
        使用 DataFrame 中的坐标  # 来自步骤 2
    else:
        调用高德 API 地理编码
else:
    调用高德 API 地理编码

# 地理编码失败时
使用哈希生成近似坐标  # fallback
```

### 控制台输出示例

```
[Geo] Geocoding addresses with Amap API...
  ✓ [1] 重庆市长寿区寿城水岸 -> 29.848574, 107.068400 (from DataFrame)
  ✓ [2] 重庆市长寿区凤城街道 -> 29.838487, 107.079203 (geocoded)
  ~ [3] 未知地址 -> 29.829583, 106.983705 (fallback)

[Geo] Summary: 8 geocoded, 2 from DataFrame, 0 fallback
[Geo] Total: 10 points

[Debug] All points with coordinates:
  [1] 重庆市长寿区寿城水岸 -> Lng: 107.068400, Lat: 29.848574
  [2] 重庆市长寿区凤城街道 -> Lng: 107.079203, Lat: 29.838487
```

---

## API 集成

### 高德地图 API

#### 地理编码 API

**端点**: `https://restapi.amap.com/v3/geocoding/geo`

**请求参数**:
```python
params = {
    "key": "YOUR_API_KEY",
    "address": "北京市朝阳区阜通东大街 6 号",
    "city": "北京市",  # 可选
    "output": "json"
}
```

**响应格式**:
```json
{
  "status": "1",
  "info": "OK",
  "geocodes": [{
    "formatted_address": "北京市朝阳区阜通东大街 6 号",
    "location": "116.480881,39.989410",
    "district": "朝阳区"
  }]
}
```

**当前 API Key**: `de9b271958d5cf291a018d5e95f7e53d`

**并发限制**: 3 QPS（每秒 3 次请求）
- 代码中设置 `request_delay=0.4`（400ms 延迟）

#### 常见错误码

| 错误码 | 说明 | 解决方案 |
|--------|------|----------|
| 10000 | OK | 请求成功 |
| 10002 | SERVICE_NOT_AVAILABLE | 服务未绑定/配额用尽 |
| 10009 | USERKEY_PLAT_NOMATCH | Key 平台类型不匹配 |

### 使用示例

```python
from navigate.geocoding.amap import AmapGeocoder

geocoder = AmapGeocoder("de9b271958d5cf291a018d5e95f7e53d", request_delay=0.4)
result = geocoder.geocode("重庆市长寿区寿城水岸")

if result:
    lng, lat = result
    print(f"经度：{lng}, 纬度：{lat}")
```

---

## 配置说明

### Web 应用配置 (app.py)

```python
# 地理编码 API Key
AMAP_KEY = "de9b271958d5cf291a018d5e95f7e53d"

# 默认城市/区县
DEFAULT_CITY = "重庆"
DEFAULT_DISTRICT = "长寿区"
```

### 命令行配置 (YAML)

```yaml
base_point:
  name: "中共重庆市自来水有限公司委员会"

strategy:
  name: overnight  # overnight / tsp / cluster
  options:
    cluster_method: centroid
    outlier_threshold_km: 5.0

constraints:
  max_daily_hours: 10.0
  single_day_max_hours: 6.0
  max_daily_points: 5
  stop_time_per_point_min: 15
  overnight_threshold_km: 80.0  # 隔夜距离阈值

distance:
  provider: haversine  # haversine / amap
  avg_speed_kmh: 35.0

data:
  points:
    file: 最终地址列表.xlsx
    column_mapping:
      name: "地址"

export:
  output_dir: ./output
  formats:
    - type: json
    - type: excel
    - type: docx
      title: "路线规划报告"
      include_maps: true
    - type: map
      format: html
```

---

## 部署指南

### 环境要求

- Python 3.9+
- Node.js (可选，用于前端开发)
- Chromium (可选，用于地图截图)

### 安装依赖

```bash
cd /home/macrossfev/SP-navigate
pip install -r requirements.txt
```

### 启动 Web 应用

```bash
# 方式 1: 直接启动
streamlit run app.py

# 方式 2: 使用启动脚本
bash run_web.sh

# 方式 3: 后台运行
nohup streamlit run app.py --server.address 0.0.0.0 --server.port 8501 > /tmp/streamlit.log 2>&1 &
```

### 访问地址

- **本地**: http://localhost:8501
- **内网**: http://192.168.0.160:8501
- **外网**: http://106.87.81.146:8501 (需配置防火墙)

### 防火墙配置

```bash
# 开放 8501 端口
sudo ufw allow 8501/tcp
sudo ufw status
```

---

## 故障排查

### 问题 1: 点位坐标错误

**症状**: 结果中的坐标是近似值（如 106.9837, 29.8296）

**排查步骤**:
1. 检查步骤 2 是否完成地址验证
2. 查看控制台输出 `[Geo]` 部分
3. 确认坐标来源是 `from DataFrame` 或 `geocoded`

**解决方案**:
```bash
# 清除浏览器缓存
# 重新上传数据
# 完成地址验证（会保存坐标）
# 生成规划
```

### 问题 2: Word 报告没有图片

**症状**: 下载的 Word 报告中没有地图图片

**排查步骤**:
1. 检查 `output/images/day_X.png` 是否存在
2. 查看控制台是否有 `Map image not found` 警告
3. 确认 Chromium 已安装

**解决方案**:
```bash
# 安装 Chromium
sudo snap install chromium

# 重启应用
pkill -f streamlit
streamlit run app.py
```

### 问题 3: 地理编码失败

**症状**: 控制台显示 `SERVICE_NOT_AVAILABLE`

**排查步骤**:
1. 检查 API Key 是否有效
2. 查看高德控制台的 Key 配置
3. 确认地理编码服务已绑定

**解决方案**:
- 登录 https://console.amap.com/
- 找到对应 Key
- 绑定"地理编码"服务
- 等待 5-10 分钟生效

### 问题 4: Streamlit 无法启动

**症状**: 进程启动后立即退出

**排查步骤**:
```bash
# 检查端口占用
netstat -tlnp | grep 8501

# 清除缓存
rm -rf ~/.streamlit /tmp/sp_navigate_*

# 查看日志
cat /tmp/streamlit.log
```

**解决方案**:
```bash
pkill -9 -f streamlit
rm -rf ~/.streamlit
streamlit run app.py
```

---

## 版本历史

### v1.0.0 (2026-03-08)

**新增功能**:
- Streamlit Web 界面
- 隔夜住宿策略
- 高德地图地理编码
- Word 报告中文化

**修复问题**:
- 坐标来源问题（步骤 2 不保存坐标）
- Word 报告无图片
- API 并发限制

**技术改进**:
- 添加 `create_validated_dataframe()` 函数
- 优化坐标来源优先级
- 添加详细调试输出

### v0.9.0 (2026-03-06)

- 驾驶舱主页
- 地狱死神深色主题
- 主题切换功能

### v0.8.0 (2026-03-06)

- 初始版本
- TSP 和聚类策略
- 命令行接口

---

## 附录

### A. 关键函数说明

#### `create_validated_dataframe(df, results)`
- **作用**: 将地理编码结果保存回 DataFrame
- **输入**: 
  - `df`: 原始 DataFrame（包含"地址"列）
  - `results`: 地理编码结果列表
- **输出**: 新的 DataFrame（包含"经度"、"纬度"、"地理编码状态"列）

#### `build_config_for_planner(points_df, ...)`
- **作用**: 构建规划器配置
- **关键逻辑**:
  1. 检查 DataFrame 中是否有坐标
  2. 有坐标 → 直接使用
  3. 无坐标 → 调用地理编码
  4. 失败 → 使用近似坐标

### B. 调试技巧

1. **查看坐标来源**:
   ```
   控制台搜索：[Geo] Summary
   ```

2. **查看点位坐标**:
   ```
   控制台搜索：[Debug] All points with coordinates
   ```

3. **验证 DataFrame**:
   ```python
   # 在步骤 2 后
   st.session_state.validated_df
   # 应该包含：地址、经度、纬度、地理编码状态
   ```

### C. 联系方式

- GitHub: https://github.com/macrossfev/SP-navigate
- 问题反馈：提交 Issue
