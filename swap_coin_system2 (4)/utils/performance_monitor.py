import time
import logging
from datetime import datetime

class PerformanceMonitor:
    def __init__(self):
        self.start_time = time.time()
        self.trade_count = 0
        self.api_calls = {
            "market_data": 0,      # 市场数据API调用
            "account": 0,          # 账户API调用  
            "trade": 0,            # 交易API调用
            "public_data": 0,      # 公共数据API调用
            "trading_data": 0,     # 交易数据API调用
            "other": 0             # 其他API调用
        }
        self.last_report_time = time.time()
    
    def record_trade(self, symbol, side, size, price):
        """记录交易"""
        self.trade_count += 1
        logging.info(f"[绩效记录] 第{self.trade_count}笔交易: {side} {symbol} {size:.4f} @ {price:.2f}")
    
    def record_api_call(self, api_type):
        """记录API调用"""
        if api_type in self.api_calls:
            self.api_calls[api_type] += 1
        else:
            self.api_calls["other"] += 1
        logging.debug(f"API调用记录: {api_type} - 总计: {self.get_total_api_calls()}")
    
    def get_total_api_calls(self):
        """获取总API调用次数"""
        return sum(self.api_calls.values())
    
    def get_api_calls_per_minute(self):
        """获取每分钟API调用次数"""
        current_time = time.time()
        runtime_minutes = (current_time - self.start_time) / 60
        if runtime_minutes < 0.1:  # 避免除以0
            return 0
        return self.get_total_api_calls() / runtime_minutes
    
    def get_trades_per_hour(self):
        """获取每小时交易次数"""
        current_time = time.time()
        runtime_hours = (current_time - self.start_time) / 3600
        if runtime_hours < 0.01:  # 避免除以0
            return 0
        return self.trade_count / runtime_hours
    
    def generate_report(self):
        """生成详细的性能报告"""
        from core.state_manager import strategy_state
        
        current_time = time.time()
        runtime = current_time - self.start_time
        hours = runtime / 3600
        minutes = runtime / 60
        
        total_api_calls = self.get_total_api_calls()
        api_per_minute = self.get_api_calls_per_minute()
        trades_per_hour = self.get_trades_per_hour()
        
        # 获取账户余额
        current_balance = strategy_state.get('last_balance', 0)
        initial_balance = strategy_state.get('initial_balance', current_balance)
        
        # 计算盈亏
        if initial_balance > 0:
            pnl = current_balance - initial_balance
            pnl_percent = (pnl / initial_balance) * 100
        else:
            pnl = 0
            pnl_percent = 0
        
        # 获取活跃仓位详情
        positions = strategy_state.get('positions', {})
        position_details = []
        for symbol, pos in positions.items():
            pos_type = "手动" if pos.get('manual') else "自动"
            position_details.append(f"{symbol}({pos_type})")
        
        report = f"""
    === 策略性能报告 ===
    运行时间: {hours:.2f} 小时 ({minutes:.0f} 分钟)
    总交易次数: {self.trade_count}
    交易频率: {trades_per_hour:.2f} 次/小时

    API调用统计:
    总API调用: {total_api_calls} 次
    API频率: {api_per_minute:.2f} 次/分钟
    市场数据: {self.api_calls['market_data']} 次
    账户查询: {self.api_calls['account']} 次
    交易执行: {self.api_calls['trade']} 次
    公共数据: {self.api_calls['public_data']} 次
    交易数据: {self.api_calls['trading_data']} 次
    其他: {self.api_calls['other']} 次

    账户状态:
    初始余额: {initial_balance:.2f} USDT
    当前余额: {current_balance:.2f} USDT
    盈亏: {pnl:+.2f} USDT ({pnl_percent:+.2f}%)
    活跃仓位: {len(positions)} 个
    仓位详情: {', '.join(position_details) if position_details else '无'}

    信号状态:
    监控标的: {len(strategy_state.get('selected_symbols', []))} 个
    最后选标时间: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(strategy_state.get('last_selection_time', 0)))}

    报告时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
    ==================
    """
        logging.info(report)
        return report

# 全局性能监控器
performance_monitor = PerformanceMonitor()