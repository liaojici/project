import logging
from typing import Dict

def get_error_explanation(error_code: str) -> str:
    """获取错误代码的详细解释"""
    error_explanations = {
        "1": "一般错误，通常是参数错误或系统繁忙",
        "50000": "系统错误，请稍后重试",
        "50004": "请求太频繁，请降低请求频率",
        "51000": "参数错误，请检查请求参数",
        "51001": "产品不存在或已下线",
        "51002": "交易金额太小",
        "51003": "交易金额太大", 
        "51004": "价格精度错误",
        "51005": "数量精度错误",
        "51006": "杠杆倍数错误",
        "51007": "该产品不支持全仓模式",
        "51008": "该产品不支持逐仓模式",
        "51020": "保证金不足",
        "51100": "账户余额不足",
        "51106": "账户保证金不足",
        "51107": "账户可用余额不足",
    }
    return error_explanations.get(error_code, "未知错误，请参考API文档")

def get_error_suggestions(error_code: str) -> str:
    """获取针对错误的建议"""
    suggestions = {
        "51020": "检查账户余额和保证金是否充足",
        "51100": "检查账户余额和保证金是否充足", 
        "51106": "检查账户余额和保证金是否充足",
        "51107": "检查账户余额和保证金是否充足",
        "51004": "检查价格精度是否符合要求",
        "51005": "检查数量精度是否符合要求",
        "51001": "检查交易对是否存在或已下线",
        "50004": "API调用频率过高，请降低请求频率",
        "1": "检查订单参数是否正确，特别是价格和数量精度",
    }
    return suggestions.get(error_code, "请参考API文档检查参数")

# error_handlers.py 中的 log_trade_error_details 函数
def log_trade_error_details(error_code: str, error_msg: str, symbol: str, order_data: dict):
    """记录交易错误的详细信息"""
    explanation = get_error_explanation(error_code)
    suggestion = get_error_suggestions(error_code)
    
    logging.error(f"❌ 交易错误详情:")
    logging.error(f"   错误代码: {error_code}")
    logging.error(f"   错误信息: {error_msg}")
    logging.error(f"   错误解释: {explanation}")
    logging.error(f"   建议: {suggestion}")
    logging.error(f"   交易对: {symbol}")
    logging.error(f"   订单参数: {order_data}")
    
    # 添加更详细的调试信息
    logging.error(f"   订单参数类型检查:")
    for key, value in order_data.items():
        logging.error(f"     {key}: {value} (类型: {type(value)})")
    
    # 记录调试信息
    logging.debug(f"完整错误上下文 - 代码: {error_code}, 消息: {error_msg}")

def log_api_error_details(api_type: str, error: Exception, context: str = ""):
    """记录API错误的详细信息"""
    logging.error(f"❌ {api_type} API错误: {str(error)}")
    if context:
        logging.error(f"   上下文: {context}")
    
    # 记录详细的异常信息（仅在调试模式）
    import traceback
    logging.debug(f"完整堆栈跟踪:\n{traceback.format_exc()}")

def handle_connection_error(api_type: str, attempt: int, max_attempts: int, error: Exception):
    """处理连接错误"""
    logging.warning(f"🔌 {api_type} 连接错误 (尝试 {attempt}/{max_attempts}): {error}")
    if attempt < max_attempts:
        wait_time = 2 ** attempt
        logging.info(f"⏳ 等待 {wait_time} 秒后重试...")
        import time
        time.sleep(wait_time)