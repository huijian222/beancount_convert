import pandas as pd
import re
from datetime import datetime

class BillMapping:
    """
    通用账单映射类
    负责识别不同账单格式并标准化处理数据
    """
    
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