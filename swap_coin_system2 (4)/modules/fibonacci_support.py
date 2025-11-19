# /www/python/swap_coin_system/modules/fibonacci_support.py
import pandas as pd
import numpy as np
import logging
from utils.decorators import safe_request

# 在 fibonacci_support.py 中添加阻力位分析功能
class FibonacciSupportAnalyzer:
    def __init__(self):
        self.fib_levels = [0.236, 0.382, 0.5, 0.618, 0.786]
        self.strong_fib_levels = [0.382, 0.5, 0.618]
    
    def analyze_fibonacci_resistance_strength(self, df, current_price, depth_data=None):
        """分析斐波那契阻力强度"""
        fib_levels, swing_high, swing_low = self.calculate_fibonacci_levels(df)
        
        if fib_levels is None:
            return 0, None
        
        try:
            closest_level = None
            min_distance = float('inf')
            resistance_strength = 0
            
            for level, price in fib_levels.items():
                distance = abs(current_price - price) / current_price
                
                # 如果在阻力位附近（2%以内）
                if distance < 0.02 and current_price <= price:  # 当前价格在阻力位下方
                    if distance < min_distance:
                        min_distance = distance
                        closest_level = level
                    
                    # 计算该阻力位的强度
                    level_strength = self.calculate_single_fib_strength(
                        level, distance, df, depth_data
                    )
                    resistance_strength = max(resistance_strength, level_strength)
            
            # 如果当前价格在强斐波那契水平附近，增强信号
            if closest_level in self.strong_fib_levels and min_distance < 0.01:
                resistance_strength *= 1.3
                resistance_strength = min(resistance_strength, 1.0)
            
            # 结合价格行为确认阻力
            price_action_confirmation = self.analyze_price_action_resistance_confirmation(
                df, fib_levels, current_price
            )
            resistance_strength *= price_action_confirmation
            
            return resistance_strength, fib_levels.get(closest_level) if closest_level else None
            
        except Exception as e:
            logging.error(f"分析斐波那契阻力强度失败: {e}")
            return 0, None
    
    def analyze_price_action_resistance_confirmation(self, df, fib_levels, current_price):
        """分析价格行为对斐波那契阻力的确认"""
        if len(df) < 10:
            return 0.5
        
        try:
            confirmation_score = 0.5  # 基础分数
            
            # 1. 检查是否出现看跌吞没形态
            bearish_engulfing = self.detect_bearish_engulfing(df)
            if bearish_engulfing:
                confirmation_score += 0.2
            
            # 2. 检查是否出现上吊线
            hanging_man = self.detect_hanging_man(df)
            if hanging_man:
                confirmation_score += 0.15
            
            # 3. 检查RSI顶背离
            rsi_top_divergence = self.check_rsi_top_divergence(df)
            if rsi_top_divergence:
                confirmation_score += 0.15
            
            # 4. 检查成交量萎缩
            volume_decline = self.check_volume_decline(df)
            if volume_decline:
                confirmation_score += 0.1
            
            return min(confirmation_score, 1.0)
            
        except Exception as e:
            logging.debug(f"价格行为阻力确认分析失败: {e}")
            return 0.5
    
    def detect_bearish_engulfing(self, df):
        """检测看跌吞没形态"""
        if len(df) < 2:
            return False
        
        current = df.iloc[-1]
        previous = df.iloc[-2]
        
        # 看跌吞没条件
        return (current["close"] < current["open"] and  # 当前阴线
                previous["close"] > previous["open"] and  # 前一根阳线
                current["open"] > previous["close"] and  # 当前开盘高于前收盘
                current["close"] < previous["open"])  # 当前收盘低于前开盘
    
    def detect_hanging_man(self, df):
        """检测上吊线（与锤子线形态相同，但出现在上升趋势中）"""
        if len(df) < 1:
            return False
        
        current = df.iloc[-1]
        body_size = abs(current["close"] - current["open"])
        lower_shadow = min(current["open"], current["close"]) - current["low"]
        upper_shadow = current["high"] - max(current["open"], current["close"])
        
        # 上吊线条件：下影线至少是实体长度的2倍，上影线很短
        return (lower_shadow >= 2 * body_size and 
                upper_shadow <= body_size * 0.5)
    
    def check_rsi_top_divergence(self, df, period=14):
        """检查RSI顶背离"""
        if len(df) < period + 5:
            return False
        
        # 计算RSI
        delta = df["close"].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rsi = 100 - (100 / (1 + gain / loss))
        
        # 顶背离检测：价格创新高但RSI没有
        if (df["close"].iloc[-1] > df["close"].iloc[-5] and 
            rsi.iloc[-1] < rsi.iloc[-5]):
            return True
        
        return False
    
    def check_volume_decline(self, df, multiplier=0.7):
        """检查成交量萎缩"""
        if len(df) < 20:
            return False
        
        current_volume = df["volume"].iloc[-1]
        avg_volume = df["volume"].tail(20).mean()
        
        return current_volume < avg_volume * multiplier

    # 其余现有函数保持不变...
    
    def calculate_fibonacci_levels(self, df, period=100):
        """计算斐波那契回撤水平"""
        if df is None or len(df) < period:
            return None, None, None
            
        try:
            # 获取周期内的最高价和最低价
            high_period = df["high"].tail(period)
            low_period = df["low"].tail(period)
            
            swing_high = high_period.max()
            swing_low = low_period.min()
            current_price = df.iloc[-1]["close"]
            
            # 计算斐波那契回撤水平
            fib_levels = {}
            for level in self.fib_levels:
                price_level = swing_high - (swing_high - swing_low) * level
                fib_levels[level] = price_level
            
            return fib_levels, swing_high, swing_low
            
        except Exception as e:
            logging.error(f"计算斐波那契水平失败: {e}")
            return None, None, None
    
    def analyze_fibonacci_support_strength(self, df, current_price, depth_data=None):
        """分析斐波那契支撑强度"""
        fib_levels, swing_high, swing_low = self.calculate_fibonacci_levels(df)
        
        if fib_levels is None:
            return 0, None
        
        try:
            # 1. 计算当前价格与各斐波那契水平的接近程度
            closest_level = None
            min_distance = float('inf')
            support_strength = 0
            
            for level, price in fib_levels.items():
                distance = abs(current_price - price) / current_price
                
                # 如果在支撑位附近（2%以内）
                if distance < 0.02 and current_price >= price:  # 当前价格在支撑位上方
                    if distance < min_distance:
                        min_distance = distance
                        closest_level = level
                    
                    # 计算该支撑位的强度
                    level_strength = self.calculate_single_fib_strength(
                        level, distance, df, depth_data
                    )
                    support_strength = max(support_strength, level_strength)
            
            # 2. 如果当前价格在强斐波那契水平附近，增强信号
            if closest_level in self.strong_fib_levels and min_distance < 0.01:
                support_strength *= 1.3
                support_strength = min(support_strength, 1.0)
            
            # 3. 结合价格行为确认支撑
            price_action_confirmation = self.analyze_price_action_confirmation(
                df, fib_levels, current_price
            )
            support_strength *= price_action_confirmation
            
            return support_strength, fib_levels.get(closest_level) if closest_level else None
            
        except Exception as e:
            logging.error(f"分析斐波那契支撑强度失败: {e}")
            return 0, None
    
    def calculate_single_fib_strength(self, fib_level, distance, df, depth_data):
        """计算单个斐波那契水平的支撑强度"""
        base_strength = 0
        
        # 基于斐波那契水平的重要性
        if fib_level in [0.382, 0.5, 0.618]:
            base_strength = 0.7
        elif fib_level in [0.236, 0.786]:
            base_strength = 0.5
        else:
            base_strength = 0.3
        
        # 距离调整：越接近支撑位，强度越高
        distance_factor = 1 - (distance / 0.02)  # 2%范围内线性衰减
        base_strength *= max(0.3, distance_factor)
        
        # 成交量确认
        volume_confirmation = self.check_volume_confirmation(df, fib_level)
        base_strength *= volume_confirmation
        
        # 深度数据确认（如果可用）
        if depth_data:
            depth_confirmation = self.check_depth_confirmation(depth_data, fib_level)
            base_strength *= depth_confirmation
        
        return min(base_strength, 1.0)
    
    def analyze_price_action_confirmation(self, df, fib_levels, current_price):
        """分析价格行为对斐波那契支撑的确认"""
        if len(df) < 10:
            return 0.5
        
        try:
            confirmation_score = 0.5  # 基础分数
            
            # 1. 检查是否出现看涨吞没形态
            bullish_engulfing = self.detect_bullish_engulfing(df)
            if bullish_engulfing:
                confirmation_score += 0.2
            
            # 2. 检查是否出现锤子线
            hammer = self.detect_hammer(df)
            if hammer:
                confirmation_score += 0.15
            
            # 3. 检查RSI背离
            rsi_divergence = self.check_rsi_divergence(df)
            if rsi_divergence:
                confirmation_score += 0.15
            
            # 4. 检查成交量放大
            volume_spike = self.check_volume_spike(df)
            if volume_spike:
                confirmation_score += 0.1
            
            return min(confirmation_score, 1.0)
            
        except Exception as e:
            logging.debug(f"价格行为确认分析失败: {e}")
            return 0.5
    
    def detect_bullish_engulfing(self, df):
        """检测看涨吞没形态"""
        if len(df) < 2:
            return False
        
        current = df.iloc[-1]
        previous = df.iloc[-2]
        
        # 看涨吞没条件
        return (current["close"] > current["open"] and  # 当前阳线
                previous["close"] < previous["open"] and  # 前一根阴线
                current["open"] < previous["close"] and  # 当前开盘低于前收盘
                current["close"] > previous["open"])  # 当前收盘高于前开盘
    
    def detect_hammer(self, df):
        """检测锤子线"""
        if len(df) < 1:
            return False
        
        current = df.iloc[-1]
        body_size = abs(current["close"] - current["open"])
        lower_shadow = min(current["open"], current["close"]) - current["low"]
        upper_shadow = current["high"] - max(current["open"], current["close"])
        
        # 锤子线条件：下影线至少是实体长度的2倍，上影线很短
        return (lower_shadow >= 2 * body_size and 
                upper_shadow <= body_size * 0.5)
    
    def check_rsi_divergence(self, df, period=14):
        """检查RSI背离"""
        if len(df) < period + 5:
            return False
        
        # 计算RSI
        delta = df["close"].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rsi = 100 - (100 / (1 + gain / loss))
        
        # 简单背离检测：价格创新低但RSI没有
        if (df["close"].iloc[-1] < df["close"].iloc[-5] and 
            rsi.iloc[-1] > rsi.iloc[-5]):
            return True
        
        return False
    
    def check_volume_spike(self, df, multiplier=1.5):
        """检查成交量放大"""
        if len(df) < 20:
            return False
        
        current_volume = df["volume"].iloc[-1]
        avg_volume = df["volume"].tail(20).mean()
        
        return current_volume > avg_volume * multiplier
    
    def check_volume_confirmation(self, df, fib_level):
        """检查成交量确认"""
        if len(df) < 5:
            return 0.7
        
        # 在支撑位附近成交量应该放大
        recent_volume = df["volume"].tail(5).mean()
        avg_volume = df["volume"].tail(20).mean()
        
        if recent_volume > avg_volume:
            return 1.0
        elif recent_volume > avg_volume * 0.8:
            return 0.8
        else:
            return 0.6
    
    def check_depth_confirmation(self, depth_data, fib_level):
        """检查深度数据确认"""
        if not depth_data:
            return 0.7
        
        try:
            # 分析买盘深度
            bid_volume = sum([float(bid[1]) for bid in depth_data.get("bids", [])[:5]])
            ask_volume = sum([float(ask[1]) for ask in depth_data.get("asks", [])[:5]])
            
            if bid_volume + ask_volume == 0:
                return 0.7
            
            bid_ratio = bid_volume / (bid_volume + ask_volume)
            
            # 买盘深度越大，确认度越高
            if bid_ratio > 0.6:
                return 1.0
            elif bid_ratio > 0.5:
                return 0.8
            else:
                return 0.6
                
        except Exception as e:
            logging.debug(f"深度数据确认失败: {e}")
            return 0.7

# 全局实例
fibonacci_analyzer = FibonacciSupportAnalyzer()