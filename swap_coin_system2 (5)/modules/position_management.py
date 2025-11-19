import logging
from core.state_manager import strategy_state, get_tradable_balance, get_position_value, get_total_equity
from config.constants import (
    LOW_VOLATILITY_THRESHOLD, HIGH_VOLATILITY_THRESHOLD,
    LEVERAGE_LOW_VOL, LEVERAGE_HIGH_VOL,
    MAX_SWAP_MARGIN_RATIO, RISK_PARAMS, SWAP_STOP_LOSS
)
from utils.instrument_utils import adjust_quantity_precision, validate_order_parameters, get_min_contract_size

def get_volatility_level(df):
    """获取波动率等级"""
    if df is None or len(df) < 14:
        return 1
    atr = df.iloc[-1].get("atr", 0.01)
    if atr <= LOW_VOLATILITY_THRESHOLD:
        return 0
    elif atr > HIGH_VOLATILITY_THRESHOLD:
        return 2
    else:
        return 1

def get_leverage(vol_level, signal_confidence):
    """获取杠杆倍数 - 只用于合约，返回整数"""
    if vol_level == 0:
        min_lev, max_lev = LEVERAGE_LOW_VOL
    else:
        min_lev, max_lev = LEVERAGE_HIGH_VOL
    
    base_leverage = min_lev + (max_lev - min_lev) * signal_confidence
    aggressive_factor = 1.0
    leverage = round(base_leverage * aggressive_factor, 0)
    
    # 确保返回整数，且在合理范围内
    return int(min(max(leverage, 1), 5))  # 1-5倍杠杆


# 在 position_management.py 中添加函数

def get_contract_value(symbol):
    """获取合约面值 - 从API获取真实数据"""
    try:
        from utils.instrument_utils import get_instrument_info
        info = get_instrument_info(symbol)
        if info and "ctVal" in info:
            ct_val = float(info["ctVal"])
            ct_val_ccy = info.get("ctValCcy", "USD")
            logging.debug(f"{symbol} 合约面值: {ct_val} {ct_val_ccy}")
            return ct_val
        
        # 后备方案：常见币种的默认合约面值
        default_values = {
            "BTC-USDT-SWAP": 0.01,   # 0.01 BTC
            "ETH-USDT-SWAP": 0.1,    # 0.1 ETH
            "ADA-USDT-SWAP": 10,     # 10 ADA - 这个可能很大
            "XRP-USDT-SWAP": 10,     # 10 XRP
            "TRX-USDT-SWAP": 100,    # 100 TRX
            "SAND-USDT-SWAP": 10,    # 10 SAND
            "ALGO-USDT-SWAP": 10,    # 10 ALGO
            "SOL-USDT-SWAP": 1,      # 1 SOL
            "DOT-USDT-SWAP": 1,      # 1 DOT
            "DOGE-USDT-SWAP": 100,   # 100 DOGE
        }
        default_value = default_values.get(symbol, 1)
        logging.warning(f"{symbol} 使用默认合约面值: {default_value}")
        return default_value
    except Exception as e:
        logging.error(f"获取{symbol}合约面值失败: {e}")
        return 1.0


def get_coin_total_position_value(coin):
    """获取同一币种的总仓位价值 - 优化版本"""
    positions = strategy_state.get("positions", {})
    total_value = 0
    
    for symbol, position in positions.items():
        position_coin = position.get("coin")
        # 确保coin字段存在且匹配，同时检查交易对前缀
        if position_coin and position_coin == coin:
            total_value += position.get("notional_value", 0)
        elif coin in symbol:  # 后备检查
            total_value += position.get("notional_value", 0)
    
    return total_value

def calculate_position_size(symbol, current_price, df, signal_strength, direction):
    """计算仓位大小 - 添加详细日志"""
    logging.info(f"🧮 {symbol} 开始仓位计算:")
    logging.info(f"   当前价格: {current_price:.6f}")
    logging.info(f"   信号强度: {signal_strength:.3f}")
    logging.info(f"   方向: {direction}")
    
    coin = symbol.split("-")[0]
    
    # 获取同币种总仓位价值
    coin_total_value = get_coin_total_position_value(coin)
    total_equity = get_total_equity()
    
    logging.info(f"   同币种仓位: {coin_total_value:.2f} / {total_equity:.2f} = {(coin_total_value/total_equity*100):.1f}%")
    
    # 如果同币种仓位已超过10%，不允许再开仓
    if total_equity > 0 and coin_total_value / total_equity > 0.10:
        logging.info(f"⏸️ {coin} 同币种总仓位已超过10% ({coin_total_value:.2f}/{total_equity:.2f})，跳过{symbol}开仓")
        return 0, 1
    
    # 获取最小张数和合约面值
    min_contract_size = get_min_contract_size(symbol)
    contract_value = get_contract_value(symbol)
    
    logging.info(f"   最小张数: {min_contract_size}")
    logging.info(f"   合约面值: {contract_value}")
    
    tradable_balance = get_tradable_balance()
    logging.info(f"   可交易余额: {tradable_balance:.2f} USDT")
    
    # 严格的可交易余额检查
    if tradable_balance < 2:  # 至少需要2 USDT，考虑手续费等
        logging.info(f"⏸️ {symbol} 可交易余额不足: {tradable_balance:.2f} USDT")
        return 0, 1
    
    # 只处理合约
    is_swap = "SWAP" in symbol
    if not is_swap:
        return 0, 1
    
    vol_level = get_volatility_level(df)
    leverage = get_leverage(vol_level, signal_strength)
    
    base_risk = RISK_PARAMS.get("base_risk_per_trade", 0.05)
    dynamic_risk = base_risk * (1 + signal_strength * 0.5)
    
    if vol_level == 2:
        leverage = max(1, leverage // 2)
    
    # 使用可交易金额计算风险金额，但不超过总资金的15%
    max_risk_amount = min(tradable_balance * dynamic_risk, 
                         total_equity * 0.15)
    
    logging.info(f"   波动率等级: {vol_level}")
    logging.info(f"   杠杆: {leverage}x")
    logging.info(f"   基础风险: {base_risk}")
    logging.info(f"   动态风险: {dynamic_risk}")
    logging.info(f"   最大风险金额: {max_risk_amount:.2f} USDT")
    
    # 计算一张合约的价值
    one_contract_value = contract_value * current_price
    logging.info(f"   单张合约价值: {one_contract_value:.2f} USDT")
    
    # 确保风险金额至少能开最小张数
    min_required_margin = (min_contract_size * one_contract_value) / leverage
    if max_risk_amount < min_required_margin:
        logging.info(f"⏸️ {symbol} 风险金额不足: {max_risk_amount:.2f} < {min_required_margin:.2f}")
        return 0, leverage
    
    # 使用合约止损比例
    stop_loss_ratio = SWAP_STOP_LOSS
    logging.info(f"   止损比例: {stop_loss_ratio}")
    
    # 计算基于风险的基础张数
    base_contracts = max_risk_amount / stop_loss_ratio / one_contract_value
    logging.info(f"   基础张数: {base_contracts:.2f}")
    
    # 合约仓位计算 - 基于保证金
    max_margin = tradable_balance * MAX_SWAP_MARGIN_RATIO
    max_contracts_by_margin = (max_margin * leverage) / one_contract_value
    
    logging.info(f"   最大保证金: {max_margin:.2f} USDT")
    logging.info(f"   保证金限制最大张数: {max_contracts_by_margin:.2f}")
    
    # 取基础数量和最大数量中的较小值
    position_size = min(base_contracts, max_contracts_by_margin)
    logging.info(f"   初步计算张数: {position_size:.2f}")
    
    # 确保不低于最小张数
    if position_size < min_contract_size:
        logging.info(f"⏸️ {symbol} 计算仓位小于最小张数: {position_size:.2f} < {min_contract_size}")
        return 0, leverage
    
    # 调整到正确的精度
    position_size = adjust_position_to_lot_size(symbol, position_size)
    logging.info(f"   精度调整后张数: {position_size}")
    
    # 计算名义价值和保证金
    notional_value = position_size * one_contract_value
    margin_used = notional_value / leverage
    
    logging.info(f"   名义价值: {notional_value:.2f} USDT")
    logging.info(f"   所需保证金: {margin_used:.2f} USDT")
    
    # 检查新开仓后同币种总仓位是否超过10%
    new_coin_total_value = coin_total_value + notional_value
    if total_equity > 0 and new_coin_total_value / total_equity > 0.10:
        # 调整仓位大小，确保不超过10%
        max_coin_value = total_equity * 0.10
        available_coin_value = max(0, max_coin_value - coin_total_value)
        
        if available_coin_value <= 0:
            return 0, leverage
            
        # 重新计算仓位大小
        position_size = available_coin_value / one_contract_value
        position_size = adjust_position_to_lot_size(symbol, position_size)
        
        # 确保不低于最小张数
        if position_size < min_contract_size:
            return 0, leverage
        
        notional_value = position_size * one_contract_value
        margin_used = notional_value / leverage
        
        logging.info(f"   调整至同币种10%限制内: {position_size}张")
    
    # 再次检查仓位是否超过总资金的15%
    if notional_value > total_equity * 0.15:
        max_notional_value = total_equity * 0.15
        max_position_size = max_notional_value / one_contract_value
        position_size = adjust_position_to_lot_size(symbol, max_position_size)
        
        if position_size < min_contract_size:
            return 0, leverage
            
        notional_value = position_size * one_contract_value
        margin_used = notional_value / leverage
        logging.info(f"   调整至总资金的15%以内: {position_size}张")
    
    # 检查保证金是否足够
    if margin_used > tradable_balance:
        logging.info(f"⏸️ {symbol} 保证金不足: {margin_used:.2f} > {tradable_balance:.2f}")
        return 0, leverage
    
    logging.info(f"✅ {symbol} 仓位计算完成: 张数={position_size}, 杠杆={leverage}x")
    return position_size, leverage



def can_open_new_position(symbol, position_size, current_price, leverage):
    """检查是否可以开新仓位 - 只处理合约"""
    tradable_balance = get_tradable_balance()
    
    # 只处理合约
    required_margin = position_size * current_price / leverage
    
    if required_margin > tradable_balance:
        logging.warning(f"所需保证金 {required_margin:.2f} 超过可交易金额 {tradable_balance:.2f}")
        return False
    
    total_balance = strategy_state.get("last_balance", 0)
    
    if total_balance >= 150 and RISK_PARAMS.get("enable_risk_limit", False):
        max_portfolio_risk = RISK_PARAMS.get("max_portfolio_risk", 0.5)
        current_risk_ratio = get_position_value() / total_balance if total_balance > 0 else 0
        new_risk_ratio = current_risk_ratio + (required_margin / total_balance)
        
        if new_risk_ratio > max_portfolio_risk:
            logging.warning(f"超过最大组合风险限制: {new_risk_ratio:.2%} > {max_portfolio_risk:.2%}")
            return False
    
    return True


# 在 position_management.py 末尾添加

def get_contract_value(symbol):
    """获取合约面值 - 修复版本"""
    try:
        from utils.instrument_utils import get_instrument_info
        info = get_instrument_info(symbol)
        if info and "ctVal" in info:
            ct_val_str = info["ctVal"]
            try:
                ct_val = float(ct_val_str)
                logging.debug(f"{symbol} 合约面值: {ct_val} (来自API)")
                return ct_val
            except ValueError:
                logging.warning(f"{symbol} 合约面值转换失败: {ct_val_str}")
        
        # 后备方案：常见币种的默认合约面值
        default_values = {
            "BTC-USDT-SWAP": 0.01,   # 0.01 BTC
            "ETH-USDT-SWAP": 0.1,    # 0.1 ETH
            "ADA-USDT-SWAP": 10,     # 10 ADA
            "XRP-USDT-SWAP": 10,     # 10 XRP
            "TRX-USDT-SWAP": 100,    # 100 TRX
            "SAND-USDT-SWAP": 10,    # 10 SAND
            "ALGO-USDT-SWAP": 10,    # 10 ALGO
            "SOL-USDT-SWAP": 1,      # 1 SOL
            "DOT-USDT-SWAP": 1,      # 1 DOT
            "DOGE-USDT-SWAP": 100,   # 100 DOGE
            "LTC-USDT-SWAP": 0.1,    # 0.1 LTC
            "BNB-USDT-SWAP": 0.01,   # 0.01 BNB
            "AVAX-USDT-SWAP": 0.1,   # 0.1 AVAX
            "LINK-USDT-SWAP": 0.1,   # 0.1 LINK
            "BCH-USDT-SWAP": 0.01,   # 0.01 BCH
            "ATOM-USDT-SWAP": 0.1,   # 0.1 ATOM
            "FIL-USDT-SWAP": 0.1,    # 0.1 FIL
            "XLM-USDT-SWAP": 10,     # 10 XLM
            "XTZ-USDT-SWAP": 1,      # 1 XTZ
            "HBAR-USDT-SWAP": 100,   # 100 HBAR
            "TON-USDT-SWAP": 0.1,    # 0.1 TON
        }
        default_value = default_values.get(symbol, 1)
        logging.warning(f"{symbol} 使用默认合约面值: {default_value}")
        return default_value
    except Exception as e:
        logging.error(f"获取{symbol}合约面值失败: {e}")
        return 1.0

def adjust_position_to_lot_size(symbol, position_size):
    """调整仓位到lotSize的整数倍 - 修复版本"""
    from utils.instrument_utils import get_lot_size, get_min_contract_size
    
    lot_size = get_lot_size(symbol)
    min_size = get_min_contract_size(symbol)
    
    # 确保不低于最小张数
    position_size = max(min_size, position_size)
    
    # 调整到lotSize的整数倍
    if lot_size > 0:
        # 计算最接近的lotSize倍数
        adjusted = round(position_size / lot_size) * lot_size
        adjusted = max(min_size, adjusted)
    else:
        adjusted = max(min_size, round(position_size))
    
    # 根据lotSize调整类型
    if lot_size >= 1:
        adjusted = int(adjusted)
    
    logging.debug(f"仓位调整: {symbol} 原始={position_size:.4f}, 调整后={adjusted}")
    return adjusted