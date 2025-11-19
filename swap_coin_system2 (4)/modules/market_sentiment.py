import logging
import pandas as pd
from utils.decorators import safe_request
#from core.cache_manager import get_cached_data

class MarketSentimentAnalyzer:
    def __init__(self):
        self.market_api = None
    
    def initialize_api(self, market_api):
        self.market_api = market_api
    
    @safe_request
    def get_open_interest(self, symbol):
        """获取持仓总量"""
        if self.market_api is None:
            logging.error("市场API未初始化")
            return None
        
        try:
            # 这里需要根据实际API调整
            # result = self.market_api.get_open_interest(instId=symbol)
            # 暂时返回模拟数据
            return {
                "open_interest": 1000000,  # 模拟数据
                "timestamp": pd.Timestamp.now().timestamp() * 1000
            }
        except Exception as e:
            logging.error(f"获取{symbol}持仓总量失败: {e}")
            return None
    
    def analyze_sentiment_signals(self, symbol, df):
        """分析市场情绪信号"""
        if df is None or len(df) < 20:
            return 0, 0
        
        # 基于价格和成交量的情绪分析
        latest = df.iloc[-1]
        
        # 1. 价格动量情绪
        price_change = (latest["close"] - df.iloc[-5]["close"]) / df.iloc[-5]["close"]
        price_sentiment = 1 if price_change > 0.02 else (-1 if price_change < -0.02 else 0)
        
        # 2. 成交量情绪
        volume_avg = df["volume"].tail(20).mean()
        volume_sentiment = 1 if latest["volume"] > volume_avg * 1.5 else 0
        
        # 3. 波动率情绪
        volatility = df["close"].tail(20).std() / df["close"].tail(20).mean()
        volatility_sentiment = -1 if volatility > 0.05 else 0  # 高波动率通常伴随不确定性
        
        # 综合情绪得分
        sentiment_score = (price_sentiment * 0.4 + volume_sentiment * 0.3 + volatility_sentiment * 0.3)
        confidence = min(abs(sentiment_score) * 2, 1.0)
        
        return sentiment_score, confidence

# 创建全局实例 - 添加这行
market_sentiment_analyzer = MarketSentimentAnalyzer()