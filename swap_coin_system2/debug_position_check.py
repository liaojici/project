# debug_position_detailed.py
import logging
import sys
import os
import time
import traceback

# 设置项目根目录
PROJECT_ROOT = '/www/python/swap_coin_system2'
sys.path.insert(0, PROJECT_ROOT)
os.chdir(PROJECT_ROOT)

from core.state_manager import strategy_state
from modules.technical_analysis import get_kline_data

def debug_check_enhanced_exit_signals(symbol, df):
    """详细调试 check_enhanced_exit_signals 函数"""
    print(f"\n🔍 详细调试 {symbol} 的退出信号检查:")
    
    positions = strategy_state.get("positions", {})
    if symbol not in positions:
        print(f"  ❌ 仓位不存在于策略状态中")
        return
    
    position = positions[symbol]
    
    try:
        # 1. 测试智能止盈检查
        print(f"  🧪 测试 check_smart_take_profit...")
        from modules.trading_execution import check_smart_take_profit
        
        # 获取当前信号
        from modules.trading_execution import check_enhanced_multi_signal
        current_signal_ok, _, current_signal_strength, current_direction = check_enhanced_multi_signal(symbol)
        print(f"    当前信号: 方向={current_direction}, 强度={current_signal_strength:.3f}")
        
        take_profit_decision, action, close_ratio, close_reason = check_smart_take_profit(
            symbol, df, position, current_signal_strength, current_direction
        )
        print(f"    ✅ check_smart_take_profit 完成: {take_profit_decision}, {action}, {close_ratio}, {close_reason}")
        
    except Exception as e:
        print(f"    ❌ check_smart_take_profit 失败: {e}")
        print(f"    🔍 详细错误: {traceback.format_exc()}")
        return
    
    try:
        # 2. 测试止损检查
        print(f"  🧪 测试 check_stop_loss_conditions...")
        from modules.trading_execution import check_stop_loss_conditions
        
        should_stop, stop_reason = check_stop_loss_conditions(symbol, df, position)
        print(f"    ✅ check_stop_loss_conditions 完成: {should_stop}, {stop_reason}")
        
    except Exception as e:
        print(f"    ❌ check_stop_loss_conditions 失败: {e}")
        print(f"    🔍 详细错误: {traceback.format_exc()}")
        return
    
    try:
        # 3. 测试浮亏加仓检查
        print(f"  🧪 测试 check_float_loss_add_condition...")
        from modules.trading_execution import check_float_loss_add_condition
        
        add_condition_met, add_ratio_or_reason = check_float_loss_add_condition(
            symbol, df, position, current_signal_strength, current_direction
        )
        print(f"    ✅ check_float_loss_add_condition 完成: {add_condition_met}, {add_ratio_or_reason}")
        
    except Exception as e:
        print(f"    ❌ check_float_loss_add_condition 失败: {e}")
        print(f"    🔍 详细错误: {traceback.format_exc()}")
        return
    
    # 4. 最后测试完整的退出信号检查
    try:
        print(f"  🧪 测试完整的 check_enhanced_exit_signals...")
        from modules.trading_execution import check_enhanced_exit_signals
        
        start_time = time.time()
        result = check_enhanced_exit_signals(symbol, df)
        end_time = time.time()
        
        print(f"    ✅ check_enhanced_exit_signals 完成，耗时: {end_time - start_time:.2f}秒")
        print(f"    结果: {result}")
        
    except Exception as e:
        print(f"    ❌ check_enhanced_exit_signals 失败: {e}")
        print(f"    🔍 详细错误: {traceback.format_exc()}")

def debug_smart_take_profit_components(symbol, df, position):
    """详细调试智能止盈的各个组件"""
    print(f"\n🔍 详细调试 {symbol} 的智能止盈组件:")
    
    try:
        # 获取当前信号
        from modules.trading_execution import check_enhanced_multi_signal
        current_signal_ok, _, current_signal_strength, current_direction = check_enhanced_multi_signal(symbol)
        print(f"  当前信号: 方向={current_direction}, 强度={current_signal_strength:.3f}")
        
        # 测试 check_smart_take_profit 内部逻辑
        current_price = df.iloc[-1]["close"]
        open_price = position["open_price"]
        side = position.get("side", "long")
        leverage = position.get("leverage", 1)
        
        print(f"  仓位信息: 开仓价={open_price:.6f}, 当前价={current_price:.6f}, 方向={side}, 杠杆={leverage}")
        
        # 计算盈利比例
        if side == "long":
            price_profit_ratio = (current_price - open_price) / open_price
            account_profit_ratio = price_profit_ratio * leverage
        else:
            price_profit_ratio = (open_price - current_price) / open_price
            account_profit_ratio = price_profit_ratio * leverage
        
        print(f"  价格盈利比例: {price_profit_ratio:.3f}")
        print(f"  账户盈利比例: {account_profit_ratio:.3f}")
        
        # 检查止盈阈值
        from config.constants import TAKE_PROFIT1, TAKE_PROFIT2, TAKE_PROFIT3
        TAKE_PROFIT1_ACCOUNT = TAKE_PROFIT1 * leverage
        TAKE_PROFIT2_ACCOUNT = TAKE_PROFIT2 * leverage
        TAKE_PROFIT3_ACCOUNT = TAKE_PROFIT3 * leverage
        
        print(f"  止盈阈值 (考虑杠杆):")
        print(f"    TP1: {TAKE_PROFIT1_ACCOUNT:.3f}")
        print(f"    TP2: {TAKE_PROFIT2_ACCOUNT:.3f}")
        print(f"    TP3: {TAKE_PROFIT3_ACCOUNT:.3f}")
        
        # 检查是否达到止盈点
        take_profit_reached = False
        take_profit_level = 0
        
        if account_profit_ratio >= TAKE_PROFIT1_ACCOUNT and position.get("remaining", 1.0) == 1.0:
            take_profit_reached = True
            take_profit_level = 1
        elif account_profit_ratio >= TAKE_PROFIT2_ACCOUNT and position.get("remaining", 1.0) > 0.5:
            take_profit_reached = True
            take_profit_level = 2
        elif account_profit_ratio >= TAKE_PROFIT3_ACCOUNT:
            take_profit_reached = True
            take_profit_level = 3
        
        print(f"  止盈检查: 达到={take_profit_reached}, 级别={take_profit_level}")
        
        if not take_profit_reached:
            print(f"  ⏸️ 未达到止盈条件，跳过后续检查")
            return
        
        # 获取支撑阻力分析
        try:
            from modules.enhanced_strategy import enhanced_strategy
            support_strength, support_price, resistance_strength, resistance_price = enhanced_strategy.calculate_enhanced_support_resistance(df, symbol)
            print(f"  支撑阻力分析:")
            print(f"    支撑位: {support_price:.6f} (强度: {support_strength:.3f})")
            print(f"    阻力位: {resistance_price:.6f} (强度: {resistance_strength:.3f})")
        except Exception as e:
            print(f"  ⚠️ 支撑阻力分析失败: {e}")
        
        # 智能止盈决策
        from config.constants import SMART_TAKE_PROFIT
        
        action = None
        close_reason = None
        close_ratio = 1.0
        
        if current_signal_strength > SMART_TAKE_PROFIT["strong_signal_threshold"] and \
            account_profit_ratio >= SMART_TAKE_PROFIT["min_rollover_profit"] and \
            current_direction == side:
            action = "rollover"
            close_reason = "strong_signal_rollover"
        elif current_signal_strength < SMART_TAKE_PROFIT["weak_signal_threshold"]:
            action = "close"
            close_reason = "weak_signal_take_profit"
            close_ratio = 1.0
        else:
            action = "partial_close"
            close_reason = f"partial_take_profit_level_{take_profit_level}"
            
            if take_profit_level == 1:
                close_ratio = SMART_TAKE_PROFIT["partial_profit_ratios"][0]
            elif take_profit_level == 2:
                close_ratio = SMART_TAKE_PROFIT["partial_profit_ratios"][1]
            else:
                close_ratio = SMART_TAKE_PROFIT["partial_profit_ratios"][2]
        
        print(f"  智能止盈决策:")
        print(f"    动作: {action}")
        print(f"    平仓比例: {close_ratio}")
        print(f"    原因: {close_reason}")
        
    except Exception as e:
        print(f"  ❌ 智能止盈组件调试失败: {e}")
        print(f"  🔍 详细错误: {traceback.format_exc()}")

def debug_enhanced_multi_signal(symbol):
    """调试增强多重信号检查"""
    print(f"\n🔍 调试 {symbol} 的增强多重信号:")
    
    try:
        from modules.trading_execution import check_enhanced_multi_signal
        
        start_time = time.time()
        result = check_enhanced_multi_signal(symbol)
        end_time = time.time()
        
        print(f"  ✅ check_enhanced_multi_signal 完成，耗时: {end_time - start_time:.2f}秒")
        
        if len(result) == 4:
            signal_ok, df, signal_strength, direction = result
            print(f"    结果: signal_ok={signal_ok}, df_size={len(df) if df is not None else 'None'}, strength={signal_strength:.3f}, direction={direction}")
        else:
            print(f"    ⚠️ 返回值数量异常: {len(result)}")
            
    except Exception as e:
        print(f"  ❌ check_enhanced_multi_signal 失败: {e}")
        print(f"  🔍 详细错误: {traceback.format_exc()}")

def debug_position_detailed(symbol):
    """详细调试单个仓位"""
    print(f"\n🔍 详细诊断 {symbol}:")
    
    # 1. 检查仓位是否存在
    positions = strategy_state.get("positions", {})
    if symbol not in positions:
        print(f"  ❌ 仓位不存在于策略状态中")
        return
    
    position = positions[symbol]
    print(f"  ✅ 找到仓位: {position.get('side', 'unknown')}, 大小: {position.get('size', 0)}")
    
    # 2. 获取K线数据
    try:
        df = get_kline_data(symbol, "1H", 50)
        if df is None or df.empty:
            print(f"  ❌ 无法获取K线数据")
            return
        
        print(f"  ✅ 获取到 {len(df)} 条K线数据")
        current_price = df.iloc[-1]["close"]
        print(f"  📊 当前价格: {current_price:.6f}")
        
    except Exception as e:
        print(f"  ❌ 获取K线数据失败: {e}")
        return
    
    # 3. 调试增强多重信号
    debug_enhanced_multi_signal(symbol)
    
    # 4. 调试智能止盈组件
    debug_smart_take_profit_components(symbol, df, position)
    
    # 5. 调试完整的退出信号检查
    debug_check_enhanced_exit_signals(symbol, df)

def debug_all_positions_detailed():
    """详细诊断所有持仓"""
    positions = strategy_state.get("positions", {})
    print(f"📊 总持仓数量: {len(positions)}")
    
    for symbol in positions.keys():
        debug_position_detailed(symbol)

if __name__ == "__main__":
    # 初始化必要的组件
    from core.api_client import initialize_okx_api
    from config.settings import initialize_environment
    
    print("🚀 开始详细仓位诊断...")
    
    initialize_environment()
    initialize_okx_api()
    
    # 同步手动仓位
    from core.state_manager import sync_manual_positions
    sync_manual_positions()
    
    debug_all_positions_detailed()
    
    print("\n🎉 详细诊断完成")