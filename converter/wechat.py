import csv
import re
import pandas as pd
from datetime import datetime
from .wechat_mapping import WeChatMapping
from .utils import escape_string

class WeChatConverter:
    """
    微信账单转换器
    将微信支付账单CSV文件转换为Beancount格式
    """
    
    def __init__(self):
        self.mapping = WeChatMapping()
    def detect_transaction_type(self, row, narration, payee, status):
        """
        增强型交易类型检测方法，即使在type字段为None的情况下也能工作
        """
        print("\n===== 增强型交易类型检测 =====")
        transaction_type = 'expense'  # 默认为支出
        
        # 尝试从type字段判断
        if 'type' in row and not pd.isna(row['type']) and row['type'] is not None:
            type_value = str(row['type']).strip()
            print(f"收/支标记值: '{type_value}'")
            
            if type_value == '收入':
                transaction_type = 'income'
                print("✓ 基于type字段判断为收入")
            elif type_value == '/':
                transaction_type = 'transfer'
                print("✓ 基于type字段判断为转账")
        else:
            print("⚠ type字段为空或不存在，尝试使用其他字段判断")
        
        # 尝试从原始列名判断
        for col_name in row.index:
            if '收/支' in col_name and not pd.isna(row[col_name]):
                value = str(row[col_name]).strip()
                print(f"找到收/支相关列 '{col_name}': '{value}'")
                if value == '收入':
                    transaction_type = 'income'
                    print("✓ 基于收/支列判断为收入")
                elif value == '/':
                    transaction_type = 'transfer'
                    print("✓ 基于收/支列判断为转账") 
        
        # 通过交易分类判断
        category = ""
        if 'transaction_category' in row and not pd.isna(row['transaction_category']):
            category = str(row['transaction_category']).strip()
        elif '交易类型' in row and not pd.isna(row['交易类型']):
            category = str(row['交易类型']).strip()
        
        if category:
            print(f"交易分类: '{category}'")
            
            # 通过分类判断红包
            if '微信红包' in category and not '发红包' in category:
                transaction_type = 'income'
                print("✓ 基于交易分类判断为红包收入")
            elif '转账' in category or '提现' in category:
                transaction_type = 'transfer'
                print("✓ 基于交易分类判断为转账")
        
        # 通过交易对方判断
        if payee:
            print(f"交易对方: '{payee}'")
            if '微信红包' in payee or '微信安全支付' in payee:
                transaction_type = 'income'
                print("✓ 基于交易对方判断为红包收入")
        
        # 通过交易状态判断
        if status:
            print(f"交易状态: '{status}'")
            if '已存入零钱' in status or '已领取' in status:
                # 这些状态通常表示收到钱
                if '红包' in category or '红包' in narration:
                    transaction_type = 'income'
                    print("✓ 基于交易状态和内容判断为红包收入")
        
        # 通过交易描述判断
        if narration:
            print(f"交易描述: '{narration}'")
            if '微信红包' in narration and not '发红包' in narration:
                transaction_type = 'income'
                print("✓ 基于交易描述判断为红包收入")
        
        print(f"最终判断的交易类型: {transaction_type}")
        return transaction_type
    def format_beancount_entry(self, transaction):
        """格式化一条Beancount交易记录"""
        try:
            date = transaction['date']
            payee = escape_string(transaction['payee'])
            narration = escape_string(transaction['narration'])
            
            # 显示当前处理的交易基本信息，帮助调试
            print(f"\n格式化交易: 日期={date}, 交易对方={payee}, 描述={narration}, 类型={transaction['transaction_type']}")
            
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
            print(f"交易金额: {amount} CNY")
            
            # 添加账户和金额
            if transaction['transaction_type'] == 'expense':
                # 支出：从资产账户到支出账户
                print(f"✓ 处理为支出交易 | 支出: {transaction['expense_account']} <- 资产: {transaction['asset_account']}")
                entry += f"    {transaction['expense_account']}  {amount} CNY\n"
                entry += f"    {transaction['asset_account']}  -{amount} CNY\n"
            elif transaction['transaction_type'] == 'income':
                # 收入：从收入账户到资产账户
                print(f"✓ 处理为收入交易 | 资产: {transaction['asset_account']} <- 收入: {transaction['income_account']}")
                entry += f"    {transaction['asset_account']}  {amount} CNY\n"
                entry += f"    {transaction['income_account']}  -{amount} CNY\n"
            elif transaction['transaction_type'] == 'transfer':
                # 转账：从一个账户到另一个账户
                print(f"✓ 处理为转账交易 | 目标: {transaction['to_account']} <- 来源: {transaction['from_account']}")
                entry += f"    {transaction['to_account']}  {amount} CNY\n"
                entry += f"    {transaction['from_account']}  -{amount} CNY\n"
            else:
                # 未知类型，使用默认处理
                print(f"⚠ 未知交易类型，使用默认处理")
                entry += f"    Expenses:Uncategorized  {amount} CNY\n"
                entry += f"    Assets:WeChat:Balance  -{amount} CNY\n"
            
            return entry
        except Exception as e:
            print(f"格式化条目时出错: {str(e)}, 交易: {transaction}")
            return ""
    def convert(self, filepath):
        """将微信账单转换为Beancount格式"""
        try:
            # 使用映射类加载和预处理文件
            df = self.mapping.load_file(filepath)
            
            # 如果没有有效的交易数据，返回空字符串
            if len(df) == 0:
                print("警告: 没有找到任何交易数据")
                return "# 没有发现有效的交易数据"
            
            # # 跳过标记为不计收支的交易 (微信中是"/")
            # if '支付方式' in df.columns:
            #     df = df[df['type'] != '/']
            
            # 跳过交易状态为"已全额退款"、"对方已退还"、"已退款"的交易
            print(df.columns)
            if '当前状态' in df.columns:
                print(f"过滤前交易数: {len(df)}")
                # 合并所有需要过滤的状态
                ignore_statuses = ["已全额退款"]
                if hasattr(self.mapping, 'ignore_statuses'):
                    for status in self.mapping.ignore_statuses:
                        if status not in ignore_statuses:
                            ignore_statuses.append(status)
                df = df[~df['当前状态'].isin(ignore_statuses)]
                print(f"过滤后交易数: {len(df)}")
            
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
                    if amount <= 0:
                        # 尝试所有可能的列，不仅仅是'amount'
                        for col_name in row.index:
                            if pd.isna(row[col_name]):
                                continue
                                
                            col_value = str(row[col_name])
                            # 检查此列是否可能包含金额信息
                            if '¥' in col_value or '￥' in col_value or \
                               (re.search(r'\d+\.?\d*', col_value) and ('元' in col_value or '￥' in col_value)):
                                try:
                                    # 微信账单金额格式特殊处理
                                    amount_str = col_value
                                    # 移除¥符号和逗号
                                    amount_str = re.sub(r'[¥,￥,\s,，]', '', amount_str)
                                    # 提取数字
                                    matches = re.search(r'([-+]?\d+\.?\d*)', amount_str)
                                    if matches:
                                        extracted_amount = float(matches.group(1))
                                        if extracted_amount > 0:
                                            amount = extracted_amount
                                            print(f"从列 '{col_name}' 中提取到金额: {amount} (来自值: {col_value})")
                                            break
                                except Exception as e:
                                    print(f"从列 '{col_name}' 解析金额出错: {str(e)}, 原始值: {col_value}")
                                    continue
                            
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
                    if 'counterparty' in row and not pd.isna(row['counterparty']):
                        payee = str(row['counterparty']).strip()
                    elif '交易对方' in row and not pd.isna(row['交易对方']):
                        payee = str(row['交易对方']).strip()
                    
                    # 商品/交易说明
                    narration = "Unknown"
                    if 'commodity' in row and not pd.isna(row['commodity']):
                        narration = str(row['commodity']).strip()
                    elif '商品' in row and not pd.isna(row['商品']):
                        narration = str(row['商品']).strip()
                    # 如果商品为空，使用交易类型
                    if narration == "Unknown" or not narration:
                        if 'transaction_category' in row and not pd.isna(row['transaction_category']):
                            narration = str(row['transaction_category']).strip()
                        elif '交易类型' in row and not pd.isna(row['交易类型']):
                            narration = str(row['交易类型']).strip()
                    
                    # 支付方式
                    payment_method = "零钱"  # 默认为微信零钱
                    if 'payment_method' in row and not pd.isna(row['payment_method']):
                        payment_method = str(row['payment_method']).strip()
                    elif '支付方式' in row and not pd.isna(row['支付方式']):
                        payment_method = str(row['支付方式']).strip()
                    
                    # 交易状态
                    status = "交易成功"
                    if 'status' in row and not pd.isna(row['status']):
                        status = str(row['status']).strip()
                    elif '当前状态' in row and not pd.isna(row['当前状态']):
                        status = str(row['当前状态']).strip()
                    
                    # 交易编号
                    transaction_id = ""
                    if 'transaction_id' in row and not pd.isna(row['transaction_id']):
                        transaction_id = str(row['transaction_id']).strip()
                    elif '交易单号' in row and not pd.isna(row['交易单号']):
                        transaction_id = str(row['交易单号']).strip()
                    
                    transaction_type = 'expense'  # 默认为支出
                    if '收/支' in row and not pd.isna(row['收/支']):
                        type_value = str(row['收/支']).strip()
                        print(f"原始交易类型标记: '{type_value}'")
                        if type_value == '收入':
                            transaction_type = 'income'
                            print("✓ 确认为收入交易")
                        elif type_value == '/':
                            transaction_type = 'transfer'
                            print("✓ 确认为转账交易")
                        else:
                            print("✓ 确认为支出交易")

                    # 处理特殊交易类型 - 增加调试输出
                    if 'transaction_category' in row and not pd.isna(row['transaction_category']):
                        category = str(row['transaction_category']).strip()
                        print(f"交易分类: {category}")
                        
                        # 特殊类型检测 - 收入交易
                        if '微信红包' in category or '收红包' in category:
                            print(f"✓ 检测到红包收入: {category}")
                            transaction_type = 'income'
                        # 特殊类型检测 - 转账
                        elif '信用卡还款' in category:
                            print(f"✓ 检测到信用卡还款: {category}")
                            transaction_type = 'transfer'
                        elif '零钱提现' in category:
                            print(f"✓ 检测到零钱提现: {category}")
                            transaction_type = 'transfer'
                        elif '零钱充值' in category:
                            print(f"✓ 检测到零钱充值: {category}")
                            transaction_type = 'transfer'
                        elif '理财通' in category:
                            print(f"✓ 检测到理财通交易: {category}")
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
                        'status': f"WeChat - {status}",
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
                        from_account, to_account = self.get_transfer_accounts(row, category, payment_method, asset_account)
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
            raise ValueError(f"转换微信账单时出错: {str(e)}")
    
    def get_expense_account(self, row, payee="", narration=""):
        """获取支出账户（支持自定义映射，按照优先级顺序）"""
        expense_account = "Expenses:Uncategorized"
        
        # 详细记录行数据，帮助调试
        print("\n===== 处理微信交易记录 =====")
        
        # 收集交易信息
        counterparty = payee
        if not counterparty and '交易对方' in row and not pd.isna(row['交易对方']):
            counterparty = str(row['交易对方']).strip()
        print(f"交易对方: {counterparty}")
            
        description = narration
        if not description:
            # 检查所有可能包含商品说明的字段
            if '商品' in row and not pd.isna(row['商品']):
                description = str(row['商品']).strip()
            elif 'commodity' in row and not pd.isna(row['commodity']):
                description = str(row['commodity']).strip()
        print(f"商品说明: {description}")
            
        category = ""
        if '交易类型' in row and not pd.isna(row['交易类型']):
            category = str(row['交易类型']).strip()
        elif 'transaction_category' in row and not pd.isna(row['transaction_category']):
            category = str(row['transaction_category']).strip()
        print(f"交易类型: {category}")
            
        remarks = ""
        if '备注' in row and not pd.isna(row['备注']):
            remarks = str(row['备注']).strip()
        elif 'remarks' in row and not pd.isna(row['remarks']):
            remarks = str(row['remarks']).strip()
            print(f"备注: {remarks}")
        
        # 检查自定义映射
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
            
            # 4. 最后检查交易类型
            if category:
                print(f"检查交易类型: {category}")
                for key, account in self.mapping.custom_expense_categories.items():
                    if key in category:
                        print(f"✓ 交易类型匹配: '{key}' 在 '{category}' 中")
                        return account
                print("✗ 交易类型无匹配")
            
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
        
        # 从商品说明中提取标签
        if description and "#" in description:
            tag = description.split("#")[1].strip()
            if tag:
                print(f"从商品说明中提取标签: {tag}")
                # 可以基于标签设置账户
        
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
            if '商品' in row and not pd.isna(row['商品']):
                description = str(row['商品']).strip()
            elif 'commodity' in row and not pd.isna(row['commodity']):
                description = str(row['commodity']).strip()
            
        category = ""
        if '交易类型' in row and not pd.isna(row['交易类型']):
            category = str(row['交易类型']).strip()
        elif 'transaction_category' in row and not pd.isna(row['transaction_category']):
            category = str(row['transaction_category']).strip()
            
        remarks = ""
        if '备注' in row and not pd.isna(row['备注']):
            remarks = str(row['备注']).strip()
        elif 'remarks' in row and not pd.isna(row['remarks']):
            remarks = str(row['remarks']).strip()
        
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
        asset_account = "Assets:WeChat:Balance"  # 默认账户
        
        # 获取支付方式
        if not payment_method and '支付方式' in row and not pd.isna(row['支付方式']):
            payment_method = str(row['支付方式']).strip()
        
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
                    
        # 处理银行卡
        if '储蓄卡' in payment_method:
            # 提取银行名称和卡号
            bank_match = re.search(r'([\u4e00-\u9fa5]+)银行', payment_method)
            card_match = re.search(r'\((\d+)\)', payment_method)
            
            if bank_match and card_match:
                bank = bank_match.group(1)
                card = card_match.group(1)
                asset_account = f"Assets:Bank:{bank}:{card}"
            elif card_match:
                card = card_match.group(1)
                asset_account = f"Assets:Bank:{card}"
        elif '信用卡' in payment_method:
            # 提取银行名称和卡号
            bank_match = re.search(r'([\u4e00-\u9fa5]+)银行', payment_method)
            card_match = re.search(r'\((\d+)\)', payment_method)
            
            if bank_match and card_match:
                bank = bank_match.group(1)
                card = card_match.group(1)
                asset_account = f"Liabilities:CreditCard:{bank}:{card}"
            elif card_match:
                card = card_match.group(1)
                asset_account = f"Liabilities:CreditCard:{card}"
        
        return asset_account
    
    def get_transfer_accounts(self, row, category, payment_method, asset_account):
        """处理特殊的转账交易类型，返回(from_account, to_account)"""
        from_account = asset_account
        to_account = "Assets:Unknown"
        
        # 根据交易类型处理特殊情况
        if '信用卡还款' in category:
            # 信用卡还款，从支付方式到交易对方（信用卡）
            from_account = asset_account
            
            counterparty = ""
            if '交易对方' in row and not pd.isna(row['交易对方']):
                counterparty = str(row['交易对方']).strip()
            elif 'counterparty' in row and not pd.isna(row['counterparty']):
                counterparty = str(row['counterparty']).strip()
                
            if counterparty:
                # 尝试提取银行名称
                bank_match = re.search(r'([\u4e00-\u9fa5]+)银行', counterparty)
                if bank_match:
                    bank = bank_match.group(1)
                    to_account = f"Liabilities:CreditCard:{bank}"
                else:
                    to_account = "Liabilities:CreditCard"
                    
        elif '零钱提现' in category:
            # 零钱提现，从零钱到银行卡
            from_account = "Assets:WeChat:Balance"
            
            # 尝试从交易对方或交易分类中获取银行信息
            bank_info = ""
            if '交易对方' in row and not pd.isna(row['交易对方']):
                bank_info = str(row['交易对方']).strip()
            
            if not bank_info and 'transaction_category' in row and not pd.isna(row['transaction_category']):
                bank_info = str(row['transaction_category']).strip()
                
            # 提取银行名称和卡号
            bank_match = re.search(r'([\u4e00-\u9fa5]+)银行', bank_info)
            card_match = re.search(r'\((\d+)\)', bank_info)
            
            if bank_match and card_match:
                bank = bank_match.group(1)
                card = card_match.group(1)
                to_account = f"Assets:Bank:{bank}:{card}"
            elif card_match:
                card = card_match.group(1)
                to_account = f"Assets:Bank:{card}"
            else:
                to_account = "Assets:Bank"
                
        elif '零钱充值' in category:
            # 零钱充值，从银行卡到零钱
            from_account = asset_account
            to_account = "Assets:WeChat:Balance"
            
        elif '理财通' in category:
            if '购买' in category:
                # 购买理财通，从支付方式到理财通
                from_account = asset_account
                to_account = "Assets:WeChat:Fund"
            elif '赎回' in category:
                # 赎回理财通，从理财通到零钱
                from_account = "Assets:WeChat:Fund"
                to_account = "Assets:WeChat:Balance"
                
        elif '零钱通' in category:
            if '转出' in category:
                # 从零钱通转出，到其他账户
                from_account = "Assets:WeChat:LQT"
                to_account = asset_account
            else:
                # 转入零钱通
                from_account = asset_account
                to_account = "Assets:WeChat:LQT"
        
        return from_account, to_account