import pandas as pd
from .mapping import BillMapping
import re
import json
import os

class AlipayMapping(BillMapping):
    """支付宝账单专用映射类"""
    
    def __init__(self):
        super().__init__()
        # 支付宝特定的忽略状态
        self.ignore_statuses = ["退款成功", "交易关闭", "还款失败", "解冻成功", "已关闭", "等待付款"]
        
        # 中文列名到标准列名的映射
        self.zh_to_std = {
            '交易时间': 'transaction_time',
            '交易分类': 'category',
            '交易对方': 'counterparty',
            '对方账号': 'counterparty_account',
            '商品说明': 'description',
            '商品名称': 'description',  # 增加"商品名称"也映射到description
            '收/支': 'type',
            '金额': 'amount',
            '收/付款方式': 'payment_method',
            '交易状态': 'status',
            '交易订单号': 'order_id',
            '商家订单号': 'merchant_order_id',
            '交易单号': 'transaction_id',
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
            "余额宝": "Assets:Alipay:Yuebao",
            "余额": "Assets:Alipay:Balance",
            "储蓄卡": "Assets:Bank"
        }
        
        # 负债账户映射
        self.liability_accounts = {
            "花呗": "Liabilities:Alipay:Huabei",
            "信用卡": "Liabilities:CreditCard"
        }
        
        # 自定义映射（初始为空）
        self.custom_expense_categories = {}
        self.custom_income_categories = {}
        self.custom_asset_accounts = {}
        self.custom_liability_accounts = {}
        
        # 尝试加载自定义映射
        self.load_custom_mappings()

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

    def identify_columns(self, df):
        """识别支付宝账单的列"""
        column_map = {}
        
        # 输出前几行数据用于调试
        print("数据样例:")
        print(df.head(2).to_string())
        
        # 直接匹配列名
        for col in df.columns:
            std_col = self.zh_to_std.get(col)
            if std_col:
                column_map[col] = std_col
        
        # 对于未匹配的标准列，进行内容分析
        sample_data = df.head(5)
        for col in df.columns:
            col_values = sample_data[col].astype(str).str.strip().tolist()
            print(f"列 '{col}' 的值: {col_values}")
            
            # 跳过已匹配的列
            if col in column_map:
                continue
                
            values = sample_data[col].astype(str).str.strip().tolist()
            
            # 检查是否为交易时间列
            if any(re.match(r'\d{4}[-/]\d{1,2}[-/]\d{1,2}', val) for val in values):
                if 'transaction_time' not in column_map.values():
                    column_map[col] = 'transaction_time'
            
            # 检查是否为收/支类型列
            elif any(val in ['收入', '支出', '不计收支'] for val in values):
                if 'type' not in column_map.values():
                    column_map[col] = 'type'
                
            # 检查是否为金额列
            elif all(self._is_possible_amount(val) for val in values if val and val != 'nan'):
                if 'amount' not in column_map.values():
                    column_map[col] = 'amount'
                    
            # 检查是否为支付方式列
            elif any(('卡' in val or '余额' in val or '花呗' in val) for val in values if val and val != 'nan'):
                if 'payment_method' not in column_map.values():
                    column_map[col] = 'payment_method'
                    
            # 检查是否为交易状态列
            elif any(('成功' in val or '失败' in val or '关闭' in val) for val in values if val and val != 'nan'):
                if 'status' not in column_map.values():
                    column_map[col] = 'status'
                    
            # 检查是否为交易对方
            elif not any(val.isdigit() for val in values) and not all(val == 'nan' or val == '/' for val in values):
                if 'counterparty' not in column_map.values():
                    column_map[col] = 'counterparty'
                    
            # 检查是否为交易单号
            elif any(len(val) > 15 and val.isdigit() for val in values):
                if 'transaction_id' not in column_map.values():
                    column_map[col] = 'transaction_id'
        
        # 如果关键列仍未找到，尝试基于位置推断
        essential_cols = ['transaction_time', 'counterparty', 'description', 'type', 'amount']
        for col in essential_cols:
            if col not in column_map.values():
                # 根据列位置猜测
                if col == 'transaction_time' and len(df.columns) > 0:
                    column_map[df.columns[0]] = 'transaction_time'
                elif col == 'counterparty' and len(df.columns) > 2:
                    column_map[df.columns[2]] = 'counterparty'
                elif col == 'description' and len(df.columns) > 4:
                    column_map[df.columns[4]] = 'description'
                elif col == 'type' and len(df.columns) > 5:
                    column_map[df.columns[5]] = 'type'
                elif col == 'amount' and len(df.columns) > 6:
                    column_map[df.columns[6]] = 'amount'
        
        # 反转映射关系，以标准列名为键
        std_to_col = {}
        for col, std in column_map.items():
            std_to_col[std] = col
            
        print("最终列映射:", std_to_col)
        return std_to_col
    
    def _is_possible_amount(self, value):
        """判断值是否可能为金额"""
        if not value or value == 'nan':
            return False
            
        # 尝试提取数字部分
        clean_value = re.sub(r'[^0-9.-]', '', str(value))
        try:
            float(clean_value)
            return True
        except:
            return False
    
    def clean_data(self, df):
        """清洗支付宝账单数据"""
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
        import pandas as pd  # 确保在方法内部导入pandas
        
        if 'type' in row and row['type'] is not None:
            type_value = str(row['type']).strip()
            
            if '收入' in type_value:
                return 'income'
            elif '支出' in type_value:
                return 'expense'
            elif '不计收支' in type_value:
                return 'transfer'
                
        # 通过其他线索判断类型
        if 'category' in row and row['category'] is not None:
            category = str(row['category']).strip()
            
            if '退款' in category:
                return 'income'
            elif '转账' in category:
                return 'transfer'
                
        # 通过金额判断
        if 'actual_amount' in row and row['actual_amount'] is not None:
            amount = float(row['actual_amount'])
            if amount > 0:
                return 'expense'
            elif amount < 0:
                return 'income'
                
        return 'unknown'
    
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
                
        return "Assets:Alipay:Balance"