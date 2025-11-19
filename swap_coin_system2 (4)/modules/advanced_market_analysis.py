import logging
import pandas as pd
from utils.decorators import safe_request
from core.cache_manager import get_cached_data

class AdvancedMarketAnalyzer:
    def __init__(self):
        self.trading_data_api = None
    
    def initialize_api(self):
        """初始化API"""
        try:
            from core.api_client import trading_data_api
            self.trading_data_api = trading_data_api
            if self.trading_data_api:
                logging.info("✅ 高级市场分析API初始化成功")
            else:
                logging.warning("⚠️ 交易数据API未初始化")
        except Exception as e:
            logging.error(f"❌ 高级市场分析API初始化失败: {e}")
    
    @safe_request
    def get_leverage_ratio(self, ccy="BTC", period="1H"):
        """获取杠杆多空比"""
        if self.trading_data_api is None:
            self.initialize_api()
            if self.trading_data_api is None:
                logging.error("交易数据API未初始化")
                return None
        
        try:
            result = self.trading_data_api.get_margin_lending_ratio(
                ccy=ccy,
                period=period
            )
            if result and result.get("code") == "0":
                return result.get("data", [])
            return None
        except Exception as e:
            logging.error(f"获取{ccy}杠杆多空比失败: {e}")
            return None
    
    @safe_request
    def get_taker_volume(self, ccy, instType="SPOT", period="1H"):
        """获取主动买入/卖出情况"""
        if self.trading_data_api is None:
            self.initialize_api()
            if self.trading_data_api is None:
                logging.error("交易数据API未初始化")
                return None
        
        try:
            result = self.trading_data_api.get_taker_volume(
                ccy=ccy,
                instType=instType,
                period=period
            )
            if result and result.get("code") == "0":
                return result.get("data", [])
            return None
        except Exception as e:
            logging.error(f"获取{ccy}主动买入/卖出情况失败: {e}")
            return None
    
    def analyze_market_sentiment(self, symbol):
        """分析市场情绪 - 简化版本，移除精英交易员数据"""
        coin = symbol.split("-")[0]
        is_swap = "SWAP" in symbol
        
        sentiment_score = 0
        confidence = 0
        
        try:
            # 1. 杠杆多空比分析
            leverage_data = get_cached_data(
                f"leverage_ratio_{coin}",
                lambda: self.get_leverage_ratio(ccy=coin),
                300  # 5分钟缓存
            )
            
            if leverage_data and len(leverage_data) > 0:
                latest_ratio = float(leverage_data[0][1])  # [ts, ratio]
                # 多空比 > 1 表示看多情绪，< 1 表示看空情绪
                if latest_ratio > 1.2:
                    sentiment_score += 0.3
                elif latest_ratio < 0.8:
                    sentiment_score -= 0.3
                confidence += 0.2
        except Exception as e:
            logging.debug(f"获取{coin}杠杆多空比失败: {e}")
        
        try:
            # 2. 主动买卖分析
            taker_data = get_cached_data(
                f"taker_volume_{coin}",
                lambda: self.get_taker_volume(ccy=coin, instType="SPOT"),
                300
            )
            
            if taker_data and len(taker_data) > 0:
                latest_taker = taker_data[0]  # [ts, sellVol, buyVol]
                buy_vol = float(latest_taker[2])
                sell_vol = float(latest_taker[1])
                
                if buy_vol > sell_vol * 1.2:  # 买入量显著大于卖出量
                    sentiment_score += 0.3
                elif sell_vol > buy_vol * 1.2:  # 卖出量显著大于买入量
                    sentiment_score -= 0.3
                confidence += 0.2
        except Exception as e:
            logging.debug(f"获取{coin}主动买卖数据失败: {e}")
        
        # 确保分数在合理范围内
        sentiment_score = max(-1.0, min(1.0, sentiment_score))
        confidence = max(0.0, min(1.0, confidence))
        
        return sentiment_score, confidence

# 全局实例
advanced_market_analyzer = AdvancedMarketAnalyzer()