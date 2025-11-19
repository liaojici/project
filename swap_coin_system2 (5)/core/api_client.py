import time
import logging
from okx import Account, MarketData, Trade, PublicData, TradingData
from config.settings import OKX_API_KEY, OKX_SECRET_KEY, OKX_PASSWORD, FLAG
# 在 api_client.py 和 state_manager.py 的顶部添加导入
from utils.common_utils import safe_float_convert, format_currency
# 全局API对象
account_api = None
market_api = None
trade_api = None
public_data_api = None
trading_data_api = None



def get_account_balance_with_retry(max_retries=3, delay=2):
    """带重试机制的账户余额获取"""
    for attempt in range(max_retries):
        try:
            if account_api is None:
                logging.error("账户API未初始化")
                return 0.0
                
            # 记录API调用
            from utils.performance_monitor import performance_monitor
            performance_monitor.record_api_call("account")
            
            # 获取账户余额，指定USDT币种
            response = account_api.get_account_balance(ccy="USDT")
            
            if not response:
                logging.error("获取账户余额无响应")
                continue
                
            if response.get("code") != "0":
                error_msg = response.get("msg", "未知错误")
                logging.error(f"获取USDT余额信息失败: {error_msg}")
                
                # 如果是限流错误，等待后重试
                if "Too Many Requests" in error_msg and attempt < max_retries - 1:
                    wait_time = delay * (attempt + 1)
                    logging.warning(f"API限流，等待{wait_time}秒后重试 ({attempt + 1}/{max_retries})")
                    time.sleep(wait_time)
                    continue
                return 0.0
                
            if "data" not in response or len(response["data"]) == 0:
                logging.error("账户余额数据为空")
                return 0.0
                
            data = response["data"][0]
            
            # 根据官方文档，优先使用 totalEq（美金层面权益）
            total_equity = 0.0
            if "totalEq" in data and data["totalEq"]:
                total_equity = safe_float_convert(data["totalEq"])
                logging.info(f"获取到总权益 (totalEq): {total_equity:.2f} USDT")
            else:
                # 如果没有totalEq，尝试从details中获取USDT余额
                if "details" in data and data["details"]:
                    for detail in data["details"]:
                        if detail.get("ccy") == "USDT":
                            # 使用 availBal（可用余额）作为可交易金额
                            total_equity = safe_float_convert(detail.get("availBal", 0))
                            logging.info(f"从details获取USDT余额: {total_equity:.2f} USDT")
                            break
            
            from core.state_manager import strategy_state
            if strategy_state["initial_balance"] is None:
                strategy_state["initial_balance"] = total_equity
            strategy_state["last_balance"] = total_equity
            
            return total_equity
            
        except Exception as e:
            logging.error(f"获取账户余额失败 (尝试 {attempt + 1}/{max_retries}): {e}")
            if attempt < max_retries - 1:
                time.sleep(delay * (attempt + 1))
    
    return 0.0

def get_account_balance():
    """获取账户余额 - 使用重试机制"""
    return get_account_balance_with_retry(max_retries=3, delay=2)

# 添加获取未成交订单的函数
def get_pending_orders(instType="SWAP"):
    """获取未成交订单列表"""
    try:
        if trade_api is None:
            logging.error("交易API未初始化")
            return None
            
        # 记录API调用
        from utils.performance_monitor import performance_monitor
        performance_monitor.record_api_call("trade")
        
        response = trade_api.get_order_list(instType=instType)
        if response and response.get("code") == "0":
            return response.get("data", [])
        else:
            error_msg = response.get("msg", "未知错误") if response else "无响应"
            logging.error(f"获取未成交订单失败: {error_msg}")
            return None
    except Exception as e:
        logging.error(f"获取未成交订单异常: {e}")
        return None

def get_pending_orders_margin():
    """获取未成交订单占用的保证金"""
    try:
        orders = get_pending_orders(instType="SWAP")
        if not orders:
            return 0.0
            
        pending_margin = 0.0
        for order in orders:
            if order.get("state") in ["live", "partially_filled"]:
                # 计算订单占用的保证金
                sz = safe_float_convert(order.get("sz", 0))
                px = safe_float_convert(order.get("px", 0))
                lever = safe_float_convert(order.get("lever", 1))
                
                if sz > 0 and px > 0 and lever > 0:
                    order_margin = (sz * px) / lever
                    pending_margin += order_margin
        
        return pending_margin
        
    except Exception as e:
        logging.error(f"获取未成交订单保证金失败: {e}")
        return 0.0

# api_client.py 中添加以下函数

def get_instruments_info(instType="SWAP"):
    """获取交易产品基础信息"""
    try:
        if account_api is None:
            logging.error("账户API未初始化")
            return None
            
        # 记录API调用
        from utils.performance_monitor import performance_monitor
        performance_monitor.record_api_call("account")
        
        response = account_api.get_instruments(instType=instType)
        
        if response and response.get("code") == "0" and response.get("data"):
            instruments = {}
            for item in response["data"]:
                inst_id = item.get("instId")
                if inst_id:
                    instruments[inst_id] = {
                        "instId": inst_id,
                        "instType": item.get("instType"),
                        "baseCcy": item.get("baseCcy"),
                        "quoteCcy": item.get("quoteCcy"),
                        "settleCcy": item.get("settleCcy"),
                        "ctVal": item.get("ctVal"),  # 合约面值
                        "ctValCcy": item.get("ctValCcy"),  # 合约面值计价币种
                        "ctType": item.get("ctType"),  # 合约类型
                        "lever": item.get("lever"),  # 最大杠杆倍数
                        "lotSz": item.get("lotSz"),  # 下单数量精度
                        "minSz": item.get("minSz"),  # 最小下单数量
                        "tickSz": item.get("tickSz"),  # 下单价格精度
                        "state": item.get("state"),  # 产品状态
                        "maxLmtSz": item.get("maxLmtSz"),  # 限价单最大委托数量
                        "maxMktSz": item.get("maxMktSz"),  # 市价单最大委托数量
                    }
            logging.info(f"成功获取 {len(instruments)} 个{instType}产品信息")
            return instruments
        else:
            error_msg = response.get("msg", "未知错误") if response else "无响应"
            logging.error(f"获取交易产品信息失败: {error_msg}")
            return None
            
    except Exception as e:
        logging.error(f"获取交易产品信息异常: {e}")
        return None

def get_swap_instruments():
    """获取永续合约产品信息"""
    return get_instruments_info("SWAP")



# 在 api_client.py 的 initialize_okx_api 函数中添加调试
def initialize_okx_api():
    global account_api, market_api, trade_api, public_data_api, trading_data_api
    
    try:
        logging.info("开始初始化OKX API...")
        
        # 需要API密钥的API
        account_api = Account.AccountAPI(OKX_API_KEY, OKX_SECRET_KEY, OKX_PASSWORD, False, FLAG)
        logging.info("✅ 账户API初始化成功")
        
        trade_api = Trade.TradeAPI(OKX_API_KEY, OKX_SECRET_KEY, OKX_PASSWORD, False, FLAG)
        logging.info("✅ 交易API初始化成功")
        
        # 不需要API密钥的公共API
        market_api = MarketData.MarketAPI(flag=FLAG)
        logging.info("✅ 市场API初始化成功")
        
        public_data_api = PublicData.PublicAPI(flag=FLAG)
        logging.info("✅ 公共数据API初始化成功")
        
        trading_data_api = TradingData.TradingDataAPI(flag=FLAG)
        logging.info("✅ 交易数据API初始化成功")

        # 调试信息：检查各API是否真的初始化成功
        logging.debug(f"账户API类型: {type(account_api)}")
        logging.debug(f"交易API类型: {type(trade_api)}")
        logging.debug(f"市场API类型: {type(market_api)}")
        logging.debug(f"公共数据API类型: {type(public_data_api)}")
        logging.debug(f"交易数据API类型: {type(trading_data_api)}")
        
        # 添加更详细的调试信息
        logging.info(f"交易API实例: {trade_api}")
        logging.info(f"交易API模块: {Trade}")
        
        logging.info("所有OKX API初始化成功")
        return True
    except Exception as e:
        logging.error(f"OKX API初始化失败: {e}")
        import traceback
        logging.error(traceback.format_exc())
        return False

def test_market_api():
    """测试市场API功能"""
    if market_api is None:
        logging.error("市场API未初始化")
        return False
    
    try:
        # 使用正确的方法名 get_candlesticks
        result = market_api.get_candlesticks(instId="BTC-USDT", bar="1H", limit="5")
        if result and result.get("code") == "0":
            data = result.get("data", [])
            logging.info(f"✅ 市场API测试成功 - 获取了 {len(data)} 条K线数据")
            return True
        else:
            error_msg = result.get("msg", "未知错误") if result else "无响应"
            logging.error(f"❌ 市场API测试失败: {error_msg}")
            return False
    except Exception as e:
        logging.error(f"❌ 市场API测试异常: {e}")
        return False

# 导出所有API实例
__all__ = [
    'account_api', 'market_api', 'trade_api', 
    'public_data_api', 'trading_data_api',
    'initialize_okx_api', 'get_account_balance', 'get_pending_orders'
]