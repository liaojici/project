# 修改 enhanced_strategy.py
import logging
import pandas as pd
import numpy as np
from utils.decorators import safe_request
from core.cache_manager import get_cached_data
from modules.fibonacci_support import fibonacci_analyzer
from modules.momentum_breakout import momentum_breakout   # 新增导入
from config.constants import ENTRY_STRATEGY
class EnhancedStrategy:
    def __init__(self):
        self.volume_threshold = 1.5
        self.volatility_threshold = 0.03
        
    def calculate_enhanced_score(self, df, symbol, depth_data=None):
        """计算综合增强得分 - 包含减分项"""
        if df is None or len(df) < 50:
            return 0, 0, 0
            
        try:
            current_price = df.iloc[-1]["close"]
            
            # 1. 动量得分（可正可负）
            momentum_score = momentum_breakout.calculate_momentum_score(df)
            
            # 2. 突破信号
            breakout_detected, breakout_direction = momentum_breakout.detect_breakout(df)
            breakout_score = breakout_direction * 0.3 if breakout_detected else 0
            
            # 3. 支撑阻力分析（包含减分逻辑）
            position_score, support_penalty, resistance_penalty = self.calculate_position_score_with_penalty(df, current_price)
            
            # 4. 斐波那契分析
            fib_support_strength, fib_support_price = fibonacci_analyzer.analyze_fibonacci_support_strength(df, current_price, depth_data)
            fib_resistance_strength, fib_resistance_price = fibonacci_analyzer.analyze_fibonacci_resistance_strength(df, current_price, depth_data)
            
            # 5. 成交量确认
            volume_score = self.calculate_volume_score(df)
            
            # 6. 波动率调整（高波动率减分）
            volatility_penalty = self.calculate_volatility_penalty(df)
            
            # 综合计算（包含减分项）
            enhanced_score = (
                momentum_score * 0.25 +
                breakout_score * 0.20 +
                position_score * 0.15 +
                (fib_support_strength - fib_resistance_strength) * 0.15 +
                volume_score * 0.10 +
                support_penalty * 0.08 +
                resistance_penalty * 0.07 -
                volatility_penalty * 0.10
            )
            
            # 确保在合理范围内
            enhanced_score = max(-1.0, min(1.0, enhanced_score))
            
            logging.debug(f"增强得分分析 - {symbol}: 动量={momentum_score:.3f}, 突破={breakout_score:.3f}, "
                            f"位置={position_score:.3f}, 支撑强度={fib_support_strength:.3f}, 阻力强度={fib_resistance_strength:.3f}, "
                            f"成交量={volume_score:.3f}, 波动惩罚={volatility_penalty:.3f}, 最终得分={enhanced_score:.3f}")
            
            return enhanced_score, fib_support_strength, fib_resistance_strength
            
        except Exception as e:
            logging.error(f"计算增强得分失败: {e}")
            return 0, 0, 0
    
    def calculate_position_score_with_penalty(self, df, current_price):
        """计算位置得分，包含接近阻力位的减分"""
        if len(df) < 20:
            return 0, 0, 0
            
        try:
            # 传统位置得分
            traditional_score = self.calculate_traditional_support(df)
            
            # 阻力位接近度惩罚
            resistance_distance = self.calculate_resistance_distance(df, current_price)
            resistance_penalty = max(0, 0.5 - resistance_distance * 10)  # 距离越近惩罚越大
            
            # 支撑位接近度奖励（但不超过传统得分）
            support_distance = self.calculate_support_distance(df, current_price)
            support_bonus = min(0.3, support_distance * 5)
            
            # 综合位置得分
            position_score = traditional_score + support_bonus - resistance_penalty
            
            return max(0, min(1, position_score)), resistance_penalty, 0
            
        except Exception as e:
            logging.debug(f"位置得分计算失败: {e}")
            return 0, 0, 0
    
    def calculate_resistance_distance(self, df, current_price, period=20):
        """计算当前价格距离阻力位的相对距离"""
        resistance_level = df['high'].tail(period).max()
        distance = (resistance_level - current_price) / current_price
        return max(0, distance)
    
    def calculate_support_distance(self, df, current_price, period=20):
        """计算当前价格距离支撑位的相对距离"""
        support_level = df['low'].tail(period).min()
        distance = (current_price - support_level) / current_price
        return max(0, distance)
    
    def calculate_volume_score(self, df):
        """计算成交量确认得分"""
        if len(df) < 5:
            return 0
            
        current_volume = df['volume'].iloc[-1]
        avg_volume = df['volume'].tail(20).mean()
        
        if current_volume > avg_volume * 2:
            return 1.0
        elif current_volume > avg_volume * 1.5:
            return 0.7
        elif current_volume > avg_volume:
            return 0.3
        else:
            return -0.2  # 成交量不足减分
    
    def calculate_volatility_penalty(self, df, period=20):
        """计算高波动率惩罚"""
        if len(df) < period:
            return 0
            
        volatility = df['close'].tail(period).std() / df['close'].tail(period).mean()
        
        if volatility > 0.08:  # 超过8%波动率
            return 0.8
        elif volatility > 0.05:  # 5-8%波动率
            return 0.4
        else:
            return 0

    # 保留原有的支撑阻力计算方法（因为新方法中会调用到）
    def calculate_enhanced_support_resistance(self, df, symbol, depth_data=None):
        """增强版支撑阻力计算 - 使用配置参数"""
        if df is None or len(df) < 50:
            return 0, 0, 0, 0
            
        try:
            # 使用配置参数
            support_strength_threshold = ENTRY_STRATEGY["support_strength_threshold"]
            resistance_strength_threshold = ENTRY_STRATEGY["resistance_strength_threshold"]
            
            current_price = df.iloc[-1]["close"]
            
            # 1. 斐波那契支撑阻力
            fib_support_strength, fib_support_price = fibonacci_analyzer.analyze_fibonacci_support_strength(df, current_price, depth_data)
            fib_resistance_strength, fib_resistance_price = fibonacci_analyzer.analyze_fibonacci_resistance_strength(df, current_price, depth_data)
            
            # 2. 移动平均线支撑阻力
            ma_support, ma_resistance = self.calculate_ma_support_resistance(df, current_price)
            
            # 3. 布林带支撑阻力
            bb_support, bb_resistance = self.calculate_bollinger_support_resistance(df, current_price)
            
            # 4. 前高前低支撑阻力
            # 在 calculate_enhanced_support_resistance 方法中替换原来的调用
            previous_support, previous_resistance = self.calculate_previous_support_resistance(df, current_price)
            
            # 5. 成交量分布支撑阻力
            volume_support, volume_resistance = self.calculate_volume_profile_support_resistance(df)
            
            # 综合计算支撑位（取最低的有效支撑位）
            support_candidates = []
            if fib_support_price > 0 and fib_support_strength > support_strength_threshold:
                support_candidates.append((fib_support_price, fib_support_strength))
            if ma_support[0] > 0 and ma_support[1] > 0.5:
                support_candidates.append((ma_support[0], ma_support[1]))
            if bb_support[0] > 0 and bb_support[1] > 0.5:
                support_candidates.append((bb_support[0], bb_support[1]))
            if previous_support[0] > 0 and previous_support[1] > 0.5:
                support_candidates.append((previous_support[0], previous_support[1]))
            if volume_support[0] > 0 and volume_support[1] > 0.5:
                support_candidates.append((volume_support[0], volume_support[1]))
            
            # 综合计算阻力位（取最高的有效阻力位）
            resistance_candidates = []
            if fib_resistance_price > 0 and fib_resistance_strength > resistance_strength_threshold:
                resistance_candidates.append((fib_resistance_price, fib_resistance_strength))
            if ma_resistance[0] > 0 and ma_resistance[1] > 0.5:
                resistance_candidates.append((ma_resistance[0], ma_resistance[1]))
            if bb_resistance[0] > 0 and bb_resistance[1] > 0.5:
                resistance_candidates.append((bb_resistance[0], bb_resistance[1]))
            if previous_resistance[0] > 0 and previous_resistance[1] > 0.5:
                resistance_candidates.append((previous_resistance[0], previous_resistance[1]))
            if volume_resistance[0] > 0 and volume_resistance[1] > 0.5:
                resistance_candidates.append((volume_resistance[0], volume_resistance[1]))
            
            # 选择最强的支撑阻力位
            final_support_price = 0
            final_support_strength = 0
            if support_candidates:
                # 选择最接近当前价格的支撑位
                valid_supports = [s for s in support_candidates if s[0] < current_price]
                if valid_supports:
                    final_support_price = max(s[0] for s in valid_supports)  # 选择最高的有效支撑
                    final_support_strength = max(s[1] for s in valid_supports if s[0] == final_support_price)
            
            final_resistance_price = 0
            final_resistance_strength = 0
            if resistance_candidates:
                # 选择最接近当前价格的阻力位
                valid_resistances = [r for r in resistance_candidates if r[0] > current_price]
                if valid_resistances:
                    final_resistance_price = min(r[0] for r in valid_resistances)  # 选择最低的有效阻力
                    final_resistance_strength = max(r[1] for r in valid_resistances if r[0] == final_resistance_price)
            
            # 如果找不到有效的支撑阻力位，使用技术指标计算
            if final_support_price == 0:
                final_support_price = df['low'].tail(20).min()
                final_support_strength = 0.3
                
            if final_resistance_price == 0:
                final_resistance_price = df['high'].tail(20).max()
                final_resistance_strength = 0.3
            
            logging.debug(f"支撑阻力综合分析 - {symbol}: 支撑={final_support_price:.6f}(强度{final_support_strength:.2f}), 阻力={final_resistance_price:.6f}(强度{final_resistance_strength:.2f})")
            
            return final_support_strength, final_support_price, final_resistance_strength, final_resistance_price
            
        except Exception as e:
            logging.error(f"增强支撑阻力位计算失败: {e}")
            # 返回基本的技术支撑阻力
            basic_support = df['low'].tail(20).min()
            basic_resistance = df['high'].tail(20).max()
            return 0.5, basic_support, 0.5, basic_resistance
    # 保留原有的技术指标计算方法
    def calculate_traditional_support(self, df, window=20):
        """传统技术指标支撑计算"""
        if len(df) < window:
            return 0
        return 0.5  # 简化返回

    def calculate_traditional_resistance(self, df, window=20):
        """传统技术指标阻力计算"""
        if len(df) < window:
            return 0
            
        try:
            # 移动平均线阻力
            ma_resistance = self.calculate_ma_resistance(df, window)
            
            # 布林带上轨阻力
            bb_resistance = self.calculate_bollinger_resistance(df, window)
            
            # 前高点阻力
            previous_high_resistance = self.calculate_previous_high_resistance(df, window)
            
            # 综合传统阻力
            traditional_resistance = (ma_resistance + bb_resistance + previous_high_resistance) / 3
            
            return traditional_resistance
            
        except Exception as e:
            logging.debug(f"传统阻力计算失败: {e}")
            return 0
    
    def calculate_ma_support_resistance(self, df, current_price, periods=[20, 50, 100]):
        """移动平均线支撑阻力"""
        support_price = 0
        resistance_price = 0
        support_strength = 0
        resistance_strength = 0
        
        for period in periods:
            if len(df) >= period:
                ma = df['close'].rolling(window=period).mean().iloc[-1]
                if ma < current_price and ma > support_price:
                    support_price = ma
                    support_strength = 0.6
                elif ma > current_price and (resistance_price == 0 or ma < resistance_price):
                    resistance_price = ma
                    resistance_strength = 0.6
        
        return (support_price, support_strength), (resistance_price, resistance_strength)
    
    def calculate_bollinger_support_resistance(self, df, current_price, period=20):
        """布林带支撑阻力"""
        if len(df) < period:
            return (0, 0), (0, 0)
        
        bb_mid = df['close'].rolling(window=period).mean()
        bb_std = df['close'].rolling(window=period).std()
        bb_upper = bb_mid + 2 * bb_std
        bb_lower = bb_mid - 2 * bb_std
        
        bb_upper_value = bb_upper.iloc[-1]
        bb_lower_value = bb_lower.iloc[-1]
        
        support_strength = 0.7 if current_price > bb_lower_value else 0.3
        resistance_strength = 0.7 if current_price < bb_upper_value else 0.3
        
        return (bb_lower_value, support_strength), (bb_upper_value, resistance_strength)
    
    def calculate_previous_support_resistance(self, df, current_price, lookback_period=50):
        """前高前低支撑阻力计算 - 替代原来的单一函数"""
        if len(df) < lookback_period:
            return (0, 0), (0, 0)
        
        # 获取前高前低
        previous_lows = df['low'].tail(lookback_period)
        previous_highs = df['high'].tail(lookback_period)
        
        # 找出显著的前低（支撑位）
        significant_low = previous_lows.min()
        # 找出显著的前高（阻力位）
        significant_high = previous_highs.max()
        
        # 计算支撑强度
        if current_price >= significant_low:
            distance_to_support = abs(current_price - significant_low) / current_price
            support_strength = max(0, 1 - distance_to_support * 10)  # 距离越近强度越高
        else:
            support_strength = 0.1  # 价格在支撑下方，支撑很弱
        
        # 计算阻力强度
        if current_price <= significant_high:
            distance_to_resistance = abs(current_price - significant_high) / current_price
            resistance_strength = max(0, 1 - distance_to_resistance * 10)  # 距离越近强度越高
        else:
            resistance_strength = 0.1  # 价格在阻力上方，阻力很弱
        
        logging.debug(f"前高前低分析 - 支撑: {significant_low:.6f}(强度{support_strength:.2f}), 阻力: {significant_high:.6f}(强度{resistance_strength:.2f})")
        
        return (significant_low, support_strength), (significant_high, resistance_strength)
    
    def calculate_volume_profile_support_resistance(self, df, period=20):
        """成交量分布支撑阻力"""
        if len(df) < period:
            return 0, 0
        
        # 计算价格区间的成交量集中度
        price_levels = np.linspace(df["low"].min(), df["high"].max(), 10)
        volume_concentration = {}
        
        for i in range(len(price_levels)-1):
            mask = (df["close"] >= price_levels[i]) & (df["close"] < price_levels[i+1])
            volume_concentration[i] = df[mask]["volume"].sum()
        
        # 找到成交量最大的价格区间作为主要支撑/阻力
        if volume_concentration:
            max_volume_level = max(volume_concentration, key=volume_concentration.get)
            total_volume = df["volume"].sum()
            
            # 支撑强度（低价格区间）
            support_levels = [k for k in volume_concentration.keys() if k <= max_volume_level]
            support_volume = sum(volume_concentration[k] for k in support_levels)
            support_strength = support_volume / total_volume
            
            # 阻力强度（高价格区间）
            resistance_levels = [k for k in volume_concentration.keys() if k >= max_volume_level]
            resistance_volume = sum(volume_concentration[k] for k in resistance_levels)
            resistance_strength = resistance_volume / total_volume
            
            return min(support_strength, 1.0), min(resistance_strength, 1.0)
        
        return 0, 0
    
    def get_depth_support_resistance(self, symbol, depth_data, current_price):
        """基于深度数据的支撑阻力分析"""
        if depth_data is None:
            return 0.5, 0.5  # 中性
        
        try:
            # 分析买盘深度（支撑）
            bid_volume = sum([float(bid[1]) for bid in depth_data.get("bids", [])[:3]])
            
            # 分析卖盘深度（阻力）
            ask_volume = sum([float(ask[1]) for ask in depth_data.get("asks", [])[:3]])
            
            if bid_volume + ask_volume == 0:
                return 0.5, 0.5
            
            # 支撑强度（买盘深度占比）
            support_strength = bid_volume / (bid_volume + ask_volume)
            
            # 阻力强度（卖盘深度占比）
            resistance_strength = ask_volume / (bid_volume + ask_volume)
            
            # 当前价格距离最近大单的距离调整
            if depth_data.get("bids"):
                nearest_bid = float(depth_data["bids"][0][0])
                bid_distance = abs(current_price - nearest_bid) / current_price
                
                if bid_distance < 0.01:  # 1%以内
                    support_strength *= 0.9
                else:
                    support_strength *= 0.6
            
            if depth_data.get("asks"):
                nearest_ask = float(depth_data["asks"][0][0])
                ask_distance = abs(current_price - nearest_ask) / current_price
                
                if ask_distance < 0.01:  # 1%以内
                    resistance_strength *= 0.9
                else:
                    resistance_strength *= 0.6
                
            return support_strength, resistance_strength
            
        except Exception as e:
            logging.debug(f"深度数据支撑阻力分析失败: {e}")
            return 0.5, 0.5
    
    def calculate_resistance_price(self, df, fib_resistance_price, traditional_resistance, volume_resistance):
        """计算综合阻力位价格"""
        current_price = df.iloc[-1]["close"]
        
        # 如果有斐波那契阻力位，优先使用
        if fib_resistance_price and fib_resistance_price > 0:
            return fib_resistance_price
        
        # 否则使用技术指标计算的阻力位
        traditional_resistance_price = df["high"].tail(20).max()
        
        # 确保阻力位在当前价格上方
        resistance_price = max(traditional_resistance_price, current_price * 1.01)
        
        return resistance_price

    def calculate_support_price(self, df, fib_support_price, traditional_support, volume_support):
        """计算综合支撑位价格"""
        current_price = df.iloc[-1]["close"]
        
        # 如果有斐波那契支撑位，优先使用
        if fib_support_price and fib_support_price > 0:
            return fib_support_price
        
        # 否则使用技术指标计算的支撑位
        traditional_support_price = df["low"].tail(20).min()
        
        # 确保支撑位在当前价格下方
        support_price = min(traditional_support_price, current_price * 0.99)
        
        return support_price

# 全局实例
enhanced_strategy = EnhancedStrategy()