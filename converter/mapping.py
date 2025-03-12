import pandas as pd
import re
from datetime import datetime
import json
import os

class BillMapping:
    """
    通用账单映射类
    负责识别不同账单格式并标准化处理数据
    """
    
    # 统一映射文件路径 - 类变量，所有子类共享
    MAPPING_FILE_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'shared_mappings.json')
    
    # 统一自定义映射 - 类变量，所有子类共享
    custom_expense_categories = {}
    custom_income_categories = {}
    custom_asset_accounts = {}
    custom_liability_accounts = {}
    
    # 是否已加载映射
    _mappings_loaded = False
    
    def __init__(self):
        # 基本列映射关系
        self.column_map = {}
        # 需要的标准列名
        self.required_columns = [
            'transaction_time',  # 交易时间
            'category',          # 交易分类
            'counterparty',      # 交易对方 
            'description',       # 商品说明
            'type',              # 收/支类型
            'amount',            # 金额
            'payment_method',    # 支付方式
            'status',            # 交易状态
            'transaction_id'     # 交易单号
        ]
        # 忽略的交易状态
        self.ignore_statuses = []
        
        # 加载自定义映射（如果尚未加载）
        if not BillMapping._mappings_loaded:
            self.load_custom_mappings()
        
    def detect_file_encoding(self, filepath):
        """尝试检测文件编码"""
        encodings = ['utf-8', 'gbk', 'cp1252', 'gb18030', 'latin1']
        for encoding in encodings:
            try:
                with open(filepath, 'r', encoding=encoding) as f:
                    f.read(1024)  # 尝试读取一部分内容
                    return encoding
            except UnicodeDecodeError:
                continue
        return 'utf-8'  # 默认编码
        
    def detect_header_position(self, filepath, encoding):
        """检测CSV文件中表头的位置"""
        header_row = 0
        with open(filepath, 'r', encoding=encoding) as f:
            lines = [line for i, line in enumerate(f) if i < 50]  # 读取前50行
            
        # 查找可能的表头行
        for i, line in enumerate(lines):
            # 不同账单格式有不同的表头特征
            if '交易时间' in line and ('交易分类' in line or '收/支' in line):
                header_row = i
                break
                
        return header_row
    
    def identify_columns(self, df):
        """根据实际内容识别列的含义"""
        # 基础列映射逻辑，需要在子类中扩展
        return {}
    
    def clean_data(self, df):
        """数据清洗和规范化"""
        # 子类应该重写这个方法，提供特定的数据清洗逻辑
        return df
    
    def extract_amount(self, value):
        """提取金额数值"""
        if pd.isna(value):
            return 0.0
            
        if isinstance(value, (int, float)):
            return float(value)
            
        # 转换为字符串并清理
        value_str = str(value).strip()
        
        # 移除货币符号和千位分隔符
        value_str = re.sub(r'[¥,$,￥,\s,]', '', value_str)
        
        # 提取数字部分
        matches = re.search(r'([-+]?\d+\.?\d*)', value_str)
        if matches:
            return float(matches.group(1))
            
        return 0.0
    
    def parse_datetime(self, value):
        """解析日期时间"""
        if pd.isna(value):
            return datetime.now()
            
        if isinstance(value, datetime):
            return value
            
        # 尝试常见格式
        formats = [
            '%Y-%m-%d %H:%M:%S',
            '%Y/%m/%d %H:%M:%S',
            '%Y.%m.%d %H:%M:%S',
            '%Y-%m-%d'
        ]
        
        for fmt in formats:
            try:
                return datetime.strptime(str(value).strip(), fmt)
            except ValueError:
                continue
                
        # 无法解析，返回当前时间
        return datetime.now()
    
    def determine_transaction_type(self, row):
        """确定交易类型（收入/支出/转账）"""
        # 子类应该实现这个方法
        return 'unknown'
    
    def load_file(self, filepath):
        """加载并预处理账单文件"""
        # 检测编码
        encoding = self.detect_file_encoding(filepath)
        
        # 检测表头位置
        header_row = self.detect_header_position(filepath, encoding)
        
        # 读取CSV
        try:
            df = pd.read_csv(filepath, skiprows=header_row, encoding=encoding)
            print(f"原始列名: {df.columns.tolist()}")
            
            # 识别列
            self.column_map = self.identify_columns(df)
            print(f"识别到的列映射: {self.column_map}")
            
            # 重命名列
            if self.column_map:
                df = df.rename(columns=self.column_map)
                
            # 数据清洗
            df = self.clean_data(df)
            
            return df
        except Exception as e:
            raise ValueError(f"无法读取文件: {str(e)}")
    
    @classmethod
    def load_custom_mappings(cls, filepath=None):
        """从JSON文件加载自定义映射 - 类方法，所有实例共享结果"""
        if filepath is None:
            filepath = cls.MAPPING_FILE_PATH
        
        if os.path.exists(filepath):
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    mappings = json.load(f)
                    
                    if 'expense_categories' in mappings:
                        cls.custom_expense_categories = mappings['expense_categories']
                    if 'income_categories' in mappings:
                        cls.custom_income_categories = mappings['income_categories']
                    if 'asset_accounts' in mappings:
                        cls.custom_asset_accounts = mappings['asset_accounts']
                    if 'liability_accounts' in mappings:
                        cls.custom_liability_accounts = mappings['liability_accounts']
                        
                print(f"已加载共享自定义映射: {filepath}")
                cls._mappings_loaded = True
                return True
            except Exception as e:
                print(f"加载自定义映射失败: {str(e)}")
                return False
        return False
    
    @classmethod
    def save_custom_mappings(cls, filepath=None):
        """保存自定义映射到JSON文件 - 类方法，所有实例共享"""
        if filepath is None:
            filepath = cls.MAPPING_FILE_PATH
        
        try:
            mappings = {
                'expense_categories': cls.custom_expense_categories,
                'income_categories': cls.custom_income_categories,
                'asset_accounts': cls.custom_asset_accounts,
                'liability_accounts': cls.custom_liability_accounts
            }
            
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(mappings, f, ensure_ascii=False, indent=2)
                
            print(f"已保存共享自定义映射: {filepath}")
            return True
        except Exception as e:
            print(f"保存自定义映射失败: {str(e)}")
            return False
    
    @classmethod
    def get_all_mappings(cls):
        """获取所有映射（默认和自定义）- 类方法，所有实例共享结果"""
        # 注意：各个子类需要提供自己的默认映射
        return {
            'expense_categories': {
                'default': {},  # 子类需要提供
                'custom': cls.custom_expense_categories
            },
            'income_categories': {
                'default': {},  # 子类需要提供
                'custom': cls.custom_income_categories
            },
            'asset_accounts': {
                'default': {},  # 子类需要提供
                'custom': cls.custom_asset_accounts
            },
            'liability_accounts': {
                'default': {},  # 子类需要提供
                'custom': cls.custom_liability_accounts
            }
        }
    
    @classmethod
    def update_custom_mappings(cls, mapping_type, mappings):
        """更新自定义映射 - 类方法，所有实例共享结果"""
        if mapping_type == 'expense':
            cls.custom_expense_categories = mappings
        elif mapping_type == 'income':
            cls.custom_income_categories = mappings
        elif mapping_type == 'asset':
            cls.custom_asset_accounts = mappings
        elif mapping_type == 'liability':
            cls.custom_liability_accounts = mappings
        return cls.save_custom_mappings()