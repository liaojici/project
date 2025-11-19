import logging
#import pandas as pd
from utils.decorators import safe_request
from core.cache_manager import get_cached_data
from config.constants import CACHE_EXPIRES

class FundingRateAnalyzer:
    def __init__(self):
        # 不在初始化时设置API，在需要时获取
        pass
    
    @safe_request
    def get_current_funding_rate(self, symbol):
        """获取当前资金费率"""
        # 在函数内部获取API
        from core.api_client import public_data_api

        # 添加API调用记录
        
        if public_data_api is None:
            logging.error("公共数据API未初始化")
            return None
        
        try:
            result = public_data_api.get_funding_rate(instId=symbol)
            
            if result and result.get("code") == "0" and result.get("data"):
                data = result["data"][0]
                return {
                    "funding_rate": float(data.get("fundingRate", 0)),
                    "next_funding_rate": float(data.get("nextFundingRate", 0)) if data.get("nextFundingRate") else None,
                    "funding_time": int(data.get("fundingTime", 0)),
                    "next_funding_time": int(data.get("nextFundingTime", 0)),
                    "premium": float(data.get("premium", 0)),
                    "settlement_state": data.get("settState", "")
                }
            return None
            
        except Exception as e:
            logging.error(f"获取{symbol}资金费率失败: {e}")
            return None
    
    @safe_request
    def get_funding_rate_history(self, symbol, limit=100):
        """获取历史资金费率"""
        from core.api_client import public_data_api

        # 添加API调用记录
        try:
            from utils.performance_monitor import performance_monitor
            performance_monitor.record_api_call("public_data")
        except ImportError:
            pass
        
        if public_data_api is None:
            logging.error("公共数据API未初始化")
            return None
        
        try:
            result = public_data_api.funding_rate_history(
                instId=symbol, 
                limit=str(limit)
            )
            
            if result and result.get("code") == "0" and result.get("data"):
                return result["data"]
            return None
            
        except Exception as e:
            logging.error(f"获取{symbol}历史资金费率失败: {e}")
            return None
    
    def analyze_funding_rate_signal(self, symbol):
        """分析资金费率信号"""
        current_data = get_cached_data(
            f"funding_rate_{symbol}",
            lambda: self.get_current_funding_rate(symbol),
            CACHE_EXPIRES.get("funding_rate", 300)  # 默认5分钟
        )
        
        if not current_data:
            return 0, 0  # 中性信号
        
        current_rate = current_data["funding_rate"]
        premium = current_data["premium"]
        
        # 资金费率策略
        # 负费率：利于做多（收到资金费）
        # 正费率：利于做空（收到资金费）
        funding_signal = 0
        confidence = 0
        
        if current_rate < -0.0005:  # 负费率较大
            funding_signal = 1  # 做多信号
            confidence = min(abs(current_rate) * 1000, 1.0)
        elif current_rate > 0.0005:  # 正费率较大
            funding_signal = -1  # 做空信号
            confidence = min(current_rate * 1000, 1.0)
        
        # 考虑溢价
        if abs(premium) > 0.001:  # 溢价较大
            if premium > 0 and funding_signal == 1:
                confidence *= 1.2  # 增强信心
            elif premium < 0 and funding_signal == -1:
                confidence *= 1.2
        
        return funding_signal, confidence

# 全局实例
funding_analyzer = FundingRateAnalyzer()