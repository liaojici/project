# modules/momentum_breakout.py
import pandas as pd
import numpy as np
import logging

class MomentumBreakoutStrategy:
    def __init__(self):
        self.breakout_threshold = 0.02  # 2%突破阈值
    
    def calculate_momentum_score(self, df, period=20):
        """计算动量得分"""
        if len(df) < period:
            return 0
            
        try:
            # 价格动量
            price_change = (df['close'].iloc[-1] - df['close'].iloc[-period]) / df['close'].iloc[-period]
            
            # 成交量动量
            volume_change = (df['volume'].iloc[-1] - df['volume'].iloc[-period:].mean()) / df['volume'].iloc[-period:].mean()
            
            # RSI动量
            rsi = self.calculate_rsi(df, period=14)
            rsi_momentum = (rsi.iloc[-1] - 50) / 50
            
            # 波动率调整
            volatility = df['close'].tail(period).std() / df['close'].tail(period).mean()
            volatility_adjustment = 1 - min(volatility * 10, 0.5)  # 高波动率降低得分
            
            # 综合动量得分
            momentum_score = (
                price_change * 0.4 +
                np.tanh(volume_change) * 0.3 +
                rsi_momentum * 0.3
            ) * volatility_adjustment
            
            return max(-1, min(1, momentum_score))
            
        except Exception as e:
            logging.debug(f"动量得分计算失败: {e}")
            return 0
    
    def detect_breakout(self, df, lookback_period=20):
        """检测突破信号"""
        if len(df) < lookback_period:
            return False, 0
            
        try:
            current_high = df['high'].iloc[-1]
            current_low = df['low'].iloc[-1]
            
            # 计算近期高低点
            recent_high = df['high'].tail(lookback_period).max()
            recent_low = df['low'].tail(lookback_period).min()
            
            # 突破检测
            upward_breakout = current_high > recent_high * (1 + self.breakout_threshold)
            downward_breakout = current_low < recent_low * (1 - self.breakout_threshold)
            
            if upward_breakout:
                return True, 1  # 向上突破
            elif downward_breakout:
                return True, -1  # 向下突破
            else:
                return False, 0
                
        except Exception as e:
            logging.debug(f"突破检测失败: {e}")
            return False, 0
    
    def calculate_rsi(self, df, period=14):
        """计算RSI"""
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        return rsi

# 全局实例
momentum_breakout = MomentumBreakoutStrategy()