#!/usr/bin/env python3
"""
测试通用工具函数
"""
import sys
import os
sys.path.insert(0, '/www/python/swap_coin_system2')

from utils.common_utils import *

def test_common_utils():
    """测试通用工具函数"""
    print("测试通用工具函数...")
    
    # 测试安全转换
    assert safe_float_convert("123.45") == 123.45
    assert safe_float_convert(None) == 0.0
    assert safe_float_convert("invalid", 99.0) == 99.0
    
    # 测试货币格式化
    assert format_currency(1500000) == "1.50M USDT"
    assert format_currency(2500) == "2.50K USDT"
    assert format_currency(100) == "100.00 USDT"
    
    # 测试百分比格式化
    assert format_percentage(0.1567) == "15.67%"
    assert format_percentage(0.1567, 1) == "15.7%"
    
    # 测试百分比变化计算
    assert calculate_percentage_change(100, 120) == 0.2
    assert calculate_percentage_change(100, 80) == -0.2
    
    # 测试标准化
    assert normalize_signal(1.5) == 1.0
    assert normalize_signal(-2.0) == -1.0
    assert normalize_signal(0.5) == 0.5
    
    # 测试安全除法
    assert safe_divide(10, 2) == 5.0
    assert safe_divide(10, 0) == 0.0
    assert safe_divide(10, 0, 99.0) == 99.0
    
    # 测试范围限制
    assert clamp(15, 0, 10) == 10
    assert clamp(-5, 0, 10) == 0
    assert clamp(5, 0, 10) == 5
    
    print("✅ 所有通用工具函数测试通过!")

if __name__ == "__main__":
    test_common_utils()