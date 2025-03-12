import os
import json
from flask import Flask, render_template, request, redirect, url_for, send_file, flash, jsonify
from werkzeug.utils import secure_filename
import tempfile

from converter.alipay import AlipayConverter
from converter.alipay_mapping import AlipayMapping
from converter.wechat import WeChatConverter
from converter.wechat_mapping import WeChatMapping

app = Flask(__name__)
app.secret_key = 'bill2beancount_secret_key'
app.config['UPLOAD_FOLDER'] = tempfile.gettempdir()
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

ALLOWED_EXTENSIONS = {'csv'}

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def detect_bill_type(filepath):
    """检测账单类型"""
    try:
        # 尝试检测编码
        encodings = ['utf-8', 'gbk', 'cp1252', 'gb18030', 'latin1']
        
        for encoding in encodings:
            try:
                with open(filepath, 'r', encoding=encoding) as f:
                    content = f.read(4096)  # 读取更多内容
                    
                    # 检查是否为微信账单 (先检查微信，因为它有更明确的标识)
                    if "微信支付账单明细" in content or "微信支付" in content:
                        print("检测到微信支付账单")
                        return "wechat", encoding
                        
                    # 检查是否为支付宝账单
                    elif "支付宝交易记录明细查询" in content or "支付宝" in content and "账单" in content:
                        print("检测到支付宝账单")
                        return "alipay", encoding
                    
                    # 检查通过文件内容特征进行检测
                    if "交易时间,交易类型,交易对方,商品,收/支" in content:
                        # 这是微信账单的典型列结构
                        print("通过列结构检测到微信账单")
                        return "wechat", encoding
                    elif "交易号,商家订单号,交易创建时间,付款时间" in content:
                        # 这是支付宝账单的典型列结构
                        print("通过列结构检测到支付宝账单")
                        return "alipay", encoding
            except UnicodeDecodeError:
                continue
                
        # 尝试读取CSV文件的列结构
        for encoding in encodings:
            try:
                with open(filepath, 'r', encoding=encoding) as f:
                    # 跳过前20行，因为账单文件通常有头部说明
                    for _ in range(20):
                        line = f.readline()
                        if not line:
                            break
                        # 检查列结构
                        if "交易时间,交易类型,交易对方,商品,收/支" in line:
                            print("在表头中检测到微信账单")
                            return "wechat", encoding
                        elif "交易号,商家订单号,交易创建时间,付款时间" in line:
                            print("在表头中检测到支付宝账单")
                            return "alipay", encoding
            except:
                continue
                
        # 如果无法检测，默认为支付宝账单
        print("无法确定账单类型，默认为支付宝账单")
        return "alipay", 'utf-8'
    except Exception as e:
        print(f"账单类型检测出错: {str(e)}")
        return "alipay", 'utf-8'  # 出错时默认为支付宝账单

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        # 检查是否有文件
        if 'file' not in request.files:
            flash('没有选择文件')
            return redirect(request.url)
        
        file = request.files['file']
        
        # 如果用户没有选择文件
        if file.filename == '':
            flash('没有选择文件')
            return redirect(request.url)
        
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath)
            
            try:
                # 检测账单类型
                bill_type, encoding = detect_bill_type(filepath)
                
                # 根据账单类型选择转换器
                if bill_type == "wechat":
                    converter = WeChatConverter()
                    bill_name = "微信账单"
                else:
                    converter = AlipayConverter()
                    bill_name = "支付宝账单"
                
                # 处理账单文件
                beancount_entries = converter.convert(filepath)
                
                if not beancount_entries.strip():
                    flash(f'转换结果为空，请检查{bill_name}格式')
                    return redirect(request.url)
                
                # 创建临时结果文件
                result_file = os.path.join(app.config['UPLOAD_FOLDER'], f'{bill_type}_beancount.bean')
                with open(result_file, 'w', encoding='utf-8') as f:
                    f.write(beancount_entries)
                
                # 下载结果或显示结果
                if request.form.get('action') == 'download':
                    return send_file(result_file, as_attachment=True, download_name=f'{bill_type}_beancount.bean')
                else:
                    entries = beancount_entries.split('\n\n')
                    # 确保最后一个不是空字符串
                    entries = [e for e in entries if e.strip()]
                    return render_template('result.html', entries=entries, bill_type=bill_type)
            
            except Exception as e:
                import traceback
                error_details = traceback.format_exc()
                print(f"处理文件时出错: {str(e)}")
                print(error_details)
                flash(f'处理文件时出错: {str(e)}')
                return redirect(request.url)
            finally:
                # 确保无论如何都删除上传的文件
                try:
                    if os.path.exists(filepath):
                        os.remove(filepath)
                except:
                    pass
    
    return render_template('index.html')

@app.route('/mappings')
def view_mappings():
    """查看映射配置页面"""
    # 加载支付宝映射
    alipay_mapping = AlipayMapping()
    alipay_mappings = alipay_mapping.get_all_mappings()
    
    # 加载微信映射
    wechat_mapping = WeChatMapping()
    wechat_mappings = wechat_mapping.get_all_mappings()
    
    return render_template('mappings.html', 
                          alipay_mappings=alipay_mappings,
                          wechat_mappings=wechat_mappings)

@app.route('/mappings/update/<bill_type>/<mapping_type>', methods=['POST'])
def update_mappings(bill_type, mapping_type):
    """更新自定义映射"""
    if mapping_type not in ['expense', 'income', 'asset', 'liability']:
        flash('无效的映射类型')
        return redirect(url_for('view_mappings'))
    
    # 从请求中获取映射数据
    try:
        mapping_data = request.form.to_dict()
        
        # 转换为合适的格式
        mappings = {}
        for key, value in mapping_data.items():
            if key.startswith('key_') and value.strip():
                # 提取索引
                idx = key.split('_')[1]
                map_key = value.strip()
                map_value = mapping_data.get(f'value_{idx}', '').strip()
                
                if map_key and map_value:
                    mappings[map_key] = map_value
        
        # 根据账单类型选择映射类
        if bill_type == 'wechat':
            mapping = WeChatMapping()
        else:
            mapping = AlipayMapping()
            
        # 保存映射
        success = mapping.update_custom_mappings(mapping_type, mappings)
        
        if success:
            flash(f'映射已更新')
        else:
            flash(f'保存映射失败')
    except Exception as e:
        flash(f'更新映射时出错: {str(e)}')
    
    return redirect(url_for('view_mappings'))

@app.route('/mappings/export/<bill_type>')
def export_mappings(bill_type):
    """导出映射配置为JSON文件"""
    # 根据账单类型选择映射类
    if bill_type == 'wechat':
        mapping = WeChatMapping()
        filename = 'wechat_custom_mappings.json'
    else:
        mapping = AlipayMapping()
        filename = 'alipay_custom_mappings.json'
    
    mappings = {
        'expense_categories': mapping.custom_expense_categories,
        'income_categories': mapping.custom_income_categories,
        'asset_accounts': mapping.custom_asset_accounts,
        'liability_accounts': mapping.custom_liability_accounts
    }
    
    # 创建临时文件
    export_file = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    with open(export_file, 'w', encoding='utf-8') as f:
        json.dump(mappings, f, ensure_ascii=False, indent=2)
        
    return send_file(export_file, as_attachment=True, download_name=filename)

@app.route('/mappings/import/<bill_type>', methods=['POST'])
def import_mappings(bill_type):
    """导入映射配置"""
    if 'mapping_file' not in request.files:
        flash('没有选择文件')
        return redirect(url_for('view_mappings'))
    
    file = request.files['mapping_file']
    
    if file.filename == '':
        flash('没有选择文件')
        return redirect(url_for('view_mappings'))
    
    if file and file.filename.endswith('.json'):
        try:
            # 读取JSON文件
            file_content = file.read()
            mappings = json.loads(file_content)
            
            # 验证JSON结构
            required_keys = ['expense_categories', 'income_categories', 'asset_accounts', 'liability_accounts']
            if not all(key in mappings for key in required_keys):
                flash('导入的映射文件格式不正确')
                return redirect(url_for('view_mappings'))
            
            # 保存为临时文件
            import_file = os.path.join(app.config['UPLOAD_FOLDER'], f'{bill_type}_imported_mappings.json')
            with open(import_file, 'w', encoding='utf-8') as f:
                json.dump(mappings, f, ensure_ascii=False, indent=2)
            
            # 根据账单类型选择映射类
            if bill_type == 'wechat':
                mapping = WeChatMapping()
            else:
                mapping = AlipayMapping()
                
            # 使用映射类加载文件
            success = mapping.load_custom_mappings(import_file)
            
            if success:
                # 保存到默认位置
                mapping.save_custom_mappings()
                flash('映射导入成功')
            else:
                flash('导入映射失败')
                
        except Exception as e:
            flash(f'导入映射时出错: {str(e)}')
    else:
        flash('请选择有效的JSON文件')
        
    return redirect(url_for('view_mappings'))

if __name__ == '__main__':
    app.run(debug=True)