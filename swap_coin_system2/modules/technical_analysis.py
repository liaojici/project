import pandas as pd
import numpy as np
import logging
import time
import requests
from core.cache_manager import get_cached_data
from utils.validators import validate_data
from config.constants import CACHE_EXPIRES, RSI_OVERSOLD, VOLUME_MULTIPLE, RSI_OVERBOUGHT

def get_kline_data(symbol, timeframe="1H", limit=200, max_retries=3):
    """获取K线数据 - 无锁串行版"""
    tf_map = {"1h": "1H", "4h": "4H", "1d": "1D", "15m": "15m", "30m": "30m"}
    okx_timeframe = tf_map.get(timeframe.lower(), timeframe)

    for attempt in range(max_retries):
        try:
            import core.api_client
            api = core.api_client.market_api
            
            if api is None:
                return pd.DataFrame()
            
            # 不再使用锁，因为上层已经是串行的了
            # 增加间隔防止触发限流
            time.sleep(0.1)
            
            # 这里如果是 SDK 内部封装的 requests，通常无法直接传 timeout
            # 但串行执行可以避免并发导致的 socket 阻塞
            response = api.get_candlesticks(instId=symbol, bar=okx_timeframe, limit=str(limit))
            
            if not response:
                logging.warning(f"⚠️ {symbol} K线请求返回空")
                continue

            if response.get("code") != "0":
                error_msg = response.get("msg", "")
                if "Instrument ID" in error_msg:
                    logging.warning(f"⚠️ 移除无效交易对: {symbol}")
                    from core.state_manager import strategy_state
                    if symbol in strategy_state["selected_symbols"]:
                        strategy_state["selected_symbols"].remove(symbol)
                    return pd.DataFrame()
                
                logging.warning(f"⚠️ {symbol} API错误 ({response.get('code')}): {error_msg}")
                time.sleep(1)
                continue
                
            if not response.get("data"):
                return pd.DataFrame()
            
            ohlcv = []
            for item in response["data"]:
                ohlcv.append([
                    int(item[0]), float(item[1]), float(item[2]), 
                    float(item[3]), float(item[4]), float(item[5])
                ])
            
            df = pd.DataFrame(ohlcv, columns=["time", "open", "high", "low", "close", "volume"])
            df = df.sort_values("time").reset_index(drop=True)
            
            # logging.info(f"   ✅ 获取 {symbol} 数据成功: {len(df)}条")
            return df

        except Exception as e:
            logging.error(f"❌ 获取K线异常 {symbol}: {e}")
            time.sleep(1)
            
    return pd.DataFrame()
    
def calculate_indicators(df):
    if df is None or len(df) < 20:
        return df

    try:
        df["close"] = df["close"].astype(float)
        df["ma200"] = df["close"].rolling(window=200).mean()
        df["volume_avg5"] = df["volume"].rolling(window=5).mean()
        
        delta = df["close"].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        df["rsi"] = 100 - (100 / (1 + rs))
        
        exp1 = df["close"].ewm(span=12, adjust=False).mean()
        exp2 = df["close"].ewm(span=26, adjust=False).mean()
        df["macd"] = exp1 - exp2
        df["macd_signal"] = df["macd"].ewm(span=9, adjust=False).mean()
        
        high_low = df["high"] - df["low"]
        high_close = np.abs(df["high"] - df["close"].shift())
        low_close = np.abs(df["low"] - df["close"].shift())
        ranges = pd.concat([high_low, high_close, low_close], axis=1)
        true_range = np.max(ranges, axis=1)
        df["atr"] = true_range.rolling(window=14).mean() / df["close"]

        return df
    except Exception as e:
        logging.error(f"指标计算失败: {e}")
        return df

def get_technical_signals(symbol):
    try:
        # 禁用缓存，强制获取最新数据进行调试
        # df = get_cached_data(...) 
        df = get_kline_data(symbol, timeframe="1H", limit=100)
        
        if not validate_data(df, symbol):
            return False, df
            
        df = calculate_indicators(df)
        if df is None or df.empty:
            return False, df
            
        latest = df.iloc[-1]
        
        macd_gold = latest["macd"] > latest["macd_signal"]
        volume_boost = latest["volume"] >= latest.get("volume_avg5", latest["volume"]) * VOLUME_MULTIPLE
        rsi_oversold = latest["rsi"] <= RSI_OVERSOLD
        
        signal_ok = (macd_gold or volume_boost or rsi_oversold)
        
        return signal_ok, df
        
    except Exception as e:
        logging.debug(f"获取{symbol}技术信号失败: {e}")
        return False, pd.DataFrame()