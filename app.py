import os
import json
from flask import Flask, render_template, request, redirect, url_for, send_file, flash, jsonify
from werkzeug.utils import secure_filename
import tempfile

from converter.alipay import AlipayConverter
from converter.alipay_mapping import AlipayMapping

app = Flask(__name__)
app.secret_key = 'alipay2beancount_secret_key'
app.config['UPLOAD_FOLDER'] = tempfile.gettempdir()
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

ALLOWED_EXTENSIONS = {'csv'}

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

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
                # 处理账单文件
                converter = AlipayConverter()
                beancount_entries = converter.convert(filepath)
                
                if not beancount_entries.strip():
                    flash('转换结果为空，请检查账单格式')
                    return redirect(request.url)
                
                # 创建临时结果文件
                result_file = os.path.join(app.config['UPLOAD_FOLDER'], 'alipay_beancount.bean')
                with open(result_file, 'w', encoding='utf-8') as f:
                    f.write(beancount_entries)
                
                # 下载结果或显示结果
                if request.form.get('action') == 'download':
                    return send_file(result_file, as_attachment=True, download_name='alipay_beancount.bean')
                else:
                    entries = beancount_entries.split('\n\n')
                    # 确保最后一个不是空字符串
                    entries = [e for e in entries if e.strip()]
                    return render_template('result.html', entries=entries)
            
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
    mapping = AlipayMapping()
    all_mappings = mapping.get_all_mappings()
    return render_template('mappings.html', mappings=all_mappings)

@app.route('/mappings/update/<mapping_type>', methods=['POST'])
def update_mappings(mapping_type):
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
        
        # 保存映射
        mapping = AlipayMapping()
        success = mapping.update_custom_mappings(mapping_type, mappings)
        
        if success:
            flash(f'映射已更新')
        else:
            flash(f'保存映射失败')
    except Exception as e:
        flash(f'更新映射时出错: {str(e)}')
    
    return redirect(url_for('view_mappings'))

@app.route('/mappings/export')
def export_mappings():
    """导出映射配置为JSON文件"""
    mapping = AlipayMapping()
    mappings = {
        'expense_categories': mapping.custom_expense_categories,
        'income_categories': mapping.custom_income_categories,
        'asset_accounts': mapping.custom_asset_accounts,
        'liability_accounts': mapping.custom_liability_accounts
    }
    
    # 创建临时文件
    export_file = os.path.join(app.config['UPLOAD_FOLDER'], 'custom_mappings.json')
    with open(export_file, 'w', encoding='utf-8') as f:
        json.dump(mappings, f, ensure_ascii=False, indent=2)
        
    return send_file(export_file, as_attachment=True, download_name='custom_mappings.json')

@app.route('/mappings/import', methods=['POST'])
def import_mappings():
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
            import_file = os.path.join(app.config['UPLOAD_FOLDER'], 'imported_mappings.json')
            with open(import_file, 'w', encoding='utf-8') as f:
                json.dump(mappings, f, ensure_ascii=False, indent=2)
            
            # 使用映射类加载文件
            mapping = AlipayMapping()
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