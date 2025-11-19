#!/bin/bash
# 宝塔面板专用启动脚本

# 设置环境变量
export OKX_API_KEY="bf75e5eb-4573-4614-9dcd-0c624dc1e6d2"
export OKX_SECRET_KEY="ADFAAF641906C516E0C1097160081C3D"
export OKX_PASSWORD="591868Ljc@"
export CRYPTOPANIC_API="0c636455dd5d969ee8491cbc0d7fd6cc6cfe70cc"

# 进入项目目录
cd /www/python/coin_system2.2

# 激活虚拟环境（如果使用虚拟环境）
if [ -d ".venv" ]; then
    source .venv/bin/activate
fi

# 启动程序
python main.py