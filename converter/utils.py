import re

def escape_string(string):
    """
    转义Beancount字符串中的特殊字符
    """
    if not string:
        return "Unknown"
    return string.replace('"', '\\"')

def get_account_by_keyword(text, account_map, default_account):
    """
    根据关键词在账户映射表中查找对应的账户
    """
    if not text:
        return default_account
        
    for keyword, account in account_map.items():
        if keyword in text:
            return account
    
    return default_account

def format_amount(amount):
    """
    格式化金额为两位小数
    """
    return f"{float(amount):.2f}"