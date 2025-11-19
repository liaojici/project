# test_simple_order.py
import os
import sys
import logging
import time

# 设置项目根目录
PROJECT_ROOT = '/www/python/swap_coin_system'
sys.path.insert(0, PROJECT_ROOT)
os.chdir(PROJECT_ROOT)

from core.api_client import initialize_okx_api
from config.settings import initialize_environment
from utils.instrument_utils import adjust_price_precision, get_tick_size, get_min_contract_size



def check_account_balance():
    """检查账户余额"""
    try:
        from core.api_client import account_api
        response = account_api.get_account_balance(ccy="USDT")
        if response and response.get("code") == "0" and response.get("data"):
            data = response["data"][0]
            if "details" in data and data["details"]:
                for detail in data["details"]:
                    if detail.get("ccy") == "USDT":
                        available_balance = float(detail.get("availBal", 0))
                        total_balance = float(detail.get("bal", 0))
                        logging.info(f"账户余额 - 可用: {available_balance:.2f} USDT, 总额: {total_balance:.2f} USDT")
                        return available_balance
        return 0
    except Exception as e:
        logging.error(f"检查账户余额失败: {e}")
        return 0
# 在 test_simple_order 函数开头添加
def test_simple_order():
    setup_logging()
    
    # 检查账户余额
    balance = check_account_balance()
    if balance < 10:  # 如果余额小于10 USDT
        logging.warning(f"⚠️ 账户余额较低: {balance:.2f} USDT，可能影响测试")
    
    # 其余代码保持不变...


def setup_logging():
    """设置日志"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )

def get_trade_api():
    """安全获取交易API"""
    try:
        from core.api_client import trade_api
        if trade_api is None:
            logging.error("交易API为None，尝试重新初始化...")
            if initialize_okx_api():
                from core.api_client import trade_api as new_trade_api
                return new_trade_api
            return None
        return trade_api
    except Exception as e:
        logging.error(f"获取交易API失败: {e}")
        return None

def get_realtime_price(symbol):
    """获取实时价格"""
    try:
        from core.api_client import market_api
        result = market_api.get_ticker(instId=symbol)
        if result and result.get("code") == "0" and result.get("data"):
            data = result["data"][0]
            return float(data.get("last", 0))
        return None
    except Exception as e:
        logging.error(f"获取{symbol}实时价格失败: {e}")
        return None

def test_simple_order():
    """简易下单测试 - 使用市价单和正确的最小张数"""
    setup_logging()
    
    # 初始化环境
    if not initialize_environment():
        logging.error("环境初始化失败")
        return False
        
    # 初始化API
    if not initialize_okx_api():
        logging.error("API初始化失败")
        return False
    
    # 获取交易API
    trade_api = get_trade_api()
    if trade_api is None:
        logging.error("交易API获取失败")
        return False
        
    logging.info(f"交易API类型: {type(trade_api)}")
    
    # 测试交易对
    test_symbols = [
        "TRX-USDT-SWAP",
        "XRP-USDT-SWAP", 
        "SOL-USDT-SWAP"
    ]
    
    for symbol in test_symbols:
        try:
            logging.info(f"测试 {symbol}...")
            
            # 获取最小张数
            min_quantity = get_min_contract_size(symbol)
            logging.info(f"{symbol} 最小张数: {min_quantity}")
            
            # 获取实时价格
            current_price = get_realtime_price(symbol)
            if not current_price or current_price <= 0:
                logging.error(f"❌ 无法获取{symbol}的实时价格")
                continue
                
            logging.info(f"{symbol} 当前价格: {current_price}")
            
            # 尝试设置杠杆
            from modules.trading_execution import set_leverage_for_instrument
            if set_leverage_for_instrument(symbol, 2, "cross"):
                logging.info(f"✅ {symbol} 杠杆设置成功")
            else:
                logging.error(f"❌ {symbol} 杠杆设置失败")
                continue
            
            # 方法1：尝试市价单（更容易成功）
            logging.info("--- 测试市价单 ---")
            order_data_market = {
                "instId": symbol,
                "tdMode": "cross",
                "side": "buy",
                "posSide": "long",
                "ordType": "market",  # 市价单
                "sz": str(min_quantity)
            }
            
            logging.info(f"尝试市价单: {order_data_market}")
            
            result_market = trade_api.place_order(**order_data_market)
            
            if result_market and result_market.get("code") == "0":
                order_id = result_market["data"][0]["ordId"]
                logging.info(f"✅ {symbol} 市价单成功! 订单ID: {order_id}")
                
                # 等待订单成交
                time.sleep(2)
                
                # 立即平仓（市价单）
                close_order_data = {
                    "instId": symbol,
                    "tdMode": "cross",
                    "side": "sell",
                    "posSide": "long",
                    "ordType": "market",
                    "sz": str(min_quantity)
                }
                
                close_result = trade_api.place_order(**close_order_data)
                if close_result and close_result.get("code") == "0":
                    logging.info(f"✅ {symbol} 平仓成功")
                else:
                    logging.warning(f"⚠️ {symbol} 平仓失败")
                    
            else:
                error_msg = result_market.get("msg", "未知错误") if result_market else "无响应"
                error_code = result_market.get("code", "无错误码") if result_market else "无错误码"
                logging.error(f"❌ {symbol} 市价单失败: {error_code} - {error_msg}")
                
                # 方法2：尝试更接近当前价格的限价单
                logging.info("--- 测试限价单（接近市价）---")
                # 使用比当前价格高一点的价格（对于买单）
                limit_price = current_price * 1.001  # 提高0.1%
                adjusted_price = adjust_price_precision(symbol, limit_price)
                
                order_data_limit = {
                    "instId": symbol,
                    "tdMode": "cross",
                    "side": "buy",
                    "posSide": "long",
                    "ordType": "limit",
                    "px": str(adjusted_price),
                    "sz": str(min_quantity)
                }
                
                logging.info(f"尝试限价单: {order_data_limit}")
                
                result_limit = trade_api.place_order(**order_data_limit)
                
                if result_limit and result_limit.get("code") == "0":
                    order_id = result_limit["data"][0]["ordId"]
                    logging.info(f"✅ {symbol} 限价单成功! 订单ID: {order_id}")
                    
                    # 立即撤销订单
                    time.sleep(1)
                    cancel_result = trade_api.cancel_order(instId=symbol, ordId=order_id)
                    if cancel_result and cancel_result.get("code") == "0":
                        logging.info(f"✅ {symbol} 订单撤销成功")
                    else:
                        logging.warning(f"⚠️ {symbol} 订单撤销失败")
                        
                else:
                    error_msg = result_limit.get("msg", "未知错误") if result_limit else "无响应"
                    error_code = result_limit.get("code", "无错误码") if result_limit else "无错误码"
                    logging.error(f"❌ {symbol} 限价单失败: {error_code} - {error_msg}")
                    
                    # 记录详细的错误信息
                    from utils.error_handlers import log_trade_error_details
                    log_trade_error_details(error_code, error_msg, symbol, order_data_limit)
                
        except Exception as e:
            logging.error(f"❌ {symbol} 测试异常: {str(e)}")
            import traceback
            logging.error(traceback.format_exc())
            
    return True

if __name__ == "__main__":
    test_simple_order()