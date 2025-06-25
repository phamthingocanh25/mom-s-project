# backend/app.py
import os
from flask import Flask, request, jsonify
from flask_cors import CORS
import werkzeug.utils
import gc

# --- IMPORT CÁC MODULE XỬ LÝ ---
# THAY ĐỔI 1: Import thêm hàm preprocess_oversized_pallets
from data_processor import (
    load_and_prepare_pallets,
    preprocess_oversized_pallets, 
    separate_pallets_by_company,
    preprocess_and_classify_pallets,
    layered_priority_packing,
    defragment_and_consolidate,
    phase_3_cross_shipping_and_finalization,
    generate_response_data 
)

# --- KHỞI TẠO ỨNG DỤNG FLASK ---
app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024
CORS(app)

UPLOAD_FOLDER = 'uploads'
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# --- API ENDPOINTS ---

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
    Endpoint chính điều phối toàn bộ quy trình tối ưu hóa bằng cách gọi
    các hàm từ module `data_processor`.
    """
    try:
        data = request.get_json()
        filepath = data.get('filepath')
        sheet_name = data.get('sheetName')
        company1_name = data.get('company1Name', '1.0').strip()
        company2_name = data.get('company2Name', '2.0').strip()

        if not all([filepath, sheet_name]):
            return jsonify({"success": False, "error": "Thiếu thông tin file hoặc sheet."}), 400

        # BƯỚC 1: Tải và chuẩn bị dữ liệu pallet
        all_pallets, error = load_and_prepare_pallets(filepath, sheet_name)
        if error:
            return jsonify({"success": False, "error": error}), 400
        if not all_pallets:
             return jsonify({"success": False, "error": "Không có dữ liệu pallet hợp lệ để xử lý."}), 400
        
        # Khởi tạo bộ đếm ID cho container (dùng chung cho toàn bộ quá trình)
        container_id_counter = {'count': 1}

        # THAY ĐỔI 2: Thêm bước tiền xử lý pallet quá khổ
        pre_packed_containers, pallets_to_process = preprocess_oversized_pallets(
            all_pallets, container_id_counter
        )

        # BƯỚC 2: THỰC HIỆN CHUỖI THUẬT TOÁN TỐI ƯU HÓA
        # 2.1: Phân tách pallet theo từng công ty
        # THAY ĐỔI 3: Sử dụng 'pallets_to_process' thay vì 'all_pallets'
        pallets_c1, pallets_c2 = separate_pallets_by_company(
            pallets_to_process, company1_name, company2_name
        )

        # 2.2: Xử lý cho công ty 1 (Giai đoạn 0, 1, 2)
        int_p1, comb_p1, float_p1 = preprocess_and_classify_pallets(pallets_c1)
        packed_containers_c1 = layered_priority_packing(int_p1, comb_p1, float_p1, company1_name, container_id_counter)
        final_containers_c1, cross_ship_pallets_c1 = defragment_and_consolidate(packed_containers_c1)

        # 2.3: Xử lý cho công ty 2 (Giai đoạn 0, 1, 2)
        int_p2, comb_p2, float_p2 = preprocess_and_classify_pallets(pallets_c2)
        packed_containers_c2 = layered_priority_packing(int_p2, comb_p2, float_p2, company2_name, container_id_counter)
        final_containers_c2, cross_ship_pallets_c2 = defragment_and_consolidate(packed_containers_c2)

        # 2.4: Giai đoạn 3 - Vận chuyển chéo và hoàn thiện
        final_optimized_containers = phase_3_cross_shipping_and_finalization(
            final_containers_c1, cross_ship_pallets_c1,
            final_containers_c2, cross_ship_pallets_c2,
            container_id_counter
        )

        # THAY ĐỔI 4: Gộp các container đã đóng gói sẵn vào kết quả cuối cùng
        all_final_containers = pre_packed_containers + final_optimized_containers
        
        # BƯỚC 3: Định dạng kết quả và trả về cho frontend
        # Sử dụng hàm generate_response_data đã có sẵn
        formatted_results = generate_response_data(all_final_containers)

        gc.collect() # Dọn dẹp bộ nhớ

        return jsonify(formatted_results) # Trả về trực tiếp đối tượng JSON

    except Exception as e:
        import traceback
        traceback.print_exc() # In lỗi chi tiết ra console của server
        return jsonify({"success": False, "error": f"Đã xảy ra lỗi hệ thống không mong muốn: {str(e)}"}), 500

# --- CHẠY ỨNG DỤNG ---
if __name__ == '__main__':
    from waitress import serve
    print("Starting server with Waitress on http://0.0.0.0:5001")
    serve(app, host='0.0.0.0', port=5001)