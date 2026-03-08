#!/bin/bash
# SP-navigate Streamlit App Launcher

echo "========================================"
echo "  SP-navigate 路线规划系统"
echo "  Streamlit Web 应用启动器"
echo "========================================"
echo ""

# Check if virtual environment exists
if [ -d "venv" ]; then
    echo "激活虚拟环境..."
    source venv/bin/activate
fi

# Check dependencies
echo "检查依赖..."
pip install -q streamlit 2>/dev/null

# Start Streamlit
echo ""
echo "启动 Streamlit 应用..."
echo "访问地址：http://localhost:8501"
echo ""
echo "按 Ctrl+C 停止服务"
echo "========================================"
echo ""

streamlit run app.py --server.address 0.0.0.0 --server.port 8501
