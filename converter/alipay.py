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
            
            # 获取交易金额，可能为0
            amount = transaction['amount']
            
            # 添加账户和金额
            if transaction['transaction_type'] == 'expense':
                entry += f"    {transaction['expense_account']}  {amount} CNY\n"
                entry += f"    {transaction['asset_account']}  -{amount} CNY\n"
            elif transaction['transaction_type'] == 'income':
                entry += f"    {transaction['asset_account']}  {amount} CNY\n"
                entry += f"    {transaction['income_account']}  -{amount} CNY\n"
            elif transaction['transaction_type'] == 'transfer':
                entry += f"    {transaction['to_account']}  {amount} CNY\n"
                entry += f"    {transaction['from_account']}  -{amount} CNY\n"
            else:
                # 未知类型，使用默认处理
                entry += f"    Expenses:Uncategorized  {amount} CNY\n"
                entry += f"    Assets:Alipay:Balance  -{amount} CNY\n"
            
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
            
            # 跳过标记为"不计收支"的交易
            if '收/支' in df.columns:
                df = df[df['收/支'] != '不计收支']
            
            # 跳过交易状态为"交易关闭"的交易
            if '交易状态' in df.columns:
                df = df[df['交易状态'] != '交易关闭']
            
            # 跳过transaction_type为'transfer'的交易
            if 'transaction_type' in df.columns:
                df = df[df['transaction_type'] != 'transfer']
                
            # 如果过滤后没有交易数据，返回空字符串
            if len(df) == 0:
                print("警告: 过滤后没有找到任何交易数据")
                return "# 过滤后没有发现有效的交易数据"
                
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
                            
                    # 注意：不再跳过金额为0的交易
                    # 即使金额为0也继续处理
                    
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
                    
                    # 获取交易数据
                    # 交易对方
                    payee = "Unknown"
                    if '交易对方' in row and not pd.isna(row['交易对方']):
                        payee = str(row['交易对方']).strip()
                    
                    # 商品说明/名称
                    narration = "Unknown"
                    if '商品说明' in row and not pd.isna(row['商品说明']):
                        narration = str(row['商品说明']).strip()
                    elif 'description' in row and not pd.isna(row['description']):
                        narration = str(row['description']).strip()
                    elif '商品名称' in row and not pd.isna(row['商品名称']):
                        narration = str(row['商品名称']).strip()
                    elif '交易分类' in row and not pd.isna(row['交易分类']):
                        narration = str(row['交易分类']).strip()
                    
                    # 交易方式
                    payment_method = ""
                    if '收/付款方式' in row and not pd.isna(row['收/付款方式']):
                        payment_method = str(row['收/付款方式']).strip()
                    
                    # 交易状态
                    status = "交易成功"
                    if '交易状态' in row and not pd.isna(row['交易状态']):
                        status = str(row['交易状态']).strip()
                    
                    # 交易编号
                    transaction_id = ""
                    if '交易订单号' in row and not pd.isna(row['交易订单号']):
                        transaction_id = str(row['交易订单号']).strip()
                    
                    # 交易类型
                    transaction_type = 'expense'
                    if '收/支' in row and not pd.isna(row['收/支']):
                        if row['收/支'] == '收入':
                            transaction_type = 'income'
                        elif row['收/支'] == '不计收支':
                            transaction_type = 'transfer'
                    
                    # 获取资产账户
                    asset_account = self.get_asset_account(row, payment_method)
                    
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
                        'asset_account': asset_account,
                    }
                    
                    # 根据交易类型设置账户
                    if transaction_type == 'expense':
                        # 获取支出账户映射
                        expense_account = self.get_expense_account(row, payee, narration)
                        transaction['expense_account'] = expense_account
                        
                        # 记录映射应用情况，帮助调试
                        print(f"交易明细: 付款方 '{payee}', 描述 '{narration}', 分配账户 '{expense_account}'")
                    
                    elif transaction_type == 'income':
                        # 获取收入账户映射
                        income_account = self.get_income_account(row, payee, narration)
                        transaction['income_account'] = income_account
                    
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
    
    def get_expense_account(self, row, payee="", narration=""):
        """获取支出账户（支持自定义映射，按照优先级顺序）"""
        expense_account = "Expenses:Uncategorized"
        
        # 详细记录行数据，帮助调试
        print("\n===== 处理交易记录 =====")
        
        # 收集交易信息
        counterparty = payee
        if not counterparty and '交易对方' in row and not pd.isna(row['交易对方']):
            counterparty = str(row['交易对方']).strip()
        print(f"交易对方: {counterparty}")
            
        description = narration
        if not description:
            # 检查所有可能包含商品说明的字段
            if '商品说明' in row and not pd.isna(row['商品说明']):
                description = str(row['商品说明']).strip()
            elif 'description' in row and not pd.isna(row['description']):
                description = str(row['description']).strip()
            elif '商品名称' in row and not pd.isna(row['商品名称']):
                description = str(row['商品名称']).strip()
        print(f"商品说明: {description}")
            
        category = ""
        if '交易分类' in row and not pd.isna(row['交易分类']):
            category = str(row['交易分类']).strip()
        print(f"交易分类: {category}")
            
        remarks = ""
        if '备注' in row and not pd.isna(row['备注']):
            remarks = str(row['备注']).strip()
            print(f"备注: {remarks}")
        
        # 记录所有自定义映射
        if hasattr(self.mapping, 'custom_expense_categories') and self.mapping.custom_expense_categories:
            print(f"当前自定义支出映射: {self.mapping.custom_expense_categories}")
            
            # 按照优先级顺序检查字段: 交易对方 > 商品说明 > 备注 > 交易分类
            
            # 1. 首先检查交易对方
            if counterparty:
                print(f"检查交易对方: {counterparty}")
                for key, account in self.mapping.custom_expense_categories.items():
                    if key in counterparty:
                        print(f"✓ 交易对方匹配: '{key}' 在 '{counterparty}' 中")
                        return account
                print("✗ 交易对方无匹配")
            
            # 2. 然后检查商品说明
            if description:
                print(f"检查商品说明: {description}")
                for key, account in self.mapping.custom_expense_categories.items():
                    if key in description:
                        print(f"✓ 商品说明匹配: '{key}' 在 '{description}' 中")
                        return account
                print("✗ 商品说明无匹配")
            
            # 3. 再检查备注
            if remarks:
                print(f"检查备注: {remarks}")
                for key, account in self.mapping.custom_expense_categories.items():
                    if key in remarks:
                        print(f"✓ 备注匹配: '{key}' 在 '{remarks}' 中")
                        return account
                print("✗ 备注无匹配")
            
            # 4. 最后检查交易分类
            if category:
                print(f"检查交易分类: {category}")
                for key, account in self.mapping.custom_expense_categories.items():
                    if key in category:
                        print(f"✓ 交易分类匹配: '{key}' 在 '{category}' 中")
                        return account
                print("✗ 交易分类无匹配")
            
            print("未找到自定义映射匹配项，使用默认映射")
        
        # 如果没有匹配的自定义映射，回退到默认映射
        if category:
            # 基于默认交易分类设置支出账户
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
                    print(f"使用默认映射: {category} -> {expense_account}")
                    break
        
        return expense_account
    
    def get_income_account(self, row, payee="", narration=""):
        """获取收入账户（支持自定义映射，按照优先级顺序）"""
        income_account = "Income:Uncategorized"
        
        # 收集交易信息
        counterparty = payee
        if not counterparty and '交易对方' in row and not pd.isna(row['交易对方']):
            counterparty = str(row['交易对方']).strip()
            
        description = narration
        if not description:
            # 检查所有可能包含商品说明的字段
            if '商品说明' in row and not pd.isna(row['商品说明']):
                description = str(row['商品说明']).strip()
            elif 'description' in row and not pd.isna(row['description']):
                description = str(row['description']).strip()
            elif '商品名称' in row and not pd.isna(row['商品名称']):
                description = str(row['商品名称']).strip()
            
        category = ""
        if '交易分类' in row and not pd.isna(row['交易分类']):
            category = str(row['交易分类']).strip()
            
        remarks = ""
        if '备注' in row and not pd.isna(row['备注']):
            remarks = str(row['备注']).strip()
        
        # 检查自定义映射（如果有）
        if hasattr(self.mapping, 'custom_income_categories') and self.mapping.custom_income_categories:
            # 按照优先级顺序检查字段: 交易对方 > 商品说明 > 备注 > 交易分类
            
            # 1. 首先检查交易对方
            if counterparty:
                for key, account in self.mapping.custom_income_categories.items():
                    if key in counterparty:
                        return account
            
            # 2. 然后检查商品说明
            if description:
                for key, account in self.mapping.custom_income_categories.items():
                    if key in description:
                        return account
            
            # 3. 再检查备注
            if remarks:
                for key, account in self.mapping.custom_income_categories.items():
                    if key in remarks:
                        return account
            
            # 4. 最后检查交易分类
            if category:
                for key, account in self.mapping.custom_income_categories.items():
                    if key in category:
                        return account
        
        # 如果没有匹配的自定义映射，回退到默认映射
        if category:
            # 默认映射
            if '退款' in category:
                income_account = "Income:Refund"
            elif '工资' in category or '薪资' in category:
                income_account = "Income:Salary"
            elif '奖金' in category:
                income_account = "Income:Bonus"
            elif '红包' in category:
                income_account = "Income:Gift"
        
        return income_account
    
    def get_asset_account(self, row, payment_method=""):
        """获取资产账户（支持自定义映射）"""
        asset_account = "Assets:Alipay:Balance"  # 默认账户
        
        # 获取支付方式
        if not payment_method and '收/付款方式' in row and not pd.isna(row['收/付款方式']):
            payment_method = str(row['收/付款方式']).strip()
        
        # 先检查是否为负债账户
        is_liability = False
        if hasattr(self.mapping, 'custom_liability_accounts') and self.mapping.custom_liability_accounts:
            for key, account in self.mapping.custom_liability_accounts.items():
                if key in payment_method:
                    asset_account = account
                    is_liability = True
                    return asset_account
                    
        # 如果不是自定义负债，检查默认负债
        for key, account in self.mapping.liability_accounts.items():
            if key in payment_method:
                asset_account = account
                is_liability = True
                break
        
        # 如果不是负债，检查自定义资产
        if not is_liability and hasattr(self.mapping, 'custom_asset_accounts') and self.mapping.custom_asset_accounts:
            for key, account in self.mapping.custom_asset_accounts.items():
                if key in payment_method:
                    asset_account = account
                    return asset_account
        
        # 如果不是自定义负债或资产，检查默认资产
        if not is_liability:
            for key, account in self.mapping.asset_accounts.items():
                if key in payment_method:
                    asset_account = account
                    break
                    
        # 其他特殊情况处理
        if not is_liability:
            # 处理储蓄卡
            if '储蓄卡' in payment_method:
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
            # 处理银行账户
            elif any(bank in payment_method for bank in ['工商', '农业', '中国', '建设', '交通', '邮政', '招商']):
                # 尝试提取银行名称和卡号
                for bank in ['工商', '农业', '中国', '建设', '交通', '邮政', '招商']:
                    if bank in payment_method:
                        card_match = re.search(r'\((\d+)\)', payment_method)
                        if card_match:
                            card = card_match.group(1)
                            asset_account = f"Assets:Bank:{bank}:{card}"
                            break
        # 处理信用卡
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
        
        return asset_account