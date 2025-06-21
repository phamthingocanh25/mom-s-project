# backend/app.py
import os
from flask import Flask, request, jsonify
from flask_cors import CORS
import werkzeug.utils
import gc

# --- IMPORT CÁC MODULE XỬ LÝ ---
# Thay đổi 1: Import các hàm cần thiết từ các module đã tách biệt
from data_processor import load_and_prepare_pallets
from optimizer import optimize_container_packing

# --- KHỞI TẠO ỨNG DỤNG FLASK (Giữ nguyên) ---
app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024 
CORS(app)

UPLOAD_FOLDER = 'uploads'
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# --- HÀM TIỆN ÍCH ĐỂ ĐỊNH DẠNG KẾT QUẢ ---
# Thay đổi 2: Tạo một hàm riêng để định dạng JSON trả về
def format_results_for_frontend(containers):
    final_results = []
    for c in sorted(containers, key=lambda c: int(c.id.split('_')[-1])):
        container_contents = []
        for p in c.pallets:
            pallet_data = {
                "is_cross_ship": p.is_cross_ship,
                "company": p.company,
                "quantity": p.quantity,
                "total_weight": p.total_weight
            }
            if p.is_combined:
                pallet_data["type"] = "CombinedPallet"
                pallet_data["items"] = [{
                    "product_code": sub_p.product_code,
                    "product_name": sub_p.product_name,
                    "company": sub_p.company,
                    "quantity": sub_p.quantity,
                    "total_weight": sub_p.total_weight,
                } for sub_p in p.original_pallets]
            else:
                pallet_data["type"] = "SinglePallet"
                pallet_data["is_split"] = p.is_split
                pallet_data["product_code"] = p.product_code
                pallet_data["product_name"] = p.product_name
            container_contents.append(pallet_data)

        final_results.append({
            'id': c.id,
            'main_company': c.main_company,
            'total_quantity': c.total_quantity,
            'total_weight': c.total_weight,
            'contents': sorted(container_contents, key=lambda x: (x['type'], x.get('product_name', '')))
        })
    return final_results

# --- API ENDPOINTS (Chỉnh sửa endpoint /api/process) ---

@app.route('/api/upload', methods=['POST'])
def upload_file(): # Giữ nguyên endpoint này
    if 'file' not in request.files:
        return jsonify({"success": False, "error": "No file part"}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({"success": False, "error": "No selected file"}), 400
    if file and (file.filename.endswith('.xlsx') or file.filename.endswith('.xls')):
        try:
            filename = werkzeug.utils.secure_filename(file.filename)
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath)
            import pandas as pd
            xls = pd.ExcelFile(filepath)
            return jsonify({"success": True, "filepath": filepath, "sheets": xls.sheet_names})
        except Exception as e:
            return jsonify({"success": False, "error": f"Lỗi khi xử lý file: {str(e)}"}), 500
    return jsonify({"success": False, "error": "Định dạng file không hợp lệ"}), 400


@app.route('/api/process', methods=['POST'])
def process_data():
    """
    Endpoint chính để điều phối quy trình tối ưu hóa.
    """
    try:
        data = request.get_json()
        filepath = data.get('filepath')
        sheet_name = data.get('sheetName')

        if not all([filepath, sheet_name]):
            return jsonify({"success": False, "error": "Thiếu thông tin file hoặc sheet."}), 400
        
        # BƯỚC 1: Tải và chuẩn bị dữ liệu
        pallets, error = load_and_prepare_pallets(filepath, sheet_name)
        if error:
            return jsonify({"success": False, "error": error}), 400
        if not pallets:
             return jsonify({"success": False, "error": "Không có dữ liệu pallet hợp lệ để xử lý."}), 400

        # BƯỚC 2: Gọi module tối ưu hóa
        optimized_containers = optimize_container_packing(pallets)

        # BƯỚC 3: Định dạng kết quả và trả về cho frontend
        formatted_results = format_results_for_frontend(optimized_containers)
        
        gc.collect() # Dọn dẹp bộ nhớ
        
        return jsonify({"success": True, "results": formatted_results})

    except Exception as e:
        import traceback
        traceback.print_exc() # In lỗi chi tiết ra console server
        return jsonify({"success": False, "error": f"Đã xảy ra lỗi hệ thống: {str(e)}"}), 500

# --- CHẠY ỨNG DỤNG (Giữ nguyên) ---
if __name__ == '__main__':
    from waitress import serve
    print("Starting server with Waitress on http://0.0.0.0:5001")
    serve(app, host='0.0.0.0', port=5001)