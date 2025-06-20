import os
import sys
import math
import pandas as pd
from flask import Flask, request, jsonify
from flask_cors import CORS
import werkzeug.utils
import requests
import json
import gc

# --- KHỞI TẠO ỨNG DỤNG FLASK ---
app = Flask(__name__)

# Tăng giới hạn kích thước tệp tải lên lên 500MB để xử lý các file dữ liệu lớn
app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024 
CORS(app)

UPLOAD_FOLDER = 'uploads'
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# --- LOGIC TỐI ƯU HÓA (GIỮ NGUYÊN) ---
# Hằng số và logic cốt lõi của việc tối ưu hóa không thay đổi.
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
    
    if file and (file.filename.endswith('.xlsx') or file.filename.endswith('.xls') or file.filename.endswith('.csv')):
        try:
            filename = werkzeug.utils.secure_filename(file.filename)
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath)

            # Với file lớn, chỉ lấy tên sheet từ file excel, không đọc toàn bộ file
            if file.filename.endswith(('.xlsx', '.xls')):
                xls = pd.ExcelFile(filepath)
                sheets = xls.sheet_names
                return jsonify({
                    "success": True,
                    "filepath": filepath,
                    "sheets": sheets,
                    "file_type": "excel"
                })
            else: # .csv file
                return jsonify({
                    "success": True,
                    "filepath": filepath,
                    "sheets": ["CSV Data"], # CSV chỉ có 1 "sheet"
                    "file_type": "csv"
                })

        except Exception as e:
            return jsonify({
                "success": False,
                "error": f"Lỗi xử lý file: {str(e)}"
            }), 500
    
    return jsonify({
        "success": False,
        "error": "Định dạng file không được hỗ trợ. Vui lòng tải lên file .xlsx, .xls hoặc .csv"
    }), 400

@app.route('/api/process', methods=['POST'])
def process_data():
    try:
        data = request.get_json()
        filepath = data.get('filepath')
        sheet_name = data.get('sheetName')
        quantity_col = data.get('quantityCol')
        weight_col = data.get('weightCol')
        filter_col = data.get('filterCol')
        filter_val = data.get('filterVal')
        header_row = int(data.get('headerRow', 3))
        file_type = data.get('file_type', 'excel')

        if not all([filepath, quantity_col, weight_col]):
             return jsonify({
                 "success": False,
                 "error": "Thiếu các trường thông tin bắt buộc"
             }), 400

        # *** TỐI ƯU HÓA: Đọc file theo từng phần (chunk) để tiết kiệm bộ nhớ ***
        chunk_size = 10000  # Xử lý 10,000 dòng mỗi lần
        boxes_data = []
        
        # Khởi tạo reader tương ứng với loại file
        if file_type == 'excel':
            if not sheet_name:
                return jsonify({"success": False, "error": "Vui lòng chọn sheet để xử lý."}), 400
            reader = pd.read_excel(
                filepath, 
                sheet_name=sheet_name, 
                header=header_row,
                engine='openpyxl',
                chunksize=chunk_size
            )
        else: # 'csv'
            reader = pd.read_csv(
                filepath, 
                header=header_row, 
                chunksize=chunk_size,
                on_bad_lines='skip' # Bỏ qua các dòng bị lỗi nếu có
            )

        # Lặp qua từng chunk để xử lý
        for chunk in reader:
            # Áp dụng bộ lọc nếu có
            if filter_col and filter_val:
                try:
                    if filter_col in chunk.columns:
                        if chunk[filter_col].dtype == 'object':
                            chunk = chunk[chunk[filter_col].astype(str) == str(filter_val)]
                        else:
                            numeric_filter_val = pd.to_numeric(filter_val, errors='coerce')
                            if not pd.isna(numeric_filter_val):
                                chunk[filter_col] = pd.to_numeric(chunk[filter_col], errors='coerce')
                                chunk = chunk[chunk[filter_col] == numeric_filter_val]
                except Exception as e:
                    print(f"Filter error on chunk: {e}") # Ghi log lỗi filter nhưng vẫn tiếp tục

            # Kiểm tra sự tồn tại của cột trong chunk
            if quantity_col not in chunk.columns or weight_col not in chunk.columns:
                 return jsonify({
                    "success": False,
                    "error": f"Cột '{quantity_col}' hoặc '{weight_col}' không tồn tại."
                }), 400

            # Làm sạch dữ liệu trong chunk
            chunk[quantity_col] = pd.to_numeric(chunk[quantity_col], errors='coerce')
            chunk[weight_col] = pd.to_numeric(chunk[weight_col], errors='coerce')
            
            # Loại bỏ các dòng có giá trị không hợp lệ (NaN) hoặc <= 0
            chunk.dropna(subset=[quantity_col, weight_col], inplace=True)
            chunk = chunk[(chunk[quantity_col] > 0) & (chunk[weight_col] > 0)]

            # Thêm dữ liệu đã xử lý từ chunk vào danh sách tổng
            if not chunk.empty:
                boxes_data.extend(list(zip(chunk[quantity_col], chunk[weight_col])))

        if not boxes_data:
            return jsonify({
                "success": False,
                "error": "Không tìm thấy dữ liệu hợp lệ sau khi đọc và lọc file."
            }), 400
        
        # Gọi hàm tối ưu hóa với danh sách dữ liệu đầy đủ
        result = optimize_packing_prioritized(boxes_data)
        
        # Giải phóng bộ nhớ
        del reader
        del boxes_data
        gc.collect()
        
        return jsonify({
            "success": True,
            "results": result
        })
    except Exception as e:
        print(f"Error in /api/process: {e}", file=sys.stderr)
        return jsonify({
            "success": False,
            "error": f"Đã xảy ra lỗi không mong muốn: {str(e)}"
        }), 500

# --- TÍNH NĂNG MỚI: GEMINI API (GIỮ NGUYÊN) ---
def create_report_prompt(results_data):
    prompt = "Bạn là một điều phối viên logistics chuyên nghiệp. Dựa trên dữ liệu xếp container sau đây, hãy viết một báo cáo vận chuyển bằng tiếng Việt.\n\n"
    prompt += "Yêu cầu báo cáo:\n"
    prompt += "1.  **Tóm tắt tổng quan:** Nêu rõ tổng số container, tổng trọng lượng hàng, và hiệu suất sử dụng (tính trung bình % trọng lượng đã lấp đầy so với 24000kg).\n"
    prompt += "2.  **Chi tiết từng container:** Liệt kê các container, trọng lượng, số pallet, và hiệu suất lấp đầy của từng container. Nhắc đến có bao nhiêu pallet đơn và pallet kết hợp.\n"
    prompt += "3.  **Lưu ý & Đề xuất:** Đưa ra các cảnh báo nếu có (ví dụ: container gần quá tải) và các đề xuất để việc bốc dỡ hiệu quả.\n\n"
    prompt += "Dữ liệu:\n"
    prompt += f"```json\n{json.dumps(results_data, indent=2)}\n```\n\n"
    prompt += "Vui lòng trình bày báo cáo một cách chuyên nghiệp, rõ ràng và dễ hiểu."
    return prompt

@app.route('/api/generate-report', methods=['POST'])
def generate_report():
    try:
        optimization_results = request.get_json()
        if not optimization_results:
            return jsonify({"error": "No optimization data provided"}), 400

        prompt = create_report_prompt(optimization_results)
        
        # Lấy API Key từ biến môi trường để bảo mật hơn
        api_key = os.environ.get("GEMINI_API_KEY") 
        if not api_key:
            return jsonify({"error": "API key for Gemini is not configured on the server."}), 500

        api_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash-latest:generateContent?key={api_key}"
        headers = {'Content-Type': 'application/json'}
        payload = {"contents": [{"role": "user", "parts": [{"text": prompt}]}]}

        response = requests.post(api_url, headers=headers, data=json.dumps(payload))
        response.raise_for_status() 

        result_json = response.json()
        
        if (result_json.get('candidates') and 
            result_json['candidates'][0].get('content') and 
            result_json['candidates'][0]['content'].get('parts')):
            
            generated_text = result_json['candidates'][0]['content']['parts'][0]['text']
            return jsonify({"report": generated_text})
        else:
            return jsonify({"error": "Failed to generate report from API. The response was empty.", "details": result_json}), 500

    except requests.exceptions.RequestException as e:
        return jsonify({"error": f"API request failed: {e}"}), 500
    except Exception as e:
        print(f"Error in /api/generate-report: {e}", file=sys.stderr)
        return jsonify({"error": f"An unexpected error occurred: {str(e)}"}), 500

# --- CHẠY ỨNG DỤNG ---
if __name__ == '__main__':
    # Chạy trên port 5001 và cho phép truy cập từ mọi địa chỉ IP trong mạng
    # Sử dụng `threaded=True` để xử lý nhiều yêu cầu tốt hơn
    app.run(host='0.0.0.0', port=5001, debug=True, threaded=True)