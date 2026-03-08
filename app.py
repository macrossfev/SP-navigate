"""
SP-navigate Streamlit Web Application
Simplified interface for route planning with file upload and visual results.
"""
import streamlit as st
import pandas as pd
import os
import tempfile
import yaml
from pathlib import Path

# Configure page
st.set_page_config(
    page_title="SP-navigate 路线规划系统",
    page_icon="🗺️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom CSS
st.markdown("""
<style>
    .main-header {font-size: 2.5rem; color: #1f77b4; margin-bottom: 1rem;}
    .sub-header {font-size: 1.2rem; color: #666; margin-bottom: 2rem;}
    .result-box {background: #f0f2f6; padding: 1rem; border-radius: 0.5rem; margin: 1rem 0;}
    .metric-card {background: white; padding: 1rem; border-radius: 0.5rem; box-shadow: 0 1px 3px rgba(0,0,0,0.1);}
    .overnight-badge {background: #9933CC; color: white; padding: 0.2rem 0.6rem; border-radius: 1rem; font-size: 0.8rem;}
    .single-day-badge {background: #00AA00; color: white; padding: 0.2rem 0.6rem; border-radius: 1rem; font-size: 0.8rem;}
</style>
""", unsafe_allow_html=True)

# Session state
if "result" not in st.session_state:
    st.session_state.result = None
if "output_dir" not in st.session_state:
    st.session_state.output_dir = None


def main():
    st.markdown('<h1 class="main-header">🗺️ SP-navigate 路线规划系统</h1>', unsafe_allow_html=True)
    st.markdown('<p class="sub-header">多点位路线规划与调度优化系统 - 支持单日往返和隔夜住宿两种模式</p>', unsafe_allow_html=True)
    
    # Sidebar
    with st.sidebar:
        st.header("⚙️ 配置")
        
        # Strategy selection
        strategy = st.selectbox(
            "规划策略",
            options=["overnight", "tsp", "cluster"],
            format_func=lambda x: {
                "overnight": "🏨 隔夜住宿 (混合模式)",
                "tsp": "🚗 单日往返 (TSP)",
                "cluster": "📍 聚类分组"
            }.get(x, x),
            help="overnight: 自动判断远近距离，远距离启用隔夜模式；tsp: 全部单日往返；cluster: 按区域聚类"
        )
        
        st.divider()
        
        # Constraints
        st.subheader("约束条件")
        max_daily_hours = st.slider("每日最大工时 (小时)", 4.0, 12.0, 8.0, 0.5)
        max_daily_points = st.slider("每日最大点数", 1, 20, 5, 1)
        stop_time_min = st.slider("每点停留时间 (分钟)", 5, 60, 15, 5)
        
        # Overnight settings
        st.divider()
        st.subheader("隔夜模式设置")
        overnight_threshold_km = st.slider(
            "隔夜距离阈值 (公里)",
            0.0, 200.0, 80.0, 10.0,
            help="超过此距离的点位将启用隔夜住宿模式"
        )
        single_day_max_hours = st.slider("单日往返最大工时 (小时)", 4.0, 10.0, 6.0, 0.5)
        
        # Distance settings
        st.divider()
        st.subheader("距离计算")
        distance_provider = st.selectbox(
            "距离提供者",
            options=["haversine", "amap"],
            format_func=lambda x: "高德地图 (实时路况)" if x == "amap" else "半正矢公式 (直线距离)",
        )
        avg_speed_kmh = st.slider("平均速度 (km/h)", 20, 80, 35, 5)
        
        if distance_provider == "amap":
            amap_key = st.text_input("高德 API Key", type="password", help="使用高德地图需要 API Key")
        else:
            amap_key = ""
    
    # Main content
    col1, col2 = st.columns([2, 1])
    
    with col1:
        st.subheader("1️⃣ 上传采样点数据")
        
        uploaded_file = st.file_uploader(
            "上传 Excel 文件",
            type=["xlsx", "xls"],
            help="Excel 文件需包含'地址'列，可选'坐标'列 (格式：经度，纬度)"
        )
        
        if uploaded_file:
            # Preview data
            df = pd.read_excel(uploaded_file)
            st.write(f"✅ 已加载 **{len(df)}** 个点位")
            
            with st.expander("📋 数据预览"):
                st.dataframe(df.head(10), use_container_width=True)
            
            # Save to temp file
            with tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx") as f:
                f.write(uploaded_file.getvalue())
                temp_file = f.name
    
    with col2:
        st.subheader("2️⃣ 起点配置")
        
        base_name = st.text_input(
            "公司名称/起点",
            value="中共重庆市自来水有限公司委员会",
            help="出发点和返回点"
        )
        
        # Optional: manual coordinates
        with st.expander("📍 手动输入坐标 (可选)"):
            base_lng = st.number_input("经度", value=107.081, format="%.6f")
            base_lat = st.number_input("纬度", value=29.857, format="%.6f")
    
    # Run button
    st.divider()
    st.subheader("3️⃣ 开始规划")
    
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        run_button = st.button(
            "▶️ 运行路线规划",
            type="primary",
            use_container_width=True,
            disabled=not uploaded_file
        )
    
    if run_button and uploaded_file:
        with st.spinner("🔄 正在规划路线，请稍候..."):
            try:
                # Build config
                config = build_config(
                    strategy=strategy,
                    points_file=temp_file,
                    base_name=base_name,
                    base_lng=base_lng if base_lng else None,
                    base_lat=base_lat if base_lat else None,
                    max_daily_hours=max_daily_hours,
                    max_daily_points=max_daily_points,
                    stop_time_min=stop_time_min,
                    overnight_threshold_km=overnight_threshold_km,
                    single_day_max_hours=single_day_max_hours,
                    distance_provider=distance_provider,
                    avg_speed_kmh=avg_speed_kmh,
                    amap_key=amap_key,
                )
                
                # Run planner
                result = run_planner(config)
                
                st.session_state.result = result
                st.session_state.output_dir = config.export.output_dir
                
                st.success("✅ 路线规划完成！")
                
            except Exception as e:
                st.error(f"❌ 规划失败：{str(e)}")
                import traceback
                st.code(traceback.format_exc())
    
    # Display results
    if st.session_state.result:
        display_results(st.session_state.result, st.session_state.output_dir)


def build_config(
    strategy: str,
    points_file: str,
    base_name: str,
    base_lng: float = None,
    base_lat: float = None,
    max_daily_hours: float = 8.0,
    max_daily_points: int = 5,
    stop_time_min: int = 15,
    overnight_threshold_km: float = 80.0,
    single_day_max_hours: float = 6.0,
    distance_provider: str = "haversine",
    avg_speed_kmh: float = 35.0,
    amap_key: str = "",
) -> dict:
    """Build configuration dictionary."""
    output_dir = tempfile.mkdtemp(prefix="sp_navigate_")
    
    config = {
        "base_point": {
            "name": base_name,
        },
        "strategy": {
            "name": strategy,
            "options": {
                "cluster_method": "centroid",
                "outlier_threshold_km": overnight_threshold_km,
            }
        },
        "constraints": {
            "max_daily_hours": max_daily_hours,
            "max_daily_points": max_daily_points,
            "min_daily_points": 1,
            "stop_time_per_point_min": stop_time_min,
            "roundtrip_overhead_min": 60,
            "overnight_threshold_km": overnight_threshold_km,
            "single_day_max_hours": single_day_max_hours,
        },
        "distance": {
            "provider": distance_provider,
            "avg_speed_kmh": avg_speed_kmh,
        },
        "data": {
            "points": {
                "file": points_file,
                "format": "excel",
                "column_mapping": {
                    "name": "地址",
                    "coordinates": "坐标",
                }
            }
        },
        "export": {
            "output_dir": output_dir,
            "formats": [
                {"type": "json"},
                {"type": "excel"},
                {"type": "map", "format": "html"},
            ]
        }
    }
    
    if base_lng and base_lat:
        config["base_point"]["lng"] = base_lng
        config["base_point"]["lat"] = base_lat
    
    if distance_provider == "amap" and amap_key:
        config["distance"]["amap_key"] = amap_key
        config["distance"]["request_delay"] = 0.5
    
    return config


def run_planner(config: dict) -> dict:
    """Run the route planner."""
    import sys
    sys.path.insert(0, str(Path(__file__).parent / "src"))
    
    from navigate.core.config import NavigateConfig
    from navigate.core.planner import Planner
    
    # Convert dict to NavigateConfig
    config_obj = NavigateConfig()
    
    # Base point
    bp = config["base_point"]
    config_obj.base_point.name = bp.get("name", "")
    config_obj.base_point.lng = bp.get("lng")
    config_obj.base_point.lat = bp.get("lat")
    
    # Strategy
    config_obj.strategy.name = config["strategy"]["name"]
    config_obj.strategy.options = config["strategy"].get("options", {})
    
    # Constraints
    c = config["constraints"]
    config_obj.constraints.max_daily_hours = c["max_daily_hours"]
    config_obj.constraints.max_daily_points = c["max_daily_points"]
    config_obj.constraints.min_daily_points = c["min_daily_points"]
    config_obj.constraints.stop_time_per_point_min = c["stop_time_per_point_min"]
    config_obj.constraints.roundtrip_overhead_min = c["roundtrip_overhead_min"]
    config_obj.constraints.overnight_threshold_km = c.get("overnight_threshold_km", 0)
    config_obj.constraints.single_day_max_hours = c.get("single_day_max_hours", 0)
    
    # Distance
    d = config["distance"]
    config_obj.distance.provider = d["provider"]
    config_obj.distance.avg_speed_kmh = d["avg_speed_kmh"]
    config_obj.distance.options = {k: v for k, v in d.items() if k not in ["provider", "avg_speed_kmh"]}
    
    # Data
    config_obj.data.points.file = config["data"]["points"]["file"]
    config_obj.data.points.format = "excel"
    
    # Export
    config_obj.export.output_dir = config["export"]["output_dir"]
    config_obj.export.formats = []
    for fmt in config["export"]["formats"]:
        from navigate.core.config import ExportFormatConfig
        config_obj.export.formats.append(ExportFormatConfig(
            type=fmt.get("type", "json"),
            format=fmt.get("format", "html"),
        ))
    
    # Run planner
    planner = Planner(config_obj)
    result = planner.run()
    
    return {
        "result": result,
        "output_dir": config_obj.export.output_dir,
    }


def display_results(result_data: dict, output_dir: str):
    """Display planning results."""
    result = result_data["result"]
    
    st.divider()
    st.subheader("📊 规划结果")
    
    # Summary metrics
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("总点位", result.total_points)
    
    with col2:
        st.metric("总天数", result.total_days)
    
    with col3:
        st.metric("总距离", f"{result.total_distance_km:.1f} km")
    
    with col4:
        st.metric("总时间", f"{result.total_hours:.1f} h")
    
    # Day-by-day breakdown
    st.markdown("### 📅 每日行程")
    
    for day in result.days:
        trip_type_badge = (
            '<span class="overnight-badge">🏨 隔夜住宿</span>'
            if day.is_overnight else
            '<span class="single-day-badge">🚗 单日往返</span>'
        )
        
        with st.expander(
            f"**第 {day.day} 天** {trip_type_badge} - "
            f"{day.point_count} 点位 | {day.drive_distance_km:.1f} km | {day.total_time_hours:.1f} h"
        ):
            # Route info
            col1, col2 = st.columns(2)
            with col1:
                st.write(f"**起点**: {day.start_point_name or 'N/A'}")
                st.write(f"**终点**: {day.end_point_name or 'N/A'}")
            with col2:
                st.write(f"**行驶时间**: {day.drive_time_min:.0f} 分钟")
                st.write(f"**停留时间**: {day.stop_time_min:.0f} 分钟")
            
            if day.is_overnight and day.hotel:
                st.info(f"🏨 **住宿点**: {day.hotel.name}")
            
            # Point list
            st.write("**采样点列表**:")
            point_data = []
            for i, p in enumerate(day.points):
                point_data.append({
                    "序号": i + 1,
                    "名称": p.name,
                    "经度": p.lng,
                    "纬度": p.lat,
                })
            st.dataframe(pd.DataFrame(point_data), use_container_width=True)
    
    # Download links
    st.divider()
    st.subheader("📥 下载结果")
    
    col1, col2, col3 = st.columns(3)
    
    # Find output files
    excel_file = None
    map_files = []
    
    if output_dir and os.path.exists(output_dir):
        for root, dirs, files in os.walk(output_dir):
            for f in files:
                if f.endswith(".xlsx"):
                    excel_file = os.path.join(root, f)
                elif f.endswith(".html") and "day_" in f:
                    map_files.append(os.path.join(root, f))
    
    with col1:
        if excel_file:
            with open(excel_file, "rb") as f:
                st.download_button(
                    "📊 下载 Excel 结果",
                    f.read(),
                    file_name="route_plan.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
        else:
            st.download_button(
                "📊 下载 Excel 结果",
                b"",
                file_name="route_plan.xlsx",
                disabled=True,
            )
    
    with col2:
        # JSON result
        import json
        json_data = {
            "strategy": result.strategy_name,
            "total_days": result.total_days,
            "total_points": result.total_points,
            "total_distance_km": result.total_distance_km,
            "total_hours": result.total_hours,
            "days": [
                {
                    "day": d.day,
                    "trip_type": d.trip_type.value,
                    "points": d.point_count,
                    "distance_km": d.drive_distance_km,
                    "hours": d.total_time_hours,
                }
                for d in result.days
            ]
        }
        st.download_button(
            "📄 下载 JSON 结果",
            json.dumps(json_data, ensure_ascii=False, indent=2),
            file_name="route_plan.json",
            mime="application/json",
        )
    
    with col3:
        # Map files
        if map_files:
            map_zip_path = os.path.join(output_dir, "maps.zip")
            import zipfile
            with zipfile.ZipFile(map_zip_path, 'w') as zf:
                for mf in map_files:
                    zf.write(mf, os.path.basename(mf))
            with open(map_zip_path, "rb") as f:
                st.download_button(
                    "🗺️ 下载地图文件",
                    f.read(),
                    file_name="route_maps.zip",
                    mime="application/zip",
                )


if __name__ == "__main__":
    main()
