import numpy as np
import logging
import time
from utils.decorators import safe_request
from core.cache_manager import get_cached_data
from config.constants import CACHE_EXPIRES, BATCHES, MIN_VOLUME_24H
from utils.common_utils import safe_float_convert

# 全局变量，记录上次更新交易量前十的时间
last_volume_update_time = 0
VOLUME_UPDATE_INTERVAL = 24 * 60 * 60  # 24小时

def validate_symbol_exists(symbol):
    """验证交易对是否存在"""
    try:
        from core.api_client import market_api
        if market_api is None:
            return True  # 如果API未初始化，暂时返回True
            
        # 尝试获取交易对信息
        from modules.technical_analysis import get_kline_data
        df = get_kline_data(symbol, "1H", 1)  # 只获取1条数据来验证
        
        if df is None or df.empty:
            logging.warning(f"交易对 {symbol} 验证失败，可能不存在")
            return False
            
        logging.debug(f"交易对 {symbol} 验证成功")
        return True
        
    except Exception as e:
        logging.warning(f"验证交易对 {symbol} 时出错: {e}")
        return False

@safe_request
def get_swap_tickers():
    """获取所有永续合约的行情信息"""
    try:
        from core.api_client import market_api
        if market_api is None:
            logging.error("市场API未初始化")
            return []
            
        result = market_api.get_tickers(instType="SWAP")
        if result and result.get("code") == "0":
            data = result.get("data", [])
            logging.info(f"成功获取 {len(data)} 个永续合约行情")
            return data
        else:
            logging.error(f"获取永续合约行情失败: {result}")
            return []
    except Exception as e:
        logging.error(f"获取永续合约行情异常: {e}")
        return []

def calculate_volatility(ticker_data):
    """计算币种的波动率"""
    try:
        high24h = safe_float_convert(ticker_data.get('high24h', 0))
        low24h = safe_float_convert(ticker_data.get('low24h', 0))
        open24h = safe_float_convert(ticker_data.get('open24h', 0))
        
        if open24h == 0:
            return 0.0
            
        # 波动率 = (最高价 - 最低价) / 开盘价
        volatility = (high24h - low24h) / open24h
        return abs(volatility)
    except Exception as e:
        logging.error(f"计算波动率失败: {e}")
        return 0.0

def get_top_volume_symbols(tickers, top_n=10):
    """获取交易量前十的币种"""
    try:
        # 按24小时交易量排序
        volume_symbols = []
        for ticker in tickers:
            symbol = ticker.get('instId', '')
            if symbol.endswith('-USDT-SWAP'):
                vol24h = safe_float_convert(ticker.get('volCcy24h', 0))
                volume_symbols.append((symbol, vol24h))
        
        # 按交易量降序排序
        volume_symbols.sort(key=lambda x: x[1], reverse=True)
        
        # 取前top_n个
        top_symbols = [symbol for symbol, volume in volume_symbols[:top_n]]
        logging.info(f"交易量前十的币种: {top_symbols}")
        return top_symbols
        
    except Exception as e:
        logging.error(f"获取交易量前十币种失败: {e}")
        return []

def classify_symbols_by_volatility(tickers, symbols_to_classify):
    """根据波动率将币种分类到不同的交易频率组"""
    try:
        # 计算每个币种的波动率
        symbol_volatility = {}
        for ticker in tickers:
            symbol = ticker.get('instId', '')
            if symbol in symbols_to_classify:
                volatility = calculate_volatility(ticker)
                symbol_volatility[symbol] = volatility
        
        if not symbol_volatility:
            return [], [], []
        
        # 计算波动率的分位数
        volatilities = list(symbol_volatility.values())
        low_threshold = np.percentile(volatilities, 33)  # 低波动率阈值 (33%分位数)
        high_threshold = np.percentile(volatilities, 66)  # 高波动率阈值 (66%分位数)
        
        # 分类币种
        high_freq = []  # 高波动 -> 高频交易
        medium_freq = []  # 中波动 -> 中频交易
        low_freq = []  # 低波动 -> 低频交易
        
        for symbol, volatility in symbol_volatility.items():
            if volatility >= high_threshold:
                high_freq.append(symbol)
                logging.debug(f"高波动币种: {symbol}, 波动率: {volatility:.4f}")
            elif volatility >= low_threshold:
                medium_freq.append(symbol)
                logging.debug(f"中波动币种: {symbol}, 波动率: {volatility:.4f}")
            else:
                low_freq.append(symbol)
                logging.debug(f"低波动币种: {symbol}, 波动率: {volatility:.4f}")
        
        logging.info(f"波动率分类 - 高频: {len(high_freq)}, 中频: {len(medium_freq)}, 低频: {len(low_freq)}")
        return high_freq, medium_freq, low_freq
        
    except Exception as e:
        logging.error(f"按波动率分类币种失败: {e}")
        return [], [], []

# symbol_selection.py 中修改 ensure_position_symbols_in_monitoring 函数

def ensure_position_symbols_in_monitoring(high_freq, medium_freq, low_freq):
    """确保有仓位的币种在监控列表中 - 增强版本"""
    try:
        from core.state_manager import strategy_state
        
        positions = strategy_state.get("positions", {})
        if not positions:
            return high_freq, medium_freq, low_freq
        
        position_symbols = list(positions.keys())
        added_count = 0
        
        for symbol in position_symbols:
            # 如果仓位币种不在任何频率组中，添加到中频组
            if symbol not in high_freq and symbol not in medium_freq and symbol not in low_freq:
                medium_freq.append(symbol)
                added_count += 1
                logging.info(f"📥 添加仓位币种到监控: {symbol}")
        
        if added_count > 0:
            logging.info(f"✅ 共添加 {added_count} 个仓位币种到监控列表")
        
        # 同时确保币种的基础交易对也在监控中（如果有手动仓位）
        for symbol, position in positions.items():
            coin = position.get("coin")
            if coin:
                # 构造标准的USDT-SWAP交易对
                standard_symbol = f"{coin}-USDT-SWAP"
                if standard_symbol not in high_freq and standard_symbol not in medium_freq and standard_symbol not in low_freq:
                    medium_freq.append(standard_symbol)
                    logging.info(f"📥 添加标准交易对到监控: {standard_symbol}")
        
        return high_freq, medium_freq, low_freq
        
    except Exception as e:
        logging.error(f"确保仓位币种在监控中失败: {e}")
        return high_freq, medium_freq, low_freq

def select_symbols():
    """选择交易标的 - 基于波动率和交易量的动态选择"""
    global last_volume_update_time
    
    try:
        # 获取所有永续合约行情
        tickers = get_swap_tickers()
        if not tickers:
            logging.warning("无法获取合约行情数据，使用默认标的")
            initial_symbols = [symbol for batch in BATCHES for symbol in batch]
            
            # 验证交易对是否存在
            valid_symbols = []
            for symbol in initial_symbols:
                if validate_symbol_exists(symbol):
                    valid_symbols.append(symbol)
            
            # 确保仓位币种在监控中
            from core.state_manager import strategy_state
            strategy_state["dynamic_batches"] = BATCHES
            
            logging.info(f"使用默认标的，筛选出 {len(valid_symbols)} 个有效交易对")
            return valid_symbols
        
        # 获取原有BATCHES中的所有币种
        original_symbols = [symbol for batch in BATCHES for symbol in batch]
        
        # 根据波动率将原有币种分类
        high_freq, medium_freq, low_freq = classify_symbols_by_volatility(tickers, original_symbols)
        
        # 检查是否需要更新交易量前十（每天一次）
        current_time = time.time()
        if current_time - last_volume_update_time >= VOLUME_UPDATE_INTERVAL:
            # 获取交易量前十的币种
            top_volume_symbols = get_top_volume_symbols(tickers, top_n=10)
            
            # 将交易量前十的币种加入高频组（不重复）
            added_count = 0
            for symbol in top_volume_symbols:
                if symbol not in high_freq:
                    # 如果币种在中频或低频组，从中移除
                    if symbol in medium_freq:
                        medium_freq.remove(symbol)
                    elif symbol in low_freq:
                        low_freq.remove(symbol)
                    
                    # 添加到高频组
                    high_freq.append(symbol)
                    added_count += 1
                    logging.info(f"将交易量前十币种 {symbol} 加入到高频交易组")
            
            if added_count > 0:
                logging.info(f"成功添加 {added_count} 个交易量前十币种到高频组")
            
            # 更新最后更新时间
            last_volume_update_time = current_time
            logging.info(f"交易量前十币种已更新，下次更新在24小时后")
        else:
            logging.info("交易量前十币种尚未到更新时间，使用上次结果")
        
        # 确保有仓位的币种在监控列表中
        high_freq, medium_freq, low_freq = ensure_position_symbols_in_monitoring(high_freq, medium_freq, low_freq)
        
        # 将分类结果存储到策略状态中
        from core.state_manager import strategy_state
        strategy_state["dynamic_batches"] = {
            "high_frequency": high_freq,
            "medium_frequency": medium_freq, 
            "low_frequency": low_freq,
            "last_volume_update": last_volume_update_time
        }
        
        # 记录分类结果
        logging.info("=== 动态标的分类结果 ===")
        logging.info(f"高频交易 ({len(high_freq)}个): {high_freq}")
        logging.info(f"中频交易 ({len(medium_freq)}个): {medium_freq}")
        logging.info(f"低频交易 ({len(low_freq)}个): {low_freq}")
        
        # 返回所有有效币种（三个频率组的并集）
        all_selected_symbols = list(set(high_freq + medium_freq + low_freq))
        logging.info(f"最终筛选出 {len(all_selected_symbols)} 个有效交易对")
        
        return all_selected_symbols
        
    except Exception as e:
        logging.error(f"动态选择交易标的过程出错: {e}")
        # 出错时返回默认标的
        initial_symbols = [symbol for batch in BATCHES for symbol in batch]
        valid_symbols = []
        for symbol in initial_symbols:
            if validate_symbol_exists(symbol):
                valid_symbols.append(symbol)
        
        # 确保仓位币种在监控中
        high_freq, medium_freq, low_freq = ensure_position_symbols_in_monitoring(
            BATCHES[0] if len(BATCHES) > 0 else [],
            BATCHES[1] if len(BATCHES) > 1 else [],
            BATCHES[2] if len(BATCHES) > 2 else []
        )
        
        from core.state_manager import strategy_state
        strategy_state["dynamic_batches"] = [high_freq, medium_freq, low_freq]
        
        logging.info(f"使用默认标的，筛选出 {len(valid_symbols)} 个有效交易对")
        return valid_symbols

# 需要在多频率监控模块中使用的辅助函数
def get_dynamic_batches():
    """获取动态分类的交易批次"""
    from core.state_manager import strategy_state
    dynamic_batches = strategy_state.get("dynamic_batches")
    
    if dynamic_batches and isinstance(dynamic_batches, dict):
        return [
            dynamic_batches["high_frequency"],
            dynamic_batches["medium_frequency"], 
            dynamic_batches["low_frequency"]
        ]
    elif dynamic_batches and isinstance(dynamic_batches, list):
        return dynamic_batches
    else:
        # 如果没有动态分类，返回原始的BATCHES
        return BATCHES

def force_update_volume_symbols():
    """强制更新交易量前十的币种（用于手动触发）"""
    global last_volume_update_time
    last_volume_update_time = 0  # 重置时间，强制下次更新
    logging.info("已标记强制更新交易量前十币种，将在下次标的选择时生效")

@safe_request
def fetch_top_market_cap():
    """获取市值排名（简化版）"""
    try:
        # 直接返回新的交易对列表
        symbols = {}
        for batch in BATCHES:
            for symbol in batch:
                coin = symbol.split("-")[0]
                symbols[coin] = {"symbol": coin, "total_volume": MIN_VOLUME_24H * 2}
        return symbols
    except Exception as e:
        logging.error(f"获取市值排名失败: {e}")
        return {}

@safe_request
def fetch_holders_growth(coin):
    """获取持有者增长数据（简化版）"""
    try:
        # 返回随机增长数据用于测试
        return np.random.uniform(0.05, 0.2)
    except Exception as e:
        logging.error(f"获取{coin}持有者增长数据失败: {e}")
        return 0.0