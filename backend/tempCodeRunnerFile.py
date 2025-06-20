import sys
import os
import math
import numpy as np
from flask import Flask, request, jsonify
import pandas as pd

app = Flask(__name__)

# Fallback CORS support nếu không cài flask-cors
@app.after_request
def add_cors_headers(response):
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
    return response

UPLOAD_FOLDER = 'uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# --- TÍCH HỢP TOÀN BỘ LOGIC TỪ core_math.py ---
# --- HẰNG SỐ TOÀN CỤC ---
MAX_CONTAINER_WEIGHT = 24000
MAX_CONTAINER_BOXES = 20.0
EPSILON = 1e-6

def create_float_combinations(float_pallets):
    """Tạo các tổ hợp pallet thập phân"""
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
    """Tối ưu hóa đóng gói container với ưu tiên pallet đơn"""
    # Tạo tổ hợp toàn cục
    integer_pallets = []
    float_pallets = []
    for idx, (box_num, weight_per_unit) in enumerate(boxes_data):
        pallet_info = {"original_index": idx, "number_of_boxes": box_num, "total_item_weight_tons": weight_per_unit}
        if abs(box_num - round(box_num)) < EPSILON:
            integer_pallets.append(pallet_info)
        else:
            float_pallets.append(pallet_info)

    global_combinations, global_single_floats = create_float_combinations(float_pallets)

    # Đóng gói ưu tiên
    single_items_to_pack = []
    for p in integer_pallets:
        single_items_to_pack.append({"type": "SingleInteger", "items": [p], "total_boxes_count": p['number_of_boxes'], "total_weight_tons": p['total_item_weight_tons']})
    for p in global_single_floats:
        single_items_to_pack.append({"type": "SingleFloat", "items": [p], "total_boxes_count": p['number_of_boxes'], "total_weight_tons": p['total_item_weight_tons']})
    
    single_items_to_pack.sort(key=lambda x: x['total_weight_tons'], reverse=True)

    packed_containers = []
    for item in single_items_to_pack:
        best_container_index = -1
        best_fit_score = sys.float_info.max
        for i, container in enumerate(packed_containers):
            if (container['total_weight'] + item['total_weight_tons'] <= MAX_CONTAINER_WEIGHT and
                container['total_boxes'] + item['total_boxes_count'] <= MAX_CONTAINER_BOXES):
                current_score = MAX_CONTAINER_WEIGHT - (container['total_weight'] + item['total_weight_tons'])
                if current_score < best_fit_score:
                    best_fit_score = current_score
                    best_container_index = i
        
        if best_container_index != -1:
            packed_containers[best_container_index]['contents'].append(item)
            packed_containers[best_container_index]['total_weight'] += item['total_weight_tons']
            packed_containers[best_container_index]['total_boxes'] += item['total_boxes_count']
        else:
            packed_containers.append({"contents": [item], "total_weight": item['total_weight_tons'], "total_boxes": item['total_boxes_count']})

    # Đóng gói pallet kết hợp
    combo_items_to_pack = []
    for group in global_combinations:
        combo_items_to_pack.append({"type": "Combination", "items": group, "total_boxes_count": sum(p['number_of_boxes'] for p in group), "total_weight_tons": sum(p['total_item_weight_tons'] for p in group)})
    
    combo_items_to_pack.sort(key=lambda x: x['total_weight_tons'], reverse=True)
    
    for item in combo_items_to_pack:
        best_container_index = -1
        best_fit_score = sys.float_info.max
        for i, container in enumerate(packed_containers):
            if (container['total_weight'] + item['total_weight_tons'] <= MAX_CONTAINER_WEIGHT and
                container['total_boxes'] + item['total_boxes_count'] <= MAX_CONTAINER_BOXES):
                current_score = MAX_CONTAINER_WEIGHT - (container['total_weight'] + item['total_weight_tons'])
                if current_score < best_fit_score:
                    best_fit_score = current_score
                    best_container_index = i
        
        if best_container_index != -1:
            packed_containers[best_container_index]['contents'].append(item)
            packed_containers[best_container_index]['total_weight'] += item['total_weight_tons']
            packed_containers[best_container_index]['total_boxes'] += item['total_boxes_count']
        else:
            packed_containers.append({"contents": [item], "total_weight": item['total_weight_tons'], "total_boxes": item['total_boxes_count']})

    # Tối ưu hóa sau đóng gói
    final_containers = []
    for i, container in enumerate(packed_containers):
        single_floats_in_container = [content['items'][0] for content in container['contents'] if content['type'] == 'SingleFloat']
        other_contents = [content for content in container['contents'] if content['type'] != 'SingleFloat']
        new_local_combinations, still_single_floats = create_float_combinations(single_floats_in_container)
        
        new_container_contents = list(other_contents)
        for group in new_local_combinations:
             new_container_contents.append({"type": "Combination", "items": group, "total_boxes_count": sum(p['number_of_boxes'] for p in group), "total_weight_tons": sum(p['total_item_weight_tons'] for p in group)})
        for p in still_single_floats:
            new_container_contents.append({"type": "SingleFloat", "items": [p], "total_boxes_count": p['number_of_boxes'], "total_weight_tons": p['total_item_weight_tons']})
        
        final_containers.append({
            "container_number": i + 1,
            "contents": new_container_contents,
            "total_weight": container['total_weight'],
            "total_boxes": container['total_boxes']
        })
        
    return final_containers

def optimize_container_allocation(boxes_data):
    """Giao diện chính cho tối ưu hóa container"""
    if not boxes_data:
        return []
    
    return optimize_packing_prioritized(boxes_data)
# --- KẾT THÚC PHẦN TÍCH HỢP TỪ core_math.py ---

# --- HÀM XỬ LÝ DỮ LIỆU ---
def process_uploaded_file(file_path):
    """Đọc file Excel và trả về danh sách các sheet"""
    try:
        xl = pd.ExcelFile(file_path)
        return {
            "success": True,
            "sheets": xl.sheet_names,
            "message": "File processed successfully"
        }
    except Exception as e:
        return {
            "success": False,
            "message": f"Error processing file: {str(e)}"
        }

def load_sheet_data(file_path, sheet_name, filters=None, header_row=3):
    """Đọc dữ liệu từ sheet cụ thể và áp dụng bộ lọc"""
    if filters is None:
        filters = {}
    
    try:
        df = pd.read_excel(file_path, sheet_name=sheet_name, header=header_row)
        
        # Áp dụng bộ lọc
        if 'factory' in filters and filters['factory']:
            factory_value = int(filters['factory'])
            df = df[df['Unnamed: 3'] == factory_value]
        
        if 'minPallets' in filters and filters['minPallets']:
            min_val = float(filters['minPallets'])
            df = df[df['Unnamed: 11'] >= min_val]
        
        if 'maxPallets' in filters and filters['maxPallets']:
            max_val = float(filters['maxPallets'])
            df = df[df['Unnamed: 11'] <= max_val]
        
        # Lọc giá trị pallet > 0
        df = df[df['Unnamed: 11'] > 0]
        
        # Chuẩn bị dữ liệu cho tối ưu hóa
        results = []
        for _, row in df.iterrows():
            if pd.notna(row['Unnamed: 11']):
                pallets = round(row['Unnamed: 11'], 2)
                weight_per_pallet = row.get('Tổng\nK.lg/kiện\n(GW/pallet)', 0)
                if pd.isna(weight_per_pallet):
                    weight_per_pallet = 0
                weight = round(pallets * weight_per_pallet)
                results.append((pallets, weight))
        
        return {
            "success": True,
            "data": results,
            "columns": list(df.columns),
            "row_count": len(df)
        }
    except Exception as e:
        return {
            "success": False,
            "message": f"Error loading sheet: {str(e)}"
        }
# --- KẾT THÚC PHẦN XỬ LÝ DỮ LIỆU ---

# --- ĐỊNH NGHĨA API ---
@app.route('/')
def home():
    return "Container Optimization API - All-in-One Version"

@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return jsonify({"error": "No file part"}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "No selected file"}), 400
    
    file_path = os.path.join(app.config['UPLOAD_FOLDER'], file.filename)
    file.save(file_path)
    
    result = process_uploaded_file(file_path)
    result['file_path'] = file_path
    
    return jsonify(result)

@app.route('/process', methods=['POST'])
def process_data():
    data = request.json
    file_path = data.get('file_path')
    sheet_name = data.get('sheet_name')
    filters = data.get('filters', {})
    
    if not file_path or not sheet_name:
        return jsonify({"error": "Missing required parameters"}), 400
    
    # Tiền xử lý dữ liệu
    processed_data = load_sheet_data(file_path, sheet_name, filters)
    
    if not processed_data['success']:
        return jsonify(processed_data), 400
    
    # Tối ưu hóa container
    optimization_results = optimize_container_allocation(processed_data['data'])
    processed_data['optimization'] = optimization_results
    
    return jsonify(processed_data)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)