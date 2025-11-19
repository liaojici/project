import time
import logging
from config.constants import STOP_LOSS_ON_50_PERCENT_LOSS, MAX_ACCOUNT_DD
from utils.common_utils import safe_float_convert, format_currency, calculate_percentage_change,format_percentage

# 策略状态
strategy_state = {
    "selected_symbols": [],
    "last_selection_time": 0,
    "positions": {},
    "initial_balance": None,
    "last_balance": None,
    "initial_equity": None,
    "last_equity": None,
    "tradable_balance": 0.0, # 默认浮点数
    "position_value": 0.0,
    "manual_positions_value": 0.0,
    "auto_positions_value": 0.0,
    "running": True,
    "pending_orders": {},
    "low_balance_mode": False,
    "low_balance_threshold": 3.0
}

def save_pending_orders():
    from modules.trading_execution import pending_orders
    strategy_state["pending_orders"] = pending_orders

def load_pending_orders():
    from modules.trading_execution import pending_orders
    pending_orders.update(strategy_state.get("pending_orders", {}))

def sync_manual_positions():
    try:
        import core.api_client # 动态导入避免循环引用
        account_api = core.api_client.account_api
        
        if account_api is None:
            logging.warning("账户API未初始化，无法同步手动仓位")
            return
            
        response = account_api.get_positions()
        if response and response.get("code") == "0" and response.get("data"):
            manual_positions = {}
            manual_value = 0.0
            
            for position in response["data"]:
                try:
                    pos_str = position.get("pos", "0")
                    pos = safe_float_convert(pos_str, 0)
                    
                    if pos != 0:
                        symbol = position.get("instId", "")
                        inst_type = position.get("instType", "")
                        
                        if symbol and inst_type == "SWAP":
                            coin = symbol.split("-")[0]
                            avg_px = safe_float_convert(position.get("avgPx", "0"), 0)
                            if avg_px == 0:
                                avg_px = safe_float_convert(position.get("markPx", "0"), 0)
                                
                            margin = safe_float_convert(position.get("margin", "0"), 0)
                            lever = safe_float_convert(position.get("lever", "1"), 1)
                            notional_usd = safe_float_convert(position.get("notionalUsd", "0"), 0)
                            
                            if margin == 0 and notional_usd > 0 and lever > 0:
                                margin = notional_usd / lever
                            
                            entry_time = time.time() # 简化处理
                            side = "long" if pos > 0 else "short"
                            size = abs(pos)
                                
                            manual_positions[symbol] = {
                                "open_price": avg_px,
                                "size": size,
                                "leverage": lever,
                                "margin": margin,
                                "notional_value": notional_usd,
                                "entry_time": entry_time,
                                "side": side,
                                "inst_type": inst_type,
                                "coin": coin,
                                "manual": True,
                                "remaining": 1.0
                            }
                            
                            manual_value += margin
                            logging.debug(f"成功接管手动仓位: {symbol}")
                            
                except Exception as e:
                    logging.warning(f"处理仓位数据错误 {position.get('instId')}: {e}")
                    continue
            
            strategy_state["positions"] = manual_positions # 更新
            strategy_state["manual_positions_value"] = manual_value
            
            if manual_positions:
                logging.info(f"✅ 同步 {len(manual_positions)} 个手动仓位，保证金: {manual_value:.2f} USDT")
            
            recalculate_asset_allocation()
                
    except Exception as e:
        logging.error(f"同步手动仓位失败: {e}")

def get_pending_orders_margin():
    try:
        import core.api_client
        trade_api = core.api_client.trade_api
        if trade_api is None:
            return 0.0
            
        response = trade_api.get_order_list(instType="SWAP")
        if not response or response.get("code") != "0":
            return 0.0
            
        pending_margin = 0.0
        for order in response.get("data", []):
            if order.get("state") in ["live", "partially_filled"]:
                sz = safe_float_convert(order.get("sz", 0))
                px = safe_float_convert(order.get("px", 0))
                lever = safe_float_convert(order.get("lever", 1))
                if sz > 0 and px > 0:
                    pending_margin += (sz * px) / lever
        return pending_margin
    except Exception:
        return 0.0

def recalculate_asset_allocation():
    try:
        import core.api_client
        current_balance = core.api_client.get_account_balance()
        
        # 重新计算仓位保证金
        manual_value = 0.0
        auto_value = 0.0
        total_position_margin = 0.0
        
        for symbol, position in strategy_state["positions"].items():
            margin = position.get("margin", 0)
            if position.get("manual", False):
                manual_value += margin
            else:
                auto_value += margin
            total_position_margin += margin
        
        strategy_state["manual_positions_value"] = manual_value
        strategy_state["auto_positions_value"] = auto_value
        
        pending_orders_value = get_pending_orders_margin()
        
        total_occupied = total_position_margin + pending_orders_value
        strategy_state["position_value"] = total_occupied
        strategy_state["tradable_balance"] = max(0.0, current_balance - total_occupied)
        strategy_state["last_equity"] = current_balance
        
        if strategy_state["initial_equity"] is None and current_balance > 0:
            strategy_state["initial_equity"] = current_balance
            
        logging.info(f"资产分配 - 总余额: {current_balance:.2f}, 可交易: {strategy_state['tradable_balance']:.2f}, 仓位保证金: {total_position_margin:.2f}")
                    
    except Exception as e:
        logging.error(f"计算资产分配失败: {e}")

def calculate_total_equity(current_balance):
    """计算总权益（余额 + 浮动盈亏）"""
    try:
        import core.api_client
        account_api = core.api_client.account_api
        if account_api is None:
            return current_balance
            
        response = account_api.get_account_balance(ccy="USDT")
        if response and response.get("code") == "0" and response.get("data"):
            data = response["data"][0]
            if "totalEq" in data and data["totalEq"]:
                return safe_float_convert(data["totalEq"], current_balance)
    except Exception:
        pass
    return current_balance

def check_50_percent_loss():
    current_equity = strategy_state.get("last_equity") or 0.0
    initial = strategy_state.get("initial_equity")
    if current_equity == 0 or not initial:
        return
    
    loss_ratio = (current_equity - initial) / initial
    if loss_ratio <= -0.5:
        logging.error(f"账户亏损已达{loss_ratio*100:.1f}%，触发熔断停止")
        strategy_state["running"] = False

def check_account_drawdown():
    current_equity = strategy_state.get("last_equity") or 0.0
    initial = strategy_state.get("initial_equity")
    if current_equity == 0 or not initial:
        return False
    
    max_dd = (initial - current_equity) / initial
    if max_dd >= MAX_ACCOUNT_DD:
        logging.warning(f"回撤 {max_dd*100:.2f}% 超过阈值")
        return True
    return False

def get_positions(): return strategy_state["positions"]

def update_position(symbol, position_data):
    strategy_state["positions"][symbol] = position_data
    recalculate_asset_allocation()

def remove_position(symbol):
    if symbol in strategy_state["positions"]:
        del strategy_state["positions"][symbol]
        recalculate_asset_allocation()

def get_tradable_balance():
    """安全获取可交易余额，确保返回浮点数"""
    return float(strategy_state.get("tradable_balance") or 0.0)

def get_position_value():
    return float(strategy_state.get("position_value") or 0.0)

def get_total_equity():
    """安全获取总权益，确保返回浮点数"""
    return float(strategy_state.get("last_equity") or 0.0)

def check_low_balance_mode():
    tradable = get_tradable_balance()
    threshold = strategy_state.get("low_balance_threshold", 3.0)
    
    is_low = tradable < threshold
    prev_is_low = strategy_state.get("low_balance_mode", False)
    
    if is_low != prev_is_low:
        if is_low:
            logging.info(f"💰 进入低余额模式 (余额: {tradable:.2f} < {threshold})")
        else:
            logging.info(f"💰 退出低余额模式 (余额: {tradable:.2f})")
            
    strategy_state["low_balance_mode"] = is_low
    return is_low

def get_position_symbols():
    return list(strategy_state.get("positions", {}).keys())

def is_in_low_balance_mode():
    return strategy_state.get("low_balance_mode", False)

__all__ = [
    'strategy_state', 'sync_manual_positions', 'recalculate_asset_allocation',
    'check_50_percent_loss', 'check_account_drawdown', 'get_positions',
    'update_position', 'remove_position', 'get_tradable_balance',
    'get_position_value', 'get_total_equity', 'check_low_balance_mode',
    'get_position_symbols', 'is_in_low_balance_mode'
]