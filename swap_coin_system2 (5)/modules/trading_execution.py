# trading_execution.py - 修复导入问题以解决重复初始化
import time
import logging
from datetime import datetime, timedelta
# 移除顶层API对象导入，改为动态获取
# from core.api_client import trade_api, account_api 
import core.api_client 

from core.state_manager import (
    strategy_state, 
    check_account_drawdown, 
    recalculate_asset_allocation, 
    get_tradable_balance
)
from modules.chain_analysis import get_chain_signals
from modules.sentiment_analysis import get_sentiment_signals
from modules.technical_analysis import get_technical_signals
from modules.position_management import calculate_position_size, can_open_new_position, get_coin_total_position_value
from modules.funding_rate_analysis import funding_analyzer
from modules.advanced_market_analysis import advanced_market_analyzer
from utils.decorators import safe_request
from utils.performance_monitor import performance_monitor as perf_monitor
import pandas as pd
from utils.instrument_utils import (
    adjust_quantity_precision, 
    adjust_price_precision,
    validate_order_parameters, get_min_contract_size, get_lot_size
)

from modules.position_management import (
    calculate_position_size, can_open_new_position, 
    get_contract_value, adjust_position_to_lot_size, get_total_equity
)

# 杠杆管理字典
leverage_settings = {}

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
from config.constants import PENDING_ORDER_CONFIG

pending_orders = {}  # 存储待处理订单

def monitor_pending_orders():
    """监测委托单状态"""
    global pending_orders
    current_time = time.time()
    
    max_wait_time = PENDING_ORDER_CONFIG["max_wait_time"]
    price_deviation_threshold = PENDING_ORDER_CONFIG["price_deviation_threshold"]
    
    orders_to_remove = []
    
    for order_id, order_info in pending_orders.items():
        symbol = order_info['symbol']
        order_place_time = order_info['time']
        target_price = order_info['target_price']
        direction = order_info['direction']
        
        if current_time - order_place_time > max_wait_time:
            logging.info(f"⏰ {symbol} 委托单超过{max_wait_time/3600:.0f}小时未成交，取消订单")
            cancel_order(order_id)
            orders_to_remove.append(order_id)
            continue
        
        if (current_time - order_place_time) % (4 * 3600) < 60:
            current_price = get_realtime_price(symbol)
            if current_price:
                price_diff_ratio = abs(current_price - target_price) / target_price
                
                if direction == "long":
                    if current_price < target_price and price_diff_ratio > price_deviation_threshold:
                        logging.info(f"📉 {symbol} 多单价格偏离超过{price_deviation_threshold*100:.0f}%，取消订单")
                        cancel_order(order_id)
                        orders_to_remove.append(order_id)
                else:
                    if current_price > target_price and price_diff_ratio > price_deviation_threshold:
                        logging.info(f"📈 {symbol} 空单价格偏离超过{price_deviation_threshold*100:.0f}%，取消订单")
                        cancel_order(order_id)
                        orders_to_remove.append(order_id)
    
    for order_id in orders_to_remove:
        if order_id in pending_orders:
            del pending_orders[order_id]

def cancel_order(order_id):
    """取消订单"""
    try:
        trade_api = core.api_client.trade_api
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
        trade_api = core.api_client.trade_api
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
        return core.api_client.account_api is not None and core.api_client.trade_api is not None
    except Exception as e:
        logging.error(f"检查API状态失败: {e}")
        return False

def initialize_trading_system():
    """初始化交易系统 - 修复版本，支持已有仓位的情况"""
    try:
        if not check_account_api():
            logging.error("❌ 交易系统初始化失败：账户API未就绪")
            return False
            
        trading_mode_ok = initialize_trading_mode()
        
        if trading_mode_ok:
            logging.info("✅ 交易系统初始化完成")
        else:
            logging.warning("⚠️ 交易模式初始化有警告，但程序将继续运行以接管现有仓位")
            
        return True
        
    except Exception as e:
        logging.error(f"❌ 交易系统初始化失败: {e}")
        return True

def check_account_api():
    """检查账户API是否已初始化"""
    if core.api_client.account_api is None:
        try:
            if core.api_client.initialize_okx_api():
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
    try:
        return core.api_client.trade_api
    except Exception as e:
        logging.error(f"获取交易API失败: {e}")
        return None

def initialize_trading_mode():
    """初始化交易模式为全仓"""
    try:
        if not check_account_api():
            logging.error("❌ 无法初始化交易模式：账户API未就绪")
            return False
            
        try:
            account_api = core.api_client.account_api
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
        
        account_api = core.api_client.account_api
        result = account_api.set_position_mode(posMode="long_short_mode")
        if result and result.get('code') == "0":
            logging.info("✅ 持仓模式设置为: long_short_mode (开平仓模式)")
            return True
        else:
            error_msg = result.get("msg", "未知错误") if result else "无响应"
            if "Cancel any open orders" in error_msg or "close positions" in error_msg:
                logging.warning("⚠️ 检测到当前有持仓或未成交订单，无法更改持仓模式")
                logging.warning("⚠️ 策略将继续运行，但请确保当前持仓模式为 long_short_mode")
                return True
            else:
                logging.warning(f"⚠️ 持仓模式设置失败: {error_msg}")
                return False
    except Exception as e:
        logging.warning(f"⚠️ 持仓模式设置异常: {str(e)}")
        return True

def execute_open_position(symbol, direction, size, price, signal_strength, base_leverage=3.0):
    """执行开仓操作"""
    try:
        coin = symbol.split("-")[0]
        adjusted_price = adjust_price_precision(symbol, price)
        adjusted_size = adjust_quantity_precision(symbol, size)
        
        if adjusted_size <= 0:
            logging.error(f"❌ {symbol} 调整后张数无效: {adjusted_size}")
            return False
            
        min_sz = get_min_contract_size(symbol)
        if adjusted_size < min_sz:
            logging.error(f"❌ {symbol} 调整后张数{adjusted_size}小于最小要求{min_sz}")
            return False
        
        current_price = get_realtime_price(symbol)
        logging.info(f"开仓价格详情 - {symbol}:")
        logging.info(f"  当前市场价格: {current_price:.6f}")
        logging.info(f"  计算入场价格: {price:.6f}")
        logging.info(f"  精度调整后价格: {adjusted_price:.6f}")
        logging.info(f"  交易方向: {direction}")
        logging.info(f"  原始张数: {size}")
        logging.info(f"  调整后张数: {adjusted_size}")
        logging.info(f"  最小张数要求: {min_sz}")
        
        if adjusted_price <= 0:
            logging.error(f"❌ {symbol} 调整后价格异常: {adjusted_price}")
            return False
            
        if adjusted_size <= 0:
            logging.error(f"❌ {symbol} 调整后张数异常: {adjusted_size}")
            return False
            
        if current_price:
            price_diff_ratio = abs(adjusted_price - current_price) / current_price
            if price_diff_ratio > 0.05:
                logging.warning(f"⚠️ {symbol} 价格偏离较大: {adjusted_price:.6f} vs 市价 {current_price:.6f} (偏离 {price_diff_ratio*100:.1f}%)")
        
        logging.info(f"🔍 开仓调试信息:")
        logging.info(f"  - 交易对: {symbol}")
        logging.info(f"  - 方向: {direction}")
        logging.info(f"  - 张数: {adjusted_size}")
        logging.info(f"  - 价格: {adjusted_price:.6f}")
        logging.info(f"  - 信号强度: {signal_strength:.3f}")
        
        dynamic_leverage = calculate_dynamic_leverage(signal_strength, base_leverage)
        logging.info(f"  - 杠杆: {dynamic_leverage}x")
        
        logging.info(f"🚀 {symbol} 执行开仓 - 方向: {direction}, 张数: {adjusted_size}, 价格: {adjusted_price:.6f}, 杠杆: {dynamic_leverage}x")
        
        side_map = {'long': 'buy', 'short': 'sell'}
        pos_side_map = {'long': 'long', 'short': 'short'}
        
        side = side_map[direction]
        posSide = pos_side_map[direction]
        
        order = execute_trade(
            symbol=symbol,
            side=side,
            quantity=adjusted_size,
            price=adjusted_price,
            leverage=dynamic_leverage,
            posSide=posSide,
            tdMode="cross"
        )
        
        if order and order.get("code") == "0":
            from modules.position_management import get_contract_value
            contract_value = get_contract_value(symbol)
            
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
            
            notional_value = size * contract_value * price
            margin_used = notional_value / dynamic_leverage
            
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
                "coin": coin,
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
    global leverage_settings
    
    try:
        account_api = core.api_client.account_api
        if account_api is None:
            logging.error("❌ 账户API未初始化，无法设置杠杆")
            return False
            
        leverage_int = int(round(leverage))
        leverage_int = max(1, min(leverage_int, 5))
        
        if (instId in leverage_settings and 
            leverage_settings[instId]['leverage'] == leverage_int and
            leverage_settings[instId]['mode'] == mgnMode):
            return True
            
        result = account_api.set_leverage(
            instId=instId,
            lever=str(leverage_int),
            mgnMode=mgnMode
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
    try:
        market_api = core.api_client.market_api
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
    try:
        market_api = core.api_client.market_api
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

def get_optimal_entry_price(symbol, current_price, signal_strength, direction, df):
    try:
        from modules.enhanced_strategy import enhanced_strategy
        
        strong_signal_threshold = ENTRY_STRATEGY["strong_signal_threshold"]
        min_signal_threshold = ENTRY_STRATEGY["min_signal_threshold"]
        support_strength_threshold = ENTRY_STRATEGY["support_strength_threshold"]
        resistance_strength_threshold = ENTRY_STRATEGY["resistance_strength_threshold"]
        
        support_strength, support_price, resistance_strength, resistance_price = enhanced_strategy.calculate_enhanced_support_resistance(df, symbol)
        
        logging.info(f"📊 {symbol} 支撑阻力分析:")
        logging.info(f"   支撑位: {support_price:.6f} (强度: {support_strength:.3f})")
        logging.info(f"   阻力位: {resistance_price:.6f} (强度: {resistance_strength:.3f})")
        logging.info(f"   当前价格: {current_price:.6f}, 信号强度: {signal_strength:.3f}, 方向: {direction}")
        
        if signal_strength > strong_signal_threshold:
            logging.info(f"🎯 {symbol} 信号很强，使用当前价格入场")
            return current_price
        
        if signal_strength > min_signal_threshold:
            if direction == "long":
                if support_price > 0 and support_strength > support_strength_threshold:
                    entry_price = support_price * 1.001
                    logging.info(f"🛡️ {symbol} 在支撑位附近下多单: {entry_price:.6f}")
                    return entry_price
                else:
                    logging.info(f"⚠️ {symbol} 没有有效支撑位，使用当前价格")
                    return current_price
            else:
                if resistance_price > 0 and resistance_strength > resistance_strength_threshold:
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
    for attempt in range(max_retries):
        try:
            trade_api = get_trade_api()
            if trade_api is None:
                logging.error("❌ 交易API未初始化")
                if attempt < max_retries - 1:
                    time.sleep(2 ** attempt)
                    continue
                return None
                
            if not validate_order_parameters(symbol, side, quantity, price, leverage, posSide, tdMode):
                if attempt < max_retries - 1:
                    time.sleep(1)
                    continue
                return None
                
            if not set_leverage_for_instrument(symbol, leverage, tdMode):
                logging.error(f"❌ {symbol} 杠杆设置失败，跳过交易")
                if attempt < max_retries - 1:
                    time.sleep(1)
                    continue
                return None
            
            adjusted_price = adjust_price_precision(symbol, price)
            adjusted_quantity = adjust_quantity_precision(symbol, quantity)
            
            lot_size = get_lot_size(symbol)
            if lot_size >= 1:
                sz_str = str(int(adjusted_quantity))
            else:
                lot_str = str(lot_size).rstrip('0')
                if '.' in lot_str:
                    decimals = len(lot_str.split('.')[-1])
                    sz_str = f"{adjusted_quantity:.{decimals}f}"
                else:
                    sz_str = str(int(adjusted_quantity))
            
            order_data = {
                "instId": symbol,
                "tdMode": tdMode,
                "side": side,
                "posSide": posSide,
                "ordType": "limit",
                "px": str(adjusted_price),
                "sz": sz_str
            }
            
            logging.info(f"📝 创建合约订单 (尝试 {attempt + 1}/{max_retries}): {symbol}")
            logging.info(f"   订单参数: {order_data}")
            logging.info(f"   张数详情: 原始={quantity}, 调整后={adjusted_quantity}, 格式化后={sz_str}, lot_size={lot_size}")
            
            result = trade_api.place_order(**order_data)
            
            if result and result.get("code") == "0":
                order_id = result["data"][0]["ordId"]
                
                pending_orders[order_id] = {
                    'symbol': symbol,
                    'side': side,
                    'quantity': quantity,
                    'price': price,
                    'target_price': price,
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
                
                from utils.error_handlers import log_trade_error_details
                log_trade_error_details(error_code, error_msg, symbol, order_data)
                
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

@timing_decorator
def check_enhanced_multi_signal(symbol):
    """增强的多重信号检查"""
    try:
        coin = symbol.split("-")[0]
        
        if "SWAP" not in symbol:
            return False, pd.DataFrame(), 0.0, "neutral"
        
        chain_ok = get_chain_signals(coin)
        sentiment_ok = get_sentiment_signals(coin)
        technical_ok, df = get_technical_signals(symbol)
        
        if df is None or df.empty:
            return False, pd.DataFrame(), 0.0, "neutral"
            
    except Exception as e:
        logging.debug(f"{symbol} 信号检查异常: {e}")
        return False, pd.DataFrame(), 0.0, "neutral"
    
    if df is None:
        return False, pd.DataFrame(), 0.0, "neutral"
    
    try:
        depth_data = None
        
        funding_signal = 0
        funding_confidence = 0
        try:
            funding_signal, funding_confidence = funding_analyzer.analyze_funding_rate_signal(symbol)
        except Exception as e:
            pass
        
        sentiment_score = 0
        sentiment_confidence = 0
        try:
            sentiment_score, sentiment_confidence = advanced_market_analyzer.analyze_market_sentiment(symbol)
        except Exception as e:
            pass
        
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
        
        latest = df.iloc[-1]
        
        macd_bullish = latest.get("macd", 0) > latest.get("macd_signal", -1)
        rsi_oversold = latest.get("rsi", 50) <= RSI_OVERSOLD
        rsi_overbought = latest.get("rsi", 50) >= RSI_OVERBOUGHT
        price_trend = latest["close"] >= df.iloc[-5]["close"]
        
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
        
        if funding_signal > 0:
            long_strength += funding_confidence * 0.08
        elif funding_signal < 0:
            short_strength += funding_confidence * 0.08
        
        if sentiment_score > 0:
            long_strength += sentiment_confidence * 0.08
        elif sentiment_score < 0:
            short_strength += sentiment_confidence * 0.08
        
        long_strength = max(0, long_strength)
        short_strength = max(0, short_strength)
        
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
        
        if signal_ok and final_strength > 0.6:
            logging.info(f"📊 {symbol} 强信号 - 方向: {direction}, 强度: {final_strength:.3f}")
        
        return signal_ok, df, final_strength, direction
        
    except Exception as e:
        logging.error(f"{symbol} 信号计算失败: {e}")
        return False, df, 0.0, "neutral"

@timing_decorator
def process_symbol(symbol):
    """处理单个交易标的 - 终极调试版（带详细分步日志）"""
    logging.info(f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    logging.info(f"开始处理交易对: {symbol}")

    try:
        from core.state_manager import is_in_low_balance_mode

        # 步骤0: 基本过滤
        logging.info(f"[{symbol}] 步骤0 - 检查运行状态和低余额模式")
        if not strategy_state.get("running", False):
            logging.info(f"[{symbol}] 策略已停止，退出")
            return

        if is_in_low_balance_mode():
            positions = strategy_state.get("positions", {})
            if symbol not in positions:
                logging.info(f"[{symbol}] 低余额模式，仅处理持仓币，跳过")
                return

        if "SWAP" not in symbol:
            logging.warning(f"[{symbol}] 非SWAP合约，跳过")
            return

        coin = symbol.split("-")[0]
        logging.info(f"[{symbol}] 币种: {coin}")

        # 步骤1: 获取综合信号（最容易卡的地方）
        logging.info(f"[{symbol}] 步骤1/9 - 调用 check_enhanced_multi_signal 获取信号...")
        start_time = time.time()
        result = check_enhanced_multi_signal(symbol)
        signal_cost = time.time() - start_time
        logging.info(f"[{symbol}] 信号获取完成，耗时 {signal_cost:.2f}s")

        if len(result) == 4:
            signal_ok, df, signal_strength, direction = result
        else:
            signal_ok, df, signal_strength, direction = False, pd.DataFrame(), 0.0, "neutral"

        if df is None or df.empty:
            logging.warning(f"[{symbol}] K线数据为空，终止处理")
            return

        current_price = df.iloc[-1]["close"]
        logging.info(f"[{symbol}] 当前价格: {current_price:.6f} | 信号强度: {signal_strength:.3f} | 方向: {direction}")

        # 步骤2: 检查是否已有持仓
        positions = strategy_state.get("positions", {})
        has_position = symbol in positions
        logging.info(f"[{symbol}] 当前是否有持仓: {has_position}")

        if has_position:
            logging.info(f"[{symbol}] 步骤2/9 - 检查平仓条件...")
            should_close, close_reason = check_enhanced_exit_signals(symbol, df)
            if should_close:
                logging.info(f"[{symbol}] 触发平仓 - 原因: {close_reason}")
                close_position(symbol, close_reason)
                return

            logging.info(f"[{symbol}] 步骤3/9 - 检查滚仓条件...")
            should_rollover, rollover_reason = check_rollover_conditions(symbol, df)
            if should_rollover:
                logging.info(f"[{symbol}] 触发滚仓 - 原因: {rollover_reason}")
                execute_rollover(symbol, rollover_reason)
                return

            logging.info(f"[{symbol}] 步骤4/9 - 检查加仓条件...")
            should_add, add_contracts = check_position_addition(symbol, df, signal_strength, direction)
            if should_add and add_contracts > 0:
                last_add_time = positions[symbol].get("last_add_time", 0)
                if time.time() - last_add_time > 300:
                    logging.info(f"[{symbol}] 触发加仓 {add_contracts} 张")
                    execute_position_addition(symbol, add_contracts, direction, current_price, signal_strength)
                    return

        # 步骤5: 低余额或回撤保护
        logging.info(f"[{symbol}] 步骤5/9 - 检查账户风控...")
        if is_in_low_balance_mode():
            logging.info(f"[{symbol}] 低余额模式，禁止开新仓")
            return
        if check_account_drawdown():
            logging.info(f"[{symbol}] 账户回撤保护，禁止开新仓")
            return

        # 步骤6: 开仓信号判断
        if not signal_ok or direction == "neutral":
            logging.info(f"[{symbol}] 无有效开仓信号，结束处理")
            return

        logging.info(f"[{symbol}] 步骤6/9 - 达到开仓信号！方向: {direction} 强度: {signal_strength:.3f}")

        # 步骤7: 同币种占比检查
        coin_total_value = get_coin_total_position_value(coin)
        total_equity = get_total_equity()
        if total_equity > 0 and coin_total_value / total_equity > 0.10:
            logging.info(f"[{symbol}] {coin} 占比超10% ({coin_total_value/total_equity*100:.1f}%)，禁止开仓")
            return

        tradable_balance = get_tradable_balance()
        if tradable_balance < 2:
            logging.info(f"[{symbol}] 可交易余额不足2 USDT，禁止开仓")
            return

        # 步骤8: 计算最优入场价
        logging.info(f"[{symbol}] 步骤8/9 - 计算最优入场价...")
        entry_price = get_optimal_entry_price(symbol, current_price, signal_strength, direction, df)
        if entry_price is None:
            logging.warning(f"[{symbol}] 获取最优入场价失败")
            return

        # 步骤9: 计算仓位并执行
        logging.info(f"[{symbol}] 步骤9/9 - 计算仓位大小...")
        position_size, base_leverage = calculate_position_size(symbol, entry_price, df, signal_strength, direction)

        if position_size > 0 and can_open_new_position(symbol, position_size, entry_price, base_leverage):
            logging.info(f"[{symbol}] 准备开仓 - 方向: {direction} | 张数: {position_size} | 价格: {entry_price:.6f} | 杠杆: {base_leverage}x")
            success = execute_open_position(
                symbol=symbol,
                direction=direction,
                size=position_size,
                price=entry_price,
                signal_strength=signal_strength,
                base_leverage=base_leverage
            )
            if success:
                logging.info(f"[{symbol}] 开仓成功！")
            else:
                logging.error(f"[{symbol}] 开仓失败")
        else:
            logging.info(f"[{symbol}] 仓位计算为0或不允许开仓")

    except Exception as e:
        logging.error(f"[{symbol}] process_symbol 整体异常: {e}", exc_info=True)
        import traceback
        logging.error(traceback.format_exc())

    logging.info(f"[{symbol}] 本次处理完成\n")

def monitor_signal_strength(symbol, df, signal_strength, direction, long_strength, short_strength):
    signal_threshold = RISK_PARAMS.get("signal_threshold", 0.20)
    
    distance_to_threshold = 0
    if direction == "long":
        distance_to_threshold = (signal_strength - signal_threshold) / signal_threshold
    elif direction == "short":
        short_threshold = abs(RISK_PARAMS.get("short_signal_threshold", -0.20))
        distance_to_threshold = (signal_strength - short_threshold) / short_threshold
    
    if distance_to_threshold >= 0:
        logging.info(f"🎯 {symbol} 信号强度达标 - 方向: {direction}, 强度: {signal_strength:.3f}")
    elif distance_to_threshold >= -0.1:
        logging.info(f"🔔 {symbol} 信号强度接近阈值 (>{abs(distance_to_threshold)*100:.1f}%) - 方向: {direction}")
        logging.info(f"   当前强度: {signal_strength:.3f}, 需要: {signal_threshold:.3f}")
        logging.info(f"   多空分布: 多头={long_strength:.3f}, 空头={short_strength:.3f}")
    elif distance_to_threshold >= -0.3:
        logging.info(f"📈 {symbol} 信号强度中等 (>{abs(distance_to_threshold)*100:.1f}%) - 方向: {direction}")
    elif distance_to_threshold >= -0.5:
        logging.debug(f"📊 {symbol} 信号强度一般 (>{abs(distance_to_threshold)*100:.1f}%) - 方向: {direction}")

def log_signal_components(symbol, components):
    if sum(components.values()) > 0.3:
        logging.debug(f"🔧 {symbol} 信号组成:")
        for component, value in components.items():
            if value > 0.1:
                logging.debug(f"   {component}: {value:.3f}")

def check_smart_take_profit(symbol, df, position, current_signal_strength, current_direction):
    try:
        from config.constants import SMART_TAKE_PROFIT
        
        current_price = df.iloc[-1]["close"]
        open_price = position["open_price"]
        side = position.get("side", "long")
        leverage = position.get("leverage", 1)
        
        if side == "long":
            price_profit_ratio = (current_price - open_price) / open_price
            account_profit_ratio = price_profit_ratio * leverage
        else:
            price_profit_ratio = (open_price - current_price) / open_price
            account_profit_ratio = price_profit_ratio * leverage
        
        take_profit_reached = False
        take_profit_level = 0
        
        TAKE_PROFIT1_ACCOUNT = TAKE_PROFIT1 * leverage
        TAKE_PROFIT2_ACCOUNT = TAKE_PROFIT2 * leverage
        TAKE_PROFIT3_ACCOUNT = TAKE_PROFIT3 * leverage
        
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
            
        from modules.enhanced_strategy import enhanced_strategy
        support_strength, support_price, resistance_strength, resistance_price = enhanced_strategy.calculate_enhanced_support_resistance(df, symbol)
        
        action = None
        close_reason = None
        close_ratio = 1.0
        
        if current_signal_strength > SMART_TAKE_PROFIT["strong_signal_threshold"] and \
            account_profit_ratio >= SMART_TAKE_PROFIT["min_rollover_profit"] and \
            current_direction == side:
            action = "rollover"
            close_reason = "strong_signal_rollover"
        elif current_signal_strength < SMART_TAKE_PROFIT["weak_signal_threshold"]:
            action = "close"
            close_reason = "weak_signal_take_profit"
            close_ratio = 1.0
        else:
            action = "partial_close"
            close_reason = f"partial_take_profit_level_{take_profit_level}"
            
            if take_profit_level == 1:
                close_ratio = SMART_TAKE_PROFIT["partial_profit_ratios"][0]
            elif take_profit_level == 2:
                close_ratio = SMART_TAKE_PROFIT["partial_profit_ratios"][1]
            else:
                close_ratio = SMART_TAKE_PROFIT["partial_profit_ratios"][2]
            
            if resistance_strength > 0.7 and abs(current_price - resistance_price) / current_price < 0.01:
                close_ratio = min(close_ratio + 0.2, 1.0)
                close_reason += "_near_resistance"
        
        logging.info(f"智能止盈决策 - {symbol}: 动作={action}, 比例={close_ratio}, 账户盈利={account_profit_ratio*100:.1f}%")
        
        return True, action, close_ratio, close_reason
        
    except Exception as e:
        logging.error(f"智能止盈判断失败: {e}")
        return False, None, None, None

def check_float_loss_add_condition(symbol, df, position, current_signal_strength, current_direction):
    try:
        from config.constants import FLOAT_LOSS_ADD
        
        if not FLOAT_LOSS_ADD["enabled"]:
            return False, None
        
        if position.get("add_position_count", 0) >= FLOAT_LOSS_ADD["max_add_times"]:
            return False, "max_add_times_reached"
        
        current_price = df.iloc[-1]["close"]
        open_price = position["open_price"]
        side = position.get("side", "long")
        
        if side == "long":
            loss_ratio = (open_price - current_price) / open_price
        else:
            loss_ratio = (current_price - open_price) / open_price
        
        if loss_ratio < FLOAT_LOSS_ADD["loss_threshold"]:
            return False, f"loss_ratio_{loss_ratio:.3f}_below_threshold"
        
        if current_signal_strength < FLOAT_LOSS_ADD["signal_requirement"]:
            return False, f"signal_strength_{current_signal_strength:.3f}_below_requirement"
        
        if current_direction != side:
            return False, "direction_mismatch"
        
        from modules.enhanced_strategy import enhanced_strategy
        support_strength, support_price, _, _ = enhanced_strategy.calculate_enhanced_support_resistance(df, symbol)
        
        if support_strength < FLOAT_LOSS_ADD["support_requirement"]:
            return False, f"support_strength_{support_strength:.3f}_below_requirement"
        
        distance_to_support = abs(current_price - support_price) / current_price
        if distance_to_support > 0.03:
            return False, f"too_far_from_support_{distance_to_support:.3f}"
        
        add_ratio = min(FLOAT_LOSS_ADD["max_add_ratio"], loss_ratio * 2)
        add_ratio = max(add_ratio, 0.1)
        
        logging.info(f"浮亏加仓条件满足 - {symbol}: 亏损={loss_ratio:.3f}, 支撑强度={support_strength:.3f}, 加仓比例={add_ratio:.3f}")
        
        return True, add_ratio
        
    except Exception as e:
        logging.error(f"浮亏加仓条件检查失败: {e}")
        return False, None

def execute_float_loss_add(symbol, add_ratio):
    try:
        positions = strategy_state.get("positions", {})
        if symbol not in positions:
            return False
        
        position = positions[symbol]
        current_price = get_realtime_price(symbol)
        
        if not current_price or current_price <= 0:
            return False
        
        original_size = position["size"]
        add_size = original_size * add_ratio
        
        tradable_balance = get_tradable_balance()
        required_margin = add_size * current_price / position.get("leverage", 1)
        
        if required_margin > tradable_balance:
            logging.warning(f"加仓资金不足: 需要{required_margin:.2f}, 可用{tradable_balance:.2f}")
            return False
        
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
            new_size = original_size + add_size
            new_open_price = (original_size * position["open_price"] + add_size * current_price) / new_size
            
            position["size"] = new_size
            position["open_price"] = new_open_price
            position["add_position_count"] = position.get("add_position_count", 0) + 1
            position["add_position_time"] = time.time()
            position["total_margin"] = position.get("total_margin", 0) + required_margin
            
            if position.get("side", "long") == "long":
                position["initial_stop"] = new_open_price * (1 - STOP_LOSS_INIT)
                position["current_stop"] = new_open_price * (1 - STOP_LOSS_INIT)
            else:
                position["initial_stop"] = new_open_price * (1 + STOP_LOSS_INIT)
                position["current_stop"] = new_open_price * (1 + STOP_LOSS_INIT)
            
            logging.info(f"[浮亏加仓成功] {symbol} | 加仓比例: {add_ratio:.3f} | "
                        f"新仓位: {new_size:.6f} | 新开仓价: {new_open_price:.6f}")
            
            recalculate_asset_allocation()
            return True
        else:
            logging.error(f"浮亏加仓失败: {symbol}")
            return False
            
    except Exception as e:
        logging.error(f"执行浮亏加仓失败: {e}")
        return False

def check_enhanced_exit_signals(symbol, df):
    positions = strategy_state.get("positions", {})
    if symbol not in positions:
        return False, None
        
    position = positions[symbol]
    current_price = df.iloc[-1]["close"]
    
    current_signal_ok, _, current_signal_strength, current_direction = check_enhanced_multi_signal(symbol)
    
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
    
    should_stop, stop_reason = check_stop_loss_conditions(symbol, df, position)
    if should_stop:
        return True, stop_reason
    
    if FLOAT_LOSS_ADD["enabled"]:
        add_condition_met, add_ratio_or_reason = check_float_loss_add_condition(
            symbol, df, position, current_signal_strength, current_direction
        )
        
        if add_condition_met and isinstance(add_ratio_or_reason, float):
            if execute_float_loss_add(symbol, add_ratio_or_reason):
                return False, None
    
    return False, None

def check_stop_loss_conditions(symbol, df, position):
    current_price = df.iloc[-1]["close"]
    open_price = position["open_price"]
    side = position.get("side", "long")
    leverage = position.get("leverage", 1)
    
    if side == "long":
        account_profit_ratio = ((current_price - open_price) / open_price) * leverage
    else:
        account_profit_ratio = ((open_price - current_price) / open_price) * leverage
    
    if "peak_profit" not in position:
        position["peak_profit"] = account_profit_ratio
    
    if account_profit_ratio > position["peak_profit"]:
        position["peak_profit"] = account_profit_ratio
    
    drawdown_from_peak = position["peak_profit"] - account_profit_ratio
    
    if position["peak_profit"] >= 0.08 and drawdown_from_peak >= 0.12:
        return True, f"trailing_stop_{drawdown_from_peak*100:.1f}%_from_peak_{position['peak_profit']*100:.1f}%"

    if account_profit_ratio <= -0.08:
        if position.get("first_stop_done", False) == False:
            position["first_stop_done"] = True
            return True, f"first_stop_30%_at_{account_profit_ratio*100:.1f}%"
    
    if account_profit_ratio <= -0.12:
        if position.get("second_stop_done", False) == False:
            position["second_stop_done"] = True
            return True, f"second_stop_40%_at_{account_profit_ratio*100:.1f}%"
    
    if account_profit_ratio <= -0.15:
        return True, f"final_stop_100%_at_{account_profit_ratio*100:.1f}%"
    
    return False, None

def execute_partial_close(symbol, close_ratio, reason):
    try:
        positions = strategy_state.get("positions", {})
        if symbol not in positions:
            return False
        
        position = positions[symbol]
        current_price = get_optimal_exit_price(symbol, position["open_price"])
        
        if current_price is None or current_price <= 0:
            return False
        
        close_size = position["size"] * close_ratio
        remaining_size = position["size"] - close_size
        
        if close_size < 0.001:
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
            position["size"] = remaining_size
            position["remaining"] = remaining_size / (position["size"] + close_size)
            
            if position.get("side", "long") == "long":
                profit_loss = (current_price - position["open_price"]) * close_size
            else:
                profit_loss = (position["open_price"] - current_price) * close_size
            
            logging.info(f"[分批平仓成功] {symbol} | 比例: {close_ratio:.3f} | "
                        f"平仓数量: {close_size:.6f} | 剩余数量: {remaining_size:.6f} | "
                        f"盈亏: {profit_loss:+.2f} USDT | 原因: {reason}")
            
            if remaining_size < 0.001:
                from core.state_manager import remove_position
                remove_position(symbol)
                logging.info(f"{symbol} 剩余仓位过小，已全平")
            else:
                recalculate_asset_allocation()
            
            return True
        else:
            logging.error(f"分批平仓失败: {symbol}")
            return False
            
    except Exception as e:
        logging.error(f"执行分批平仓失败: {e}")
        return False
    
def close_position(symbol, reason):
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
    try:
        realtime_price = get_realtime_price(symbol)
        if not realtime_price or realtime_price <= 0:
            return None
            
        depth_price = get_depth_based_price(symbol, "sell")
        
        if depth_price and depth_price > 0:
            base_price = depth_price
        else:
            base_price = realtime_price
        
        final_price = base_price * 0.999
        
        logging.info(f"平仓价格优化 - 基础价: {base_price:.6f}, 最终价: {final_price:.6f}")
        return final_price
        
    except Exception as e:
        logging.error(f"获取平仓价格失败: {e}")
        return None

def check_rollover_conditions(symbol, df):
    positions = strategy_state.get("positions", {})
    if symbol not in positions:
        return False, None
        
    position = positions[symbol]
    
    if position.get("rollover_count", 0) >= MAX_ROLL_TIMES:
        return False, None
        
    current_price = df.iloc[-1]["close"]
    open_price = position["open_price"]
    side = position.get("side", "long")
    
    if side == "long":
        profit_ratio = (current_price - open_price) / open_price
    else:
        profit_ratio = (open_price - current_price) / open_price
    
    if profit_ratio >= ROLL_PROFIT_THRESHOLD:
        signal_ok, _, signal_strength, current_direction = check_enhanced_multi_signal(symbol)
        
        direction_match = (current_direction == side)
        
        if signal_ok and signal_strength > ROLL_SIGNAL_THRESHOLD and direction_match:
            logging.info(f"{symbol} 达到滚仓条件，盈利: {profit_ratio*100:.2f}%, "
                        f"信号强度: {signal_strength:.2f}, 方向匹配: {direction_match}")
            return True, "profit_rollover"
    
    if "SWAP" in symbol:
        funding_signal, funding_confidence = funding_analyzer.analyze_funding_rate_signal(symbol)
        
        funding_match = (
            (funding_signal > 0 and side == "long") or 
            (funding_signal < 0 and side == "short")
        )
        
        if funding_match and funding_confidence > 0.7 and profit_ratio > 0.05:
            logging.info(f"{symbol} 资金费率有利，考虑滚仓")
            return True, "funding_rollover"
    
    volatility = df["close"].tail(20).std() / df["close"].tail(20).mean()
    if volatility < 0.03 and profit_ratio > 0.08:
        signal_ok, _, signal_strength, current_direction = check_enhanced_multi_signal(symbol)
        if signal_ok and current_direction == side:
            logging.info(f"{symbol} 低波动环境，考虑滚仓降低风险")
            return True, "volatility_rollover"
    
    return False, None

def execute_rollover(symbol, reason):
    positions = strategy_state.get("positions", {})
    if symbol not in positions:
        return False
        
    position = positions[symbol]
    
    if position.get("rollover_count", 0) >= MAX_ROLL_TIMES:
        logging.info(f"{symbol} 已达到最大滚仓次数 {MAX_ROLL_TIMES}，停止滚仓")
        return False
        
    current_price = get_realtime_price(symbol)
    if not current_price or current_price <= 0:
        return False
        
    if position.get("side", "long") == "long":
        profit = (current_price - position["open_price"]) * position["size"]
    else:
        profit = (position["open_price"] - current_price) * position["size"]
    
    rollover_count = position.get("rollover_count", 0)
    profit_ratio = ROLL_USE_PROFIT_RATIO * (1 - rollover_count * 0.2)
    profit_ratio = max(0.2, profit_ratio)
    
    rollover_amount = profit * profit_ratio
    
    if close_position(symbol, f"rollover_{reason}"):
        new_position_size = rollover_amount / current_price
        
        signal_ok, df, signal_strength, direction = check_enhanced_multi_signal(symbol)
        if signal_ok and direction == position.get("side", "long"):
            entry_price = get_optimal_entry_price(symbol, current_price, signal_strength, direction, df)
            trade_side = "buy" if direction == "long" else "sell"
            
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
                new_rollover_count = rollover_count + 1
                
                if direction == "long":
                    initial_stop = entry_price * (1 - STOP_LOSS_INIT)
                else:
                    initial_stop = entry_price * (1 + STOP_LOSS_INIT)
                
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
            from modules.technical_analysis import get_kline_data
            df = get_kline_data(symbol, "1H", 50)
            
            if df is not None and not df.empty:
                process_symbol(symbol)
                
        except Exception as e:
            logging.error(f"检查{symbol}平仓条件失败: {e}")

def check_margin_requirements(symbol, quantity, price, leverage):
    try:
        account_api = core.api_client.account_api
        
        contract_value = quantity * price
        required_margin = contract_value / leverage
        
        response = account_api.get_account_balance(ccy="USDT")
        if response and response.get("code") == "0" and response.get("data"):
            data = response["data"][0]
            if "details" in data and data["details"]:
                for detail in data["details"]:
                    if detail.get("ccy") == "USDT":
                        available_balance = float(detail.get("availBal", 0))
                        
                        if available_balance < required_margin:
                            logging.error(f"❌ 保证金不足: 需要 {required_margin:.2f} USDT, 可用 {available_balance:.2f} USDT")
                            return False
                        
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
    try:
        coin = symbol.split("-")[0]
        
        coin_total_value = get_coin_total_position_value(coin)
        total_equity = get_total_equity()
        
        if total_equity <= 0:
            return False, 0
            
        current_ratio = coin_total_value / total_equity
        target_ratio = 0.10
        
        if current_ratio >= target_ratio:
            return False, 0
            
        if signal_strength < 0.6:
            return False, 0
            
        available_value = total_equity * target_ratio - coin_total_value
        if available_value <= 0:
            return False, 0
            
        current_price = df.iloc[-1]["close"]
        contract_value = get_contract_value(symbol)
        one_contract_value = contract_value * current_price
        
        if one_contract_value <= 0:
            return False, 0
            
        max_add_contracts = available_value / one_contract_value
        
        add_ratio = min(0.3, (signal_strength - 0.6) / 0.4)
        add_contracts = max_add_contracts * add_ratio
        
        add_contracts = adjust_position_to_lot_size(symbol, add_contracts)
        
        min_contract_size = get_min_contract_size(symbol)
        if add_contracts < min_contract_size:
            return False, 0
            
        return True, add_contracts
        
    except Exception as e:
        logging.error(f"检查加仓条件失败 {symbol}: {e}")
        return False, 0

def execute_position_addition(symbol, add_contracts, direction, current_price, signal_strength):
    try:
        logging.info(f"🎯 {symbol} 执行加仓 - 方向: {direction}, 张数: {add_contracts}, 价格: {current_price:.6f}")
        
        side_map = {'long': 'buy', 'short': 'sell'}
        pos_side_map = {'long': 'long', 'short': 'short'}
        
        side = side_map[direction]
        posSide = pos_side_map[direction]
        
        positions = strategy_state.get("positions", {})
        leverage = positions.get(symbol, {}).get("leverage", 3) if symbol in positions else 3
        
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
            if symbol in positions:
                position = positions[symbol]
                old_size = position["size"]
                old_price = position["open_price"]
                new_size = old_size + add_contracts
                new_avg_price = (old_size * old_price + add_contracts * current_price) / new_size
                
                position["size"] = new_size
                position["open_price"] = new_avg_price
                position["notional_value"] = new_size * get_contract_value(symbol) * new_avg_price
                position["margin"] = position["notional_value"] / leverage
                position["add_count"] = position.get("add_count", 0) + 1
                position["last_add_time"] = time.time()
                
                logging.info(f"✅ {symbol} 加仓成功 - 新仓位: {new_size}张, 平均价格: {new_avg_price:.6f}")
                
                recalculate_asset_allocation()
                return True
                
        return False
        
    except Exception as e:
        logging.error(f"❌ {symbol} 加仓异常: {str(e)}")
        return False