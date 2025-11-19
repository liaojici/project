# instrument_utils.py - 完全重写
import logging
from core.cache_manager import get_cached_data
from config.constants import CACHE_EXPIRES

# 缓存交易产品信息
_instrument_cache = {}

def initialize_instrument_cache():
    """初始化交易产品信息缓存"""
    global _instrument_cache
    try:
        from core.api_client import get_swap_instruments
        instruments = get_swap_instruments()
        if instruments:
            _instrument_cache = instruments
            logging.info(f"成功初始化 {len(_instrument_cache)} 个交易对信息")
        else:
            logging.warning("无法获取交易产品信息，使用默认配置")
            # 使用默认配置作为后备
            _instrument_cache = get_default_instruments()
    except Exception as e:
        logging.error(f"初始化交易产品缓存失败: {e}")
        _instrument_cache = get_default_instruments()

def get_default_instruments():
    """默认交易产品配置（后备方案）"""
    return {
        "BTC-USDT-SWAP": {"lotSz": "1", "minSz": "1", "tickSz": "0.1"},
        "ETH-USDT-SWAP": {"lotSz": "1", "minSz": "1", "tickSz": "0.01"},
        "BNB-USDT-SWAP": {"lotSz": "1", "minSz": "1", "tickSz": "0.001"},
        "XRP-USDT-SWAP": {"lotSz": "1", "minSz": "1", "tickSz": "0.0001"},
        "SOL-USDT-SWAP": {"lotSz": "1", "minSz": "1", "tickSz": "0.001"},
        "ADA-USDT-SWAP": {"lotSz": "1", "minSz": "1", "tickSz": "0.0001"},
        "DOGE-USDT-SWAP": {"lotSz": "1", "minSz": "1", "tickSz": "0.00001"},
        "TRX-USDT-SWAP": {"lotSz": "1", "minSz": "1", "tickSz": "0.00001"},
        "LTC-USDT-SWAP": {"lotSz": "1", "minSz": "1", "tickSz": "0.01"},
        "DOT-USDT-SWAP": {"lotSz": "1", "minSz": "1", "tickSz": "0.001"},
        "AVAX-USDT-SWAP": {"lotSz": "1", "minSz": "1", "tickSz": "0.001"},
        "LINK-USDT-SWAP": {"lotSz": "1", "minSz": "1", "tickSz": "0.001"},
        "BCH-USDT-SWAP": {"lotSz": "1", "minSz": "1", "tickSz": "0.01"},
        "TON-USDT-SWAP": {"lotSz": "1", "minSz": "1", "tickSz": "0.0001"},
        "HBAR-USDT-SWAP": {"lotSz": "1", "minSz": "1", "tickSz": "0.0001"},
        "ATOM-USDT-SWAP": {"lotSz": "1", "minSz": "1", "tickSz": "0.001"},
        "FIL-USDT-SWAP": {"lotSz": "1", "minSz": "1", "tickSz": "0.001"},
        "XLM-USDT-SWAP": {"lotSz": "1", "minSz": "1", "tickSz": "0.0001"},
        "ALGO-USDT-SWAP": {"lotSz": "1", "minSz": "1", "tickSz": "0.0001"},
        "XTZ-USDT-SWAP": {"lotSz": "1", "minSz": "1", "tickSz": "0.0001"},
        "SAND-USDT-SWAP": {"lotSz": "1", "minSz": "1", "tickSz": "0.0001"},
    }

def get_instrument_info(symbol):
    """获取交易对信息"""
    global _instrument_cache
    
    # 如果缓存为空，先初始化
    if not _instrument_cache:
        initialize_instrument_cache()
    
    return _instrument_cache.get(symbol)

def get_min_contract_size(symbol):
    """获取最小交易张数 - 从API获取真实数据"""
    info = get_instrument_info(symbol)
    if info and "minSz" in info:
        min_sz = float(info["minSz"])
        logging.debug(f"{symbol} 最小张数: {min_sz} (来自API)")
        return min_sz
    
    # 后备方案：根据交易对设置默认值
    default_sizes = {
        "BTC-USDT-SWAP": 1,
        "ETH-USDT-SWAP": 1,
        "ADA-USDT-SWAP": 1,  # ADA一张可能很大
        "XRP-USDT-SWAP": 1,
        "TRX-USDT-SWAP": 1,
        "SAND-USDT-SWAP": 1,
        "ALGO-USDT-SWAP": 1,
        # 添加其他交易对的默认值
    }
    default_size = default_sizes.get(symbol, 1)
    logging.debug(f"{symbol} 使用默认最小张数: {default_size}")
    return default_size

def get_lot_size(symbol):
    """获取下单数量精度 - 从API获取真实数据"""
    info = get_instrument_info(symbol)
    if info and "lotSz" in info:
        return float(info["lotSz"])
    
    # 后备方案
    default_sizes = {
        "BTC-USDT-SWAP": 1,
        "ETH-USDT-SWAP": 1,
        "ADA-USDT-SWAP": 1,
        "XRP-USDT-SWAP": 1,
        "TRX-USDT-SWAP": 1,
        "SAND-USDT-SWAP": 1,
        "ALGO-USDT-SWAP": 1,
    }
    return default_sizes.get(symbol, 1)

def get_tick_size(symbol):
    """获取价格精度"""
    info = get_instrument_info(symbol)
    if info and "tickSz" in info:
        return float(info["tickSz"])
    return 0.0001  # 默认精度

def get_instrument_precision(symbol):
    """获取交易对的精度要求"""
    return {
        "price": get_tick_size(symbol),
        "quantity": get_lot_size(symbol)  # 对于合约，这是张数精度
    }

def adjust_quantity_precision(symbol, quantity):
    """调整数量精度 - 修复张数为0的问题"""
    lot_size = get_lot_size(symbol)
    min_size = get_min_contract_size(symbol)
    
    # 记录调试信息
    logging.debug(f"张数调整前 - {symbol}: 原始数量={quantity}, lot_size={lot_size}, min_size={min_size}")
    
    # 确保不低于最小张数
    if quantity < min_size:
        logging.warning(f"{symbol} 原始张数{quantity}小于最小张数{min_size}，使用最小张数")
        quantity = min_size
    
    # 调整到lotSize的整数倍
    if lot_size > 0:
        try:
            # 使用更精确的计算方法
            multiple = round(quantity / lot_size)
            adjusted = multiple * lot_size
            
            # 确保调整后不低于最小张数
            if adjusted < min_size:
                logging.warning(f"{symbol} 调整后张数{adjusted}小于最小张数{min_size}，使用最小张数")
                adjusted = min_size
                
            # 如果调整后为0，使用最小张数
            if adjusted <= 0:
                logging.error(f"{symbol} 调整后张数为0，使用最小张数{min_size}")
                adjusted = min_size
                
        except Exception as e:
            logging.error(f"{symbol} 张数调整计算失败: {e}，使用最小张数{min_size}")
            adjusted = min_size
    else:
        adjusted = max(min_size, round(quantity))
    
    # 格式化显示，避免浮点数精度问题
    if lot_size < 1:
        # 计算小数位数
        lot_str = str(lot_size).rstrip('0')
        if '.' in lot_str:
            decimals = len(lot_str.split('.')[-1])
            # 使用格式化确保显示一致的小数位数
            adjusted = round(adjusted, decimals)
    else:
        # lotSize >= 1，确保是整数
        adjusted = int(adjusted)
    
    logging.debug(f"张数调整后 - {symbol}: 调整后数量={adjusted}")
    return adjusted

def adjust_price_precision(symbol, price):
    """调整价格精度 - 修复显示问题"""
    tick_size = get_tick_size(symbol)
    
    # 记录调试信息
    logging.debug(f"价格精度调整 - {symbol}: 原始价格={price}, tick_size={tick_size}")
    
    if tick_size <= 0:
        logging.warning(f"{symbol} tick_size异常: {tick_size}, 使用默认精度")
        return round(price, 6)
    
    try:
        # 方法1: 先计算倍数，再乘以tick_size
        multiple = round(price / tick_size)
        adjusted = multiple * tick_size
        
        # 确保调整后的价格不为0且与原始价格相近
        if adjusted <= 0 or abs(adjusted - price) / price > 0.1:
            logging.warning(f"价格调整异常: {symbol} 原始={price}, 调整后={adjusted}, 使用备选方案")
            # 使用备选方案：直接按小数位数舍入
            tick_str = str(tick_size).rstrip('0')
            if '.' in tick_str:
                precision = len(tick_str.split('.')[-1])
                adjusted = round(price, precision)
            else:
                adjusted = round(price, 0)
        
        # 格式化显示，确保小数位数一致且避免浮点数精度问题
        tick_str = str(tick_size).rstrip('0')
        if '.' in tick_str:
            precision = len(tick_str.split('.')[-1])
            # 使用格式化确保显示一致的小数位数
            adjusted_str = f"{adjusted:.{precision}f}"
            adjusted = float(adjusted_str)
        
        logging.debug(f"价格精度调整 - {symbol}: 调整后价格={adjusted}")
        return adjusted
        
    except Exception as e:
        logging.error(f"价格精度调整失败 {symbol}: {e}")
        # 备选方案：使用原始价格，但确保合理的小数位数
        return round(price, 6)

def validate_order_parameters(symbol, side, quantity, price, leverage, posSide, tdMode):
    """验证订单参数是否符合OKX要求 - 增强张数验证"""
    errors = []
    
    # 检查张数是否大于0
    if quantity <= 0:
        errors.append(f"张数{quantity}必须大于0")
    
    # 获取最小张数
    min_sz = get_min_contract_size(symbol)
    if quantity < min_sz:
        errors.append(f"张数{quantity}小于最小要求{min_sz}")
    
    # 获取lotSize
    lot_size = get_lot_size(symbol)
    
    # 检查张数是否是lotSize的整数倍
    if lot_size > 0:
        # 使用容差检查，避免浮点数精度问题
        remainder = quantity % lot_size
        tolerance = 1e-10  # 浮点数容差
        if abs(remainder) > tolerance and abs(remainder - lot_size) > tolerance:
            errors.append(f"张数{quantity}不是lotSize({lot_size})的整数倍, 余数={remainder}")
    
    if price <= 0:
        errors.append("价格必须大于0")
    
    if leverage < 1 or leverage > 100:
        errors.append(f"杠杆倍数 {leverage} 不在有效范围内(1-100)")
    
    if side not in ["buy", "sell"]:
        errors.append(f"交易方向 {side} 无效")
    
    # 全仓模式必须指定posSide
    if tdMode == "cross" and posSide not in ["long", "short"]:
        errors.append(f"全仓模式必须指定持仓方向 (long/short)，当前: {posSide}")
    
    if tdMode not in ["cross", "isolated"]:
        errors.append(f"交易模式 {tdMode} 无效")
    
    if errors:
        logging.error(f"❌ 订单参数验证失败: {', '.join(errors)}")
        logging.error(f"   参数详情: symbol={symbol}, side={side}, quantity={quantity}, price={price}, leverage={leverage}, posSide={posSide}, tdMode={tdMode}")
        logging.error(f"   交易对信息: min_sz={min_sz}, lot_size={lot_size}")
        return False
    
    return True

def log_instrument_details(symbol):
    """记录交易对详细信息"""
    info = get_instrument_info(symbol)
    if info:
        logging.info(f"📋 {symbol} 产品信息:")
        logging.info(f"   最小张数: {info.get('minSz', 'N/A')}")
        logging.info(f"   张数精度: {info.get('lotSz', 'N/A')}")
        logging.info(f"   价格精度: {info.get('tickSz', 'N/A')}")
        logging.info(f"   合约面值: {info.get('ctVal', 'N/A')} {info.get('ctValCcy', 'N/A')}")
        logging.info(f"   最大杠杆: {info.get('lever', 'N/A')}")
        logging.info(f"   产品状态: {info.get('state', 'N/A')}")

# 在 instrument_utils.py 文件末尾添加以下函数

def debug_instrument_precision(symbol):
    """调试交易对精度信息 - 改进显示"""
    tick_size = get_tick_size(symbol)
    lot_size = get_lot_size(symbol)
    min_size = get_min_contract_size(symbol)
    
    logging.info(f"🔧 {symbol} 精度调试:")
    logging.info(f"  价格精度(tick_size): {tick_size}")
    logging.info(f"  张数精度(lot_size): {lot_size}")
    logging.info(f"  最小张数(min_size): {min_size}")
    
    # 获取交易对信息
    info = get_instrument_info(symbol)
    if info:
        logging.info(f"  完整信息: {info}")
    
    # 测试价格调整 - 改进显示格式
    test_prices = [0.205255, 0.296336, 191.95]
    for test_price in test_prices:
        adjusted = adjust_price_precision(symbol, test_price)
        # 格式化显示，避免浮点数精度问题
        tick_str = str(tick_size).rstrip('0')
        if '.' in tick_str:
            precision = len(tick_str.split('.')[-1])
            adjusted_str = f"{adjusted:.{precision}f}"
            logging.info(f"  价格调整测试: {test_price} -> {adjusted_str}")
        else:
            logging.info(f"  价格调整测试: {test_price} -> {adjusted}")

def debug_all_precisions():
    """调试所有交易对的精度"""
    from config.constants import BATCHES
    all_symbols = []
    for batch in BATCHES:
        all_symbols.extend(batch)
    
    for symbol in all_symbols:
        debug_instrument_precision(symbol)

def debug_quantity_format(symbol, quantity):
    """调试张数格式化过程"""
    adjusted_quantity = adjust_quantity_precision(symbol, quantity)
    lot_size = get_lot_size(symbol)
    min_sz = get_min_contract_size(symbol)
    
    logging.info(f"🔧 {symbol} 张数格式化调试:")
    logging.info(f"  原始张数: {quantity}")
    logging.info(f"  调整后张数: {adjusted_quantity}")
    logging.info(f"  lot_size: {lot_size}")
    logging.info(f"  min_sz: {min_sz}")
    
    # 测试格式化
    if lot_size >= 1:
        sz_str = str(int(adjusted_quantity))
    else:
        lot_str = str(lot_size).rstrip('0')
        if '.' in lot_str:
            decimals = len(lot_str.split('.')[-1])
            sz_str = f"{adjusted_quantity:.{decimals}f}"
        else:
            sz_str = str(int(adjusted_quantity))
    
    logging.info(f"  格式化后字符串: '{sz_str}'")
    return sz_str

__all__ = [
    'initialize_instrument_cache',
    'get_instrument_info',
    'get_min_contract_size',
    'get_lot_size',
    'get_tick_size',
    'get_instrument_precision',
    'adjust_price_precision',  # 添加这个
    'adjust_quantity_precision',
    'validate_order_parameters',
    'log_instrument_details',
    'debug_instrument_precision',
    'debug_all_precisions',
    'debug_quantity_format'
]