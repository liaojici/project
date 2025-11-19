import os
import logging
from dotenv import load_dotenv



def initialize_environment():
    """初始化环境变量"""
    # 指定 .env 文件的绝对路径
    env_path = '/www/python/swap_coin_system2/.env'
    
    if os.path.exists(env_path):
        load_dotenv(env_path)
        logging.info(f"从 {env_path} 加载环境变量")
    else:
        logging.warning(f"未找到 .env 文件: {env_path}")
    
    # 检查必需的环境变量
    required_env_vars = ["OKX_API_KEY", "OKX_SECRET_KEY", "OKX_PASSWORD"]
    missing_vars = []
    
    for var in required_env_vars:
        value = os.getenv(var)
        if not value:
            missing_vars.append(var)
        else:
            # 记录已设置的变量（隐藏敏感信息）
            masked_value = value[:4] + '*' * (len(value) - 8) + value[-4:] if len(value) > 8 else '***'
            logging.info(f"✅ {var}: 已设置 ({masked_value})")
    
    if missing_vars:
        logging.error(f"缺少环境变量: {missing_vars}")
        return False
    
    logging.info("环境变量检查通过")
    return True

# API密钥配置
OKX_API_KEY = os.getenv("OKX_API_KEY")
OKX_SECRET_KEY = os.getenv("OKX_SECRET_KEY")
OKX_PASSWORD = os.getenv("OKX_PASSWORD")
CRYPTOPANIC_API = os.getenv("CRYPTOPANIC_API")

# 交易标志
FLAG = "0"