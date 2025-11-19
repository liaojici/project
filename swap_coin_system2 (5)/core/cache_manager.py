import time

# 全局缓存
cache = {
    "chain_data": {}, "sentiment_data": {}, "kline_data": {}, "market_data": {}
}

def get_cached_data(cache_key, fetch_func, expire, *args, **kwargs):
    """获取缓存数据"""
    now = time.time()
    if cache_key in cache and now - cache[cache_key][0] < expire:
        return cache[cache_key][1]
    data = fetch_func(*args, **kwargs)
    if data is not None:
        cache[cache_key] = (now, data)
    return data

def clear_cache():
    """清空缓存"""
    global cache
    cache = {
        "chain_data": {}, "sentiment_data": {}, "kline_data": {}, "market_data": {}
    }

# cache_manager.py 中添加
def cache_instrument_info(instruments):
    """缓存交易产品信息"""
    global cache
    cache["instrument_info"] = instruments

def get_cached_instrument_info():
    """获取缓存的交易产品信息"""
    return cache.get("instrument_info", {})