import os
import sys
import time
import logging

# 设置项目根目录
PROJECT_ROOT = '/www/python/swap_coin_system2'
sys.path.insert(0, PROJECT_ROOT)
os.chdir(PROJECT_ROOT)

from core.api_client import initialize_okx_api
from core.state_manager import (
    strategy_state, 
    sync_manual_positions, 
    recalculate_asset_allocation, 
    check_account_drawdown, 
    get_tradable_balance, 
    get_position_value, 
    get_total_equity
)
from core.scheduler import scheduler
from utils.performance_monitor import performance_monitor
from config.settings import initialize_environment
from modules.symbol_selection import select_symbols
from modules.multi_frequency_monitor import frequency_monitor
from config.constants import MONITOR_INTERVALS, RISK_PARAMS,STOP_LOSS_INIT,TAKE_PROFIT1,TAKE_PROFIT2,TAKE_PROFIT3
from config.constants import BATCHES as USED_BATCHES
from modules.trading_execution import (check_all_exits,monitor_pending_orders)

def setup_logging():
    for handler in logging.root.handlers[:]:
        logging.root.removeHandler(handler)
    
    detailed_formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s'
    )
    simple_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    
    logging.basicConfig(
        level=logging.INFO,
        handlers=[
            logging.FileHandler("multi_strategy_with_roll_okx.log", mode='a', encoding='utf-8'),
            logging.StreamHandler()
        ]
    )
    
    for handler in logging.root.handlers:
        if isinstance(handler, logging.FileHandler):
            handler.setFormatter(detailed_formatter)
        else:
            handler.setFormatter(simple_formatter)
    
    logging.getLogger('urllib3').setLevel(logging.WARNING)
    logging.getLogger('requests').setLevel(logging.WARNING)
    logging.getLogger('httpx').setLevel(logging.WARNING)
    
    logging.info("详细日志配置完成")

def initialize_strategy():
    if not initialize_environment():
        return False
    
    if not initialize_okx_api():
        return False
    
    logging.info("所有分析模块已准备就绪")
    
    from utils.instrument_utils import initialize_instrument_cache
    initialize_instrument_cache()
    
    scheduler.add_task("monitor_pending_orders", monitor_pending_orders, 4 * 3600)
    
    from modules.trading_execution import initialize_trading_system
    if not initialize_trading_system():
        logging.warning("⚠️ 交易系统初始化有警告，继续运行")
    
    test_api_connections()
    takeover_manual_positions()
    
    strategy_state["selected_symbols"] = select_symbols()
    strategy_state["selected_symbols"] = [s for s in strategy_state["selected_symbols"] if "SWAP" in s]
    
    logging.info(f"监控合约标的数量: {len(strategy_state['selected_symbols'])}")
    
    frequency_monitor.setup_monitor_groups()
    
    # 注册监控任务
    scheduler.add_task("high_freq_monitor", frequency_monitor.monitor_high_frequency, 
                        MONITOR_INTERVALS["high_frequency"], "market_data")
    scheduler.add_task("medium_freq_monitor", frequency_monitor.monitor_medium_frequency, 
                        MONITOR_INTERVALS["medium_frequency"], "market_data")
    scheduler.add_task("low_freq_monitor", frequency_monitor.monitor_low_frequency, 
                        MONITOR_INTERVALS["low_frequency"], "market_data")
    
    scheduler.add_task("performance_report", performance_monitor.generate_report, 600)
    scheduler.add_task("update_balance", update_account_balance, 120)
    scheduler.add_task("sync_positions", sync_manual_positions, 300)
    scheduler.add_task("recalculate_assets", recalculate_asset_allocation, 120)
    
    from modules.trading_execution import cleanup_old_leverage_settings
    scheduler.add_task("cleanup_leverage", cleanup_old_leverage_settings, 3600)
    
    sync_manual_positions()
    recalculate_asset_allocation()
    log_asset_status()
    
    logging.info(f"策略初始化完成 - 基础风险{RISK_PARAMS['base_risk_per_trade']*100}%")
    return True

def takeover_manual_positions():
    try:
        import core.api_client
        api = core.api_client.account_api
        if api is None:
            return
        response = api.get_positions()
        if response and response.get("code") == "0" and response.get("data"):
            count = 0
            for pos in response["data"]:
                if float(pos.get("pos", 0)) != 0:
                    symbol = pos.get("instId")
                    if symbol not in strategy_state["selected_symbols"]:
                        strategy_state["selected_symbols"].append(symbol)
                        count += 1
                        logging.info(f"📥 接管手动仓位: {symbol}")
    except Exception as e:
        logging.error(f"接管手动仓位失败: {e}")

def validate_existing_positions():
    try:
        import core.api_client
        api = core.api_client.account_api
        if api is None: return
        response = api.get_positions()
        if response and response.get("code") == "0":
            real_positions = {p["instId"] for p in response.get("data", []) if float(p.get("pos", 0)) != 0}
            strategy_positions = list(strategy_state["positions"].keys())
            for sym in strategy_positions:
                if sym not in real_positions:
                    logging.warning(f"⚠️ 移除失效仓位: {sym}")
                    del strategy_state["positions"][sym]
    except Exception as e:
        logging.error(f"验证仓位异常: {e}")

def test_api_connections():
    logging.info("测试API连接...")
    try:
        import core.api_client
        if core.api_client.test_market_api():
            logging.info("市场API连接正常")
        else:
            logging.error("市场API连接失败")
    except Exception as e:
        logging.error(f"API连接测试异常: {e}")

def update_account_balance():
    import core.api_client
    core.api_client.get_account_balance()

def log_asset_status():
    t = get_tradable_balance()
    p = get_position_value()
    e = get_total_equity()
    logging.info(f"资产状态 - 总权益: {e:.2f}, 可交易: {t:.2f}, 仓位保证金: {p:.2f}")

def main():
    setup_logging()
    logging.info("程序启动...")
    
    if not initialize_strategy():
        logging.error("策略初始化失败")
        return
    
    logging.info("进入主循环")
    
    last_pos_validate = 0
    last_low_bal_check = 0
    last_heartbeat = 0
    
    # 测试打印
    from utils.instrument_utils import debug_quantity_format
    debug_quantity_format("TRX-USDT-SWAP", 10)

    while strategy_state["running"]:
        try:
            now = time.time()
            
            # 定时任务: 验证仓位 (5分钟)
            if now - last_pos_validate > 300:
                logging.info("⚡ 执行定时仓位验证")
                validate_existing_positions()
                last_pos_validate = now
            
            # 定时任务: 检查低余额 (30秒)
            if now - last_low_bal_check > 30:
                from core.state_manager import check_low_balance_mode
                check_low_balance_mode()
                last_low_bal_check = now
            
            # 核心: 运行调度器 (监控行情)
            scheduler.run()
            
            # 心跳日志 (每10分钟)
            if now - last_heartbeat > 600:
                logging.info("💓 系统运行中...")
                last_heartbeat = now
            
            time.sleep(1)
            
        except KeyboardInterrupt:
            logging.info("用户停止程序")
            break
        except Exception as e:
            logging.error(f"主循环未捕获异常: {e}")
            time.sleep(5)

if __name__ == "__main__":
    main()