import os
import sys
import logging
import time
import requests
import threading

# 设置项目根目录
PROJECT_ROOT = '/www/python/swap_coin_system2'
sys.path.insert(0, PROJECT_ROOT)
os.chdir(PROJECT_ROOT)

# 导入模块而不是变量，确保获取最新状态
import core.api_client
from config.settings import initialize_environment

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def test_connection():
    print("🔄 开始网络连接测试...")
    initialize_environment()
    
    # 初始化 API
    if not core.api_client.initialize_okx_api():
        print("❌ API初始化失败")
        return

    symbols = ["BTC-USDT-SWAP", "ETH-USDT-SWAP", "TRX-USDT-SWAP"]
    
    for symbol in symbols:
        print(f"\n🔍 测试获取 {symbol} K线数据...")
        try:
            start_time = time.time()
            
            # 关键修正：使用 core.api_client.market_api 访问
            api = core.api_client.market_api
            
            if api is None:
                print("   ❌ Market API 对象仍为 None")
                continue

            # 尝试获取数据
            result = api.get_candlesticks(instId=symbol, bar="1H", limit="5")
            duration = time.time() - start_time
            
            if result and result.get("code") == "0":
                data_len = len(result.get("data", []))
                print(f"   ✅ 成功! 获取到 {data_len} 条数据, 耗时: {duration:.2f}秒")
                if data_len > 0:
                    print(f"   最新价格: {result['data'][0][4]}") # 打印收盘价
            else:
                msg = result.get("msg", "未知错误") if result else "无响应"
                print(f"   ❌ 失败: {msg}")
                
        except requests.exceptions.SSLError as e:
            print(f"   ❌ SSL错误: {e}")
        except Exception as e:
            print(f"   ❌ 其他异常: {e}")
            import traceback
            traceback.print_exc()
            
    print("\n测试完成。")

if __name__ == "__main__":
    test_connection()