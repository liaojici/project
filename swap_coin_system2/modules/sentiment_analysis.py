import requests
import numpy as np
import logging
from utils.decorators import safe_request
from core.cache_manager import get_cached_data
from config.constants import CACHE_EXPIRES, FEAR_GREED_THRESHOLD, COINBASE_PREMIUM_THRESHOLD
from config.settings import CRYPTOPANIC_API

@safe_request
def fetch_fear_greed_index():
    """获取恐惧贪婪指数"""
    try:
        url = "https://api.alternative.me/fng/"
        params = {"limit": 3}
        response = requests.get(url, params=params, timeout=10)
        data = response.json()["data"]
        return [int(d["value"]) for d in data]
    except Exception as e:
        logging.error(f"获取恐惧贪婪指数失败: {e}")
        return [50, 50, 50]

@safe_request
def calculate_coinbase_premium(coin):
    """计算Coinbase溢价（简化版）"""
    try:
        # 使用价格数据模拟溢价
        if coin not in ["BTC", "ETH", "SOL"]:
            return 0.0
            
        # 获取当前价格
        from modules.technical_analysis import get_kline_data
        symbol = f"{coin}-USDT"
        df = get_kline_data(symbol, "1h", 10)
        if df is None or df.empty:
            return 0.0
            
        current_price = df.iloc[-1]["close"]
        # 模拟溢价计算
        return np.random.uniform(-0.05, 0.05)
    except Exception as e:
        logging.error(f"计算{coin} Coinbase溢价失败: {e}")
        return 0.0

@safe_request
def fetch_cryptopanic_sentiment(coin):
    """获取CryptoPanic情绪数据（简化版）"""
    if not CRYPTOPANIC_API:
        return 0.5  # 返回中性情绪
        
    try:
        # 模拟情绪数据
        return np.random.uniform(0.3, 0.7)
    except Exception as e:
        logging.error(f"获取{coin} CryptoPanic情绪失败: {e}")
        return 0.5

def get_sentiment_signals(coin):
    """获取市场情绪信号"""
    sentiment_data = get_cached_data(
        f"sentiment_{coin}",
        lambda: {
            "fear_greed": fetch_fear_greed_index(),
            "coinbase_premium": calculate_coinbase_premium(coin),
            "cryptopanic_score": fetch_cryptopanic_sentiment(coin)
        },
        CACHE_EXPIRES["sentiment"]
    )
    if not sentiment_data:
        return False
        
    fear_greed_data = sentiment_data.get("fear_greed", [50, 50, 50])
    return (all([x <= FEAR_GREED_THRESHOLD for x in fear_greed_data]) and
            sentiment_data.get("coinbase_premium", 0) >= COINBASE_PREMIUM_THRESHOLD and
            sentiment_data.get("cryptopanic_score", 0) >= 0.2)