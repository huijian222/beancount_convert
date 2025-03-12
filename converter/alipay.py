import csv
import re
import pandas as pd
from datetime import datetime
from .alipay_mapping import AlipayMapping
from .utils import escape_string

class AlipayConverter:
    """
    支付宝账单转换器
    将支付宝账单CSV文件转换为Beancount格式
    """
    
    def __init__(self):
        self.mapping = AlipayMapping()
    
    def format_beancount_entry(self, transaction):
        """格式化一条Beancount交易记录"""
        try:
            date = transaction['date']
            payee = escape_string(transaction['payee'])
            narration = escape_string(transaction['narration'])
            
            entry = f"{date} * \"{payee}\" \"{narration}\"\n"
            
            # 添加元数据
            if transaction['status']:
                entry += f"    status: \"{transaction['status']}\"\n"
            if transaction['time']:
                entry += f"    time: \"{transaction['time']}\"\n"
            if transaction['uuid']:
                entry += f"    uuid: \"{transaction['uuid']}\"\n"
            
            # 添加账户和金额
            if transaction['transaction_type'] == 'expense':
                entry += f"    {transaction['expense_account']}  {transaction['amount']} CNY\n"
                entry += f"    {transaction['asset_account']}  -{transaction['amount']} CNY\n"
            elif transaction['transaction_type'] == 'income':
                entry += f"    {transaction['asset_account']}  {transaction['amount']} CNY\n"
                entry += f"    {transaction['income_account']}  -{transaction['amount']} CNY\n"
            elif transaction['transaction_type'] == 'transfer':
                entry += f"    {transaction['to_account']}  {transaction['amount']} CNY\n"
                entry += f"    {transaction['from_account']}  -{transaction['amount']} CNY\n"
            else:
                # 未知类型，使用默认处理
                entry += f"    Expenses:Uncategorized  {transaction['amount']} CNY\n"
                entry += f"    Assets:Alipay:Balance  -{transaction['amount']} CNY\n"
            
            return entry
        except Exception as e:
            print(f"格式化条目时出错: {str(e)}, 交易: {transaction}")
            return ""
    
    def convert(self, filepath):
        """将支付宝账单转换为Beancount格式"""
        try:
            # 使用映射类加载和预处理文件
            df = self.mapping.load_file(filepath)
            
            # 如果没有有效的交易数据，返回空字符串
            if len(df) == 0:
                print("警告: 没有找到任何交易数据")
                return "# 没有发现有效的交易数据"
                
            beancount_entries = []
            
            for idx, row in df.iterrows():
                try:
                    # 首先检查金额
                    amount = 0.0
                    if 'actual_amount' in row and not pd.isna(row['actual_amount']):
                        amount = float(row['actual_amount'])
                    
                    # 直接从原始列获取金额作为后备
                    if amount <= 0 and '金额' in row and not pd.isna(row['金额']):
                        try:
                            amount = float(str(row['金额']).replace(',', ''))
                        except:
                            pass
                            
                    # 跳过金额为0的交易
                    if amount <= 0:
                        continue
                    
                    # 解析日期和时间
                    date_str = None
                    if 'transaction_time' in row and not pd.isna(row['transaction_time']):
                        date_str = row['transaction_time']
                    elif '交易时间' in row and not pd.isna(row['交易时间']):
                        date_str = row['交易时间']
                        
                    if not date_str or pd.isna(date_str):
                        print(f"警告: 行 {idx} 无法获取交易时间，跳过")
                        continue
                        
                    try:
                        datetime_obj = datetime.strptime(str(date_str).strip(), '%Y-%m-%d %H:%M:%S')
                    except ValueError:
                        print(f"警告: 无法解析日期 '{date_str}'，尝试其他格式")
                        try:
                            # 尝试其他常见格式
                            datetime_obj = datetime.strptime(str(date_str).strip(), '%Y/%m/%d %H:%M:%S')
                        except:
                            print(f"错误: 无法解析日期 '{date_str}'，使用当前日期")
                            datetime_obj = datetime.now()
                            
                    date = datetime_obj.strftime('%Y-%m-%d')
                    time = datetime_obj.strftime('%H:%M:%S')
                    
                    # 直接从原始列获取交易信息
                    payee = "Unknown"
                    if '交易对方' in row and not pd.isna(row['交易对方']):
                        payee = str(row['交易对方']).strip()
                    
                    narration = "Unknown"
                    if '商品说明' in row and not pd.isna(row['商品说明']):
                        narration = str(row['商品说明']).strip()
                    elif '交易分类' in row and not pd.isna(row['交易分类']):
                        narration = str(row['交易分类']).strip()
                    
                    payment_method = ""
                    if '收/付款方式' in row and not pd.isna(row['收/付款方式']):
                        payment_method = str(row['收/付款方式']).strip()
                    
                    status = "交易成功"
                    if '交易状态' in row and not pd.isna(row['交易状态']):
                        status = str(row['交易状态']).strip()
                    
                    transaction_id = ""
                    if '交易订单号' in row and not pd.isna(row['交易订单号']):
                        transaction_id = str(row['交易订单号']).strip()
                    
                    transaction_type = 'expense'
                    if '收/支' in row and not pd.isna(row['收/支']):
                        if row['收/支'] == '收入':
                            transaction_type = 'income'
                        elif row['收/支'] == '不计收支':
                            transaction_type = 'transfer'
                    
                    # 收集交易信息
                    transaction = {
                        'date': date,
                        'time': time,
                        'payee': payee,
                        'narration': narration,
                        'transaction_type': transaction_type,
                        'amount': amount,
                        'payment_method': payment_method,
                        'status': f"Alipay - {status}",
                        'uuid': transaction_id,
                    }
                    
                    # 设置账户信息
                    asset_account = "Assets:Alipay:Balance"  # 默认账户
                    
                    # 根据支付方式判断资产账户
                    if '余额宝' in payment_method:
                        asset_account = "Assets:Alipay:Yuebao"
                    elif '花呗' in payment_method:
                        asset_account = "Liabilities:Alipay:Huabei"
                    elif '信用卡' in payment_method:
                        # 尝试提取银行和卡号
                        bank_match = re.search(r'([\u4e00-\u9fa5]+)银行信用卡', payment_method)
                        card_match = re.search(r'\((\d+)\)', payment_method)
                        
                        if bank_match and card_match:
                            bank = bank_match.group(1)
                            card = card_match.group(1)
                            asset_account = f"Liabilities:CreditCard:{bank}:{card}"
                        elif card_match:
                            card = card_match.group(1)
                            asset_account = f"Liabilities:CreditCard:{card}"
                    elif '储蓄卡' in payment_method:
                        # 提取银行和卡号
                        bank_match = re.search(r'([\u4e00-\u9fa5]+)银行储蓄卡', payment_method)
                        card_match = re.search(r'\((\d+)\)', payment_method)
                        
                        if bank_match and card_match:
                            bank = bank_match.group(1)
                            card = card_match.group(1)
                            asset_account = f"Assets:Bank:{bank}:{card}"
                        elif card_match:
                            card = card_match.group(1)
                            asset_account = f"Assets:Bank:{card}"
                    elif any(bank in payment_method for bank in ['工商', '农业', '中国', '建设', '交通', '邮政', '招商']):
                        # 尝试提取银行名称和卡号
                        for bank in ['工商', '农业', '中国', '建设', '交通', '邮政', '招商']:
                            if bank in payment_method:
                                card_match = re.search(r'\((\d+)\)', payment_method)
                                if card_match:
                                    card = card_match.group(1)
                                    asset_account = f"Assets:Bank:{bank}:{card}"
                                    break
                    
                    # 根据交易类型设置账户
                    if transaction_type == 'expense':
                        # 根据交易分类设置支出账户
                        expense_account = "Expenses:Uncategorized"
                        
                        if '交易分类' in row and not pd.isna(row['交易分类']):
                            category = row['交易分类']
                            
                            # 基于交易分类设置支出账户
                            category_mapping = {
                                '餐饮': 'Expenses:Food',
                                '美食': 'Expenses:Food',
                                '超市': 'Expenses:Shopping:Groceries',
                                '日用': 'Expenses:Shopping:Daily',
                                '交通': 'Expenses:Transport',
                                '服饰': 'Expenses:Clothing',
                                '娱乐': 'Expenses:Entertainment'
                            }
                            
                            for key, account in category_mapping.items():
                                if key in category:
                                    expense_account = account
                                    break
                        
                        transaction['expense_account'] = expense_account
                        transaction['asset_account'] = asset_account
                    
                    elif transaction_type == 'income':
                        # 收入账户
                        income_account = "Income:Uncategorized"
                        
                        if '交易分类' in row and not pd.isna(row['交易分类']):
                            category = row['交易分类']
                            
                            # 基于交易分类设置收入账户
                            if '退款' in category:
                                income_account = "Income:Refund"
                            elif '工资' in category or '薪资' in category:
                                income_account = "Income:Salary"
                            elif '奖金' in category:
                                income_account = "Income:Bonus"
                            elif '红包' in category:
                                income_account = "Income:Gift"
                        
                        transaction['income_account'] = income_account
                        transaction['asset_account'] = asset_account
                    
                    elif transaction_type == 'transfer':
                        # 处理转账交易
                        from_account = asset_account
                        to_account = "Assets:Unknown"
                        
                        # 根据交易描述判断转账类型
                        if '余额宝' in narration:
                            if '转出' in narration:
                                from_account = "Assets:Alipay:Yuebao"
                                to_account = "Assets:Alipay:Balance"
                            else:
                                from_account = "Assets:Alipay:Balance"
                                to_account = "Assets:Alipay:Yuebao"
                        elif '花呗' in narration:
                            if '还款' in narration:
                                from_account = asset_account
                                to_account = "Liabilities:Alipay:Huabei"
                        elif '还款' in narration:
                            # 信用卡还款
                            from_account = asset_account
                            if '交易对方' in row and not pd.isna(row['交易对方']):
                                card_name = row['交易对方']
                                if '信用卡' in card_name:
                                    bank_match = re.search(r'([\u4e00-\u9fa5]+)银行', card_name)
                                    if bank_match:
                                        bank = bank_match.group(1)
                                        to_account = f"Liabilities:CreditCard:{bank}"
                        
                        transaction['from_account'] = from_account
                        transaction['to_account'] = to_account
                    
                    # 格式化为Beancount条目
                    beancount_entry = self.format_beancount_entry(transaction)
                    if beancount_entry:
                        beancount_entries.append(beancount_entry)
                    
                except Exception as e:
                    print(f"处理交易时出错: {str(e)}, 行: {row}")
                    continue
            
            return "\n\n".join(beancount_entries)
        except Exception as e:
            raise ValueError(f"转换支付宝账单时出错: {str(e)}")