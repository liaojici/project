# constants.py

# 策略核心参数
LOW_VOLATILITY_THRESHOLD = 0.02
HIGH_VOLATILITY_THRESHOLD = 0.05
MAX_ROLL_TIMES = 3
MAX_ACCOUNT_DD = 0.1
STOP_LOSS_ON_50_PERCENT_LOSS = 0.5
MARKET_CAP_RANK = 50
MIN_VOLUME_24H = 50000000
HOLDERS_GROWTH = 0.1
CHAIN_OUTFLOW_THRESHOLD = 0.03
STABLECOIN_GROWTH_THRESHOLD = 0.1
MVRV_UNDERVALUED = 1.0
FEAR_GREED_THRESHOLD = 25
COINBASE_PREMIUM_THRESHOLD = 0.1
VOLUME_MULTIPLE = 2
RSI_OVERSOLD = 30
RSI_OVERBOUGHT = 70
STOP_LOSS_FINAL = 200

# 止损参数 - 只保留合约
SWAP_STOP_LOSS = 0.15

# 平仓和滚仓参数
ROLL_PROFIT_THRESHOLD = 0.15
ROLL_USE_PROFIT_RATIO = 0.5
ROLL_SIGNAL_THRESHOLD = 0.6

# 止盈参数
TAKE_PROFIT1 = 0.15
TAKE_PROFIT2 = 0.35
TAKE_PROFIT3 = 0.75

# 移动止损参数
STOP_LOSS_MOVE = 0.10

# 策略核心参数 - 只保留合约相关
RISK_PARAMS = {
    # 基础风险参数
    "base_risk_per_trade": 0.05,
    "max_portfolio_risk": 0.80,
    "enable_risk_limit": False,
    
    # 杠杆调整 - 只用于合约
    "leverage_low_vol": (2, 4),
    "leverage_high_vol": (1, 3),
    
    # 仓位大小调整 - 只保留合约
    "max_swap_margin_ratio": 0.15,
    
    # 止损调整
    "stop_loss_init": 0.08,
    "stop_loss_move": 0.10,
    
    # 止盈调整
    "take_profit1": 0.15,
    "take_profit2": 0.35,
    "take_profit3": 0.75,
    
    # 信号强度阈值调整
    "signal_threshold": 0.4,
    
    # 多空参数
    "enable_short": True,
    "short_signal_threshold": -0.3
}

# 合并到现有常量中 - 只保留合约相关
LEVERAGE_LOW_VOL = RISK_PARAMS["leverage_low_vol"]
LEVERAGE_HIGH_VOL = RISK_PARAMS["leverage_high_vol"]
MAX_SWAP_MARGIN_RATIO = RISK_PARAMS["max_swap_margin_ratio"]
STOP_LOSS_INIT = RISK_PARAMS["stop_loss_init"]
STOP_LOSS_MOVE = RISK_PARAMS["stop_loss_move"]

# 批次配置 - 只保留合约交易对
# 在 constants.py 中修正 BATCHES
# constants.py 中更新BATCHES
BATCHES = [
    # 高频交易 - 主流大市值币种（已验证存在的交易对）
    ["BTC-USDT-SWAP", "ETH-USDT-SWAP", "BNB-USDT-SWAP", "XRP-USDT-SWAP", "SOL-USDT-SWAP",
        "ADA-USDT-SWAP", "DOGE-USDT-SWAP", "TRX-USDT-SWAP", "LTC-USDT-SWAP", "DOT-USDT-SWAP"],
    
    # 中频交易 - 有潜力的中型币种（移除不存在的交易对）
    ["AVAX-USDT-SWAP", "LINK-USDT-SWAP", "BCH-USDT-SWAP", "TON-USDT-SWAP", 
        "HBAR-USDT-SWAP", "ATOM-USDT-SWAP", "FIL-USDT-SWAP"],  # 移除MATIC-USDT-SWAP
    
    # 低频交易 - 小市值和特殊币种（移除不存在的交易对）
    ["XLM-USDT-SWAP", "ALGO-USDT-SWAP", "XTZ-USDT-SWAP", "SAND-USDT-SWAP"]  # 移除EOS-USDT-SWAP
]

MONITOR_INTERVALS = {
    "high_frequency": 30,
    "medium_frequency": 60,
    "low_frequency": 180
}

# 新增缓存时间
CACHE_EXPIRES = {
    "chain": 1800,
    "sentiment": 300,
    "kline": 60,
    "market_cap": 43200,
    "funding_rate": 180,
    "mark_price": 15,
    "leverage_ratio": 180,
    "taker_volume": 180
}

# 资金费率策略参数 - 合约特有
FUNDING_RATE_THRESHOLD = 0.0005
FUNDING_PREMIUM_THRESHOLD = 0.001

# constants.py 中添加以下参数

# 智能止盈参数
SMART_TAKE_PROFIT = {
    "strong_signal_threshold": 0.7,      # 强信号阈值，超过则考虑滚仓
    "weak_signal_threshold": 0.4,        # 弱信号阈值，低于则直接止盈
    "partial_profit_ratios": [0.3, 0.4, 0.3],  # 分批止盈比例
    "min_rollover_profit": 0.12,         # 滚仓最小盈利要求
}

# 浮亏加仓参数
FLOAT_LOSS_ADD = {
    "enabled": True,                     # 是否启用浮亏加仓
    "max_add_times": 1,                  # 最大加仓次数
    "max_add_ratio": 0.5,                # 最大加仓比例（相对于原仓位）
    "loss_threshold": -0.08,             # 触发加仓的亏损阈值
    "signal_requirement": 0.6,           # 加仓所需的信号强度
    "support_requirement": 0.7,          # 加仓所需的支撑强度
}

# 支撑阻力位止盈止损参数
SUPPORT_RESISTANCE = {
    "dynamic_stop_loss": True,           # 是否启用动态止损
    "resistance_take_profit": True,      # 是否在阻力位止盈
    "support_stop_loss": True,           # 是否在支撑位止损
    "distance_threshold": 0.02,          # 距离支撑阻力位的阈值
}


# 交易模式配置
TRADING_MODE = "cross"  # cross: 全仓模式, isolated: 逐仓模式

# 杠杆配置
MAX_LEVERAGE = 5.0
MIN_LEVERAGE = 1.0
BASE_LEVERAGE = 3.0


# 在 constants.py 中添加
PENDING_ORDER_CONFIG = {
    "monitor_interval": 4 * 3600,  # 4小时监测一次
    "max_wait_time": 12 * 3600,    # 最大等待时间12小时
    "price_deviation_threshold": 0.05,  # 价格偏离阈值5%
}

ENTRY_STRATEGY = {
    "strong_signal_threshold": 0.8,  # 强信号阈值
    "min_signal_threshold": 0.4,     # 最小信号阈值
    "support_strength_threshold": 0.6,  # 支撑强度阈值
    "resistance_strength_threshold": 0.6,  # 阻力强度阈值
}