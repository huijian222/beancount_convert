import os
from flask import Flask, render_template, request, redirect, url_for, send_file, flash
from werkzeug.utils import secure_filename
import tempfile

from converter.alipay import AlipayConverter

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

if __name__ == '__main__':
    app.run(debug=True)