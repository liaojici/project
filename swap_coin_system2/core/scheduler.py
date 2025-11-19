import time
import logging

class SmartScheduler:
    def __init__(self):
        self.tasks = {}
        
    def add_task(self, name, function, interval, api_type=None):
        self.tasks[name] = {
            "function": function,
            "interval": interval,
            "last_run": 0,
            "api_type": api_type
        }
        logging.info(f"添加调度任务: {name} (间隔 {interval}s)")
    
    def run(self):
        current_time = time.time()
        
        for name, task in self.tasks.items():
            if current_time - task["last_run"] >= task["interval"]:
                try:
                    logging.info(f"▶️ 开始执行任务: {name}")
                    start_t = time.time()
                    
                    task["function"]()
                    
                    cost = time.time() - start_t
                    logging.info(f"✅ 任务完成: {name} (耗时 {cost:.2f}s)")
                    
                    task["last_run"] = current_time
                except Exception as e:
                    logging.error(f"❌ 任务 {name} 执行崩溃: {e}")
                    import traceback
                    logging.error(traceback.format_exc())
                    task["last_run"] = current_time 

scheduler = SmartScheduler()