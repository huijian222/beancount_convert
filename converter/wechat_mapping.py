import pandas as pd
import csv
from .mapping import BillMapping
import re
import json
import os

class WeChatMapping(BillMapping):
    """微信账单专用映射类"""
    
    def __init__(self):
        super().__init__()
        # 微信特定的忽略状态
        self.ignore_statuses = ["已全额退款", "对方已退还", "已退款"]
        
        # 中文列名到标准列名的映射
        self.zh_to_std = {
            '交易时间': 'transaction_time',
            '交易类型': 'transaction_category',
            '交易对方': 'counterparty',
            '商品': 'commodity',
            '收/支': 'type',
            '金额(元)': 'amount',
            '支付方式': 'payment_method',
            '当前状态': 'status',
            '交易单号': 'transaction_id',
            '商户单号': 'merchant_id',
            '备注': 'remarks'
        }
        
        # 支出分类映射
        self.expense_categories = {
            "餐饮": "Expenses:Food",
            "美食": "Expenses:Food",
            "外卖": "Expenses:Food",
            "食品": "Expenses:Food:Groceries",
            "超市": "Expenses:Shopping:Groceries",
            "日用": "Expenses:Shopping:Daily",
            "电子": "Expenses:Shopping:Electronics",
            "服装": "Expenses:Shopping:Clothing",
            "交通": "Expenses:Transport",
            "出行": "Expenses:Transport",
            "医疗": "Expenses:Health",
            "药品": "Expenses:Health:Medicine",
            "娱乐": "Expenses:Entertainment",
            "电影": "Expenses:Entertainment:Movie",
            "游戏": "Expenses:Entertainment:Game",
            "学习": "Expenses:Education",
            "书籍": "Expenses:Education:Book",
            "住房": "Expenses:Housing",
            "水电": "Expenses:Housing:Utilities",
            "红包": "Expenses:Gift",
            "转账": "Expenses:Transfer"
        }
        
        # 收入分类映射
        self.income_categories = {
            "工资": "Income:Salary",
            "奖金": "Income:Bonus",
            "退款": "Income:Refund",
            "利息": "Income:Interest",
            "投资": "Income:Investment",
            "红包": "Income:Gift"
        }
        
        # 资产账户映射
        self.asset_accounts = {
            "零钱": "Assets:WeChat:Balance",
            "零钱通": "Assets:WeChat:LQT",
            "理财通": "Assets:WeChat:Fund",
            "储蓄卡": "Assets:Bank",
        }
        
        # 负债账户映射
        self.liability_accounts = {
            "信用卡": "Liabilities:CreditCard"
        }
        
        # 自定义映射（初始为空）
        self.custom_expense_categories = {}
        self.custom_income_categories = {}
        self.custom_asset_accounts = {}
        self.custom_liability_accounts = {}
        
        # 尝试加载自定义映射
        self.load_custom_mappings()

    def load_file(self, filepath):
        """加载并预处理账单文件"""
        # 检测编码
        encoding = self.detect_file_encoding(filepath)
        
        # 检测表头位置
        header_row = self.detect_header_position(filepath, encoding)
        print(f"微信账单表头位置: {header_row}")
        
        # 微信账单通常有多行说明，跳过前17行左右
        if header_row == 0:
            header_row = 16  # 默认为17行（索引16）
        
        # 读取CSV
        try:
            # 使用Python内置的csv读取器先获取列名
            with open(filepath, 'r', encoding=encoding) as f:
                # 跳过前面的行
                for i in range(header_row):
                    next(f)
                reader = csv.reader(f)
                headers = next(reader)
                print(f"检测到的微信账单列名: {headers}")
            
            # 然后用pandas读取数据
            df = pd.read_csv(filepath, skiprows=header_row, encoding=encoding, dtype=str)
            print(f"原始列名: {df.columns.tolist()}")
            
            # 调试输出
            print("数据前2行:")
            print(df.head(2).to_string())
            
            # 处理特殊情况：如果金额列的名称不是'金额(元)'
            if '金额(元)' not in df.columns and '金额' in df.columns:
                df = df.rename(columns={'金额': '金额(元)'})
            
            # 识别列
            self.column_map = self.identify_columns(df)
            print(f"识别到的列映射: {self.column_map}")
            
            # 重命名列
            if self.column_map:
                df = df.rename(columns=self.column_map)
            
            # 特别处理金额列
            if 'amount' in df.columns:
                # 尝试将金额转换为浮点数
                df['actual_amount'] = df['amount'].apply(self.extract_amount)
                print("前几行金额转换结果:")
                print(df[['amount', 'actual_amount']].head())
            
            # 数据清洗
            df = self.clean_data(df)
            
            return df
        except Exception as e:
            raise ValueError(f"无法读取微信账单文件: {str(e)}")

    def detect_header_position(self, filepath, encoding):
        """检测CSV文件中表头的位置"""
        header_row = 0
        with open(filepath, 'r', encoding=encoding) as f:
            lines = [line for i, line in enumerate(f) if i < 50]  # 读取前50行
            
        # 对于微信支付账单，表头通常在第17行(索引16)
        wechat_header_identifier = "交易时间,交易类型,交易对方,商品,收/支,金额(元),支付方式,当前状态,交易单号,商户单号,备注"
        for i, line in enumerate(lines):
            if wechat_header_identifier in line or "交易时间" in line and "交易类型" in line and "收/支" in line:
                header_row = i
                break
                
        return header_row
    
    def identify_columns(self, df):
        """识别微信账单的列"""
        column_map = {}
        
        # 输出前几行数据用于调试
        print("数据样例:")
        print(df.head(2).to_string())
        
        # 直接匹配列名
        for col in df.columns:
            std_col = self.zh_to_std.get(col)
            if std_col:
                column_map[col] = std_col
        
        # 反转映射关系，以标准列名为键
        std_to_col = {}
        for col, std in column_map.items():
            std_to_col[std] = col
            
        print("最终列映射:", std_to_col)
        return std_to_col
    
    def clean_data(self, df):
        """清洗微信账单数据"""
        # 添加实际金额列
        df['actual_amount'] = df.apply(self._extract_row_amount, axis=1)
        
        # 确保所有需要的列存在
        for col in self.required_columns:
            if col not in df.columns:
                df[col] = None
        
        # 处理收/支类型
        df['transaction_type'] = df.apply(self.determine_transaction_type, axis=1)
        
        # 过滤忽略的交易
        if 'status' in df.columns:
            df = df[~df['status'].isin(self.ignore_statuses)]
            
        return df
    
    def _extract_row_amount(self, row):
        """从行数据中提取金额"""
        # 尝试多个可能的列
        amount_cols = ['amount', 'payment_method', 'counterparty']
        
        for col in amount_cols:
            if col in row and not pd.isna(row[col]):
                try:
                    amount = self.extract_amount(row[col])
                    if amount != 0:
                        return amount
                except:
                    pass
        
        return 0.0
    
    def determine_transaction_type(self, row):
        """确定交易类型"""
        if 'type' in row and row['type'] is not None:
            type_value = str(row['type']).strip()
            
            if type_value == '收入':
                return 'income'
            elif type_value == '支出':
                return 'expense'
            elif type_value == '/':  # 微信的不计收支是'/'
                return 'transfer'
                
        # 通过其他线索判断类型
        if 'transaction_category' in row and row['transaction_category'] is not None:
            category = str(row['transaction_category']).strip()
            
            if '退款' in category:
                return 'income'
            elif '转账' in category or '收款' in category:
                return 'transfer'
                
        # 通过金额判断
        if 'actual_amount' in row and row['actual_amount'] is not None:
            amount = float(row['actual_amount'])
            if amount > 0:
                return 'expense'
            elif amount < 0:
                return 'income'
                
        return 'unknown'
    
    def extract_amount(self, value):
        """提取金额数值，特别处理微信余额格式"""
        if pd.isna(value):
            return 0.0
            
        if isinstance(value, (int, float)):
            return float(value)
            
        # 转换为字符串并清理
        value_str = str(value).strip()
        
        # 移除货币符号(¥)和千位分隔符
        value_str = re.sub(r'[¥,$,￥,\s,]', '', value_str)
        
        # 提取数字部分
        matches = re.search(r'([-+]?\d+\.?\d*)', value_str)
        if matches:
            result = float(matches.group(1))
            print(f"从 '{value}' 提取金额: {result}")
            return result
            
        return 0.0
    
    def load_custom_mappings(self, filepath=None):
        """从JSON文件加载自定义映射"""
        if filepath is None:
            # 默认保存在与应用相同目录下
            filepath = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'custom_mappings.json')
        
        if os.path.exists(filepath):
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    mappings = json.load(f)
                    
                    if 'expense_categories' in mappings:
                        self.custom_expense_categories = mappings['expense_categories']
                    if 'income_categories' in mappings:
                        self.custom_income_categories = mappings['income_categories']
                    if 'asset_accounts' in mappings:
                        self.custom_asset_accounts = mappings['asset_accounts']
                    if 'liability_accounts' in mappings:
                        self.custom_liability_accounts = mappings['liability_accounts']
                        
                print(f"已加载自定义映射: {filepath}")
                return True
            except Exception as e:
                print(f"加载自定义映射失败: {str(e)}")
                return False
        return False
    
    def save_custom_mappings(self, filepath=None):
        """保存自定义映射到JSON文件"""
        if filepath is None:
            # 默认保存在与应用相同目录下
            filepath = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'custom_mappings.json')
        
        try:
            mappings = {
                'expense_categories': self.custom_expense_categories,
                'income_categories': self.custom_income_categories,
                'asset_accounts': self.custom_asset_accounts,
                'liability_accounts': self.custom_liability_accounts
            }
            
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(mappings, f, ensure_ascii=False, indent=2)
                
            print(f"已保存自定义映射: {filepath}")
            return True
        except Exception as e:
            print(f"保存自定义映射失败: {str(e)}")
            return False
    
    def get_all_mappings(self):
        """获取所有映射（默认和自定义）"""
        return {
            'expense_categories': {
                'default': self.expense_categories,
                'custom': self.custom_expense_categories
            },
            'income_categories': {
                'default': self.income_categories,
                'custom': self.custom_income_categories
            },
            'asset_accounts': {
                'default': self.asset_accounts,
                'custom': self.custom_asset_accounts
            },
            'liability_accounts': {
                'default': self.liability_accounts,
                'custom': self.custom_liability_accounts
            }
        }
    
    def update_custom_mappings(self, mapping_type, mappings):
        """更新自定义映射"""
        if mapping_type == 'expense':
            self.custom_expense_categories = mappings
        elif mapping_type == 'income':
            self.custom_income_categories = mappings
        elif mapping_type == 'asset':
            self.custom_asset_accounts = mappings
        elif mapping_type == 'liability':
            self.custom_liability_accounts = mappings
        return self.save_custom_mappings()
    
    def guess_expense_account(self, description, counterparty):
        """根据描述和交易对手猜测支出账户"""
        for keyword, account in self.expense_categories.items():
            if keyword in str(description) or keyword in str(counterparty):
                return account
        return "Expenses:Uncategorized"
    
    def guess_income_account(self, description, counterparty):
        """根据描述和交易对手猜测收入账户"""
        for keyword, account in self.income_categories.items():
            if keyword in str(description) or keyword in str(counterparty):
                return account
        return "Income:Uncategorized"
    
    def guess_asset_account(self, payment_method):
        """根据支付方式猜测资产账户"""
        for keyword, account in self.asset_accounts.items():
            if keyword in str(payment_method):
                return account
                
        # 处理银行卡
        if '储蓄卡' in str(payment_method) or '借记卡' in str(payment_method):
            # 尝试提取卡号后四位
            card_match = re.search(r'[0-9]{4}', str(payment_method))
            if card_match:
                return f"Assets:Bank:Card{card_match.group(0)}"
                
        elif '信用卡' in str(payment_method):
            # 尝试提取卡号后四位
            card_match = re.search(r'[0-9]{4}', str(payment_method))
            if card_match:
                return f"Liabilities:CreditCard:Card{card_match.group(0)}"
                
        return "Assets:WeChat:Balance"  # 默认返回微信零钱