import time
import logging
from functools import wraps
#from okx.exceptions import OkxAPIException

def safe_request(func):
    """安全请求装饰器，处理API调用异常"""
    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            logging.error(f"API请求失败 {func.__name__}: {e}")
            return None
    return wrapper

def rate_limit(limit_count, limit_seconds):
    """限流装饰器"""
    def decorator(func):
        call_times = []
        
        @wraps(func)
        def wrapper(*args, **kwargs):
            now = time.time()
            # 移除超过时间窗口的调用记录
            call_times[:] = [t for t in call_times if now - t < limit_seconds]
            
            if len(call_times) >= limit_count:
                sleep_time = limit_seconds - (now - call_times[0])
                if sleep_time > 0:
                    logging.warning(f"达到API限流，等待{sleep_time:.2f}秒")
                    time.sleep(sleep_time)
            
            call_times.append(now)
            return func(*args, **kwargs)
        return wrapper
    return decorator