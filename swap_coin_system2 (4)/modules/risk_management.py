import logging
from utils.decorators import safe_request
from core.cache_manager import get_cached_data

class RiskManager:
    def __init__(self):
        self.public_data_api = None
    
    def initialize_api(self, public_api):
        self.public_data_api = public_api
    
    @safe_request
    def get_mark_price(self, symbol):
        """获取标记价格（用于强平计算）"""
        if self.public_data_api is None:
            logging.error("公共数据API未初始化")
            return None
        
            
        
        try:
            result = self.public_data_api.get_mark_price(instId=symbol)
            if result and result.get("code") == "0" and result.get("data"):
                data = result["data"][0]
                return float(data.get("markPx", 0))
            return None
        except Exception as e:
            logging.error(f"获取{symbol}标记价格失败: {e}")
            return None
    
    @safe_request
    def get_price_limit(self, symbol):
        """获取限价信息"""
        if self.public_data_api is None:
            logging.error("公共数据API未初始化")
            return None
        
            # 添加API调用记录
        try:
            from utils.performance_monitor import performance_monitor
            performance_monitor.record_api_call("public_data")
        except ImportError:
            pass
        
        try:
            result = self.public_data_api.get_price_limit(instId=symbol)
            if result and result.get("code") == "0" and result.get("data"):
                data = result["data"][0]
                return {
                    "buy_limit": float(data.get("buyLmt", 0)),
                    "sell_limit": float(data.get("sellLmt", 0)),
                    "enabled": data.get("enabled", False)
                }
            return None
        except Exception as e:
            logging.error(f"获取{symbol}限价信息失败: {e}")
            return None
    
    def calculate_liquidation_price(self, symbol, position_size, leverage, entry_price, is_long=True):
        """计算强平价格"""
        mark_price = get_cached_data(
            f"mark_price_{symbol}",
            lambda: self.get_mark_price(symbol),
            30  # 30秒缓存
        ) or entry_price
        
        if is_long:
            # 多头强平价格 = 入场价格 * (1 - 1/杠杆)
            liquidation_price = entry_price * (1 - 1/leverage)
        else:
            # 空头强平价格 = 入场价格 * (1 + 1/杠杆)
            liquidation_price = entry_price * (1 + 1/leverage)
        
        return liquidation_price
    
    def calculate_position_health(self, symbol, position_data, current_price):
        """计算仓位健康度"""
        liquidation_price = self.calculate_liquidation_price(
            symbol, 
            position_data["size"], 
            position_data["leverage"], 
            position_data["open_price"],
            position_data["side"] == "buy"
        )
        
        if position_data["side"] == "buy":
            # 多头仓位
            price_to_liquidation = current_price - liquidation_price
            health_ratio = price_to_liquidation / (current_price - position_data["open_price"]) if current_price > position_data["open_price"] else 1.0
        else:
            # 空头仓位
            price_to_liquidation = liquidation_price - current_price
            health_ratio = price_to_liquidation / (position_data["open_price"] - current_price) if current_price < position_data["open_price"] else 1.0
        
        return {
            "liquidation_price": liquidation_price,
            "health_ratio": max(0, min(1, health_ratio)),
            "distance_to_liquidation": abs(current_price - liquidation_price) / current_price
        }

# 全局实例
risk_manager = RiskManager()