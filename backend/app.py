import os
import sys
import math
import pandas as pd
from flask import Flask, request, jsonify
from flask_cors import CORS
import werkzeug.utils
import gc

# --- KHỞI TẠO ỨNG DỤNG FLASK ---
app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024 
CORS(app)

UPLOAD_FOLDER = 'uploads'
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# --- LOGIC TỐI ƯU HÓA (GIỮ NGUYÊN) ---
MAX_CONTAINER_WEIGHT = 24000
MAX_CONTAINER_BOXES = 20.0
EPSILON = 1e-6

def create_float_combinations(float_pallets):
    if not float_pallets:
        return [], []
    def perform_combination_pass(pallets_to_process):
        pallets_copy = list(pallets_to_process)
        pallets_copy.sort(key=lambda p: p['number_of_boxes'], reverse=True)
        processed_flags = {p['original_index']: False for p in pallets_copy}
        final_groups = []
        for base_pallet in pallets_copy:
            if processed_flags[base_pallet['original_index']]:
                continue
            new_group = [base_pallet]
            processed_flags[base_pallet['original_index']] = True
            current_sum = base_pallet['number_of_boxes']
            limit = math.floor(base_pallet['number_of_boxes']) + 0.9 + EPSILON
            for candidate_pallet in pallets_copy:
                if processed_flags[candidate_pallet['original_index']]:
                    continue
                if current_sum + candidate_pallet['number_of_boxes'] <= limit:
                    new_group.append(candidate_pallet)
                    processed_flags[candidate_pallet['original_index']] = True
                    current_sum += candidate_pallet['number_of_boxes']
            final_groups.append(new_group)
        return final_groups
    initial_groups = perform_combination_pass(float_pallets)
    true_combinations = [group for group in initial_groups if len(group) > 1]
    single_leftovers = [group[0] for group in initial_groups if len(group) == 1]
    if len(single_leftovers) > 1:
        rerun_groups = perform_combination_pass(single_leftovers)
        true_combinations.extend([group for group in rerun_groups if len(group) > 1])
        single_leftovers = [group[0] for group in rerun_groups if len(group) == 1]
    return true_combinations, single_leftovers

def optimize_packing_prioritized(boxes_data):
    integer_pallets, float_pallets = [], []
    for idx, (box_num, weight) in enumerate(boxes_data):
        pallet_info = {"original_index": idx, "number_of_boxes": box_num, "total_item_weight": weight}
        if abs(box_num - round(box_num)) < EPSILON:
            integer_pallets.append(pallet_info)
        else:
            float_pallets.append(pallet_info)

    global_combinations, global_single_floats = create_float_combinations(float_pallets)
    
    single_items_to_pack = []
    for p in integer_pallets:
        single_items_to_pack.append({"type": "SinglePallet", "items": [p], "total_boxes_count": p['number_of_boxes'], "total_weight": p['total_item_weight']})
    for p in global_single_floats:
        single_items_to_pack.append({"type": "SinglePallet", "items": [p], "total_boxes_count": p['number_of_boxes'], "total_weight": p['total_item_weight']})
    
    single_items_to_pack.sort(key=lambda x: x['total_weight'], reverse=True)

    packed_containers = []
    for item in single_items_to_pack:
        best_container_index, min_remaining_space = -1, sys.float_info.max
        for i, container in enumerate(packed_containers):
            if (container['total_weight'] + item['total_weight'] <= MAX_CONTAINER_WEIGHT and
                container['total_boxes'] + item['total_boxes_count'] <= MAX_CONTAINER_BOXES):
                remaining_space = MAX_CONTAINER_WEIGHT - (container['total_weight'] + item['total_weight'])
                if remaining_space < min_remaining_space:
                    min_remaining_space, best_container_index = remaining_space, i
        
        if best_container_index != -1:
            packed_containers[best_container_index]['contents'].append(item)
            packed_containers[best_container_index]['total_weight'] += item['total_weight']
            packed_containers[best_container_index]['total_boxes'] += item['total_boxes_count']
        else:
            packed_containers.append({"contents": [item], "total_weight": item['total_weight'], "total_boxes": item['total_boxes_count']})

    combo_items_to_pack = []
    for group in global_combinations:
        combo_items_to_pack.append({"type": "CombinedPallet", "items": group, "total_boxes_count": sum(p['number_of_boxes'] for p in group), "total_weight": sum(p['total_item_weight'] for p in group)})
    combo_items_to_pack.sort(key=lambda x: x['total_weight'], reverse=True)

    for item in combo_items_to_pack:
        best_container_index, min_remaining_space = -1, sys.float_info.max
        for i, container in enumerate(packed_containers):
            if (container['total_weight'] + item['total_weight'] <= MAX_CONTAINER_WEIGHT and
                container['total_boxes'] + item['total_boxes_count'] <= MAX_CONTAINER_BOXES):
                remaining_space = MAX_CONTAINER_WEIGHT - (container['total_weight'] + item['total_weight'])
                if remaining_space < min_remaining_space:
                    min_remaining_space, best_container_index = remaining_space, i
        
        if best_container_index != -1:
            packed_containers[best_container_index]['contents'].append(item)
            packed_containers[best_container_index]['total_weight'] += item['total_weight']
            packed_containers[best_container_index]['total_boxes'] += item['total_boxes_count']
        else:
            packed_containers.append({"contents": [item], "total_weight": item['total_weight'], "total_boxes": item['total_boxes_count']})

    final_containers = [{"container_number": i + 1, "contents": c['contents'], "total_weight": c['total_weight'], "total_boxes": c['total_boxes']} for i, c in enumerate(packed_containers)]
    return final_containers

# --- API ENDPOINTS ---

@app.route('/api/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return jsonify({"error": "No file part"}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "No selected file"}), 400
    
    if file and (file.filename.endswith('.xlsx') or file.filename.endswith('.xls')):
        try:
            filename = werkzeug.utils.secure_filename(file.filename)
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath)

            xls = pd.ExcelFile(filepath)
            sheets = xls.sheet_names
            return jsonify({
                "success": True,
                "filepath": filepath,
                "sheets": sheets
            })
        except Exception as e:
            return jsonify({"success": False, "error": f"Lỗi xử lý file Excel: {str(e)}"}), 500
    
    return jsonify({"success": False, "error": "Định dạng file không được hỗ trợ. Vui lòng chỉ tải lên file .xlsx hoặc .xls"}), 400

@app.route('/api/process', methods=['POST'])
def process_data():
    try:
        data = request.get_json()
        filepath = data.get('filepath')
        sheet_name = data.get('sheetName')

        # Đây là phiên bản chỉ cần filepath và sheetName. Lỗi của bạn là do chạy phiên bản cũ hơn.
        if not all([filepath, sheet_name]):
            return jsonify({"success": False, "error": "Thiếu thông tin file hoặc tên sheet."}), 400
        
        # Các cột được xác định cứng dựa trên file mẫu của bạn
        QUANTITY_COL = 'Unnamed: 11'
        WEIGHT_PER_PALLET_COL = 'Tổng\nK.lg/kiện\n(GW/pallet)'
        HEADER_ROW = 3 

        df = pd.read_excel(filepath, sheet_name=sheet_name, header=HEADER_ROW)

        if QUANTITY_COL not in df.columns or WEIGHT_PER_PALLET_COL not in df.columns:
            return jsonify({
                "success": False,
                "error": f"Các cột bắt buộc ('Số lượng pallet' và 'Khối lượng/pallet') không được tìm thấy trong sheet '{sheet_name}'. Vui lòng kiểm tra lại cấu trúc file Excel."
            }), 400

        df_filtered = df.copy()
        
        df_filtered[QUANTITY_COL] = pd.to_numeric(df_filtered[QUANTITY_COL], errors='coerce')
        df_filtered[WEIGHT_PER_PALLET_COL] = pd.to_numeric(df_filtered[WEIGHT_PER_PALLET_COL], errors='coerce')

        df_filtered.dropna(subset=[QUANTITY_COL, WEIGHT_PER_PALLET_COL], inplace=True)
        df_filtered = df_filtered[(df_filtered[QUANTITY_COL] > 0) & (df_filtered[WEIGHT_PER_PALLET_COL] > 0)]

        if df_filtered.empty:
            return jsonify({
                "success": False,
                "error": "Không tìm thấy dữ liệu hợp lệ (số lượng > 0 và khối lượng > 0) trong sheet đã chọn."
            }), 400

        boxes_data = list(zip(
            df_filtered[QUANTITY_COL],
            (df_filtered[QUANTITY_COL] * df_filtered[WEIGHT_PER_PALLET_COL])
        ))

        result = optimize_packing_prioritized(boxes_data)
        
        gc.collect()
        
        return jsonify({
            "success": True,
            "results": result
        })
    except Exception as e:
        print(f"Error in /api/process: {e}", file=sys.stderr)
        return jsonify({"success": False, "error": f"Đã xảy ra lỗi không mong muốn khi xử lý dữ liệu: {str(e)}"}), 500

# --- CHẠY ỨNG DỤNG ---
if __name__ == '__main__':
    from waitress import serve
    print("Starting server with Waitress on http://0.0.0.0:5001")
    serve(app, host='0.0.0.0', port=5001, threads=8)