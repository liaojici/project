# trading_execution.py - 修正导入部分
import time
import logging
from datetime import datetime, timedelta
from core.api_client import trade_api, account_api
from core.state_manager import (
    strategy_state, 
    check_account_drawdown, 
    recalculate_asset_allocation, 
    get_tradable_balance
)
from modules.chain_analysis import get_chain_signals
from modules.sentiment_analysis import get_sentiment_signals
from modules.technical_analysis import get_technical_signals
from modules.position_management import calculate_position_size, can_open_new_position,get_coin_total_position_value
from modules.funding_rate_analysis import funding_analyzer
from modules.advanced_market_analysis import advanced_market_analyzer
from utils.decorators import safe_request
from utils.performance_monitor import performance_monitor as perf_monitor
import pandas as pd
# 修正导入，确保所有函数都存在
from utils.instrument_utils import (
    adjust_quantity_precision, 
    adjust_price_precision,  # 现在这个函数存在了
    validate_order_parameters,get_min_contract_size,get_lot_size
)

# 在导入部分添加
from modules.position_management import (
    calculate_position_size, can_open_new_position, 
    get_contract_value, adjust_position_to_lot_size,get_total_equity # 新增
)
# 杠杆管理字典
leverage_settings = {}

# 在 trading_execution.py 的导入部分更新为：
from config.constants import (
    TAKE_PROFIT1, TAKE_PROFIT2, TAKE_PROFIT3,
    STOP_LOSS_MOVE, ROLL_PROFIT_THRESHOLD, ROLL_USE_PROFIT_RATIO,
    STOP_LOSS_INIT, RSI_OVERSOLD, RISK_PARAMS,
    SWAP_STOP_LOSS, RSI_OVERBOUGHT,
    ROLL_SIGNAL_THRESHOLD, MAX_ROLL_TIMES,
    SMART_TAKE_PROFIT, FLOAT_LOSS_ADD, SUPPORT_RESISTANCE
)
from config.constants import ENTRY_STRATEGY
from utils.common_utils import (
    safe_float_convert, 
    timing_decorator, 
    format_currency,
    normalize_signal,
    calculate_volatility,
    
)
pending_orders = {}  # 存储待处理订单

# 在 monitor_pending_orders 函数开头添加
from config.constants import PENDING_ORDER_CONFIG




def monitor_pending_orders():
    """监测委托单状态 - 使用配置参数"""
    global pending_orders
    current_time = time.time()
    
    # 使用配置参数
    max_wait_time = PENDING_ORDER_CONFIG["max_wait_time"]
    price_deviation_threshold = PENDING_ORDER_CONFIG["price_deviation_threshold"]
    
    orders_to_remove = []
    
    for order_id, order_info in pending_orders.items():
        symbol = order_info['symbol']
        order_place_time = order_info['time']
        target_price = order_info['target_price']
        direction = order_info['direction']
        
        # 检查订单是否已超过最大等待时间
        if current_time - order_place_time > max_wait_time:
            logging.info(f"⏰ {symbol} 委托单超过{max_wait_time/3600:.0f}小时未成交，取消订单")
            cancel_order(order_id)
            orders_to_remove.append(order_id)
            continue
        
        # 每4小时检查价格是否靠近目标价格
        if (current_time - order_place_time) % (4 * 3600) < 60:
            current_price = get_realtime_price(symbol)
            if current_price:
                price_diff_ratio = abs(current_price - target_price) / target_price
                
                if direction == "long":
                    # 多单：当前价格低于目标价格且偏离超过阈值，取消订单
                    if current_price < target_price and price_diff_ratio > price_deviation_threshold:
                        logging.info(f"📉 {symbol} 多单价格偏离超过{price_deviation_threshold*100:.0f}%，取消订单")
                        cancel_order(order_id)
                        orders_to_remove.append(order_id)
                else:
                    # 空单：当前价格高于目标价格且偏离超过阈值，取消订单
                    if current_price > target_price and price_diff_ratio > price_deviation_threshold:
                        logging.info(f"📈 {symbol} 空单价格偏离超过{price_deviation_threshold*100:.0f}%，取消订单")
                        cancel_order(order_id)
                        orders_to_remove.append(order_id)
    
    # 移除已处理的订单
    for order_id in orders_to_remove:
        if order_id in pending_orders:
            del pending_orders[order_id]

def cancel_order(order_id):
    """取消订单"""
    try:
        from core.api_client import trade_api
        if trade_api is None:
            return False
            
        result = trade_api.cancel_order(ordId=order_id)
        if result and result.get("code") == "0":
            logging.info(f"✅ 成功取消订单: {order_id}")
            return True
        else:
            logging.error(f"❌ 取消订单失败: {order_id}")
            return False
    except Exception as e:
        logging.error(f"取消订单异常: {e}")
        return False

def get_order_info(order_id):
    """获取订单信息"""
    try:
        from core.api_client import trade_api
        if trade_api is None:
            return None
            
        result = trade_api.get_order(ordId=order_id)
        if result and result.get("code") == "0" and result.get("data"):
            return result["data"][0]
        return None
    except Exception as e:
        logging.error(f"获取订单信息失败: {e}")
        return None





def check_api_status():
    """检查API状态"""
    try:
        from core.api_client import account_api, trade_api
        return account_api is not None and trade_api is not None
    except Exception as e:
        logging.error(f"检查API状态失败: {e}")
        return False

def initialize_trading_system():
    """初始化交易系统 - 修复版本，支持已有仓位的情况"""
    try:
        # 先检查账户API
        if not check_account_api():
            logging.error("❌ 交易系统初始化失败：账户API未就绪")
            return False
            
        # 初始化交易模式（即使失败也继续）
        trading_mode_ok = initialize_trading_mode()
        
        if trading_mode_ok:
            logging.info("✅ 交易系统初始化完成")
        else:
            logging.warning("⚠️ 交易模式初始化有警告，但程序将继续运行以接管现有仓位")
            
        return True  # 总是返回True，让程序继续运行
        
    except Exception as e:
        logging.error(f"❌ 交易系统初始化失败: {e}")
        # 即使在异常情况下，也返回True让程序继续运行
        return True


def check_account_api():
    """检查账户API是否已初始化"""
    global account_api
    if account_api is None:
        try:
            from core.api_client import initialize_okx_api, account_api as acc_api
            if initialize_okx_api():
                account_api = acc_api
                logging.info("✅ 账户API重新初始化成功")
                return True
            else:
                logging.error("❌ 账户API初始化失败")
                return False
        except Exception as e:
            logging.error(f"❌ 账户API检查失败: {e}")
            return False
    return True


def get_leverage_status():
    """获取当前杠杆设置状态"""
    global leverage_settings
    status = {}
    for symbol, settings in leverage_settings.items():
        status[symbol] = {
            'leverage': settings['leverage'],
            'mode': settings['mode'],
            'last_set': settings['last_set']
        }
    return status

def cleanup_old_leverage_settings(hours=24):
    """清理过时的杠杆设置记录"""
    global leverage_settings
    cutoff_time = datetime.now() - timedelta(hours=hours)
    removed = []
    for symbol in list(leverage_settings.keys()):
        if leverage_settings[symbol]['last_set'] < cutoff_time:
            removed.append(symbol)
            del leverage_settings[symbol]
    
    if removed:
        logging.info(f"🧹 清理过时杠杆设置: {removed}")



def get_trade_api():
    """获取交易API"""
    try:
        from core.api_client import trade_api
        return trade_api
    except Exception as e:
        logging.error(f"获取交易API失败: {e}")
        return None

def initialize_trading_mode():
    """初始化交易模式为全仓 - 修复版本，支持已有仓位的情况"""
    try:
        # 先检查账户API
        if not check_account_api():
            logging.error("❌ 无法初始化交易模式：账户API未就绪")
            return False
            
        # 首先检查当前持仓模式
        try:
            from core.api_client import account_api
            # 获取账户配置信息
            result = account_api.get_account_config()
            if result and result.get('code') == "0" and result.get("data"):
                current_mode = result["data"][0].get("posMode", "")
                if current_mode == "long_short_mode":
                    logging.info("✅ 当前持仓模式已经是: long_short_mode (开平仓模式)")
                    return True
                else:
                    logging.info(f"当前持仓模式: {current_mode}, 需要设置为: long_short_mode")
        except Exception as e:
            logging.debug(f"获取当前持仓模式失败: {e}")
        
        # 尝试设置持仓模式
        result = account_api.set_position_mode(posMode="long_short_mode")
        if result and result.get('code') == "0":
            logging.info("✅ 持仓模式设置为: long_short_mode (开平仓模式)")
            return True
        else:
            error_msg = result.get("msg", "未知错误") if result else "无响应"
            
            # 处理有持仓时无法设置模式的情况
            if "Cancel any open orders" in error_msg or "close positions" in error_msg:
                logging.warning("⚠️ 检测到当前有持仓或未成交订单，无法更改持仓模式")
                logging.warning("⚠️ 策略将继续运行，但请确保当前持仓模式为 long_short_mode")
                
                # 在有持仓的情况下，我们假设模式已经是正确的，继续运行
                # 记录警告但返回True让程序继续
                return True
            else:
                logging.warning(f"⚠️ 持仓模式设置失败: {error_msg}")
                return False
    except Exception as e:
        logging.warning(f"⚠️ 持仓模式设置异常: {str(e)}")
        
        # 在异常情况下，我们也返回True让程序继续运行
        # 这样即使设置模式失败，程序也能接管现有仓位
        return True

def execute_open_position(symbol, direction, size, price, signal_strength, base_leverage=3.0):
    """执行开仓操作 - 添加张数验证"""
    try:
        coin = symbol.split("-")[0]
        
        # 先调整价格精度和张数精度
        adjusted_price = adjust_price_precision(symbol, price)
        adjusted_size = adjust_quantity_precision(symbol, size)
        
        # 验证调整后的张数是否有效
        if adjusted_size <= 0:
            logging.error(f"❌ {symbol} 调整后张数无效: {adjusted_size}")
            return False
            
        # 验证张数是否符合最小要求
        min_sz = get_min_contract_size(symbol)
        if adjusted_size < min_sz:
            logging.error(f"❌ {symbol} 调整后张数{adjusted_size}小于最小要求{min_sz}")
            return False
        
        # 记录详细的价格信息
        current_price = get_realtime_price(symbol)
        logging.info(f"开仓价格详情 - {symbol}:")
        logging.info(f"  当前市场价格: {current_price:.6f}")
        logging.info(f"  计算入场价格: {price:.6f}")
        logging.info(f"  精度调整后价格: {adjusted_price:.6f}")
        logging.info(f"  交易方向: {direction}")
        logging.info(f"  原始张数: {size}")
        logging.info(f"  调整后张数: {adjusted_size}")
        logging.info(f"  最小张数要求: {min_sz}")
        
    
        # 检查价格合理性
        if adjusted_price <= 0:
            logging.error(f"❌ {symbol} 调整后价格异常: {adjusted_price}")
            return False
            
        if adjusted_size <= 0:
            logging.error(f"❌ {symbol} 调整后张数异常: {adjusted_size}")
            return False
            
        # 验证价格是否在合理范围内
        if current_price:
            price_diff_ratio = abs(adjusted_price - current_price) / current_price
            if price_diff_ratio > 0.05:  # 如果价格偏离超过5%
                logging.warning(f"⚠️ {symbol} 价格偏离较大: {adjusted_price:.6f} vs 市价 {current_price:.6f} (偏离 {price_diff_ratio*100:.1f}%)")
        
        # 其余代码保持不变，但确保使用调整后的值
        logging.info(f"🔍 开仓调试信息:")
        logging.info(f"  - 交易对: {symbol}")
        logging.info(f"  - 方向: {direction}")
        logging.info(f"  - 张数: {adjusted_size}")  # 使用调整后的张数
        logging.info(f"  - 价格: {adjusted_price:.6f}")  # 使用调整后的价格
        logging.info(f"  - 信号强度: {signal_strength:.3f}")
        
        # 计算动态杠杆
        dynamic_leverage = calculate_dynamic_leverage(signal_strength, base_leverage)
        logging.info(f"  - 杠杆: {dynamic_leverage}x")
        
        logging.info(f"🚀 {symbol} 执行开仓 - 方向: {direction}, 张数: {adjusted_size}, 价格: {adjusted_price:.6f}, 杠杆: {dynamic_leverage}x")
        
        # 设置方向映射
        side_map = {'long': 'buy', 'short': 'sell'}
        pos_side_map = {'long': 'long', 'short': 'short'}
        
        side = side_map[direction]
        posSide = pos_side_map[direction]
        
        # 创建订单 - 使用调整后的值
        order = execute_trade(
            symbol=symbol,
            side=side,
            quantity=adjusted_size,  # 使用调整后的张数
            price=adjusted_price,    # 使用调整后的价格
            leverage=dynamic_leverage,
            posSide=posSide,
            tdMode="cross"
        )
        
        
        
        if order and order.get("code") == "0":
            # 获取合约面值
            from modules.position_management import get_contract_value
            contract_value = get_contract_value(symbol)
            
            # 设置止损价格
            if direction == "long":
                initial_stop = price * (1 - STOP_LOSS_INIT)
                take_profit_1 = price * (1 + TAKE_PROFIT1)
                take_profit_2 = price * (1 + TAKE_PROFIT2)
                take_profit_3 = price * (1 + TAKE_PROFIT3)
            else:
                initial_stop = price * (1 + STOP_LOSS_INIT)
                take_profit_1 = price * (1 - TAKE_PROFIT1)
                take_profit_2 = price * (1 - TAKE_PROFIT2)
                take_profit_3 = price * (1 - TAKE_PROFIT3)
            
            if "positions" not in strategy_state:
                strategy_state["positions"] = {}
            
            # 计算名义价值和保证金
            notional_value = size * contract_value * price
            margin_used = notional_value / dynamic_leverage
            
            # 确保正确设置coin字段
            strategy_state["positions"][symbol] = {
                "open_price": price,
                "size": size,
                "contract_size": size,
                "contract_value": contract_value,
                "notional_value": notional_value,
                "leverage": dynamic_leverage,
                "margin": margin_used,
                "entry_time": time.time(),
                "side": direction,
                "remaining": 1.0,
                "initial_stop": initial_stop,
                "current_stop": initial_stop,
                "take_profit_1": take_profit_1,
                "take_profit_2": take_profit_2,
                "take_profit_3": take_profit_3,
                "rollover_count": 0,
                "signal_strength": signal_strength,
                "coin": coin,  # 确保正确设置coin字段
                "margin_mode": "cross"
            }
            logging.info(f"✅ {symbol} 开仓成功 - 方向: {direction}, 价格: {price:.6f}, "
                        f"张数: {size}, 名义价值: {notional_value:.2f} USDT, 杠杆: {dynamic_leverage}x")
            
            recalculate_asset_allocation()
            return True
        else:
            logging.error(f"❌ {symbol} 开仓失败")
            return False
            
    except Exception as e:
        logging.error(f"❌ {symbol} 开仓异常: {str(e)}")
        import traceback
        logging.error(traceback.format_exc())
        return False
    
def test_single_order(symbol="TRX-USDT-SWAP", side="buy", quantity=10, price=0.3, leverage=2):
    """测试单个订单"""
    logging.info(f"🧪 测试订单: {symbol} {side} {quantity} @ {price}")
    
    order = execute_trade(
        symbol=symbol,
        side=side,
        quantity=quantity,
        price=price,
        leverage=leverage,
        posSide="long",
        tdMode="cross"
    )
    
    if order and order.get("code") == "0":
        logging.info("✅ 测试订单成功")
        return True
    else:
        logging.error("❌ 测试订单失败")
        return False


@safe_request
def set_leverage_for_instrument(instId, leverage, mgnMode="cross"):
    """为交易品种设置杠杆 - 修复版本"""
    global leverage_settings
    
    try:
        # 检查 account_api 是否已初始化
        if account_api is None:
            logging.error("❌ 账户API未初始化，无法设置杠杆")
            return False
            
        # 将杠杆转换为整数
        leverage_int = int(round(leverage))
        # 确保杠杆在合理范围内
        leverage_int = max(1, min(leverage_int, 5))  # 1-5倍杠杆
        
        # 检查是否已经设置过相同的杠杆，避免重复设置
        if (instId in leverage_settings and 
            leverage_settings[instId]['leverage'] == leverage_int and
            leverage_settings[instId]['mode'] == mgnMode):
            return True
            
        result = account_api.set_leverage(
            instId=instId,
            lever=str(leverage_int),  # 确保是字符串
            mgnMode=mgnMode  # cross: 全仓模式
        )
        
        if result and result.get("code") == "0":
            leverage_settings[instId] = {
                'leverage': leverage_int,
                'mode': mgnMode,
                'last_set': datetime.now()
            }
            logging.info(f"✅ {instId} 杠杆设置成功: {leverage_int}x ({mgnMode})")
            return True
        else:
            error_msg = result.get("msg", "未知错误") if result else "无响应"
            logging.error(f"❌ {instId} 杠杆设置失败: {error_msg}")
            return False
    except Exception as e:
        logging.error(f"❌ {instId} 杠杆设置异常: {str(e)}")
        return False

def calculate_dynamic_leverage(signal_strength, base_leverage=3.0, max_leverage=5.0):
    """根据信号强度动态计算杠杆倍数 - 优化版本"""
    if signal_strength >= 0.8:
        leverage = min(base_leverage * 1.5, max_leverage)
    elif signal_strength >= 0.6:
        leverage = base_leverage
    elif signal_strength >= 0.4:
        leverage = max(base_leverage * 0.7, 1.5)
    else:
        leverage = 1.0
    
    return int(round(leverage))


@safe_request
def get_realtime_price(symbol):
    """获取实时最新价格"""
    try:
        from core.api_client import market_api
        if market_api is None:
            return None
            
        perf_monitor.record_api_call("market_data")
        
        result = market_api.get_ticker(instId=symbol)
        if result and result.get("code") == "0" and result.get("data"):
            data = result["data"][0]
            return float(data.get("last", 0))
        return None
    except Exception as e:
        logging.debug(f"获取{symbol}实时价格失败: {e}")
        return None

@safe_request
def get_depth_based_price(symbol, side="buy"):
    """基于买卖盘深度获取最优价格"""
    try:
        from core.api_client import market_api
        if market_api is None:
            return None
            
        perf_monitor.record_api_call("market_data")
        
        result = market_api.get_orderbook(instId=symbol, sz=5)
        if result and result.get("code") == "0" and result.get("data"):
            data = result["data"][0]
            
            if side == "buy":
                asks = data.get("asks", [])
                if asks and len(asks) > 0:
                    return float(asks[0][0])
            else:
                bids = data.get("bids", [])
                if bids and len(bids) > 0:
                    return float(bids[0][0])
                
        return None
    except Exception as e:
        return None

# 在 get_optimal_entry_price 函数开头添加
from config.constants import ENTRY_STRATEGY

def get_optimal_entry_price(symbol, current_price, signal_strength, direction, df):
    """获取最优入场价格 - 使用配置参数"""
    try:
        from modules.enhanced_strategy import enhanced_strategy
        
        # 使用配置参数
        strong_signal_threshold = ENTRY_STRATEGY["strong_signal_threshold"]
        min_signal_threshold = ENTRY_STRATEGY["min_signal_threshold"]
        support_strength_threshold = ENTRY_STRATEGY["support_strength_threshold"]
        resistance_strength_threshold = ENTRY_STRATEGY["resistance_strength_threshold"]
        
        # 获取支撑阻力位
        support_strength, support_price, resistance_strength, resistance_price = enhanced_strategy.calculate_enhanced_support_resistance(df, symbol)
        
        # 记录支撑阻力位信息
        logging.info(f"📊 {symbol} 支撑阻力分析:")
        logging.info(f"   支撑位: {support_price:.6f} (强度: {support_strength:.3f})")
        logging.info(f"   阻力位: {resistance_price:.6f} (强度: {resistance_strength:.3f})")
        logging.info(f"   当前价格: {current_price:.6f}, 信号强度: {signal_strength:.3f}, 方向: {direction}")
        
        # 信号很强时，原价买入
        if signal_strength > strong_signal_threshold:
            logging.info(f"🎯 {symbol} 信号很强，使用当前价格入场")
            return current_price
        
        # 信号达到阈值但不够强时，根据支撑阻力位下单
        if signal_strength > min_signal_threshold:
            if direction == "long":
                # 多单逻辑
                if support_price > 0 and support_strength > support_strength_threshold:
                    # 使用支撑位价格，稍微上浮一点确保成交
                    entry_price = support_price * 1.001
                    logging.info(f"🛡️ {symbol} 在支撑位附近下多单: {entry_price:.6f}")
                    return entry_price
                else:
                    logging.info(f"⚠️ {symbol} 没有有效支撑位，使用当前价格")
                    return current_price
            else:
                # 空单逻辑
                if resistance_price > 0 and resistance_strength > resistance_strength_threshold:
                    # 使用阻力位价格，稍微下浮一点确保成交
                    entry_price = resistance_price * 0.999
                    logging.info(f"🛡️ {symbol} 在阻力位附近下空单: {entry_price:.6f}")
                    return entry_price
                else:
                    logging.info(f"⚠️ {symbol} 没有有效阻力位，使用当前价格")
                    return current_price
        
        logging.info(f"⏸️ {symbol} 信号强度不足: {signal_strength:.3f}")
        return None
        
    except Exception as e:
        logging.error(f"获取最优入场价格失败 {symbol}: {e}")
        return current_price

@safe_request
def execute_trade(symbol, side, quantity, price, leverage=1, posSide="long", tdMode="cross", max_retries=3):
    """执行交易 - 修复张数格式化问题"""
    for attempt in range(max_retries):
        try:
            trade_api = get_trade_api()
            if trade_api is None:
                logging.error("❌ 交易API未初始化")
                if attempt < max_retries - 1:
                    time.sleep(2 ** attempt)
                    continue
                return None
                
            # 验证订单参数
            if not validate_order_parameters(symbol, side, quantity, price, leverage, posSide, tdMode):
                if attempt < max_retries - 1:
                    time.sleep(1)
                    continue
                return None
                
            # 先设置杠杆
            if not set_leverage_for_instrument(symbol, leverage, tdMode):
                logging.error(f"❌ {symbol} 杠杆设置失败，跳过交易")
                if attempt < max_retries - 1:
                    time.sleep(1)
                    continue
                return None
            
            # 调整价格精度
            adjusted_price = adjust_price_precision(symbol, price)
            
            # 调整张数精度并正确格式化
            adjusted_quantity = adjust_quantity_precision(symbol, quantity)
            
            # 根据lotSize决定如何格式化张数字符串
            lot_size = get_lot_size(symbol)
            if lot_size >= 1:
                # lotSize >= 1时，张数必须是整数
                sz_str = str(int(adjusted_quantity))
            else:
                # lotSize < 1时，张数可以是小数，需要正确格式化
                lot_str = str(lot_size).rstrip('0')
                if '.' in lot_str:
                    decimals = len(lot_str.split('.')[-1])
                    # 格式化到正确的小数位数
                    sz_str = f"{adjusted_quantity:.{decimals}f}"
                else:
                    sz_str = str(int(adjusted_quantity))
            
            # 构建合约订单参数
            order_data = {
                "instId": symbol,
                "tdMode": tdMode,
                "side": side,
                "posSide": posSide,
                "ordType": "limit",
                "px": str(adjusted_price),
                "sz": sz_str  # 使用正确格式化的张数字符串
            }
            
            logging.info(f"📝 创建合约订单 (尝试 {attempt + 1}/{max_retries}): {symbol}")
            logging.info(f"   订单参数: {order_data}")
            logging.info(f"   张数详情: 原始={quantity}, 调整后={adjusted_quantity}, 格式化后={sz_str}, lot_size={lot_size}")
            
            result = trade_api.place_order(**order_data)
            
            if result and result.get("code") == "0":
                order_id = result["data"][0]["ordId"]
                
                # 记录委托单信息
                pending_orders[order_id] = {
                    'symbol': symbol,
                    'side': side,
                    'quantity': quantity,
                    'price': price,
                    'target_price': price,  # 目标价格
                    'direction': posSide,
                    'time': time.time(),
                    'leverage': leverage
                }
                
                logging.info(f"✅ [交易执行成功] {side} {symbol} | 张数: {adjusted_quantity} | 价格: {adjusted_price} | 订单ID: {order_id}")
                perf_monitor.record_trade(symbol, side, adjusted_quantity, adjusted_price)
                return result
            else:
                error_msg = result.get("msg", "未知错误") if result else "无响应"
                error_code = result.get("code", "无错误码") if result else "无错误码"
                
                # 调用详细的错误处理
                from utils.error_handlers import log_trade_error_details
                log_trade_error_details(error_code, error_msg, symbol, order_data)
                
                # 如果是连接问题，等待后重试
                if "Server disconnected" in error_msg or "Connection" in error_msg:
                    if attempt < max_retries - 1:
                        wait_time = 2 ** attempt
                        logging.info(f"⏳ 连接问题，等待{wait_time}秒后重试...")
                        time.sleep(wait_time)
                        continue
                
                return None
                
        except Exception as e:
            logging.error(f"❌ 执行交易异常 (尝试 {attempt + 1}/{max_retries}): {str(e)}")
            if attempt < max_retries - 1:
                wait_time = 2 ** attempt
                time.sleep(wait_time)
                continue
    
    return None


# 在 trading_execution.py 中修改 check_enhanced_multi_signal 函数

# trading_execution.py 中修改 check_enhanced_multi_signal 函数
# 在 trading_execution.py 中修改以下函数
@timing_decorator
def check_enhanced_multi_signal(symbol):
    """增强的多重信号检查 - 确保总是返回4个值"""
    try:
        coin = symbol.split("-")[0]
        
        # 只处理合约交易对
        if "SWAP" not in symbol:
            return False, pd.DataFrame(), 0.0, "neutral"
        
        # 获取基础信号
        chain_ok = get_chain_signals(coin)
        sentiment_ok = get_sentiment_signals(coin)
        technical_ok, df = get_technical_signals(symbol)
        
        # 如果获取数据失败，返回默认值
        if df is None or df.empty:
            return False, pd.DataFrame(), 0.0, "neutral"
            
    except Exception as e:
        logging.debug(f"{symbol} 信号检查异常: {e}")
        return False, pd.DataFrame(), 0.0, "neutral"
    
    # 如果技术信号检查失败，返回默认值
    if df is None:
        return False, pd.DataFrame(), 0.0, "neutral"
    
    try:
        # 获取深度数据用于支撑分析
        depth_data = None
        
        # 资金费率信号
        funding_signal = 0
        funding_confidence = 0
        try:
            funding_signal, funding_confidence = funding_analyzer.analyze_funding_rate_signal(symbol)
        except Exception as e:
            pass
        
        # 市场情绪信号
        sentiment_score = 0
        sentiment_confidence = 0
        try:
            sentiment_score, sentiment_confidence = advanced_market_analyzer.analyze_market_sentiment(symbol)
        except Exception as e:
            pass
        
        # 增强策略信号
        enhanced_score = 0
        support_strength = 0
        resistance_strength = 0
        
        try:
            from modules.enhanced_strategy import enhanced_strategy
            enhanced_score, support_strength, resistance_strength = enhanced_strategy.calculate_enhanced_score(
                df, symbol, depth_data
            )
        except Exception as e:
            pass
        
        # 计算综合信号强度和方向
        latest = df.iloc[-1]
        
        # 技术指标
        macd_bullish = latest.get("macd", 0) > latest.get("macd_signal", -1)
        rsi_oversold = latest.get("rsi", 50) <= RSI_OVERSOLD
        rsi_overbought = latest.get("rsi", 50) >= RSI_OVERBOUGHT
        price_trend = latest["close"] >= df.iloc[-5]["close"]
        
        # 计算做多信号强度
        long_strength = (
            (1 if macd_bullish else 0) * 0.12 +
            (1 if rsi_oversold else 0) * 0.12 +
            (1 if price_trend else 0) * 0.10 +
            (0.10 if technical_ok else 0) +
            max(0, enhanced_score) * 0.15 +
            support_strength * 0.12 +
            (0.08 if chain_ok else 0) +
            (0.08 if sentiment_ok else 0) -
            resistance_strength * 0.10
        )
        
        # 计算做空信号强度
        short_strength = (
            (1 if not macd_bullish else 0) * 0.12 +
            (1 if rsi_overbought else 0) * 0.12 +
            (1 if not price_trend else 0) * 0.10 +
            (0.10 if not technical_ok else 0) +
            max(0, -enhanced_score) * 0.15 +
            (1 - support_strength) * 0.12 +
            (0.08 if not chain_ok else 0) +
            (0.08 if not sentiment_ok else 0) -
            support_strength * 0.10
        )
        
        # 加入资金费率权重
        if funding_signal > 0:
            long_strength += funding_confidence * 0.08
        elif funding_signal < 0:
            short_strength += funding_confidence * 0.08
        
        # 加入市场情绪权重
        if sentiment_score > 0:
            long_strength += sentiment_confidence * 0.08
        elif sentiment_score < 0:
            short_strength += sentiment_confidence * 0.08
        
        # 确保非负
        long_strength = max(0, long_strength)
        short_strength = max(0, short_strength)
        
        # 确定最终方向和强度
        signal_threshold = RISK_PARAMS.get("signal_threshold", 0.25)
        enable_short = RISK_PARAMS.get("enable_short", True)
        
        if long_strength > short_strength and long_strength > signal_threshold:
            direction = "long"
            final_strength = long_strength
            signal_ok = True
        elif short_strength > long_strength and short_strength > signal_threshold and enable_short:
            direction = "short"
            final_strength = short_strength
            signal_ok = True
        else:
            direction = "neutral"
            final_strength = max(long_strength, short_strength)
            signal_ok = False
        
        # 只记录强信号
        if signal_ok and final_strength > 0.6:
            logging.info(f"📊 {symbol} 强信号 - 方向: {direction}, 强度: {final_strength:.3f}")
        
        return signal_ok, df, final_strength, direction
        
    except Exception as e:
        logging.error(f"{symbol} 信号计算失败: {e}")
        return False, df, 0.0, "neutral"

# 在 trading_execution.py 的 process_symbol 函数中修复

# 在 trading_execution.py 的 process_symbol 函数中添加低余额检查
# trading_execution.py 中修改 process_symbol 函数

@timing_decorator
def process_symbol(symbol):
    """处理单个交易标的 - 修复缩进和错误处理"""
    from core.state_manager import is_in_low_balance_mode
    
    if not strategy_state.get("running", False):
        return
        
    # 在低余额模式下，只处理持仓币种
    if is_in_low_balance_mode():
        positions = strategy_state.get("positions", {})
        if symbol not in positions:
            return
    
    if "SWAP" not in symbol:
        return
        
    coin = symbol.split("-")[0]
    
    try:
        # 获取信号
        result = check_enhanced_multi_signal(symbol)
        if len(result) == 4:
            signal_ok, df, signal_strength, direction = result
        else:
            signal_ok, df, signal_strength, direction = False, pd.DataFrame(), 0.0, "neutral"
        
        if df is None or df.empty:
            return
            
    except Exception as e:
        logging.error(f"{symbol} 信号检查异常: {e}")
        return
    
    current_price = df.iloc[-1]["close"]
    positions = strategy_state.get("positions", {})
    
    # 检查平仓条件
    if symbol in positions:
        try:
            should_close, close_reason = check_enhanced_exit_signals(symbol, df)
            if should_close:
                logging.info(f"🔄 {symbol} 触发平仓 - 原因: {close_reason}")
                if close_reason.endswith("_full_close") or not close_reason.startswith("partial_"):
                    close_position(symbol, close_reason)
                return
                
            should_rollover, rollover_reason = check_rollover_conditions(symbol, df)
            if should_rollover:
                logging.info(f"🔄 {symbol} 触发滚仓 - 原因: {rollover_reason}")
                execute_rollover(symbol, rollover_reason)
                return
                
            # 检查加仓
            should_add, add_contracts = check_position_addition(symbol, df, signal_strength, direction)
            if should_add:
                last_add_time = positions[symbol].get("last_add_time", 0)
                if time.time() - last_add_time > 300:
                    logging.info(f"📈 {symbol} 触发加仓 - 张数: {add_contracts}")
                    execute_position_addition(symbol, add_contracts, direction, current_price, signal_strength)
                    return
        except Exception as e:
            logging.error(f"检查{symbol}持仓条件失败: {e}")
            return
    
    if is_in_low_balance_mode() or check_account_drawdown():
        return
    
    # 开仓逻辑 - 修复缩进部分
    if signal_ok and direction != "neutral":
        logging.info(f"🎯 {symbol} 达到开仓信号 - 方向: {direction}, 强度: {signal_strength:.3f}")
        
        try:
            # 1. 检查同币种持仓限制
            coin_total_value = get_coin_total_position_value(coin)
            total_equity = get_total_equity()
            
            if total_equity > 0 and coin_total_value / total_equity > 0.10:
                logging.info(f"⏸️ {coin} 持仓占比过高 ({(coin_total_value/total_equity*100):.1f}%)，跳过")
                return
            
            # 2. 检查余额
            tradable_balance = get_tradable_balance()
            if tradable_balance < 2:
                return
            
            # 3. 计算入场
            entry_price = get_optimal_entry_price(symbol, current_price, signal_strength, direction, df)
            if entry_price is None:
                return
                
            # 4. 计算仓位
            position_size, base_leverage = calculate_position_size(symbol, entry_price, df, signal_strength, direction)
            
            if position_size > 0:
                # 5. 执行交易
                if can_open_new_position(symbol, position_size, entry_price, base_leverage):
                    logging.info(f"🚀 执行开仓 {symbol} {direction} {position_size}张 @ {entry_price}")
                    success = execute_open_position(
                        symbol=symbol,
                        direction=direction,
                        size=position_size,
                        price=entry_price,
                        signal_strength=signal_strength,
                        base_leverage=base_leverage
                    )
                    if not success:
                        logging.error(f"❌ {symbol} 开仓执行失败")
            else:
                logging.debug(f"⏸️ {symbol} 计算仓位为0")
                
        except Exception as e:
            logging.error(f"❌ {symbol} 开仓流程异常: {e}")
            import traceback
            logging.debug(traceback.format_exc())
    else:
        logging.debug(f"⏸️ {symbol} 无开仓信号")

# 在 trading_execution.py 中添加专门的信号监控函数

def monitor_signal_strength(symbol, df, signal_strength, direction, long_strength, short_strength):
    """监控信号强度变化 - 专门用于记录接近开仓条件的信号"""
    signal_threshold = RISK_PARAMS.get("signal_threshold", 0.20)
    
    # 计算距离阈值的百分比
    distance_to_threshold = 0
    if direction == "long":
        distance_to_threshold = (signal_strength - signal_threshold) / signal_threshold
    elif direction == "short":
        short_threshold = abs(RISK_PARAMS.get("short_signal_threshold", -0.20))
        distance_to_threshold = (signal_strength - short_threshold) / short_threshold
    
    # 记录不同级别的信号
    if distance_to_threshold >= 0:
        # 已达到开仓条件
        logging.info(f"🎯 {symbol} 信号强度达标 - 方向: {direction}, 强度: {signal_strength:.3f}")
    elif distance_to_threshold >= -0.1:
        # 非常接近开仓条件 (90%+)
        logging.info(f"🔔 {symbol} 信号强度接近阈值 (>{abs(distance_to_threshold)*100:.1f}%) - 方向: {direction}")
        logging.info(f"   当前强度: {signal_strength:.3f}, 需要: {signal_threshold:.3f}")
        logging.info(f"   多空分布: 多头={long_strength:.3f}, 空头={short_strength:.3f}")
    elif distance_to_threshold >= -0.3:
        # 中等接近 (70%+)
        logging.info(f"📈 {symbol} 信号强度中等 (>{abs(distance_to_threshold)*100:.1f}%) - 方向: {direction}")
    elif distance_to_threshold >= -0.5:
        # 有一定强度 (50%+)
        logging.debug(f"📊 {symbol} 信号强度一般 (>{abs(distance_to_threshold)*100:.1f}%) - 方向: {direction}")

def log_signal_components(symbol, components):
    """记录信号各组成部分的强度"""
    if sum(components.values()) > 0.3:  # 只记录总强度较高的
        logging.debug(f"🔧 {symbol} 信号组成:")
        for component, value in components.items():
            if value > 0.1:  # 只记录有贡献的组件
                logging.debug(f"   {component}: {value:.3f}")



def check_smart_take_profit(symbol, df, position, current_signal_strength, current_direction):
    """智能止盈判断 - 修复版本（考虑杠杆）"""
    try:
        from config.constants import SMART_TAKE_PROFIT
        
        current_price = df.iloc[-1]["close"]
        open_price = position["open_price"]
        side = position.get("side", "long")
        leverage = position.get("leverage", 1)  # 获取杠杆
        
        # 计算基于账户权益的实际盈利比例（考虑杠杆）
        if side == "long":
            price_profit_ratio = (current_price - open_price) / open_price
            account_profit_ratio = price_profit_ratio * leverage  # ✅ 考虑杠杆
        else:
            price_profit_ratio = (open_price - current_price) / open_price
            account_profit_ratio = price_profit_ratio * leverage  # ✅ 考虑杠杆
        
        # 检查是否达到止盈点（基于账户权益）
        take_profit_reached = False
        take_profit_level = 0
        
        # 止盈阈值也应该基于账户权益（考虑杠杆后的实际盈利）
        TAKE_PROFIT1_ACCOUNT = TAKE_PROFIT1 * leverage  # 15% × 杠杆
        TAKE_PROFIT2_ACCOUNT = TAKE_PROFIT2 * leverage  # 35% × 杠杆  
        TAKE_PROFIT3_ACCOUNT = TAKE_PROFIT3 * leverage  # 75% × 杠杆
        
        if account_profit_ratio >= TAKE_PROFIT1_ACCOUNT and position.get("remaining", 1.0) == 1.0:
            take_profit_reached = True
            take_profit_level = 1
        elif account_profit_ratio >= TAKE_PROFIT2_ACCOUNT and position.get("remaining", 1.0) > 0.5:
            take_profit_reached = True
            take_profit_level = 2
        elif account_profit_ratio >= TAKE_PROFIT3_ACCOUNT:
            take_profit_reached = True
            take_profit_level = 3
        
        if not take_profit_reached:
            return False, None, None, None
            
        # 获取支撑阻力分析
        from modules.enhanced_strategy import enhanced_strategy
        support_strength, support_price, resistance_strength, resistance_price = enhanced_strategy.calculate_enhanced_support_resistance(df, symbol)
        
        # 智能止盈决策
        action = None
        close_reason = None
        close_ratio = 1.0  # 默认全平
        
        # 决策逻辑
        if current_signal_strength > SMART_TAKE_PROFIT["strong_signal_threshold"] and \
            account_profit_ratio >= SMART_TAKE_PROFIT["min_rollover_profit"] and \
            current_direction == side:
            # 强信号且盈利达标，考虑滚仓
            action = "rollover"
            close_reason = "strong_signal_rollover"
        elif current_signal_strength < SMART_TAKE_PROFIT["weak_signal_threshold"]:
            # 弱信号，直接止盈
            action = "close"
            close_reason = "weak_signal_take_profit"
            close_ratio = 1.0
        else:
            # 中等信号，分批止盈
            action = "partial_close"
            close_reason = f"partial_take_profit_level_{take_profit_level}"
            
            # 根据止盈级别决定平仓比例
            if take_profit_level == 1:
                close_ratio = SMART_TAKE_PROFIT["partial_profit_ratios"][0]
            elif take_profit_level == 2:
                close_ratio = SMART_TAKE_PROFIT["partial_profit_ratios"][1]
            else:  # take_profit_level == 3
                close_ratio = SMART_TAKE_PROFIT["partial_profit_ratios"][2]
            
            # 考虑阻力位影响
            if resistance_strength > 0.7 and abs(current_price - resistance_price) / current_price < 0.01:
                # 接近强阻力位，增加止盈比例
                close_ratio = min(close_ratio + 0.2, 1.0)
                close_reason += "_near_resistance"
        
        logging.info(f"智能止盈决策 - {symbol}: 动作={action}, 比例={close_ratio}, 账户盈利={account_profit_ratio*100:.1f}%")
        
        return True, action, close_ratio, close_reason
        
    except Exception as e:
        logging.error(f"智能止盈判断失败: {e}")
        return False, None, None, None

def check_float_loss_add_condition(symbol, df, position, current_signal_strength, current_direction):
    """检查浮亏加仓条件"""
    try:
        from config.constants import FLOAT_LOSS_ADD
        
        if not FLOAT_LOSS_ADD["enabled"]:
            return False, None
        
        # 检查是否已经加过仓
        if position.get("add_position_count", 0) >= FLOAT_LOSS_ADD["max_add_times"]:
            return False, "max_add_times_reached"
        
        current_price = df.iloc[-1]["close"]
        open_price = position["open_price"]
        side = position.get("side", "long")
        
        # 计算亏损比例
        if side == "long":
            loss_ratio = (open_price - current_price) / open_price
        else:
            loss_ratio = (current_price - open_price) / open_price
        
        # 检查是否达到亏损阈值
        if loss_ratio < FLOAT_LOSS_ADD["loss_threshold"]:
            return False, f"loss_ratio_{loss_ratio:.3f}_below_threshold"
        
        # 检查信号强度
        if current_signal_strength < FLOAT_LOSS_ADD["signal_requirement"]:
            return False, f"signal_strength_{current_signal_strength:.3f}_below_requirement"
        
        # 检查方向一致性
        if current_direction != side:
            return False, "direction_mismatch"
        
        # 检查支撑强度
        from modules.enhanced_strategy import enhanced_strategy
        support_strength, support_price, _, _ = enhanced_strategy.calculate_enhanced_support_resistance(df, symbol)
        
        if support_strength < FLOAT_LOSS_ADD["support_requirement"]:
            return False, f"support_strength_{support_strength:.3f}_below_requirement"
        
        # 检查是否接近支撑位
        distance_to_support = abs(current_price - support_price) / current_price
        if distance_to_support > 0.03:  # 距离支撑位超过3%
            return False, f"too_far_from_support_{distance_to_support:.3f}"
        
        # 所有条件满足，允许加仓
        add_ratio = min(FLOAT_LOSS_ADD["max_add_ratio"], loss_ratio * 2)  # 亏损越大，加仓比例越小
        add_ratio = max(add_ratio, 0.1)  # 最小加仓比例10%
        
        logging.info(f"浮亏加仓条件满足 - {symbol}: 亏损={loss_ratio:.3f}, 支撑强度={support_strength:.3f}, 加仓比例={add_ratio:.3f}")
        
        return True, add_ratio
        
    except Exception as e:
        logging.error(f"浮亏加仓条件检查失败: {e}")
        return False, None

def execute_float_loss_add(symbol, add_ratio):
    """执行浮亏加仓 - 修复版本"""
    try:
        positions = strategy_state.get("positions", {})
        if symbol not in positions:
            return False
        
        position = positions[symbol]
        current_price = get_realtime_price(symbol)
        
        if not current_price or current_price <= 0:
            return False
        
        # 计算加仓数量
        original_size = position["size"]
        add_size = original_size * add_ratio
        
        # 检查资金是否足够
        tradable_balance = get_tradable_balance()
        required_margin = add_size * current_price / position.get("leverage", 1)
        
        if required_margin > tradable_balance:
            logging.warning(f"加仓资金不足: 需要{required_margin:.2f}, 可用{tradable_balance:.2f}")
            return False
        
        # 执行加仓
        trade_side = "buy" if position.get("side", "long") == "long" else "sell"
        order = execute_trade(
            symbol=symbol, 
            side=trade_side, 
            quantity=add_size, 
            price=current_price, 
            leverage=position.get("leverage", 1),
            posSide=position.get("side", "long"),
            tdMode="cross"
        )
        
        if order and order.get("code") == "0":
            # 更新仓位信息
            new_size = original_size + add_size
            new_open_price = (original_size * position["open_price"] + add_size * current_price) / new_size
            
            position["size"] = new_size
            position["open_price"] = new_open_price
            position["add_position_count"] = position.get("add_position_count", 0) + 1
            position["add_position_time"] = time.time()
            position["total_margin"] = position.get("total_margin", 0) + required_margin
            
            # 重新计算止损位（基于新的开仓价）
            if position.get("side", "long") == "long":
                position["initial_stop"] = new_open_price * (1 - STOP_LOSS_INIT)
                position["current_stop"] = new_open_price * (1 - STOP_LOSS_INIT)
            else:
                position["initial_stop"] = new_open_price * (1 + STOP_LOSS_INIT)
                position["current_stop"] = new_open_price * (1 + STOP_LOSS_INIT)
            
            logging.info(f"[浮亏加仓成功] {symbol} | 加仓比例: {add_ratio:.3f} | "
                        f"新仓位: {new_size:.6f} | 新开仓价: {new_open_price:.6f}")
            
            # 重新计算资产分配
            recalculate_asset_allocation()
            return True
        else:
            logging.error(f"浮亏加仓失败: {symbol}")
            return False
            
    except Exception as e:
        logging.error(f"执行浮亏加仓失败: {e}")
        return False

def check_enhanced_exit_signals(symbol, df):
    """增强版平仓信号检查 - 修复版本"""
    positions = strategy_state.get("positions", {})
    if symbol not in positions:
        return False, None
        
    position = positions[symbol]
    current_price = df.iloc[-1]["close"]
    
    # 获取当前信号
    current_signal_ok, _, current_signal_strength, current_direction = check_enhanced_multi_signal(symbol)
    
    # 1. 智能止盈检查
    take_profit_decision, action, close_ratio, close_reason = check_smart_take_profit(
        symbol, df, position, current_signal_strength, current_direction
    )
    
    if take_profit_decision:
        if action == "close":
            return True, close_reason
        elif action == "partial_close":
            if execute_partial_close(symbol, close_ratio, close_reason):
                return False, None
            else:
                return True, close_reason + "_full_close"
        elif action == "rollover":
            return False, None
    
    # 2. 止损检查 - 修复返回值解包
    should_stop, stop_reason = check_stop_loss_conditions(symbol, df, position)  # 现在返回2个值
    if should_stop:
        return True, stop_reason
    
    # 3. 浮亏加仓检查
    if FLOAT_LOSS_ADD["enabled"]:
        add_condition_met, add_ratio_or_reason = check_float_loss_add_condition(
            symbol, df, position, current_signal_strength, current_direction
        )
        
        if add_condition_met and isinstance(add_ratio_or_reason, float):
            if execute_float_loss_add(symbol, add_ratio_or_reason):
                return False, None
    
    return False, None


def check_stop_loss_conditions(symbol, df, position):
    """分批止损 + 硬止损 - 修复返回值"""
    current_price = df.iloc[-1]["close"]
    open_price = position["open_price"]
    side = position.get("side", "long")
    leverage = position.get("leverage", 1)
    
    # 计算账户盈亏
    if side == "long":
        account_profit_ratio = ((current_price - open_price) / open_price) * leverage
    else:
        account_profit_ratio = ((open_price - current_price) / open_price) * leverage
    
    # 初始化移动止损相关变量
    if "peak_profit" not in position:
        position["peak_profit"] = account_profit_ratio  # 记录峰值盈利
    
    # 更新峰值盈利
    if account_profit_ratio > position["peak_profit"]:
        position["peak_profit"] = account_profit_ratio
    
    # 计算从峰值回撤的比例
    drawdown_from_peak = position["peak_profit"] - account_profit_ratio
    
    # 移动止损条件：盈利大于8%后，回撤12%触发止损
    if position["peak_profit"] >= 0.08 and drawdown_from_peak >= 0.12:
        return True, f"trailing_stop_{drawdown_from_peak*100:.1f}%_from_peak_{position['peak_profit']*100:.1f}%"

    # 分批止损逻辑
    if account_profit_ratio <= -0.08:  # 亏损8%，平仓30%
        if position.get("first_stop_done", False) == False:
            position["first_stop_done"] = True
            return True, f"first_stop_30%_at_{account_profit_ratio*100:.1f}%"
    
    if account_profit_ratio <= -0.12:  # 亏损12%，再平仓30%
        if position.get("second_stop_done", False) == False:
            position["second_stop_done"] = True
            return True, f"second_stop_40%_at_{account_profit_ratio*100:.1f}%"
    
    if account_profit_ratio <= -0.15:  # 亏损15%，平仓剩余40%
        return True, f"final_stop_100%_at_{account_profit_ratio*100:.1f}%"
    
    return False, None


def execute_partial_close(symbol, close_ratio, reason):
    """执行分批平仓 - 修复版本"""
    try:
        positions = strategy_state.get("positions", {})
        if symbol not in positions:
            return False
        
        position = positions[symbol]
        current_price = get_optimal_exit_price(symbol, position["open_price"])
        
        if current_price is None or current_price <= 0:
            return False
        
        # 计算平仓数量
        close_size = position["size"] * close_ratio
        remaining_size = position["size"] - close_size
        
        # 最小平仓数量检查
        if close_size < 0.001:  # 避免过小的平仓数量
            return False
        
        side = "sell" if position.get("side", "long") == "long" else "buy"
        order = execute_trade(
            symbol=symbol, 
            side=side, 
            quantity=close_size, 
            price=current_price, 
            leverage=position.get("leverage", 1),
            posSide=position.get("side", "long"),
            tdMode="cross"
        )
        
        if order and order.get("code") == "0":
            # 更新仓位信息
            position["size"] = remaining_size
            position["remaining"] = remaining_size / (position["size"] + close_size)  # 原始仓位大小
            
            # 计算部分盈亏
            if position.get("side", "long") == "long":
                profit_loss = (current_price - position["open_price"]) * close_size
            else:
                profit_loss = (position["open_price"] - current_price) * close_size
            
            logging.info(f"[分批平仓成功] {symbol} | 比例: {close_ratio:.3f} | "
                        f"平仓数量: {close_size:.6f} | 剩余数量: {remaining_size:.6f} | "
                        f"盈亏: {profit_loss:+.2f} USDT | 原因: {reason}")
            
            # 如果剩余数量过小，全平
            if remaining_size < 0.001:
                from core.state_manager import remove_position
                remove_position(symbol)
                logging.info(f"{symbol} 剩余仓位过小，已全平")
            else:
                # 重新计算资产分配
                recalculate_asset_allocation()
            
            return True
        else:
            logging.error(f"分批平仓失败: {symbol}")
            return False
            
    except Exception as e:
        logging.error(f"执行分批平仓失败: {e}")
        return False
    


def close_position(symbol, reason):
    """执行平仓 - 修复版本"""
    positions = strategy_state.get("positions", {})
    if symbol not in positions:
        return False
        
    position = positions[symbol]
    current_price = get_optimal_exit_price(symbol, position["open_price"])
    
    if current_price is None or current_price <= 0:
        logging.error(f"无法获取{symbol}的有效平仓价格")
        return False
    
    side = "sell" if position.get("side", "long") == "long" else "buy"
    order = execute_trade(
        symbol=symbol, 
        side=side, 
        quantity=position["size"], 
        price=current_price, 
        leverage=position.get("leverage", 1),
        posSide=position.get("side", "long"),
        tdMode="cross"
    )
    
    if order and order.get("code") == "0":
        if position.get("side", "long") == "long":
            profit_loss = (current_price - position["open_price"]) * position["size"]
            profit_ratio = (current_price - position["open_price"]) / position["open_price"]
        else:
            profit_loss = (position["open_price"] - current_price) * position["size"]
            profit_ratio = (position["open_price"] - current_price) / position["open_price"]
        
        logging.info(f"[平仓成功] {symbol} | 原因: {reason} | 盈亏: {profit_loss:+.2f} USDT ({profit_ratio*100:+.2f}%)")
        
        from core.state_manager import remove_position
        remove_position(symbol)
        return True
    else:
        logging.error(f"平仓失败: {symbol}")
        return False


def get_optimal_exit_price(symbol, open_price):
    """获取最优平仓价格"""
    try:
        # 获取实时价格
        realtime_price = get_realtime_price(symbol)
        if not realtime_price or realtime_price <= 0:
            return None
            
        # 获取深度数据
        depth_price = get_depth_based_price(symbol, "sell")
        
        # 确定基础价格
        if depth_price and depth_price > 0:
            base_price = depth_price
        else:
            base_price = realtime_price
        
        # 根据情况调整价格（平仓时更注重成交速度）
        # 如果是止损，使用更激进的价格确保成交
        # 如果是止盈，可以稍微让步获取更好价格
        
        # 简单的逻辑：使用买一价（确保快速成交）
        final_price = base_price * 0.999  # 降低0.1%确保成交
        
        logging.info(f"平仓价格优化 - 基础价: {base_price:.6f}, 最终价: {final_price:.6f}")
        return final_price
        
    except Exception as e:
        logging.error(f"获取平仓价格失败: {e}")
        return None

def check_rollover_conditions(symbol, df):
    """检查滚仓条件 - 增强版本"""
    positions = strategy_state.get("positions", {})
    if symbol not in positions:
        return False, None
        
    position = positions[symbol]
    
    # 检查是否达到最大滚仓次数
    if position.get("rollover_count", 0) >= MAX_ROLL_TIMES:
        return False, None
        
    current_price = df.iloc[-1]["close"]
    open_price = position["open_price"]
    side = position.get("side", "long")
    
    # 计算盈利比例（考虑多空方向）
    if side == "long":
        profit_ratio = (current_price - open_price) / open_price
    else:  # short
        profit_ratio = (open_price - current_price) / open_price
    
    # 滚仓条件1：达到盈利水平且信号仍然强劲
    if profit_ratio >= ROLL_PROFIT_THRESHOLD:
        signal_ok, _, signal_strength, current_direction = check_enhanced_multi_signal(symbol)
        
        # 检查信号方向是否与当前仓位一致
        direction_match = (current_direction == side)
        
        if signal_ok and signal_strength > ROLL_SIGNAL_THRESHOLD and direction_match:
            logging.info(f"{symbol} 达到滚仓条件，盈利: {profit_ratio*100:.2f}%, "
                        f"信号强度: {signal_strength:.2f}, 方向匹配: {direction_match}")
            return True, "profit_rollover"
    
    # 滚仓条件2：资金费率有利时滚仓（仅永续合约）
    if "SWAP" in symbol:
        funding_signal, funding_confidence = funding_analyzer.analyze_funding_rate_signal(symbol)
        
        # 检查资金费率方向是否与仓位方向一致
        funding_match = (
            (funding_signal > 0 and side == "long") or 
            (funding_signal < 0 and side == "short")
        )
        
        if funding_match and funding_confidence > 0.7 and profit_ratio > 0.05:
            logging.info(f"{symbol} 资金费率有利，考虑滚仓")
            return True, "funding_rollover"
    
    # 滚仓条件3：波动率降低时滚仓（降低风险）
    volatility = df["close"].tail(20).std() / df["close"].tail(20).mean()
    if volatility < 0.03 and profit_ratio > 0.08:  # 低波动且有一定盈利
        signal_ok, _, signal_strength, current_direction = check_enhanced_multi_signal(symbol)
        if signal_ok and current_direction == side:
            logging.info(f"{symbol} 低波动环境，考虑滚仓降低风险")
            return True, "volatility_rollover"
    
    return False, None

# 修复 execute_rollover 函数中的调用
def execute_rollover(symbol, reason):
    """执行滚仓 - 修复版本"""
    positions = strategy_state.get("positions", {})
    if symbol not in positions:
        return False
        
    position = positions[symbol]
    
    # 检查是否达到最大滚仓次数
    if position.get("rollover_count", 0) >= MAX_ROLL_TIMES:
        logging.info(f"{symbol} 已达到最大滚仓次数 {MAX_ROLL_TIMES}，停止滚仓")
        return False
        
    # 计算使用多少利润进行滚仓
    current_price = get_realtime_price(symbol)
    if not current_price or current_price <= 0:
        return False
        
    if position.get("side", "long") == "long":
        profit = (current_price - position["open_price"]) * position["size"]
    else:
        profit = (position["open_price"] - current_price) * position["size"]
    
    # 根据滚仓次数调整利润使用比例
    rollover_count = position.get("rollover_count", 0)
    profit_ratio = ROLL_USE_PROFIT_RATIO * (1 - rollover_count * 0.2)  # 每次滚仓减少20%利润使用
    profit_ratio = max(0.2, profit_ratio)  # 最低使用20%利润
    
    rollover_amount = profit * profit_ratio
    
    # 平掉原有仓位
    if close_position(symbol, f"rollover_{reason}"):
        # 使用部分利润开新仓
        new_position_size = rollover_amount / current_price
        
        # 获取新的信号强度
        signal_ok, df, signal_strength, direction = check_enhanced_multi_signal(symbol)
        if signal_ok and direction == position.get("side", "long"):  # 确保信号方向一致
            # 开新仓
            entry_price = get_optimal_entry_price(symbol, current_price, signal_strength, direction)
            trade_side = "buy" if direction == "long" else "sell"
            
            # 修复：使用新的 execute_trade 函数
            order = execute_trade(
                symbol=symbol, 
                side=trade_side, 
                quantity=new_position_size, 
                price=entry_price, 
                leverage=position.get("leverage", 1),
                posSide=direction,
                tdMode="cross"
            )
            
            if order and order.get("code") == "0":
                # 更新滚仓次数
                new_rollover_count = rollover_count + 1
                
                # 设置新的仓位信息
                if direction == "long":
                    initial_stop = entry_price * (1 - STOP_LOSS_INIT)
                else:
                    initial_stop = entry_price * (1 + STOP_LOSS_INIT)
                
                # 确保 positions 字典存在
                if "positions" not in strategy_state:
                    strategy_state["positions"] = {}
                
                strategy_state["positions"][symbol] = {
                    "open_price": entry_price,
                    "size": new_position_size,
                    "leverage": position.get("leverage", 1),
                    "margin": new_position_size * entry_price / position.get("leverage", 1),
                    "entry_time": time.time(),
                    "side": direction,
                    "remaining": 1.0,
                    "initial_stop": initial_stop,
                    "current_stop": initial_stop,
                    "take_profit_1": entry_price * (1 + TAKE_PROFIT1) if direction == "long" else entry_price * (1 - TAKE_PROFIT1),
                    "take_profit_2": entry_price * (1 + TAKE_PROFIT2) if direction == "long" else entry_price * (1 - TAKE_PROFIT2),
                    "take_profit_3": entry_price * (1 + TAKE_PROFIT3) if direction == "long" else entry_price * (1 - TAKE_PROFIT3),
                    "rollover_count": new_rollover_count,
                    "signal_strength": signal_strength,
                    "coin": symbol.split("-")[0]
                }
                
                logging.info(f"[滚仓成功] {symbol} | 第{new_rollover_count}次滚仓 | "
                            f"使用利润: {rollover_amount:.2f} USDT | 新仓位大小: {new_position_size:.6f}")
                return True
    
    return False

def check_all_exits():
    """检查所有仓位的平仓条件"""
    positions = strategy_state.get("positions", {})
    symbols_to_check = list(positions.keys())
    
    for symbol in symbols_to_check:
        try:
            # 获取该符号的最新数据
            from modules.technical_analysis import get_kline_data
            df = get_kline_data(symbol, "1H", 50)  # 获取50条1小时K线
            
            if df is not None and not df.empty:
                # 调用process_symbol会自动检查平仓条件
                process_symbol(symbol)
                
        except Exception as e:
            logging.error(f"检查{symbol}平仓条件失败: {e}")



def check_margin_requirements(symbol, quantity, price, leverage):
    """检查保证金要求"""
    try:
        from core.api_client import account_api
        
        # 计算所需保证金
        contract_value = quantity * price
        required_margin = contract_value / leverage
        
        # 获取账户余额
        response = account_api.get_account_balance(ccy="USDT")
        if response and response.get("code") == "0" and response.get("data"):
            data = response["data"][0]
            if "details" in data and data["details"]:
                for detail in data["details"]:
                    if detail.get("ccy") == "USDT":
                        available_balance = float(detail.get("availBal", 0))
                        
                        # 检查保证金是否足够
                        if available_balance < required_margin:
                            logging.error(f"❌ 保证金不足: 需要 {required_margin:.2f} USDT, 可用 {available_balance:.2f} USDT")
                            return False
                        
                        # 确保保留一些余额用于手续费等
                        if available_balance - required_margin < 1.0:
                            logging.error(f"❌ 开仓后余额将低于1 USDT: {available_balance - required_margin:.2f} USDT")
                            return False
                        
                        return True
        
        logging.error("❌ 无法获取账户余额信息")
        return False
        
    except Exception as e:
        logging.error(f"❌ 检查保证金要求失败: {e}")
        return False
    


def check_position_addition(symbol, df, signal_strength, direction):
    """检查是否需要加仓 - 同一币种不超过10%"""
    try:
        coin = symbol.split("-")[0]
        
        # 获取同币种总仓位价值
        coin_total_value = get_coin_total_position_value(coin)
        total_equity = get_total_equity()
        
        if total_equity <= 0:
            return False, 0
            
        current_ratio = coin_total_value / total_equity
        target_ratio = 0.10  # 10%上限
        
        # 如果已经达到或超过目标比例，不加仓
        if current_ratio >= target_ratio:
            return False, 0
            
        # 检查信号强度是否足够
        if signal_strength < 0.6:  # 加仓需要更强的信号
            return False, 0
            
        # 计算可加仓的价值
        available_value = total_equity * target_ratio - coin_total_value
        if available_value <= 0:
            return False, 0
            
        # 计算加仓数量
        current_price = df.iloc[-1]["close"]
        contract_value = get_contract_value(symbol)
        one_contract_value = contract_value * current_price
        
        if one_contract_value <= 0:
            return False, 0
            
        # 计算可加仓的张数
        max_add_contracts = available_value / one_contract_value
        
        # 根据信号强度确定加仓比例
        add_ratio = min(0.3, (signal_strength - 0.6) / 0.4)  # 信号0.6-1.0对应0-30%加仓
        add_contracts = max_add_contracts * add_ratio
        
        # 调整到正确的精度
        add_contracts = adjust_position_to_lot_size(symbol, add_contracts)
        
        min_contract_size = get_min_contract_size(symbol)
        if add_contracts < min_contract_size:
            return False, 0
            
        return True, add_contracts
        
    except Exception as e:
        logging.error(f"检查加仓条件失败 {symbol}: {e}")
        return False, 0

def execute_position_addition(symbol, add_contracts, direction, current_price, signal_strength):
    """执行加仓操作"""
    try:
        logging.info(f"🎯 {symbol} 执行加仓 - 方向: {direction}, 张数: {add_contracts}, 价格: {current_price:.6f}")
        
        # 设置方向映射
        side_map = {'long': 'buy', 'short': 'sell'}
        pos_side_map = {'long': 'long', 'short': 'short'}
        
        side = side_map[direction]
        posSide = pos_side_map[direction]
        
        # 使用现有仓位的杠杆
        positions = strategy_state.get("positions", {})
        leverage = positions.get(symbol, {}).get("leverage", 3) if symbol in positions else 3
        
        # 创建订单
        order = execute_trade(
            symbol=symbol,
            side=side,
            quantity=add_contracts,
            price=current_price,
            leverage=leverage,
            posSide=posSide,
            tdMode="cross"
        )
        
        if order and order.get("code") == "0":
            # 更新仓位信息
            if symbol in positions:
                position = positions[symbol]
                # 计算新的平均开仓价
                old_size = position["size"]
                old_price = position["open_price"]
                new_size = old_size + add_contracts
                new_avg_price = (old_size * old_price + add_contracts * current_price) / new_size
                
                # 更新仓位
                position["size"] = new_size
                position["open_price"] = new_avg_price
                position["notional_value"] = new_size * get_contract_value(symbol) * new_avg_price
                position["margin"] = position["notional_value"] / leverage
                position["add_count"] = position.get("add_count", 0) + 1
                position["last_add_time"] = time.time()
                
                logging.info(f"✅ {symbol} 加仓成功 - 新仓位: {new_size}张, 平均价格: {new_avg_price:.6f}")
                
                # 重新计算资产分配
                recalculate_asset_allocation()
                return True
                
        return False
        
    except Exception as e:
        logging.error(f"❌ {symbol} 加仓异常: {str(e)}")
        return False