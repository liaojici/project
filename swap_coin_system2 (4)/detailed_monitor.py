import logging
import sys
import os
import time
import pandas as pd

PROJECT_ROOT = '/www/python/swap_coin_system2'
sys.path.insert(0, PROJECT_ROOT)
os.chdir(PROJECT_ROOT)

from core.state_manager import strategy_state, get_total_equity, get_tradable_balance
from modules.technical_analysis import get_kline_data

def setup_detailed_logging():
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s',
        handlers=[
            logging.FileHandler("detailed_monitor.log", mode='a', encoding='utf-8'),
            logging.StreamHandler()
        ]
    )

def monitor_account_status():
    """监控账户状态 - 安全打印"""
    # 使用安全获取函数，确保返回浮点数
    total_equity = get_total_equity()
    tradable_balance = get_tradable_balance()
    positions = strategy_state.get("positions", {})
    
    logging.info("💰 账户状态监控:")
    # 这里的 .2f 不会再报错，因为函数保证返回 0.0 而不是 None
    logging.info(f"   总权益: {total_equity:.2f} USDT")
    logging.info(f"   可交易余额: {tradable_balance:.2f} USDT")
    logging.info(f"   活跃仓位: {len(positions)} 个")
    
    total_pos_value = sum(pos.get('notional_value', 0) for pos in positions.values())
    logging.info(f"   仓位总价值: {total_pos_value:.2f} USDT")
    
    if total_equity > 0:
        ratio = total_pos_value / total_equity
        logging.info(f"   仓位占比: {ratio*100:.1f}%")

def monitor_signal_strength_for_all_symbols():
    symbols = strategy_state.get("selected_symbols", [])
    if not symbols:
        logging.info("暂无监控标的")
        return
        
    logging.info(f"📊 监控 {len(symbols)} 个标的信号...")
    
    # 限制每次监控的数量，防止API超限
    for symbol in symbols[:5]: 
        try:
            from modules.trading_execution import check_enhanced_multi_signal
            result = check_enhanced_multi_signal(symbol)
            # 解包结果，提供默认值防止出错
            if len(result) == 4:
                signal_ok, df, strength, direction = result
            else:
                strength = 0
                direction = "unknown"
            
            if strength > 0.4: # 只打印有一定强度的
                logging.info(f"   {symbol}: 强度={strength:.2f}, 方向={direction}")
                
        except Exception as e:
            pass # 监控脚本不应中断

def run_detailed_monitor():
    setup_detailed_logging()
    
    # 必须正确初始化
    import core.api_client
    from config.settings import initialize_environment
    
    logging.info("🚀 启动详细监控...")
    initialize_environment()
    
    if not core.api_client.initialize_okx_api():
        logging.error("API 初始化失败，监控退出")
        return
    
    from core.state_manager import sync_manual_positions
    sync_manual_positions()
    
    while True:
        try:
            logging.info("=" * 40)
            monitor_account_status()
            monitor_signal_strength_for_all_symbols()
            logging.info("=" * 40)
            time.sleep(60)
        except KeyboardInterrupt:
            break
        except Exception as e:
            logging.error(f"监控循环错误: {e}")
            time.sleep(10)

if __name__ == "__main__":
    run_detailed_monitor()