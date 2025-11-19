"""
通用工具函数 - 集中管理所有重复的工具函数
"""
import time
import logging
import pandas as pd
import numpy as np
from functools import wraps
from datetime import datetime, timedelta

def safe_float_convert(value, default=0.0):
    """
    安全转换为浮点数
    
    Args:
        value: 要转换的值
        default: 转换失败时的默认值
    
    Returns:
        float: 转换后的浮点数
    """
    if value is None or value == "":
        return default
    try:
        return float(value)
    except (ValueError, TypeError):
        logging.debug(f"无法转换值为浮点数: {value}, 使用默认值: {default}")
        return default

def safe_int_convert(value, default=0):
    """
    安全转换为整数
    
    Args:
        value: 要转换的值
        default: 转换失败时的默认值
    
    Returns:
        int: 转换后的整数
    """
    if value is None or value == "":
        return default
    try:
        return int(value)
    except (ValueError, TypeError):
        logging.debug(f"无法转换值为整数: {value}, 使用默认值: {default}")
        return default

def timing_decorator(func):
    """
    计时装饰器 - 记录函数执行时间
    
    Args:
        func: 要计时的函数
    
    Returns:
        wrapper: 包装后的函数
    """
    @wraps(func)
    def wrapper(*args, **kwargs):
        start_time = time.time()
        result = func(*args, **kwargs)
        end_time = time.time()
        execution_time = end_time - start_time
        
        # 只在执行时间超过阈值时记录
        if execution_time > 1.0:  # 超过1秒才记录
            logging.debug(f"⏱️ {func.__name__} 执行时间: {execution_time:.3f}秒")
        
        return result
    return wrapper

def format_currency(value, currency="USDT"):
    """
    格式化货币显示
    
    Args:
        value: 货币值
        currency: 货币符号
    
    Returns:
        str: 格式化后的字符串
    """
    if value >= 1000000:
        return f"{value/1000000:.2f}M {currency}"
    elif value >= 1000:
        return f"{value/1000:.2f}K {currency}"
    else:
        return f"{value:.2f} {currency}"

def format_percentage(value, decimals=2):
    """
    格式化百分比显示
    
    Args:
        value: 百分比值（0-1之间）
        decimals: 小数位数
    
    Returns:
        str: 格式化后的百分比字符串
    """
    return f"{value*100:.{decimals}f}%"

def calculate_percentage_change(old_value, new_value):
    """
    计算百分比变化
    
    Args:
        old_value: 旧值
        new_value: 新值
    
    Returns:
        float: 百分比变化（小数形式）
    """
    if old_value == 0:
        return 0.0
    return (new_value - old_value) / old_value

def validate_dataframe(df, min_rows=10, required_columns=None):
    """
    验证DataFrame的有效性
    
    Args:
        df: 要验证的DataFrame
        min_rows: 最小行数要求
        required_columns: 必需的列列表
    
    Returns:
        bool: 数据是否有效
    """
    if df is None or df.empty:
        return False
    
    if len(df) < min_rows:
        return False
    
    if required_columns:
        for col in required_columns:
            if col not in df.columns:
                return False
    
    # 检查重要列是否有空值
    important_columns = ['close', 'volume']
    for col in important_columns:
        if col in df.columns and df[col].isna().any():
            return False
    
    return True

def calculate_weighted_average(values, weights):
    """
    计算加权平均值
    
    Args:
        values: 值列表
        weights: 权重列表
    
    Returns:
        float: 加权平均值
    """
    if not values or not weights or len(values) != len(weights):
        return 0.0
    
    total_weight = sum(weights)
    if total_weight == 0:
        return 0.0
    
    weighted_sum = sum(v * w for v, w in zip(values, weights))
    return weighted_sum / total_weight

def normalize_signal(signal_value, min_val=-1.0, max_val=1.0):
    """
    标准化信号值到指定范围
    
    Args:
        signal_value: 原始信号值
        min_val: 最小值
        max_val: 最大值
    
    Returns:
        float: 标准化后的信号值
    """
    # 确保在合理范围内
    normalized = max(min_val, min(max_val, signal_value))
    return normalized

def is_market_hours():
    """
    检查是否是市场活跃时间（简化版）
    
    Returns:
        bool: 是否是市场活跃时间
    """
    now = datetime.now()
    # 假设市场24/7开放
    return True

def calculate_volatility(df, period=20):
    """
    计算价格波动率
    
    Args:
        df: 包含价格数据的DataFrame
        period: 计算周期
    
    Returns:
        float: 波动率
    """
    if len(df) < period:
        return 0.0
    
    returns = df['close'].pct_change().dropna()
    if len(returns) < period:
        return 0.0
    
    volatility = returns.tail(period).std()
    return volatility

def format_timestamp(timestamp, format_type='datetime'):
    """
    格式化时间戳
    
    Args:
        timestamp: 时间戳
        format_type: 格式类型 ('datetime', 'date', 'time')
    
    Returns:
        str: 格式化后的时间字符串
    """
    if timestamp is None:
        return "N/A"
    
    dt = datetime.fromtimestamp(timestamp)
    
    if format_type == 'datetime':
        return dt.strftime('%Y-%m-%d %H:%M:%S')
    elif format_type == 'date':
        return dt.strftime('%Y-%m-%d')
    elif format_type == 'time':
        return dt.strftime('%H:%M:%S')
    else:
        return str(dt)

def safe_divide(numerator, denominator, default=0.0):
    """
    安全除法，避免除零错误
    
    Args:
        numerator: 分子
        denominator: 分母
        default: 除零时的默认值
    
    Returns:
        float: 除法结果
    """
    if denominator == 0:
        return default
    return numerator / denominator

def clamp(value, min_val, max_val):
    """
    将值限制在指定范围内
    
    Args:
        value: 要限制的值
        min_val: 最小值
        max_val: 最大值
    
    Returns:
        float: 限制后的值
    """
    return max(min_val, min(max_val, value))

def calculate_position_health(current_price, entry_price, liquidation_price, side):
    """
    计算仓位健康度
    
    Args:
        current_price: 当前价格
        entry_price: 入场价格
        liquidation_price: 强平价格
        side: 仓位方向 ('long' 或 'short')
    
    Returns:
        dict: 包含健康度信息的字典
    """
    if side == 'long':
        price_to_liquidation = current_price - liquidation_price
        price_moved = current_price - entry_price
    else:  # short
        price_to_liquidation = liquidation_price - current_price
        price_moved = entry_price - current_price
    
    if price_moved > 0:
        health_ratio = price_to_liquidation / price_moved
    else:
        health_ratio = 1.0
    
    return {
        'health_ratio': clamp(health_ratio, 0.0, 1.0),
        'distance_to_liquidation': abs(current_price - liquidation_price) / current_price,
        'liquidation_price': liquidation_price
    }

# 全局工具函数实例
class CommonUtils:
    """通用工具类"""
    
    @staticmethod
    def get_current_timestamp():
        """获取当前时间戳"""
        return time.time()
    
    @staticmethod
    def is_weekend():
        """检查是否是周末"""
        return datetime.now().weekday() >= 5
    
    @staticmethod
    def calculate_simple_moving_average(df, column='close', window=20):
        """计算简单移动平均线"""
        if len(df) < window:
            return None
        return df[column].rolling(window=window).mean().iloc[-1]
    
    @staticmethod
    def calculate_rsi(df, period=14):
        """计算RSI指标"""
        if len(df) < period:
            return 50.0  # 中性值
        
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        
        return rsi.iloc[-1] if not rsi.empty else 50.0

# 创建全局实例
common_utils = CommonUtils()