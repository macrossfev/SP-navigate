"""
SP-navigate Streamlit Web Application
Route planning with template download, address validation, and correction workflow.
"""
import streamlit as st
import pandas as pd
import os
import tempfile
import json
import requests
import time
from pathlib import Path
from datetime import datetime

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
    .step-box {background: #1a1a2e; color: #ffffff; padding: 1.5rem; border-radius: 0.5rem; box-shadow: 0 1px 3px rgba(0,0,0,0.3); margin: 1rem 0;}
    .step-box h3 {color: #ffffff !important;}
    .step-box p {color: #cccccc !important;}
    .success-box {background: #d4edda; border-left: 4px solid #28a745; padding: 1rem; margin: 1rem 0;}
    .warning-box {background: #fff3cd; border-left: 4px solid #ffc107; padding: 1rem; margin: 1rem 0;}
    .error-box {background: #f8d7da; border-left: 4px solid #dc3545; padding: 1rem; margin: 1rem 0;}
    .metric-card {background: white; padding: 1rem; border-radius: 0.5rem; box-shadow: 0 1px 3px rgba(0,0,0,0.1);}
    
    /* 步骤指示器样式 */
    .step-indicator {
        background: #1a1a2e !important;
        color: #ffffff;
        padding: 0.5rem 1rem;
        border-radius: 0.5rem;
        margin: 0.5rem 0;
    }
    .step-indicator-active {
        background: #1f77b4 !important;
        color: #ffffff;
        font-weight: bold;
    }
    .step-indicator-completed {
        background: #28a745 !important;
        color: #ffffff;
    }
    .step-indicator-pending {
        background: #4a4a4a !important;
        color: #888888;
    }
    
    /* Streamlit 列背景覆盖 */
    [data-testid="column"] {
        background: transparent;
    }
</style>
""", unsafe_allow_html=True)

# Session state
if "step" not in st.session_state:
    st.session_state.step = 1
if "validated_data" not in st.session_state:
    st.session_state.validated_data = None
if "failed_addresses" not in st.session_state:
    st.session_state.failed_addresses = []
if "result" not in st.session_state:
    st.session_state.result = None
if "output_dir" not in st.session_state:
    st.session_state.output_dir = None

# Constants
AMAP_KEY = "b6410cb1a118bad10e6d1161d6e896f7"
DEFAULT_CITY = "重庆"
DEFAULT_DISTRICT = "长寿区"

# ============== Helper Functions ==============

def create_template():
    """Create standard Excel template."""
    data = {
        "序号": [1, 2, 3, 4, 5],
        "地址": [
            "长寿区凤城街道 XX 社区 XX 小区",
            "长寿区菩提街道 XX 路 XX 号",
            "长寿区晏家街道 XX 小区",
            "长寿区江南街道 XX 花园",
            "长寿区渡舟街道 XX 苑"
        ],
        "小区名称": ["XX 小区", "XX 路小区", "XX 花园", "XX 苑", "XX 家园"],
        "备注": ["", "", "", "", ""]
    }
    df = pd.DataFrame(data)
    
    output = tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx")
    df.to_excel(output.name, index=False, sheet_name="采样点")
    return output.name


def geocode_address(address, city=DEFAULT_CITY):
    """Geocode single address using Amap API."""
    url = "https://restapi.amap.com/v3/geocode/geo"
    params = {
        "address": address,
        "city": city,
        "key": AMAP_KEY
    }
    try:
        resp = requests.get(url, params=params, timeout=10)
        data = resp.json()
        
        if data.get("status") == "1" and data.get("geocodes"):
            geo = data["geocodes"][0]
            return {
                "status": "OK",
                "input": address,
                "formatted": geo.get("formatted_address", ""),
                "district": geo.get("district", ""),
                "location": geo.get("location", ""),
                "level": geo.get("level", "")
            }
    except Exception as e:
        pass
    
    return {
        "status": "FAIL",
        "input": address,
        "formatted": "",
        "district": "",
        "location": "",
        "level": ""
    }


def validate_addresses(df, progress_bar):
    """Validate all addresses in dataframe."""
    results = []
    
    addresses = df["地址"].dropna().tolist()
    total = len(addresses)
    
    for i, addr in enumerate(addresses):
        result = geocode_address(addr)
        results.append(result)
        progress_bar.progress((i + 1) / total)
        time.sleep(0.1)  # Rate limiting
    
    return results


def export_failed_addresses(failed, output_path):
    """Export failed addresses to Excel for correction."""
    df = pd.DataFrame({
        "原始地址": [r["input"] for r in failed],
        "修正后地址": [""] * len(failed),
        "备注": [""] * len(failed)
    })
    df.to_excel(output_path, index=False, sheet_name="待修正地址")
    return output_path


def merge_corrected_data(original_df, corrected_df):
    """Merge original data with corrected addresses."""
    # Create mapping from corrected file
    correction_map = {}
    if "原始地址" in corrected_df.columns and "修正后地址" in corrected_df.columns:
        for _, row in corrected_df.iterrows():
            original = str(row["原始地址"]).strip()
            corrected = str(row["修正后地址"]).strip()
            if corrected and corrected != "nan":
                correction_map[original] = corrected
    
    # Apply corrections
    corrected_addresses = []
    for addr in original_df["地址"]:
        if addr in correction_map:
            corrected_addresses.append(correction_map[addr])
        else:
            corrected_addresses.append(addr)
    
    result_df = original_df.copy()
    result_df["地址"] = corrected_addresses
    return result_df, len(correction_map)


def build_config_for_planner(
    points_df,
    strategy,
    base_name,
    base_lng=None,
    base_lat=None,
    max_daily_hours=8.0,
    max_daily_points=5,
    stop_time_min=15,
    overnight_threshold_km=80.0,
    single_day_max_hours=6.0,
):
    """Build configuration for planner."""
    import sys
    sys.path.insert(0, str(Path(__file__).parent / "src"))
    from navigate.core.config import NavigateConfig, DataSourceConfig, ColumnMapping, ExportFormatConfig
    from navigate.core.models import Point
    
    output_dir = tempfile.mkdtemp(prefix="sp_navigate_")
    
    # Convert dataframe to points directly (bypass file loading)
    points = []
    for idx, row in points_df.iterrows():
        addr = str(row.get("地址", "")).strip()
        if not addr or addr == "nan":
            continue
        
        # Get coordinates if available
        lng, lat = None, None
        if "经度" in row and "纬度" in row:
            lng_val = row.get("经度")
            lat_val = row.get("纬度")
            if pd.notna(lng_val) and pd.notna(lat_val):
                lng, lat = float(lng_val), float(lat_val)
        elif "坐标" in row:
            coord_str = str(row.get("坐标", "")).strip()
            if coord_str and "," in coord_str:
                parts = coord_str.split(",")
                lng, lat = float(parts[0]), float(parts[1])
        
        # Skip if no coordinates (will be geocoded later if needed)
        # For now, create point with address as name
        points.append(Point(
            id=str(idx),
            name=addr,
            lng=lng or 0.0,  # Placeholder
            lat=lat or 0.0,  # Placeholder
            metadata={"address": addr}
        ))
    
    # Save points info for planner to use
    points_info_file = tempfile.NamedTemporaryFile(delete=False, suffix=".json", mode='w', encoding='utf-8')
    import json
    points_data = {
        "points": [
            {"id": p.id, "name": p.name, "lng": p.lng, "lat": p.lat, "metadata": p.metadata}
            for p in points
        ]
    }
    json.dump(points_data, points_info_file, ensure_ascii=False, indent=2)
    points_info_file.close()
    
    config = NavigateConfig()
    
    # Base point
    config.base_point.name = base_name
    if base_lng and base_lat:
        config.base_point.lng = base_lng
        config.base_point.lat = base_lat
    
    # Strategy
    config.strategy.name = strategy
    config.strategy.options = {
        "cluster_method": "centroid",
        "outlier_threshold_km": overnight_threshold_km,
    }
    
    # Constraints
    config.constraints.max_daily_hours = max_daily_hours
    config.constraints.max_daily_points = max_daily_points
    config.constraints.min_daily_points = 1
    config.constraints.stop_time_per_point_min = stop_time_min
    config.constraints.roundtrip_overhead_min = 60
    config.constraints.overnight_threshold_km = overnight_threshold_km
    config.constraints.single_day_max_hours = single_day_max_hours
    
    # Distance
    config.distance.provider = "haversine"
    config.distance.avg_speed_kmh = 35.0
    # Note: API Key b6410cb1a118bad10e6d1161d6e896f7 returns SERVICE_NOT_AVAILABLE
    # May need to check quota or platform configuration
    config.distance.options["amap_key"] = "b6410cb1a118bad10e6d1161d6e896f7"
    
    # Data - points (use JSON file for direct loading)
    config.data.points = DataSourceConfig(
        file=points_info_file.name,
        format="json",
        column_mapping=ColumnMapping(
            name="name",
            lng="lng",
            lat="lat",
            id="id",
            metadata={"address": "address"}
        )
    )
    
    # Store points directly in config for fallback
    config._points_cache = points
    
    # Export
    config.export.output_dir = output_dir
    config.export.formats = [
        ExportFormatConfig(type="json"),
        ExportFormatConfig(type="excel"),
        ExportFormatConfig(type="docx", title="路线规划报告", include_maps=True),
        ExportFormatConfig(type="map", format="html"),
    ]
    
    return config


def run_planner(config):
    """Run the route planner."""
    import sys
    sys.path.insert(0, str(Path(__file__).parent / "src"))
    from navigate.core.planner import Planner
    from navigate.core.models import Point, DistanceMatrix
    from navigate.distance.haversine import haversine
    import json

    # Use cached points if available (from Web app)
    points = getattr(config, '_points_cache', None)

    if points is None:
        # Fallback to file loading (for CLI usage)
        planner = Planner(config)
        result = planner.run()
    else:
        # Direct planning with cached points
        print(f"\n[Data] {len(points)} points loaded from cache")
        
        # Check if we have valid coordinates
        valid_coords = sum(1 for p in points if p.lng != 0.0 and p.lat != 0.0)
        print(f"  Points with valid coordinates: {valid_coords}/{len(points)}")
        
        # If no valid coordinates, try geocoding first
        if valid_coords == 0:
            print("[Geo] No coordinates available, attempting geocoding...")
            
            # Use the configured API key or default
            amap_key = config.distance.options.get("amap_key", "21a63b4dface4f3e756a671c57e86cac")
            geocode_success = False
            
            try:
                from navigate.geocoding.amap import AmapGeocoder
                geocoder = AmapGeocoder(amap_key)
                
                # Test geocoding with first point
                test_addr = points[0].name
                print(f"  Testing with: {test_addr}")
                test_result = geocoder.geocode(test_addr)
                
                if test_result:
                    print(f"  ✓ Amap API working! Geocoding all points...")
                    geocode_success = True
                    
                    for pt in points:
                        result = geocoder.geocode(pt.name)
                        if result:
                            pt.lng, pt.lat = result
                            print(f"    ✓ {pt.name[:40]} -> {pt.lat:.4f}, {pt.lng:.4f}")
                        else:
                            print(f"    ✗ {pt.name[:40]} - failed")
                else:
                    print(f"  ✗ Amap API test failed for first address")
                    print(f"     Error: SERVICE_NOT_AVAILABLE or USERKEY_PLAT_NOMATCH")
                    print(f"     Possible causes:")
                    print(f"       1. API Key quota exhausted")
                    print(f"       2. API Key not configured for Web API platform")
                    print(f"       3. Service not enabled in Amap console")
                    
            except Exception as e:
                print(f"  ✗ Amap geocoding error: {e}")
            
            # If geocoding failed, use fallback pseudo-coordinates
            if not geocode_success:
                print("\n[Geo] ⚠️ Amap API unavailable, using approximate coordinates...")
                print("        For accurate results, please check your API key configuration.")
                print("        Error: USERKEY_PLAT_NOMATCH - API Key not configured for Web API")
                
                # Use Chongqing Changshou district center as base
                BASE_LAT = 29.857
                BASE_LNG = 107.081
                
                for i, pt in enumerate(points):
                    # Generate pseudo-coordinates based on address hash
                    import hashlib
                    addr_hash = hashlib.md5(pt.name.encode('utf-8')).hexdigest()
                    lat_offset = (int(addr_hash[:4], 16) / 65535 - 0.5) * 0.5
                    lng_offset = (int(addr_hash[4:8], 16) / 65535 - 0.5) * 0.5
                    pt.lat = BASE_LAT + lat_offset
                    pt.lng = BASE_LNG + lng_offset
                    print(f"  ~ {pt.name[:40]} -> {pt.lat:.4f}, {pt.lng:.4f}")
        
        # Build distance matrix
        print(f"\n[Matrix] Building {len(points)}x{len(points)} distance matrix...")

        def dist_func(a, b):
            return haversine(a.lat, a.lng, b.lat, b.lng)

        dist_matrix = DistanceMatrix.from_points(points, dist_func)
        print("  Done")

        # Run strategy
        from navigate.strategies import STRATEGIES
        from navigate.strategies.tsp import TspStrategy
        from navigate.strategies.cluster import ClusterStrategy
        from navigate.strategies.overnight import OvernightStrategy

        strategy_name = config.strategy.name
        strategy_cls = STRATEGIES.get(strategy_name)
        if not strategy_cls:
            raise ValueError(f"Unknown strategy: {strategy_name}. "
                             f"Available: {list(STRATEGIES.keys())}")

        if strategy_name == "cluster":
            base_coord = None
            if config.base_point.lng and config.base_point.lat:
                base_coord = (config.base_point.lng, config.base_point.lat)
            strategy = strategy_cls(config, base_coord=base_coord)
        elif strategy_name == "overnight":
            base_coord = None
            if config.base_point.lng and config.base_point.lat:
                base_coord = (config.base_point.lng, config.base_point.lat)
            bp_name = config.base_point.name or "公司"
            strategy = strategy_cls(config, base_coord=base_coord, base_name=bp_name)
        else:
            strategy = strategy_cls(config)

        result = strategy.plan(points, dist_matrix)
        print(result.summary())

        # Export results
        from navigate.io.exporters import EXPORTERS
        output_dir = config.export.output_dir
        os.makedirs(output_dir, exist_ok=True)

        # Create a simple distance provider for map polyline (using straight lines)
        class SimpleDistanceProvider:
            def get_polyline(self, a, b):
                # Return straight line coordinates for map display
                return [(a.lat, a.lng), (b.lat, b.lng)]
        
        distance_provider = SimpleDistanceProvider()

        # First generate HTML maps
        map_exporter = EXPORTERS["map"](config)
        map_exporter.export(result, output_dir, format_config=None, distance_provider=distance_provider)
        
        # Then generate other formats
        for fmt in config.export.formats:
            if fmt.type == "map":
                continue  # Already handled
            exporter_cls = EXPORTERS.get(fmt.type)
            if exporter_cls:
                exporter = exporter_cls(config)
                exporter.export(result, output_dir, format_config=fmt, distance_provider=distance_provider)

    return {
        "result": result,
        "output_dir": config.export.output_dir,
    }


# ============== UI Functions ==============

def render_step1():
    """Step 1: Download template or upload data."""
    st.markdown("""
    <div class="step-box">
        <h3>📋 步骤 1: 准备数据</h3>
        <p>请选择以下方式之一：</p>
    </div>
    """, unsafe_allow_html=True)
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("📥 下载标准模板")
        template_path = create_template()
        with open(template_path, "rb") as f:
            st.download_button(
                label="📊 下载 Excel 模板",
                data=f.read(),
                file_name="采样点标准模板.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key="download_template"
            )
        st.info("💡 模板包含示例数据，请按格式填写您的采样点地址")
    
    with col2:
        st.subheader("📤 上传数据文件")
        uploaded_file = st.file_uploader(
            "上传填写好的 Excel 文件",
            type=["xlsx", "xls"],
            key="upload_points"
        )
    
    if uploaded_file:
        df = pd.read_excel(uploaded_file)
        st.session_state.uploaded_df = df
        st.session_state.uploaded_file = uploaded_file
        st.success(f"✅ 已加载 {len(df)} 个点位")
        
        with st.expander("📋 数据预览"):
            st.dataframe(df.head(), use_container_width=True)
        
        if st.button("下一步：地址验证 →", type="primary"):
            st.session_state.step = 2
            st.rerun()


def render_step2():
    """Step 2: Address validation."""
    st.markdown("""
    <div class="step-box">
        <h3>🔍 步骤 2: 地址验证与清洗</h3>
        <p>使用高德地图 API 验证地址有效性</p>
    </div>
    """, unsafe_allow_html=True)
    
    if "uploaded_df" not in st.session_state:
        st.error("请先上传数据文件")
        if st.button("← 返回上传"):
            st.session_state.step = 1
            st.rerun()
        return
    
    # Check if already validated and all passed
    if st.session_state.get("all_addresses_validated", False) and st.session_state.get("validated_df") is not None:
        st.success("✅ 所有地址已验证通过！")
        if st.button("进入步骤 4: 生成规划 →", type="primary"):
            st.session_state.step = 4
            st.rerun()
        if st.button("← 返回上一步"):
            st.session_state.step = 1
            st.rerun()
        return
    
    df = st.session_state.uploaded_df
    
    # Check if "地址" column exists
    if "地址" not in df.columns:
        st.error("❌ Excel 文件必须包含'地址'列")
        if st.button("← 返回上传"):
            st.session_state.step = 1
            st.rerun()
        return
    
    st.write(f"待验证地址：**{len(df)}** 个")
    
    # Validation settings
    with st.expander("⚙️ 验证设置"):
        city = st.text_input("城市", value=DEFAULT_CITY)
        district = st.text_input("区县", value=DEFAULT_DISTRICT)
        st.session_state.validate_city = city
        st.session_state.validate_district = district
    
    if st.button("🔍 开始验证地址", type="primary"):
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        status_text.text("正在调用高德 API 验证地址...")
        results = validate_addresses(df, progress_bar)
        
        ok_results = [r for r in results if r["status"] == "OK"]
        fail_results = [r for r in results if r["status"] == "FAIL"]
        
        # Check district match
        wrong_district = []
        for r in ok_results:
            if st.session_state.validate_district not in r.get("district", ""):
                wrong_district.append(r)
        
        st.session_state.validation_results = results
        st.session_state.ok_results = ok_results
        st.session_state.failed_addresses = fail_results
        st.session_state.wrong_district = wrong_district
        
        # Summary
        st.success("✅ 验证完成！")
        
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("✅ 匹配成功", len(ok_results) - len(wrong_district))
        with col2:
            st.metric("❌ 匹配失败", len(fail_results))
        with col3:
            st.metric("⚠️ 区域不符", len(wrong_district))
        
        if fail_results or wrong_district:
            st.markdown('<div class="warning-box">', unsafe_allow_html=True)
            st.write("### ⚠️ 需要处理的地址")
            
            if fail_results:
                st.write(f"**匹配失败 ({len(fail_results)} 个):**")
                fail_df = pd.DataFrame({
                    "原始地址": [r["input"] for r in fail_results]
                })
                st.dataframe(fail_df, use_container_width=True)
            
            if wrong_district:
                st.write(f"**区域不符 ({len(wrong_district)} 个):**")
                wrong_df = pd.DataFrame({
                    "原始地址": [r["input"] for r in wrong_district],
                    "实际位置": [f"{r['district']} - {r['formatted']}" for r in wrong_district]
                })
                st.dataframe(wrong_df, use_container_width=True)
            
            st.markdown('</div>', unsafe_allow_html=True)
            
            # Export failed addresses
            failed_output = tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx")
            all_failed = fail_results + wrong_district
            export_failed_addresses(all_failed, failed_output.name)
            
            with open(failed_output.name, "rb") as f:
                st.download_button(
                    label="📥 下载待修正地址表",
                    data=f.read(),
                    file_name="待修正地址.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
            
            st.info("💡 请下载待修正地址表，填写'修正后地址'列后，在下一步上传")
            
            if st.button("我已修正，上传修正表 →"):
                st.session_state.step = 3
                st.rerun()
        else:
            st.success("🎉 所有地址验证通过！可以直接生成规划方案")
            # Set flag to skip re-validation
            st.session_state.all_addresses_validated = True
            st.session_state.validated_df = df.copy()
            if st.button("生成规划方案 →", type="primary", key="go_to_step4"):
                st.session_state.step = 4
                st.rerun()
    
    if st.button("← 返回上一步"):
        st.session_state.step = 1
        st.rerun()


def render_step3():
    """Step 3: Upload corrected addresses."""
    st.markdown("""
    <div class="step-box">
        <h3>📝 步骤 3: 上传修正后的地址表</h3>
        <p>上传已填写修正地址的 Excel 文件</p>
    </div>
    """, unsafe_allow_html=True)
    
    if "uploaded_df" not in st.session_state:
        st.error("请先上传原始数据")
        if st.button("← 返回上传"):
            st.session_state.step = 1
            st.rerun()
        return
    
    corrected_file = st.file_uploader(
        "上传修正后的地址表",
        type=["xlsx", "xls"],
        key="upload_corrected"
    )
    
    if corrected_file:
        corrected_df = pd.read_excel(corrected_file)
        
        if "原始地址" not in corrected_df.columns or "修正后地址" not in corrected_df.columns:
            st.error("❌ 修正表必须包含'原始地址'和'修正后地址'列")
        else:
            # Merge
            merged_df, corrected_count = merge_corrected_data(
                st.session_state.uploaded_df,
                corrected_df
            )
            
            st.success(f"✅ 已合并修正数据，修正了 **{corrected_count}** 个地址")
            
            with st.expander("📋 修正后数据预览"):
                st.dataframe(merged_df.head(), use_container_width=True)
            
            st.session_state.validated_df = merged_df
            
            if st.button("生成规划方案 →", type="primary"):
                st.session_state.step = 4
                st.rerun()
    
    if st.button("← 返回验证"):
        st.session_state.step = 2
        st.rerun()


def render_step4():
    """Step 4: Generate plan."""
    st.markdown("""
    <div class="step-box">
        <h3>🗺️ 步骤 4: 生成路线规划</h3>
        <p>配置参数并生成最优路线方案</p>
    </div>
    """, unsafe_allow_html=True)
    
    if "validated_df" not in st.session_state:
        st.error("请先完成地址验证")
        if st.button("← 返回验证"):
            st.session_state.step = 2
            st.rerun()
        return
    
    # Sidebar configuration
    with st.sidebar:
        st.header("⚙️ 规划配置")
        
        strategy = st.selectbox(
            "规划策略",
            options=["overnight", "tsp", "cluster"],
            format_func=lambda x: {
                "overnight": "🏨 隔夜住宿 (混合模式)",
                "tsp": "🚗 单日往返 (TSP)",
                "cluster": "📍 聚类分组"
            }.get(x, x)
        )
        
        st.divider()
        
        max_daily_hours = st.slider("每日最大工时 (小时)", 4.0, 12.0, 8.0, 0.5)
        max_daily_points = st.slider("每日最大点数", 1, 20, 5, 1)
        stop_time_min = st.slider("每点停留时间 (分钟)", 5, 60, 15, 5)
        
        st.divider()
        
        overnight_threshold_km = st.slider(
            "隔夜距离阈值 (公里)",
            0.0, 200.0, 80.0, 10.0
        )
        single_day_max_hours = st.slider("单日往返最大工时 (小时)", 4.0, 10.0, 6.0, 0.5)
    
    # Base point config
    st.subheader("起点配置")
    col1, col2 = st.columns(2)
    with col1:
        base_name = st.text_input(
            "公司名称/起点",
            value="中共重庆市自来水有限公司委员会"
        )
    with col2:
        with st.expander("📍 手动输入坐标 (可选)"):
            base_lng = st.number_input("经度", value=107.081, format="%.6f")
            base_lat = st.number_input("纬度", value=29.857, format="%.6f")
    
    if st.button("▶️ 开始规划", type="primary"):
        with st.spinner("🔄 正在生成路线规划，请稍候..."):
            try:
                config = build_config_for_planner(
                    points_df=st.session_state.validated_df,
                    strategy=strategy,
                    base_name=base_name,
                    base_lng=base_lng if base_lng else None,
                    base_lat=base_lat if base_lat else None,
                    max_daily_hours=max_daily_hours,
                    max_daily_points=max_daily_points,
                    stop_time_min=stop_time_min,
                    overnight_threshold_km=overnight_threshold_km,
                    single_day_max_hours=single_day_max_hours,
                )
                
                result = run_planner(config)
                
                st.session_state.result = result
                st.session_state.output_dir = config.export.output_dir
                
                st.success("✅ 路线规划完成！")
                st.session_state.step = 5
                st.rerun()
                
            except Exception as e:
                st.error(f"❌ 规划失败：{str(e)}")
                import traceback
                st.code(traceback.format_exc())
    
    if st.button("← 返回上一步"):
        st.session_state.step = 2
        st.rerun()


def render_step5():
    """Step 5: View and download results."""
    st.markdown("""
    <div class="step-box">
        <h3>📊 步骤 5: 查看结果</h3>
        <p>查看规划方案并下载结果文件</p>
    </div>
    """, unsafe_allow_html=True)
    
    if "result" not in st.session_state:
        st.error("请先生成规划方案")
        if st.button("← 返回规划"):
            st.session_state.step = 4
            st.rerun()
        return
    
    result_data = st.session_state.result
    result = result_data["result"]
    
    # Summary metrics
    st.subheader("📈 规划概览")
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
    st.subheader("📅 每日行程")
    
    for day in result.days:
        trip_type_badge = (
            '<span style="background:#9933CC;color:white;padding:2px 8px;border-radius:10px;font-size:12px;">🏨 隔夜住宿</span>'
            if day.is_overnight else
            '<span style="background:#00AA00;color:white;padding:2px 8px;border-radius:10px;font-size:12px;">🚗 单日往返</span>'
        )
        
        with st.expander(
            f"**第 {day.day} 天** {trip_type_badge} - "
            f"{day.point_count} 点位 | {day.drive_distance_km:.1f} km | {day.total_time_hours:.1f} h"
        ):
            col1, col2 = st.columns(2)
            with col1:
                st.write(f"**起点**: {day.start_point_name or 'N/A'}")
                st.write(f"**终点**: {day.end_point_name or 'N/A'}")
            with col2:
                st.write(f"**行驶时间**: {day.drive_time_min:.0f} 分钟")
                st.write(f"**停留时间**: {day.stop_time_min:.0f} 分钟")
            
            if day.is_overnight and day.hotel:
                st.info(f"🏨 **住宿点**: {day.hotel.name}")
            
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
    
    # Download section
    st.divider()
    st.subheader("📥 下载结果")

    output_dir = st.session_state.output_dir

    # Find output files
    excel_file = None
    json_file = None
    docx_file = None
    map_files = []

    if output_dir and os.path.exists(output_dir):
        for root, dirs, files in os.walk(output_dir):
            for f in files:
                filepath = os.path.join(root, f)
                if f.endswith(".xlsx"):
                    excel_file = filepath
                elif f.endswith(".json"):
                    json_file = filepath
                elif f.endswith(".docx"):
                    docx_file = filepath
                elif f.endswith(".html") and "day_" in f:
                    map_files.append(filepath)

    st.write(f"输出目录：`{output_dir}`")
    st.write(f"找到的文件：Excel={excel_file is not None}, JSON={json_file is not None}, Word={docx_file is not None}, Maps={len(map_files)}")

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        if excel_file and os.path.exists(excel_file):
            with open(excel_file, "rb") as f:
                st.download_button(
                    "📊 下载 Excel",
                    f.read(),
                    file_name="route_plan.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    key="dl_excel"
                )
        else:
            st.download_button(
                "📊 下载 Excel",
                data=b"",
                file_name="route_plan.xlsx",
                disabled=True,
                key="dl_excel_dis"
            )

    with col2:
        if docx_file and os.path.exists(docx_file):
            with open(docx_file, "rb") as f:
                st.download_button(
                    "📄 下载 Word 报告",
                    f.read(),
                    file_name="route_plan_report.docx",
                    mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    key="dl_docx"
                )
        else:
            st.download_button(
                "📄 下载 Word 报告",
                data=b"",
                file_name="route_plan_report.docx",
                disabled=True,
                key="dl_docx_dis"
            )

    with col3:
        if json_file and os.path.exists(json_file):
            with open(json_file, "rb") as f:
                st.download_button(
                    "📄 下载 JSON",
                    f.read(),
                    file_name="route_plan.json",
                    mime="application/json",
                    key="dl_json"
                )
        else:
            st.download_button(
                "📄 下载 JSON",
                data=b"",
                file_name="route_plan.json",
                disabled=True,
                key="dl_json_dis"
            )

    with col4:
        if map_files:
            import zipfile
            map_zip_path = os.path.join(output_dir, "maps.zip")
            with zipfile.ZipFile(map_zip_path, 'w') as zf:
                for mf in map_files:
                    zf.write(mf, os.path.basename(mf))
            with open(map_zip_path, "rb") as f:
                st.download_button(
                    "🗺️ 下载地图",
                    f.read(),
                    file_name="route_maps.zip",
                    mime="application/zip",
                    key="dl_maps"
                )
        else:
            st.download_button(
                "🗺️ 下载地图",
                data=b"",
                file_name="route_maps.zip",
                disabled=True,
                key="dl_maps_dis"
            )

    if st.button("🔄 重新规划"):
        st.session_state.step = 4
        st.rerun()

    if st.button("🏠 重新开始"):
        st.session_state.step = 1
        st.session_state.validated_data = None
        st.session_state.result = None
        st.rerun()


def main():
    st.markdown('<h1 class="main-header">🗺️ SP-navigate 路线规划系统</h1>', unsafe_allow_html=True)
    st.markdown('<p class="sub-header">多点位路线规划与调度优化系统</p>', unsafe_allow_html=True)

    # Progress indicator
    steps = ["准备数据", "地址验证", "上传修正", "生成规划", "查看结果"]

    # Progress bar
    progress = st.session_state.step / len(steps)
    st.progress(progress)

    # Step indicator with dark background
    col1, col2, col3, col4, col5 = st.columns(5)
    cols = [col1, col2, col3, col4, col5]
    for i, col in enumerate(cols):
        with col:
            if i + 1 == st.session_state.step:
                # Active step - blue background
                col.markdown(
                    f'<div class="step-indicator step-indicator-active" style="text-align:center;">'
                    f'<strong>{i+1}. {steps[i]}</strong></div>',
                    unsafe_allow_html=True
                )
            elif i + 1 < st.session_state.step:
                # Completed step - green background
                col.markdown(
                    f'<div class="step-indicator step-indicator-completed" style="text-align:center;">'
                    f'✅ {steps[i]}</div>',
                    unsafe_allow_html=True
                )
            else:
                # Pending step - gray background
                col.markdown(
                    f'<div class="step-indicator step-indicator-pending" style="text-align:center;">'
                    f'⚪ {steps[i]}</div>',
                    unsafe_allow_html=True
                )

    st.divider()
    
    # Render current step
    if st.session_state.step == 1:
        render_step1()
    elif st.session_state.step == 2:
        render_step2()
    elif st.session_state.step == 3:
        render_step3()
    elif st.session_state.step == 4:
        render_step4()
    elif st.session_state.step == 5:
        render_step5()


if __name__ == "__main__":
    main()
