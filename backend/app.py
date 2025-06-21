# backend/app.py

import os
from flask import Flask, request, jsonify
from flask_cors import CORS
import werkzeug.utils
import gc

# Import logic xử lý mới
from data_processor import process_uploaded_file

# --- KHỞI TẠO ỨNG DỤNG FLASK ---
app = Flask(__name__)
# Tăng giới hạn kích thước file upload lên 50MB
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024 
CORS(app)

UPLOAD_FOLDER = 'uploads'
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER


# --- API ENDPOINTS ---

@app.route('/api/upload', methods=['POST'])
def upload_file():
    """Xử lý việc tải file Excel lên và trả về danh sách các sheet."""
    if 'file' not in request.files:
        return jsonify({"success": False, "error": "No file part in the request"}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({"success": False, "error": "No file selected"}), 400
    
    if file and (file.filename.endswith('.xlsx') or file.filename.endswith('.xls')):
        try:
            filename = werkzeug.utils.secure_filename(file.filename)
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath)

            # Sử dụng pandas để lấy danh sách sheet mà không cần logic riêng
            import pandas as pd
            xls = pd.ExcelFile(filepath)
            sheets = xls.sheet_names
            
            return jsonify({
                "success": True,
                "filepath": filepath,
                "sheets": sheets
            })
        except Exception as e:
            return jsonify({"success": False, "error": f"Lỗi khi xử lý file Excel: {str(e)}"}), 500
    
    return jsonify({"success": False, "error": "Định dạng file không hợp lệ. Vui lòng chỉ tải lên file .xlsx hoặc .xls."}), 400


@app.route('/api/process', methods=['POST'])
def process_data():
    """Nhận đường dẫn file và tên sheet, sau đó gọi logic xử lý mới."""
    try:
        data = request.get_json()
        filepath = data.get('filepath')
        sheet_name = data.get('sheetName')

        if not all([filepath, sheet_name]):
            return jsonify({"success": False, "error": "Thiếu đường dẫn file hoặc tên sheet."}), 400
        
        # Gọi hàm xử lý chính từ data_processor.py
        result = process_uploaded_file(filepath, sheet_name)
        
        # Dọn dẹp bộ nhớ
        gc.collect()
        
        if "error" in result:
            return jsonify({"success": False, "error": result["error"]}), 400

        return jsonify({"success": True, **result})

    except Exception as e:
        # Ghi log lỗi ra console của server để dễ debug
        import sys
        print(f"Error in /api/process: {e}", file=sys.stderr)
        return jsonify({"success": False, "error": f"Đã xảy ra lỗi không mong muốn khi xử lý dữ liệu: {str(e)}"}), 500


# --- CHẠY ỨNG DỤNG ---
if __name__ == '__main__':
    # Sử dụng waitress cho production-ready server
    from waitress import serve
    print("Starting server with Waitress on http://0.0.0.0:5001")
    serve(app, host='0.0.0.0', port=5001)