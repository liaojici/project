# chain_analysis.py
import logging
from utils.decorators import safe_request
from core.cache_manager import get_cached_data
from config.constants import CACHE_EXPIRES

@safe_request
def fetch_exchange_outflow(coin):
    """获取交易所流出数据 - 使用OKX数据替代"""
    try:
        # 使用OKX的持仓量变化作为替代指标
        from modules.technical_analysis import get_kline_data
        symbol = f"{coin}-USDT-SWAP"
        df = get_kline_data(symbol, "1H", 50)
        
        if df is None or len(df) < 20:
            return False
            
        # 简单的价格和成交量分析替代交易所流出
        price_change = (df['close'].iloc[-1] - df['close'].iloc[-5]) / df['close'].iloc[-5]
        volume_change = (df['volume'].iloc[-1] - df['volume'].iloc[-5:].mean()) / df['volume'].iloc[-5:].mean()
        
        # 价格上涨且成交量放大视为积极信号
        return price_change > 0 and volume_change > 0.2
        
    except Exception as e:
        logging.debug(f"获取{coin}交易所流出数据失败: {e}")
        return False

@safe_request
def fetch_mvrv(coin):
    """获取MVRV数据 - 使用技术指标替代"""
    try:
        from modules.technical_analysis import get_kline_data
        symbol = f"{coin}-USDT-SWAP"
        df = get_kline_data(symbol, "1H", 50)
        
        if df is None or len(df) < 20:
            return 1.0
            
        # 使用RSI和价格位置作为替代
        current_price = df['close'].iloc[-1]
        ma_20 = df['close'].tail(20).mean()
        ma_50 = df['close'].tail(50).mean()
        
        # 价格在均线上方视为估值合理
        if current_price > ma_20 and current_price > ma_50:
            return 0.8  # 合理估值
        else:
            return 1.2  # 可能低估或高估
            
    except Exception as e:
        logging.debug(f"获取{coin} MVRV数据失败: {e}")
        return 1.0

@safe_request
def fetch_stablecoin_growth():
    """获取稳定币增长数据 - 使用市场情绪替代"""
    try:
        # 使用BTC和ETH的价格趋势作为市场情绪代理
        from modules.technical_analysis import get_kline_data
        
        btc_df = get_kline_data("BTC-USDT-SWAP", "1H", 10)
        eth_df = get_kline_data("ETH-USDT-SWAP", "1H", 10)
        
        if btc_df is None or eth_df is None:
            return True  # 默认返回True
            
        # 如果主要币种上涨，认为市场情绪积极，稳定币可能流入
        btc_change = (btc_df['close'].iloc[-1] - btc_df['close'].iloc[-5]) / btc_df['close'].iloc[-5]
        eth_change = (eth_df['close'].iloc[-1] - eth_df['close'].iloc[-5]) / eth_df['close'].iloc[-5]
        
        return btc_change > 0 or eth_change > 0
        
    except Exception as e:
        logging.debug(f"获取稳定币增长数据失败: {e}")
        return True  # 默认返回True

def get_chain_signals(coin):
    """获取链上信号 - 简化版本"""
    try:
        # 直接使用技术分析替代复杂的链上信号
        from modules.technical_analysis import get_kline_data
        symbol = f"{coin}-USDT-SWAP"
        df = get_kline_data(symbol, "1H", 50)
        
        if df is None or len(df) < 20:
            return True  # 数据不足时默认通过
            
        # 简单的技术信号替代链上信号
        current_price = df['close'].iloc[-1]
        ma_20 = df['close'].tail(20).mean()
        volume_avg = df['volume'].tail(20).mean()
        current_volume = df['volume'].iloc[-1]
        
        # 价格在20日均线上方且成交量放大视为积极信号
        signal_ok = (current_price > ma_20 * 0.98 and 
                    current_volume > volume_avg * 0.8)
        
        return signal_ok
        
    except Exception as e:
        logging.debug(f"获取{coin}链上信号失败: {e}")
        return True  # 出错时默认通过