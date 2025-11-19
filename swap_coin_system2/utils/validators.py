import logging

def validate_data(df, symbol):
    """验证数据有效性"""
    if df is None or df.empty:
        logging.warning(f"{symbol}数据为空")
        return False
    if len(df) < 20:
        logging.warning(f"{symbol}数据量不足{len(df)}条")
        return False
    if df["close"].isna().any() or df["volume"].isna().any():
        logging.warning(f"{symbol}数据包含空值")
        return False
    return True