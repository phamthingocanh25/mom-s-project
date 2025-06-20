import math
import sys
import numpy as np
import pandas as pd # Giữ lại nếu cần các phép toán của pandas, dù không đọc file trực tiếp ở đây

# --- HẰNG SỐ TOÀN CỤC ---
# Trọng lượng tối đa của một container (kg)
MAX_CONTAINER_WEIGHT = 24000
# Số pallet tối đa (hoặc 'boxes') trong một container
MAX_CONTAINER_BOXES = 20.0
# Một giá trị nhỏ để xử lý so sánh số thực, tránh lỗi làm tròn
EPSILON = 1e-6

# Hàm create_float_combinations
def create_float_combinations(float_pallets):
    """
    Tạo các tổ hợp từ các pallet lẻ (số lượng pallet là số thực)
    để chúng có thể được ghép lại thành một tổng gần với số nguyên.
    """
    if not float_pallets:
        return [], []

    def perform_combination_pass(pallets_to_process):
        """
        Thực hiện một lần duyệt để kết hợp các pallet.
        """
        pallets_copy = list(pallets_to_process)
        # Sắp xếp giảm dần theo số lượng hộp để ưu tiên các pallet lớn hơn
        pallets_copy.sort(key=lambda p: p['number_of_boxes'], reverse=True)
        processed_flags = {p['original_index']: False for p in pallets_copy}
        final_groups = []

        for base_pallet in pallets_copy:
            # Nếu pallet đã được xử lý trong một nhóm khác, bỏ qua
            if processed_flags[base_pallet['original_index']]:
                continue

            new_group = [base_pallet]
            processed_flags[base_pallet['original_index']] = True
            current_sum = base_pallet['number_of_boxes']
            # Giới hạn cho phép kết hợp (ví dụ: pallet cơ sở 5.3 + 0.9 = 6.2, tìm pallet sao cho tổng <= 6.2)
            limit = math.floor(base_pallet['number_of_boxes']) + 0.9 + EPSILON

            for candidate_pallet in pallets_copy:
                if processed_flags[candidate_pallet['original_index']]:
                    continue
                # Nếu thêm pallet ứng viên không vượt quá giới hạn
                if current_sum + candidate_pallet['number_of_boxes'] <= limit:
                    new_group.append(candidate_pallet)
                    processed_flags[candidate_pallet['original_index']] = True
                    current_sum += candidate_pallet['number_of_boxes']
            final_groups.append(new_group) # Thêm nhóm đã tạo
        return final_groups

    # Chạy lần đầu để tạo các nhóm kết hợp
    initial_groups = perform_combination_pass(float_pallets)
    # Các nhóm có nhiều hơn 1 pallet là tổ hợp thực sự
    true_combinations = [group for group in initial_groups if len(group) > 1]
    # Các nhóm chỉ có 1 pallet là các pallet lẻ còn lại
    single_leftovers = [group[0] for group in initial_groups if len(group) == 1]

    # Nếu còn nhiều pallet lẻ chưa được ghép, thử chạy lại để tìm thêm tổ hợp
    if len(single_leftovers) > 1:
        rerun_groups = perform_combination_pass(single_leftovers)
        true_combinations.extend([group for group in rerun_groups if len(group) > 1])
        single_leftovers = [group[0] for group in rerun_groups if len(group) == 1]
    return true_combinations, single_leftovers


def optimize_container_allocation(boxes_data):
    """
    Tối ưu hóa việc phân bổ các pallet vào container,
    ưu tiên đóng gói các pallet đơn trước, sau đó là các tổ hợp.

    Args:
        boxes_data (list of tuples): Danh sách các pallet, mỗi pallet là một tuple (số lượng pallet, trọng lượng).
                                      Ví dụ: [(0.62, 260), (2.37, 1632), ...]
    Returns:
        list of dicts: Danh sách các container đã đóng gói, bao gồm thông tin về nội dung,
                        tổng trọng lượng và tổng số pallet.
    """
    
    # --- Giai đoạn 1: Phân loại và tạo Tổ Hợp Toàn Cục ---
    integer_pallets = [] # Pallet có số lượng nguyên (ví dụ: 1.0, 2.0)
    float_pallets = []   # Pallet có số lượng lẻ (ví dụ: 0.62, 2.37)
    for idx, (box_num, weight_per_unit) in enumerate(boxes_data):
        pallet_info = {
            "original_index": idx,
            "number_of_boxes": float(box_num), # Đảm bảo là float để nhất quán
            "total_item_weight_tons": float(weight_per_unit) # Đảm bảo là float
        }
        # Kiểm tra xem số lượng pallet có phải là số nguyên hay không (có tính đến EPSILON)
        if abs(pallet_info['number_of_boxes'] - round(pallet_info['number_of_boxes'])) < EPSILON:
            integer_pallets.append(pallet_info)
        else:
            float_pallets.append(pallet_info)

    # Tạo các tổ hợp từ các pallet lẻ ban đầu
    global_combinations, global_single_floats = create_float_combinations(float_pallets)

    # --- Giai đoạn 2: Đóng Gói Ưu Tiên ---

    # Bước 2a: Chuẩn bị và đóng gói CÁC PALLET ĐƠN trước
    single_items_to_pack = []
    # Thêm các pallet nguyên
    for p in integer_pallets:
        single_items_to_pack.append({
            "type": "SingleInteger",
            "items": [p], # Mặc dù là 'Single', vẫn để trong list để cấu trúc nhất quán
            "total_boxes_count": p['number_of_boxes'],
            "total_weight_tons": p['total_item_weight_tons']
        })
    # Thêm các pallet lẻ còn lại sau khi tạo tổ hợp toàn cục
    for p in global_single_floats:
        single_items_to_pack.append({
            "type": "SingleFloat",
            "items": [p],
            "total_boxes_count": p['number_of_boxes'],
            "total_weight_tons": p['total_item_weight_tons']
        })
    
    # Sắp xếp các pallet đơn theo trọng lượng giảm dần để tối ưu hóa việc đóng gói
    single_items_to_pack.sort(key=lambda x: x['total_weight_tons'], reverse=True)

    packed_containers = [] # Danh sách các container đã được đóng gói

    # Vòng lặp đóng gói cho pallet đơn
    for item in single_items_to_pack:
        best_container_index = -1
        best_fit_score = sys.float_info.max # Tìm container có khoảng trống còn lại nhỏ nhất
        
        # Duyệt qua các container hiện có để tìm nơi phù hợp nhất
        for i, container in enumerate(packed_containers):
            # Kiểm tra xem item có thể được thêm vào container hiện tại không
            if (container['total_weight'] + item['total_weight_tons'] <= MAX_CONTAINER_WEIGHT and
                container['total_boxes'] + item['total_boxes_count'] <= MAX_CONTAINER_BOXES):
                
                # Tính điểm phù hợp: khoảng trống trọng lượng còn lại sau khi thêm item
                current_score = MAX_CONTAINER_WEIGHT - (container['total_weight'] + item['total_weight_tons'])
                if current_score < best_fit_score:
                    best_fit_score = current_score
                    best_container_index = i
        
        if best_container_index != -1:
            # Nếu tìm thấy container phù hợp, thêm item vào
            packed_containers[best_container_index]['contents'].append(item)
            packed_containers[best_container_index]['total_weight'] += item['total_weight_tons']
            packed_containers[best_container_index]['total_boxes'] += item['total_boxes_count']
        else:
            # Nếu không tìm thấy container phù hợp, tạo một container mới
            packed_containers.append({
                "contents": [item],
                "total_weight": item['total_weight_tons'],
                "total_boxes": item['total_boxes_count']
            })

    # Bước 2b: Chuẩn bị và đóng gói CÁC PALLET KẾT HỢP sau
    combo_items_to_pack = []
    # Chuyển các nhóm tổ hợp toàn cục thành định dạng item để đóng gói
    for group in global_combinations:
        combo_items_to_pack.append({
            "type": "Combination",
            "items": group,
            "total_boxes_count": sum(p['number_of_boxes'] for p in group),
            "total_weight_tons": sum(p['total_item_weight_tons'] for p in group)
        })

    # Sắp xếp các pallet kết hợp theo trọng lượng giảm dần
    combo_items_to_pack.sort(key=lambda x: x['total_weight_tons'], reverse=True)

    # Vòng lặp đóng gói cho pallet kết hợp, xếp vào các container đã có hoặc tạo mới
    for item in combo_items_to_pack:
        best_container_index = -1
        best_fit_score = sys.float_info.max # Tìm container có khoảng trống còn lại nhỏ nhất
        
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
            # Nếu không tìm thấy container phù hợp, tạo một container mới
            packed_containers.append({
                "contents": [item],
                "total_weight": item['total_item_weight_tons'], # Sửa lỗi: dùng total_weight_tons của item
                "total_boxes": item['total_boxes_count'] # Sửa lỗi: dùng total_boxes_count của item
            })

    # --- Giai đoạn 3: Tối Ưu Hóa Sau Đóng Gói (Xử lý lại các pallet lẻ trong từng container) ---
    final_containers = []
    for i, container in enumerate(packed_containers):
        # Tách các pallet lẻ (SingleFloat) ra khỏi các nội dung khác trong container này
        single_floats_in_container = [content['items'][0] for content in container['contents'] if content['type'] == 'SingleFloat']
        other_contents = [content for content in container['contents'] if content['type'] != 'SingleFloat']
        
        # Thử tạo thêm các tổ hợp mới từ các pallet lẻ còn lại trong container này
        new_local_combinations, still_single_floats = create_float_combinations(single_floats_in_container)
        
        new_container_contents = list(other_contents) # Bắt đầu với các nội dung không phải SingleFloat
        
        # Thêm các tổ hợp mới được tạo ra
        for group in new_local_combinations:
             new_container_contents.append({
                 "type": "Combination",
                 "items": group,
                 "total_boxes_count": sum(p['number_of_boxes'] for p in group),
                 "total_weight_tons": sum(p['total_item_weight_tons'] for p in group)
             })
        
        # Thêm các pallet lẻ vẫn còn lại sau khi tối ưu hóa cục bộ
        for p in still_single_floats:
            new_container_contents.append({
                "type": "SingleFloat",
                "items": [p],
                "total_boxes_count": p['number_of_boxes'],
                "total_weight_tons": p['total_item_weight_tons']
            })
        
        final_containers.append({
            "container_number": i + 1,
            "contents": new_container_contents,
            "total_weight": container['total_weight'],
            "total_boxes": container['total_boxes']
        })
        
    return final_containers

# Các đoạn code chạy thử với dữ liệu cứng đã được loại bỏ để module này chỉ chứa hàm logic.
# Dữ liệu đầu vào sẽ được cung cấp từ data_processor.py
