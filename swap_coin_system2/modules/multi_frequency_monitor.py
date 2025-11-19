import logging
import time
from core.state_manager import strategy_state
from modules.trading_execution import process_symbol
from config.constants import BATCHES, MONITOR_INTERVALS

class MultiFrequencyMonitor:
    def __init__(self):
        self.monitor_groups = {
            "high_frequency": [],
            "medium_frequency": [], 
            "low_frequency": []
        }
        self.last_monitor_time = {
            "high_frequency": 0,
            "medium_frequency": 0,
            "low_frequency": 0
        }
        # 低余额模式下的监控间隔
        self.low_balance_intervals = {
            "high_frequency": 15,
            "medium_frequency": 30,
            "low_frequency": 60
        }
    
    def setup_monitor_groups(self):
        """超级无敌修复版：完全抛弃 constants.BATCHES 的硬编码分组，直接用动态分类结果"""
        # 直接从策略状态拿动态分类结果（symbol_selection.py 里存的）
        dynamic = strategy_state.get("dynamic_batches", {})
        
        if isinstance(dynamic, dict) and "high_frequency" in dynamic:
            # 完美情况：用动态分类的三个组
            high = dynamic.get("high_frequency", [])
            medium = dynamic.get("medium_frequency", [])
            low = dynamic.get("low_frequency", [])
        else:
            # 兜底：从 selected_symbols 里随便挑（基本不会走到）
            selected = strategy_state.get("selected_symbols", [])
            high = selected[:17]
            medium = selected[17:24]
            low = selected[24:31]

        # 强制过滤：确保都在最终31个里（理论上已经是了）
        selected_set = set(strategy_state.get("selected_symbols", []))
        self.monitor_groups["high_frequency"]   = [s for s in high if s in selected_set]
        self.monitor_groups["medium_frequency"] = [s for s in medium if s in selected_set]
        self.monitor_groups["low_frequency"]    = [s for s in low if s in selected_set]

        # 手动仓位强制进高频
        for symbol in strategy_state.get("positions", {}):
            if symbol not in self.monitor_groups["high_frequency"]:
                self.monitor_groups["high_frequency"].append(symbol)

        # 打印确认
        logging.info(f"【超级修复成功】高频监控 {len(self.monitor_groups['high_frequency'])} 个: {self.monitor_groups['high_frequency']}")
        logging.info(f"【超级修复成功】中频监控 {len(self.monitor_groups['medium_frequency'])} 个: {self.monitor_groups['medium_frequency']}")
        logging.info(f"【超级修复成功】低频监控 {len(self.monitor_groups['low_frequency'])} 个: {self.monitor_groups['low_frequency']}")

    def get_monitor_interval(self, group_name):
        from core.state_manager import is_in_low_balance_mode
        if is_in_low_balance_mode():
            return self.low_balance_intervals.get(group_name, 30)
        return MONITOR_INTERVALS.get(group_name, 60)
    
    def get_monitor_symbols(self, group_name):
        from core.state_manager import is_in_low_balance_mode, get_position_symbols
        if is_in_low_balance_mode():
            # 低余额模式下，只在高频任务中监控持仓币种
            pos_symbols = get_position_symbols()
            return pos_symbols if group_name == "high_frequency" else []
        return self.monitor_groups.get(group_name, [])
    
    def safe_process_symbol(self, symbol, group_name=None):
        """安全处理单个币种"""
        try:
            process_symbol(symbol)
        except Exception as e:
            logging.error(f"❌ 处理 {symbol} 异常: {e}")

    def process_symbols_concurrently(self, symbols, group_name):
        """
        【修复版】强制串行处理，彻底解决多线程卡死问题
        """
        from core.state_manager import is_in_low_balance_mode
        
        # 1. 筛选需要处理的币种
        actual_symbols = []
        selected = strategy_state.get("selected_symbols", [])
        positions = strategy_state.get("positions", {})
        
        for symbol in symbols:
            if symbol not in selected:
                logging.warning(f"⚠️ 跳过不在选中列表的币种: {symbol}")
                continue
            # 必须在选中列表中
            if symbol in selected:
                # 如果是低余额模式，必须有持仓
                if is_in_low_balance_mode():
                    if symbol in positions:
                        actual_symbols.append(symbol)
                else:
                    actual_symbols.append(symbol)
        
        if not actual_symbols:
            return
            
        logging.info(f"🚀 {group_name} 开始处理: {len(actual_symbols)} 个标的 (串行模式)")
        
        # 2. 串行循环处理
        start_total = time.time()
        for i, symbol in enumerate(actual_symbols):
            try:
                # 打印当前进度，这样如果卡住就知道是哪个币
                logging.info(f"   👉 [{i+1}/{len(actual_symbols)}] 正在分析: {symbol} ...")
                
                step_start = time.time()
                self.safe_process_symbol(symbol, group_name)
                step_cost = time.time() - step_start
                
                # 如果处理时间过长，记录警告
                if step_cost > 5.0:
                    logging.warning(f"   ⚠️ {symbol} 分析耗时过长: {step_cost:.2f}s")
                
                # 3. 强制休眠，防止 API 限流导致下次请求卡顿
                time.sleep(0.2)
                
            except Exception as e:
                logging.error(f"   ❌ 分析 {symbol} 时发生未捕获异常: {e}")
                continue

        total_cost = time.time() - start_total
        logging.info(f"🏁 {group_name} 全部完成 (总耗时: {total_cost:.2f}s)")

    def monitor_high_frequency(self):
        self._run_monitor("high_frequency")
    
    def monitor_medium_frequency(self):
        self._run_monitor("medium_frequency")
    
    def monitor_low_frequency(self):
        self._run_monitor("low_frequency")

    def _run_monitor(self, group):
        current_time = time.time()
        interval = self.get_monitor_interval(group)
        
        # 检查是否到了运行时间
        if self.last_monitor_time[group] == 0 or current_time - self.last_monitor_time[group] >= interval:
            symbols = self.get_monitor_symbols(group)
            if symbols:
                self.process_symbols_concurrently(symbols, group)
            self.last_monitor_time[group] = current_time

frequency_monitor = MultiFrequencyMonitor()