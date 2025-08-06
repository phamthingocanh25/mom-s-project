# test_def.py
from data_processor import *
import pandas as pd
import math
import re
def collect_items_for_rebalancing_v2(df_container):
    """
    Phân tích DataFrame của container, tách pallet thành 2 nhóm:
    1. Pallet đơn đã đầy (>=100%) sẽ được GIỮ LẠI.
    2. Pallet đơn chưa đầy và TẤT CẢ pallet ghép sẽ được đưa vào HÀNG CHỜ.

    Args:
        df_container (pd.DataFrame): DataFrame PKL đã được phân tích lần đầu.

    Returns:
        tuple: (list_of_kept_pallets, list_of_items_to_rebalance)
    """
    items_to_rebalance = []
    pallets_to_keep = []  # Danh sách mới để lưu các pallet được giữ lại

    # Tạo các cột tạm nếu chưa có
    if '__PalletGroup' not in df_container.columns:
        df_container['__PalletGroup'] = df_container['Pallet'].replace('', pd.NA).ffill()
    if '__ItemRatio' not in df_container.columns:
        df_container["Q'ty (boxes)"] = pd.to_numeric(df_container["Q'ty (boxes)"], errors='coerce').fillna(0)
        df_container["Box/Pallet"] = pd.to_numeric(df_container["Box/Pallet"], errors='coerce').fillna(0)
        max_box_per_pallet_map = df_container.groupby('__PalletGroup')['Box/Pallet'].transform('max')
        
        def calculate_ratio(row, max_val):
            return (row["Q'ty (boxes)"] / max_val) if max_val > 0 else 0
        df_container['__ItemRatio'] = df_container.apply(lambda row: calculate_ratio(row, max_box_per_pallet_map[row.name]), axis=1)

    # Lặp qua từng pallet để phân loại
    for _, group in df_container.groupby('__PalletGroup'):
        is_single_item_pallet = len(group) == 1
        total_pallet_ratio = group['__ItemRatio'].sum()

        if is_single_item_pallet and total_pallet_ratio >= 1.0:
            # GIỮ LẠI: Pallet đơn đã đầy, thêm vào danh sách giữ lại
            pallets_to_keep.append(group.to_dict('records'))
        else:
            # HÀNG CHỜ: Pallet ghép hoặc pallet đơn chưa đầy
            items_to_rebalance.extend(group.to_dict('records'))
            
    # Sắp xếp các item cần cân bằng
    items_to_rebalance.sort(key=lambda x: x['__ItemRatio'], reverse=True)
    
    print(f"\n[PHÂN LOẠI] Đã giữ lại {len(pallets_to_keep)} pallet tối ưu.")
    print(f"[HÀNG CHỜ] Đã thu thập {len(items_to_rebalance)} pallet con để cân bằng lại.")
    return pallets_to_keep, items_to_rebalance


def generate_final_complete_pkl(kept_pallets, rebalanced_pallets):
    """
    Tạo và hiển thị một DataFrame Packing List HOÀN CHỈNH cuối cùng, bao gồm 
    cả các pallet được giữ lại và các pallet đã được cân bằng.

    Args:
        kept_pallets (list): Danh sách các pallet đơn tối ưu đã được giữ lại.
        rebalanced_pallets (list): Danh sách các pallet mới đã được nhóm lại từ hàng chờ.
    """
    print("\n\n" + "#"*35)
    print("KẾT QUẢ PACKING LIST HOÀN CHỈNH SAU CÂN BẰNG")
    print("#"*35)

    # Gộp 2 danh sách lại để tạo PKL cuối cùng
    all_final_pallet_groups = kept_pallets + rebalanced_pallets
    all_final_pallet_groups.sort(key=lambda pg: pg[0]['Part No.']) # Sắp xếp lại cho dễ nhìn

    if not all_final_pallet_groups:
        print("Không có pallet nào để tạo Packing List cuối cùng.")
        return

    pkl_data_list = []
    pallet_counter = {'item_no': 1, 'pallet_no': 1}  # Đếm lại từ đầu cho PKL mới

    for pallet_group in all_final_pallet_groups:
        total_nw_group = sum(_safe_float(item.get('N.W (kgs)', 0)) for item in pallet_group)
        total_boxes_group = sum(_safe_float(item.get("Q'ty (boxes)", 0)) for item in pallet_group)
        max_box_per_pallet_in_group = max(_safe_float(item.get('Box/Pallet', 0)) for item in pallet_group)
        
        total_ratio_group = (total_boxes_group / max_box_per_pallet_in_group) if max_box_per_pallet_in_group > 0 else 0
        
        # Ưu tiên lấy G.W và CBM gốc từ pallet được giữ lại, nếu không có thì tính mới
        gw_kgs_group = _safe_float(pallet_group[0].get('G.W (kgs)', 0))
        cbm_group = _safe_float(pallet_group[0].get('CBM', 0))

        if gw_kgs_group == 0:  # Là pallet mới được cân bằng
            gw_kgs_group = math.ceil(total_nw_group + (total_boxes_group * 0.4) + 50)
        if cbm_group == 0:  # Là pallet mới được cân bằng
            cbm_group = max(total_ratio_group * 1.15 * 1.15 * 0.8, 0.1)

        is_first_item_in_group = True
        for item_data in pallet_group:
            row = {
                'Item No.': pallet_counter['item_no'] if is_first_item_in_group else '',
                'Pallet': f"No.{pallet_counter['pallet_no']:03d}" if is_first_item_in_group else '',
                'Part Name': item_data['Part Name'], 'Part No.': item_data['Part No.'],
                "Q'ty (boxes)": item_data["Q'ty (boxes)"], "Q'ty (pcs)": item_data["Q'ty (pcs)"],
                'W / pc (kgs)': item_data['W / pc (kgs)'], 'N.W (kgs)': item_data['N.W (kgs)'],
                'G.W (kgs)': round(gw_kgs_group) if is_first_item_in_group else 0,
                'MEAS. (m)': "1.15*1.15*0.8" if is_first_item_in_group else '',
                'CBM': round(cbm_group, 4) if is_first_item_in_group else 0,
                "Q'ty/box": item_data["Q'ty/box"], "Box/Pallet": item_data["Box/Pallet"],
                "Box Spec": item_data["Box Spec"],
            }
            pkl_data_list.append(row)
            is_first_item_in_group = False

        pallet_counter['item_no'] += 1
        pallet_counter['pallet_no'] += 1

    df_final_pkl = pd.DataFrame(pkl_data_list)
    
    # Thêm cột 'Total Pallet Ratio'
    df_final_pkl['__PalletGroup'] = df_final_pkl['Pallet'].replace('', pd.NA).ffill()
    max_bpp_map = df_final_pkl.groupby('__PalletGroup')['Box/Pallet'].transform('max')
    total_boxes_map = df_final_pkl.groupby('__PalletGroup')["Q'ty (boxes)"].transform('sum')
    group_ratios = (total_boxes_map / max_bpp_map).fillna(0)
    df_final_pkl['Total Pallet Ratio'] = group_ratios.map(lambda x: f"{x:.2%}")
    df_final_pkl.loc[df_final_pkl['__PalletGroup'].duplicated(), 'Total Pallet Ratio'] = ''
    df_final_pkl.drop(columns=['__PalletGroup'], inplace=True)

    pd.set_option('display.max_columns', None)
    pd.set_option('display.width', 1000)
    print(df_final_pkl)
    print("="*70)
def collect_items_for_rebalancing(df_container):
    """
    Phân tích DataFrame của container, tách tất cả các pallet con từ
    pallet đơn chưa đầy và TẤT CẢ pallet ghép để đưa vào hàng chờ xử lý lại.
    Pallet đơn đã đầy (>=100%) sẽ được giữ nguyên và không đưa vào hàng chờ.

    Args:
        df_container (pd.DataFrame): DataFrame PKL đã được phân tích lần đầu.

    Returns:
        list: Một danh sách các dictionary, mỗi dict là một pallet con cần sắp xếp lại.
              Các item được sắp xếp sẵn theo tỷ lệ chiếm chỗ giảm dần.
    """
    items_to_rebalance = []
    
    # Tạo các cột tạm để phân tích nếu chưa có
    df_container['__PalletGroup'] = df_container['Pallet'].replace('', pd.NA).ffill()
    if '__ItemRatio' not in df_container.columns:
        df_container["Q'ty (boxes)"] = pd.to_numeric(df_container["Q'ty (boxes)"], errors='coerce').fillna(0)
        df_container["Box/Pallet"] = pd.to_numeric(df_container["Box/Pallet"], errors='coerce').fillna(0)
        
        # Để tính tỷ lệ của pallet ghép, ta cần dùng max(Box/Pallet) của cả nhóm
        max_box_per_pallet_map = df_container.groupby('__PalletGroup')['Box/Pallet'].transform('max')
        
        def calculate_ratio(row, max_val):
            return (row["Q'ty (boxes)"] / max_val) if max_val > 0 else 0
        df_container['__ItemRatio'] = df_container.apply(lambda row: calculate_ratio(row, max_box_per_pallet_map[row.name]), axis=1)

    # Lặp qua từng pallet để quyết định có đưa vào hàng chờ không
    for _, group in df_container.groupby('__PalletGroup'):
        is_single_item_pallet = len(group) == 1
        
        if is_single_item_pallet:
            total_pallet_ratio = group['__ItemRatio'].sum()
            # Giữ lại pallet đơn đã đầy. Pallet đơn chưa đầy sẽ được đưa vào hàng chờ.
            if total_pallet_ratio >= 1.0:
                continue  # Bỏ qua, pallet này đã tối ưu
            else:
                items_to_rebalance.extend(group.to_dict('records'))
        else:
            # Luôn tách tất cả các pallet con từ pallet ghép để sắp xếp lại tối ưu
            items_to_rebalance.extend(group.to_dict('records'))
            
    # Sắp xếp các item theo tỷ lệ giảm dần để ưu tiên ghép các item lớn trước
    items_to_rebalance.sort(key=lambda x: x['__ItemRatio'], reverse=True)
    
    print(f"\n[HÀNG CHỜ] Đã thu thập {len(items_to_rebalance)} pallet con để cân bằng lại.")
    return items_to_rebalance


def process_waiting_queue(waiting_queue_items):
    """
    Xử lý hàng đợi các pallet con, ghép chúng lại thành các pallet mới
    theo quy tắc lấp đầy <= 90%. Sử dụng thuật toán tham lam (greedy).

    Args:
        waiting_queue_items (list): Danh sách các pallet con (dạng dict) đã được sắp xếp.

    Returns:
        list: Danh sách các pallet mới đã được ghép. Mỗi pallet mới là một list các pallet con.
              Ví dụ: [[item1, item2], [item3], [item4, item5]]
    """
    if not waiting_queue_items:
        return []

    rebalanced_pallets = []
    
    # Lặp cho đến khi hàng đợi được xử lý hết
    while waiting_queue_items:
        # Bắt đầu pallet mới với item lớn nhất còn lại trong hàng chờ
        current_pallet_group = [waiting_queue_items.pop(0)]
        
        # Để tính tỷ lệ pallet ghép, mẫu số phải là max(Box/Pallet) của các thành phần
        max_box_pallet_in_group = _safe_float(current_pallet_group[0].get('Box/Pallet', 0))
        
        def get_current_ratio():
            total_boxes = sum(_safe_float(p.get("Q'ty (boxes)", 0)) for p in current_pallet_group)
            return total_boxes / max_box_pallet_in_group if max_box_pallet_in_group > 0 else 0

        i = 0
        while i < len(waiting_queue_items):
            item_to_test = waiting_queue_items[i]
            test_boxes = _safe_float(item_to_test.get("Q'ty (boxes)", 0))
            
            # Tính tỷ lệ thử nghiệm nếu thêm item này vào
            prospective_max_box_pallet = max(max_box_pallet_in_group, _safe_float(item_to_test.get('Box/Pallet', 0)))
            prospective_total_boxes = sum(_safe_float(p.get("Q'ty (boxes)", 0)) for p in current_pallet_group) + test_boxes
            prospective_ratio = prospective_total_boxes / prospective_max_box_pallet if prospective_max_box_pallet > 0 else 0

            # Nếu tỷ lệ mới vẫn trong ngưỡng cho phép (<= 90%)
            if prospective_ratio <= 0.9 + 1e-6:
                # Thêm item vào nhóm và cập nhật lại max_box_pallet_in_group
                max_box_pallet_in_group = prospective_max_box_pallet
                current_pallet_group.append(waiting_queue_items.pop(i))
                # Không tăng `i` vì list đã bị thu hẹp
            else:
                i += 1 # Chuyển sang xét item tiếp theo

        # Khi không thể thêm item nào nữa, lưu pallet hiện tại vào kết quả
        rebalanced_pallets.append(current_pallet_group)
        
    print(f"[HÀNG CHỜ] Đã xử lý xong, tạo ra {len(rebalanced_pallets)} pallet mới đã cân bằng.")
    return rebalanced_pallets


def render_rebalanced_pkl(rebalanced_pallets):
    """
    Tạo và hiển thị một DataFrame Packing List mới từ các pallet đã được cân bằng lại.
    Hàm này mô phỏng lại việc tạo PKL cho các pallet đơn và pallet ghép.

    Args:
        rebalanced_pallets (list): Danh sách các pallet đã được nhóm lại.
    """
    print("\n\n" + "#"*25)
    print("KẾT QUẢ PACKING LIST SAU KHI CÂN BẰNG HÀNG CHỜ")
    print("#"*25)

    if not rebalanced_pallets:
        print("Không có pallet nào trong hàng chờ để hiển thị.")
        return

    pkl_data_list = []
    pallet_counter = {'item_no': 1, 'pallet_no': 1} # Bắt đầu lại bộ đếm cho PKL mới
    
    for pallet_group in rebalanced_pallets:
        total_nw_group = sum(_safe_float(item.get('N.W (kgs)', 0)) for item in pallet_group)
        total_boxes_group = sum(_safe_float(item.get("Q'ty (boxes)", 0)) for item in pallet_group)
        max_box_per_pallet_in_group = max(_safe_float(item.get('Box/Pallet', 0)) for item in pallet_group)
        
        total_ratio_group = (total_boxes_group / max_box_per_pallet_in_group) if max_box_per_pallet_in_group > 0 else 0
        gw_kgs_group = math.ceil(total_nw_group + (total_boxes_group * 0.4) + 50)
        cbm_group = max(total_ratio_group * 1.15 * 1.15 * 0.8, 0.1)

        is_first_item_in_group = True
        for item_data in pallet_group:
            row = {
                'Item No.': pallet_counter['item_no'] if is_first_item_in_group else '',
                'Pallet': f"No.{pallet_counter['pallet_no']:03d}" if is_first_item_in_group else '',
                'Part Name': item_data['Part Name'], 'Part No.': item_data['Part No.'],
                "Q'ty (boxes)": item_data["Q'ty (boxes)"], "Q'ty (pcs)": item_data["Q'ty (pcs)"],
                'W / pc (kgs)': item_data['W / pc (kgs)'], 'N.W (kgs)': item_data['N.W (kgs)'],
                'G.W (kgs)': round(gw_kgs_group) if is_first_item_in_group else 0,
                'MEAS. (m)': "1.15*1.15*0.8" if is_first_item_in_group else '',
                'CBM': round(cbm_group, 4) if is_first_item_in_group else 0,
                "Q'ty/box": item_data["Q'ty/box"], "Box/Pallet": item_data["Box/Pallet"],
                "Box Spec": item_data["Box Spec"],
            }
            pkl_data_list.append(row)
            is_first_item_in_group = False

        pallet_counter['item_no'] += 1
        pallet_counter['pallet_no'] += 1

    df_rebalanced_pkl = pd.DataFrame(pkl_data_list)
    
    # Thêm cột 'Total Pallet Ratio'
    df_rebalanced_pkl['__PalletGroup'] = df_rebalanced_pkl['Pallet'].replace('', pd.NA).ffill()
    max_bpp_map = df_rebalanced_pkl.groupby('__PalletGroup')['Box/Pallet'].transform('max')
    total_boxes_map = df_rebalanced_pkl.groupby('__PalletGroup')["Q'ty (boxes)"].transform('sum')
    
    group_ratios = (total_boxes_map / max_bpp_map).fillna(0)
    df_rebalanced_pkl['Total Pallet Ratio'] = group_ratios.map(lambda x: f"{x:.2%}")
    df_rebalanced_pkl.loc[df_rebalanced_pkl['__PalletGroup'].duplicated(), 'Total Pallet Ratio'] = ''
    
    df_rebalanced_pkl.drop(columns=['__PalletGroup'], inplace=True)

    pd.set_option('display.max_columns', None)
    pd.set_option('display.width', 1000)
    print(df_rebalanced_pkl)
    print("="*70)
def analyze_combined_pallets_for_rebalancing(df_container):
    """
    Phân tích các pallet trong một container, đưa ra đề xuất bóc tách,
    ghép thêm, hoặc đưa vào hàng chờ.
    - Pallet ghép: Áp dụng ngưỡng <= 90% sức chứa.
    - Pallet đơn: Nếu < 100%, đưa vào hàng chờ.

    Args:
        df_container (pd.DataFrame): DataFrame chứa dữ liệu PKL của một container.

    Returns:
        None. Hàm này chỉ in ra kết quả phân tích chi tiết.
    """
    print("\n" + "#"*25)
    print("PHÂN TÍCH CÂN BẰNG PALLET")
    print("#"*25)

    # Tạo một cột tạm để xác định các pallet (nhóm các dòng có cùng 'Pallet No.')
    df_container['__PalletGroup'] = df_container['Pallet'].replace('', pd.NA).ffill()

    # Lặp qua từng pallet duy nhất trong container
    for pallet_id, group in df_container.groupby('__PalletGroup'):
        
        # --- PHÂN TÍCH PALLET ĐƠN (chỉ có 1 loại hàng hóa) ---
        if len(group) == 1:
            print(f"\n--- Phân tích Pallet Đơn: {pallet_id} ---")
            single_item = group.iloc[0]
            current_boxes = single_item["Q'ty (boxes)"]
            max_boxes = single_item["Box/Pallet"]

            if pd.isna(max_boxes) or max_boxes == 0:
                print(" -> Bỏ qua: Không có dữ liệu 'Box/Pallet' để xác định tỷ lệ.")
                continue

            occupancy_ratio = current_boxes / max_boxes
            print(f"  - Số hộp hiện tại: {current_boxes}")
            print(f"  - Sức chứa pallet: {max_boxes} hộp")
            print(f"  - Tỷ lệ lấp đầy: {occupancy_ratio:.2%}")

            if occupancy_ratio >= 1.0:
                print(f"  -> KẾT LUẬN: ĐẠT CHUẨN (>= 100%). Không cần hành động.")
            else:
                print(f"  -> KẾT LUẬN: CHƯA ĐẦY (< 100%).")
                print(f"  - Đề xuất: Đưa vào hàng chờ để tìm pallet khác ghép cặp (theo quy tắc <=90%).")
                print(f"  - Nếu không thể ghép, sẽ tạo thành pallet đơn mới.")
            
            continue # Chuyển sang pallet tiếp theo

        # --- PHÂN TÍCH PALLET GHÉP (có nhiều loại hàng hóa) ---
        print(f"\n--- Phân tích Pallet Ghép: {pallet_id} ---")

        # Bước 1: Xác định sức chứa tối đa của pallet ghép.
        max_qty_per_box = group["Box/Pallet"].max()
        if pd.isna(max_qty_per_box) or max_qty_per_box == 0:
            print(" -> Bỏ qua: Không có dữ liệu 'Box/Pallet' để xác định sức chứa.")
            continue
        
        # Bước 2: Tính tổng số hộp hiện có và tỷ lệ lấp đầy.
        total_current_boxes = group["Q'ty (boxes)"].sum()
        occupancy_ratio = total_current_boxes / max_qty_per_box

        print(f"  - Tổng số hộp hiện tại: {total_current_boxes}")
        print(f"  - Sức chứa pallet tối đa (dựa trên max 'Box/Pallet'): {max_qty_per_box} hộp")
        print(f"  - Tỷ lệ lấp đầy: {total_current_boxes} / {max_qty_per_box} = {occupancy_ratio:.2%}")

        # Bước 3: Áp dụng quy tắc 90%.
        allowed_boxes = math.floor(0.9 * max_qty_per_box)
        print(f"  - Ngưỡng cho phép (<=90%): {allowed_boxes} hộp")

        if total_current_boxes > allowed_boxes:
            print(f"  -> KẾT LUẬN: VƯỢT NGƯỠNG 90%. Cần bóc tách.")
            
            boxes_to_remove = total_current_boxes - allowed_boxes
            print(f"  - Số hộp cần bóc tách chuyển đi: {boxes_to_remove} hộp.")

            # Logic bóc tách
            items_to_move = []
            sorted_items = group.sort_values(by="Q'ty (boxes)", ascending=True).to_dict('records')

            for item in sorted_items:
                if boxes_to_remove <= 0:
                    break
                
                part_no = item['Part No.']
                item_boxes = item["Q'ty (boxes)"]
                
                if item_boxes <= boxes_to_remove:
                    items_to_move.append(f"Toàn bộ Pallet con '{part_no}' ({item_boxes} hộp)")
                    boxes_to_remove -= item_boxes
                else:
                    items_to_move.append(f"{boxes_to_remove} hộp từ Pallet con '{part_no}'")
                    boxes_to_remove = 0

            print("  - Đề xuất hành động:")
            for action in items_to_move:
                print(f"    + {action}")

        else:
            print(f"  -> KẾT LUẬN: ĐẠT CHUẨN (<= 90%).")
            print(f"  - Pallet này sẽ được đưa vào hàng chờ để tìm các phần lẻ khác ghép thêm.")

    # Xóa cột tạm sau khi phân tích xong
    if '__PalletGroup' in df_container.columns:
        df_container.drop(columns=['__PalletGroup'], inplace=True)

# Giả sử bạn đã thêm hàm preprocess_oversized_pallets vào file data_processor.py
def _safe_float(value, default=0.0):
    """Chuyển đổi giá trị sang float một cách an toàn."""
    try:
        return float(value) if value not in [None, ""] else default
    except (ValueError, TypeError):
        return default

def _render_single_pallet_unit(item_content, raw_data_map, pallet_counter, pkl_data_list):
    """
    Tạo một dòng trong PKL cho một pallet đơn NGUYÊN.
    Hàm này được sao chép từ app.py để phục vụ mục đích test.
    """
    key = str(item_content['product_code']) + '||' + str(item_content['product_name'])
    raw_info = raw_data_map.get(key, {})

    qty_per_box_val = _safe_float(raw_info.get('QtyPerBox'))
    box_per_pallet_val = _safe_float(raw_info.get('BoxPerPallet'))
    w_pc_kgs = _safe_float(raw_info.get('Wpc_kgs'))

    qty_boxes = math.ceil(box_per_pallet_val * 1.0)
    qty_pcs = qty_boxes * qty_per_box_val
    nw_kgs = qty_pcs * w_pc_kgs
    gw_kgs = math.ceil(nw_kgs + (qty_boxes * 0.4) + 50)
    cbm = 1.0 * 1.15 * 1.15 * 0.8

    row = {
        'Item No.': pallet_counter['item_no'],
        'Pallet': f"No.{pallet_counter['pallet_no']:03d}",
        'Part Name': item_content['product_name'],
        'Part No.': item_content['product_code'],
        "Q'ty (boxes)": qty_boxes,
        "Q'ty (pcs)": qty_pcs,
        'W / pc (kgs)': w_pc_kgs,
        'N.W (kgs)': nw_kgs,
        'G.W (kgs)': gw_kgs,
        'MEAS. (m)': "1.15*1.15*0.8",
        'CBM': cbm,
        "Q'ty/box": qty_per_box_val,
        "Box/Pallet": box_per_pallet_val,
        "Box Spec": raw_info.get('BoxSpec', ''),
    }
    pkl_data_list.append(row)
    pallet_counter['item_no'] += 1
    pallet_counter['pallet_no'] += 1
    return qty_pcs

def _render_combined_pallet_block(item_content, raw_data_map, pallet_counter, pkl_data_list, total_block_ratio, processed_pcs_tracker, total_fractional_quantity, processed_fractional_quantity):
    """
    Tạo một khối dòng trong PKL cho một pallet gộp (lẻ).
    Hàm này được sao chép từ app.py để phục vụ mục đích test.
    """
    total_nw_group = 0
    total_boxes_group = 0
    items_calculated = []
    EPSILON = 1e-6

    for item in item_content['items']:
        key_item = str(item['product_code']) + '||' + str(item['product_name'])
        raw_info_item = raw_data_map.get(key_item, {})
        product_code = item['product_code']
        fractional_part = item['quantity']

        total_pcs_from_M = _safe_float(raw_info_item.get('TotalPcsFromM', 0))
        qty_per_box_item = _safe_float(raw_info_item.get('QtyPerBox'))
        box_per_pallet_val = _safe_float(raw_info_item.get('BoxPerPallet'))
        w_pc_kgs_item = _safe_float(raw_info_item.get('Wpc_kgs'))
        
        is_last_fraction = (processed_fractional_quantity.get(product_code, 0) + fractional_part) >= (total_fractional_quantity.get(product_code, 0) - EPSILON)

        if is_last_fraction:
            pcs_processed_so_far = processed_pcs_tracker.get(product_code, 0)
            qty_pcs_item = total_pcs_from_M - pcs_processed_so_far
            qty_pcs_item = max(0, round(qty_pcs_item))
        else:
            total_pcs_per_full_pallet = qty_per_box_item * box_per_pallet_val
            qty_pcs_item = round(total_pcs_per_full_pallet * fractional_part)

        processed_pcs_tracker[product_code] = processed_pcs_tracker.get(product_code, 0) + qty_pcs_item
        processed_fractional_quantity[product_code] = processed_fractional_quantity.get(product_code, 0) + fractional_part
        
        qty_boxes_item = math.ceil(qty_pcs_item / qty_per_box_item) if qty_per_box_item > 0 else 0
        nw_kgs_item = qty_pcs_item * w_pc_kgs_item

        items_calculated.append({
            'product_name': item['product_name'],
            'product_code': item['product_code'],
            'qty_boxes': qty_boxes_item,
            'qty_pcs': qty_pcs_item,
            'w_pc_kgs': w_pc_kgs_item,
            'nw_kgs': nw_kgs_item,
            'raw_info': raw_info_item
        })

        total_nw_group += nw_kgs_item
        total_boxes_group += qty_boxes_item

    gw_kgs_group = math.ceil(total_nw_group + (total_boxes_group * 0.4) + 50)
    cbm_group = total_block_ratio * 1.15 * 1.15 * 0.8

    is_first_item_in_group = True
    for item_data in items_calculated:
        row = {
            'Item No.': pallet_counter['item_no'] if is_first_item_in_group else '',
            'Pallet': f"No.{pallet_counter['pallet_no']:03d}" if is_first_item_in_group else '',
            'Part Name': item_data['product_name'],
            'Part No.': item_data['product_code'],
            "Q'ty (boxes)": item_data['qty_boxes'],
            "Q'ty (pcs)": item_data['qty_pcs'],
            'W / pc (kgs)': item_data['w_pc_kgs'],
            'N.W (kgs)': item_data['nw_kgs'],
            'G.W (kgs)': gw_kgs_group if is_first_item_in_group else 0,
            'MEAS. (m)': "1.15*1.15*0.8" if is_first_item_in_group else '',
            'CBM': cbm_group if is_first_item_in_group else 0,
            "Q'ty/box": item_data['raw_info'].get('QtyPerBox', ''),
            "Box/Pallet": item_data['raw_info'].get('BoxPerPallet', ''),
            "Box Spec": item_data['raw_info'].get('BoxSpec', ''),
        }
        pkl_data_list.append(row)
        is_first_item_in_group = False
    
    pallet_counter['item_no'] += 1
    pallet_counter['pallet_no'] += 1


def run_packing_list_test(final_containers_objects, file_path, sheet_name):
    """
    Hàm test chính để kiểm tra logic tạo Packing List.
    Hàm này mô phỏng lại logic từ endpoint /api/generate_packing_list,
    tính toán cột tỷ lệ mới và hiển thị kết quả.
    """
    print("\n\n" + "#"*80)
    print("BẮT ĐẦU TEST TẠO PACKING LIST")
    print("#"*80)

    raw_data_map, error = load_and_map_raw_data_for_pkl(file_path, sheet_name)
    if error:
        print(f"LỖI khi tải dữ liệu thô cho PKL: {error}")
        return

    optimized_results_dict = generate_response_data(final_containers_objects)['results']
    if not optimized_results_dict:
        print("Không có container nào để tạo packing list.")
        return

    # --- Bắt đầu logic mô phỏng từ endpoint ---
    processed_pcs_tracker = {}
    pallet_counter = {'item_no': 1, 'pallet_no': 1}
    optimized_results_dict.sort(key=lambda x: int(re.search(r'\d+', x['id']).group()))

    for i, container_data in enumerate(optimized_results_dict, 1):
        container_data['id'] = f"Cont_{i}"

    container_rows = {container['id']: [] for container in optimized_results_dict}
    unprocessed_fractions_all = {container['id']: [] for container in optimized_results_dict}

    total_fractional_quantity = {}
    for container_data in optimized_results_dict:
        for content_block in container_data.get('contents', []):
            items = content_block.get('items', []) if content_block.get('type') == 'CombinedPallet' else [content_block]
            for item in items:
                item_total_pallet = _safe_float(item.get('quantity'))
                fractional_part = item_total_pallet - math.floor(item_total_pallet)
                if fractional_part > 1e-6:
                    product_code = item['product_code']
                    total_fractional_quantity[product_code] = total_fractional_quantity.get(product_code, 0) + fractional_part

    processed_fractional_quantity = {}

    # Lượt 1: Xử lý pallet nguyên
    for container_data in optimized_results_dict:
        container_id = container_data['id']
        for content_block in container_data.get('contents', []):
            items_to_process = content_block.get('items', []) if content_block.get('type') == 'CombinedPallet' else [content_block]
            for item in items_to_process:
                item_total_pallet = _safe_float(item.get('quantity'))
                integer_part = math.floor(item_total_pallet)
                fractional_part = item_total_pallet - integer_part

                if integer_part > 0:
                    pseudo_single = {'product_code': item['product_code'], 'product_name': item['product_name']}
                    for _ in range(int(integer_part)):
                        pcs = _render_single_pallet_unit(pseudo_single, raw_data_map, pallet_counter, container_rows[container_id])
                        processed_pcs_tracker[item['product_code']] = processed_pcs_tracker.get(item['product_code'], 0) + pcs
                
                if fractional_part > 1e-6:
                    unprocessed_fractions_all[container_id].append({
                        "product_code": item['product_code'], "product_name": item['product_name'],
                        "company": item.get('company'), "quantity": fractional_part
                    })

    # Lượt 2: Xử lý pallet lẻ
    for container_id, fractions in unprocessed_fractions_all.items():
        if not fractions: continue
        fractions.sort(key=lambda x: x['quantity'], reverse=True)
        while fractions:
            current_group = [fractions.pop(0)]
            current_total_ratio = current_group[0]['quantity']
            i = 0
            while i < len(fractions):
                if current_total_ratio + fractions[i]['quantity'] <= 1.0 + 1e-6:
                    item_to_add = fractions.pop(i)
                    current_total_ratio += item_to_add['quantity']
                    current_group.append(item_to_add)
                else: i += 1
            
            pseudo_combined = {'type': 'CombinedPallet', 'items': current_group}
            _render_combined_pallet_block(
                pseudo_combined, raw_data_map, pallet_counter, container_rows[container_id], 
                current_total_ratio, processed_pcs_tracker, total_fractional_quantity, processed_fractional_quantity
            )

    # --- Bước 3: Phân tích, thêm cột mới và hiển thị kết quả ---
    print("\n[TEST PKL] --- KẾT QUẢ PACKING LIST CHI TIẾT ---")
    for container_id, rows in container_rows.items():
        if not rows:
            print(f"\n--- CONTAINER ID: {container_id} (Không có dữ liệu PKL) ---")
            continue

        print(f"\n" + "="*25 + f" CONTAINER ID: {container_id} " + "="*25)
        df_pkl = pd.DataFrame(rows)

        # Thêm cột "Total Pallet Ratio"
        df_pkl["Q'ty (boxes)"] = pd.to_numeric(df_pkl["Q'ty (boxes)"], errors='coerce').fillna(0)
        df_pkl["Box/Pallet"] = pd.to_numeric(df_pkl["Box/Pallet"], errors='coerce').fillna(0)

        def calculate_ratio(row):
            return (row["Q'ty (boxes)"] / row["Box/Pallet"]) if row["Box/Pallet"] > 0 else 0
        
        df_pkl['__ItemRatio'] = df_pkl.apply(calculate_ratio, axis=1)

        # Xác định nhóm pallet để tính tổng
        df_pkl['__PalletGroup'] = df_pkl['Pallet'].replace('', pd.NA).ffill()
        group_ratios = df_pkl.groupby('__PalletGroup')['__ItemRatio'].transform('sum')
        
        # Tạo cột hiển thị tổng tỷ lệ
        df_pkl['Total Pallet Ratio'] = group_ratios.map(lambda x: f"{x:.2%}")
        df_pkl.loc[df_pkl['__PalletGroup'].duplicated(), 'Total Pallet Ratio'] = ''
        
        # Gán giá trị rỗng cho các dòng không có Q'ty (boxes)
        df_pkl.loc[df_pkl["Q'ty (boxes)"] == 0, 'Total Pallet Ratio'] = ''
        
        # Xóa các cột tạm
        df_pkl.drop(columns=['__ItemRatio', '__PalletGroup'], inplace=True)

        # Hiển thị toàn bộ các cột của Packing List
        pd.set_option('display.max_columns', None)
        pd.set_option('display.width', 1000)
        print(df_pkl)
        print("="*70)
        analyze_combined_pallets_for_rebalancing(df_pkl.copy())
                # ======================================================================
        #  GIAI ĐOẠN MỚI V2: TẠO PACKING LIST HOÀN CHỈNH SAU KHI CÂN BẰNG
        # ======================================================================
        
        # Bước 1 (V2): Phân loại pallet thành nhóm 'giữ lại' và nhóm 'cần cân bằng'
        kept_pallets, waiting_queue_items = collect_items_for_rebalancing_v2(df_pkl.copy())

        # Bước 2 (V2): Xử lý hàng đợi (giữ nguyên logic)
        rebalanced_pallets = process_waiting_queue(waiting_queue_items)

        # Bước 3 (V2): Tạo và hiển thị Packing List HOÀN CHỈNH cuối cùng
        # bằng cách gộp nhóm 'giữ lại' và nhóm 'đã cân bằng'
        generate_final_complete_pkl(kept_pallets, rebalanced_pallets)
# --- HÀM MAIN ĐỂ CHẠY VÀ HIỂN THỊ KẾT QUẢ ---
if __name__ == "__main__":
    # --- BƯỚC 1: Cấu hình ---
    file_path = "C:\\Users\\emily\\Downloads\\Chia-cont-2025-filled-data (1).xlsx"
    sheet_name = "8 Apr"
    COMPANY_1 = "1"
    COMPANY_2 = "2"

    # --- BƯỚC 2: Tải và chuẩn bị dữ liệu ---
    print(f"Bắt đầu phân tích sheet: '{sheet_name}'...")
    all_pallets, error_message = load_and_prepare_pallets(file_path, sheet_name)

    if error_message:
        print(f"\nĐã xảy ra lỗi: {error_message}")
    else:
        print(f"Đã tải thành công {len(all_pallets)} pallet từ file.")
        
        # *** KHỞI TẠO BỘ ĐẾM CONTAINER TOÀN CỤC NGAY TỪ ĐẦU ***
        global_container_counter = {'count': 1}

        ##################### TEST GIAI ĐOẠN TIỀN XỬ LÝ: PALLET QUÁ KHỔ #####################
        print("\n" + "="*80)
        print("KẾT QUẢ GIAI ĐOẠN TIỀN XỬ LÝ: CHIA NHỎ PALLET QUÁ KHỔ")
        print("="*80)

        # Gọi hàm xử lý pallet quá khổ
        pre_packed_containers, pallets_to_process = preprocess_oversized_pallets(
            all_pallets, global_container_counter
        )

        if not pre_packed_containers:
            print("\n-> Không phát hiện pallet nào quá khổ.")
        else:
            print(f"\n1. CÁC CONTAINER ĐƯỢC ĐÓNG GÓI SẴN ({len(pre_packed_containers)} container):")
            for container in pre_packed_containers:
                print(f"  - CONTAINER ID: {container.id} (Công ty: {container.main_company})")
                print(f"    - Tổng SL: {container.total_quantity:.2f} / {MAX_PALLETS}, Tổng KL: {container.total_weight:.2f} / {MAX_WEIGHT}")
                for pallet in container.pallets:
                    print(f"    └─ Pallet bên trong: {pallet}")

        print(f"\n2. TỔNG SỐ PALLET CẦN XỬ LÝ TIẾP: {len(pallets_to_process)}")
        print("-" * 80)
        
        #####################################################################################
        
        # --- BƯỚC 3: Tách pallet theo công ty ---
        # *** LƯU Ý: Sử dụng `pallets_to_process` từ bước trên ***
        pallets_co1, pallets_co2 = separate_pallets_by_company(
            pallets_to_process, COMPANY_1, COMPANY_2
        )
        
        ###########################    TEST GIAI ĐOẠN 0 VÀ IN KẾT QUẢ ########################
        print("\n" + "="*80)
        print("KẾT QUẢ GIAI ĐOẠN 0: TIỀN XỬ LÝ & PHÂN LOẠI PALLET")
        print("="*80)

        # Xử lý và hiển thị cho Công ty 1
        print(f"\n--- Phân loại cho Công ty: '{COMPANY_1}' ({len(pallets_co1)} pallet thô) ---")
        int_pallets_1, combined_pallets_1, single_float_1 = preprocess_and_classify_pallets(pallets_co1)
        # (Phần in kết quả Giai đoạn 0 giữ nguyên)
        print(f"\n1. PALLET SỐ NGUYÊN ({len(int_pallets_1)} pallet):")
        if not int_pallets_1: print("-> Không có.")
        for p in int_pallets_1: print(f"  - {p}")
        print(f"\n2. PALLET ĐÃ GỘP ({len(combined_pallets_1)} pallet):")
        if not combined_pallets_1: print("-> Không có.")
        for p in combined_pallets_1:
            print(f"  - {p}")
            for p_orig in p.original_pallets: print(f"    └─ (gốc) {p_orig}")
        print(f"\n3. PALLET LẺ (KHÔNG GỘP ĐƯỢC) ({len(single_float_1)} pallet):")
        if not single_float_1: print("-> Không có.")
        for p in single_float_1: print(f"  - {p}")
        
        print("\n" + "-"*80)

        # Xử lý và hiển thị cho Công ty 2
        print(f"\n--- Phân loại cho Công ty: '{COMPANY_2}' ({len(pallets_co2)} pallet thô) ---")
        int_pallets_2, combined_pallets_2, single_float_2 = preprocess_and_classify_pallets(pallets_co2)
        # (Phần in kết quả Giai đoạn 0 giữ nguyên)
        print(f"\n1. PALLET SỐ NGUYÊN ({len(int_pallets_2)} pallet):")
        if not int_pallets_2: print("-> Không có.")
        for p in int_pallets_2: print(f"  - {p}")
        print(f"\n2. PALLET ĐÃ GỘP ({len(combined_pallets_2)} pallet):")
        if not combined_pallets_2: print("-> Không có.")
        for p in combined_pallets_2:
            print(f"  - {p}")
            for p_orig in p.original_pallets: print(f"    └─ (gốc) {p_orig}")
        print(f"\n3. PALLET LẺ (KHÔNG GỘP ĐƯỢC) ({len(single_float_2)} pallet):")
        if not single_float_2: print("-> Không có.")
        for p in single_float_2: print(f"  - {p}")
        
        print("\n" + "="*80)

        #####################    TEST GIAI ĐOẠN 1    ######################################
        # ... (Phần còn lại của file giữ nguyên không đổi) ...
        print("\n" + "="*80)
        print("KẾT QUẢ GIAI ĐOẠN 1: XẾP HÀNG ƯU TIÊN THEO LỚP")
        print("="*80)
        
        # Chạy Giai đoạn 1 cho Công ty 1
        print(f"\n>>> Bắt đầu Giai đoạn 1 cho {COMPANY_1}...")
        initial_containers_c1 = layered_priority_packing(int_pallets_1, combined_pallets_1, single_float_1, COMPANY_1, global_container_counter)

        # Chạy Giai đoạn 1 cho Công ty 2
        print(f"\n>>> Bắt đầu Giai đoạn 1 cho {COMPANY_2}...")
        initial_containers_c2 = layered_priority_packing(int_pallets_2, combined_pallets_2, single_float_2, COMPANY_2, global_container_counter)
        print("Hoàn thành Giai đoạn 1. Các container đã được xếp sơ bộ.")

        #####################         TEST GIAI ĐOẠN 2         #########################
        print("\n" + "="*80)
        print("BẮT ĐẦU GIAI ĐOẠN 2: TÁI CẤU TRÚC & HỢP NHẤT NỘI BỘ")
        print("="*80)
        
        print(f"\n>>> Đang chạy tối ưu hóa cho Công ty: '{COMPANY_1}'...")
        final_containers_c1, pallets_chuyen_di_c1 = defragment_and_consolidate(initial_containers_c1)
        print(f"-> Công ty {COMPANY_1}: {len(final_containers_c1)} container hiệu quả, {len(pallets_chuyen_di_c1)} pallet chờ vận chuyển chéo.")

        print(f"\n>>> Đang chạy tối ưu hóa cho Công ty: '{COMPANY_2}'...")
        final_containers_c2, pallets_chuyen_di_c2 = defragment_and_consolidate(initial_containers_c2)
        print(f"-> Công ty {COMPANY_2}: {len(final_containers_c2)} container hiệu quả, {len(pallets_chuyen_di_c2)} pallet chờ vận chuyển chéo.")

        print("\n" + "="*80)
        print("KẾT THÚC GIAI ĐOẠN 2.")
        print("="*80)

        #####################         TEST GIAI ĐOẠN 3         #########################
        print("\n" + "="*80)
        print("BẮT ĐẦU GIAI ĐOẠN 3: VẬN CHUYỂN CHÉO & HOÀN THIỆN")
        print("="*80)
        
        final_optimized_containers = phase_3_cross_shipping_and_finalization(
            final_containers_c1, pallets_chuyen_di_c1,
            final_containers_c2, pallets_chuyen_di_c2,
            global_container_counter
        )
        
        # *** THAY ĐỔI CUỐI CÙNG: GỘP TẤT CẢ CÁC CONTAINER LẠI ***
        all_final_containers = pre_packed_containers + final_optimized_containers
        
        # In kết quả cuối cùng
        print("\n\n" + "#"*80)
        print("KẾT QUẢ XẾP HÀNG CUỐI CÙNG")
        print("#"*80)
        
        if not all_final_containers:
            print("\nKhông có container nào được xếp.")
        else:
            sorted_final_results = sorted(all_final_containers, key=lambda c: int(c.id.split('_')[-1]))
            
            print(f"\nTổng số container cuối cùng: {len(sorted_final_results)}")
            
            for container in sorted_final_results:
                print("\n" + "-"*60)
                print(f"CONTAINER ID: {container.id}")
                print(f"  - Công ty chính:     {container.main_company}")
                print(f"  - Tổng số lượng:     {container.total_quantity:.2f} / {MAX_PALLETS}")
                print(f"  - Tổng trọng lượng:   {container.total_weight:.2f} / {MAX_WEIGHT}")
                print(f"  - Tỷ lệ lấp đầy (SL): {container.total_quantity / MAX_PALLETS:.2%}")
                print("  - Danh sách Pallet bên trong:")
                
                if not container.pallets:
                    print("    (Container rỗng)")
                else:
                    sorted_pallets = sorted(container.pallets, key=lambda p: p.id)
                    for pallet in sorted_pallets:
                        print(f"    + {pallet}")
        print("\n\n" + "#"*80)
        print("PHÂN TÍCH CHI TIẾT PALLET GỘP BỊ TÁCH (SPLIT COMBINED PALLETS)")
        print("#"*80)

        found_split_combined = False
        # Duyệt qua tất cả các container trong kết quả cuối cùng
        for container in sorted(all_final_containers, key=lambda c: int(c.id.split('_')[-1])):
            # Duyệt qua từng pallet trong container
            for pallet in container.pallets:
                # Kiểm tra xem pallet có phải là pallet gộp (is_combined) VÀ đã bị tách (is_split) không
                if pallet.is_combined and pallet.is_split:
                    found_split_combined = True
                    print("\n" + "-"*60)
                    print(f"Phát hiện Pallet Gộp Bị Tách trong CONTAINER ID: {container.id}")
                    
                    # In thông tin của chính phần pallet bị tách này
                    print(f"  -> PHẦN PALLET HIỆN TẠI: {pallet}")
                    
                    # In danh sách các pallet con (original pallets) mà nó chứa
                    print("     Thành phần bên trong phần này:")
                    if not pallet.original_pallets:
                        print("       (Không có thông tin thành phần)")
                    else:
                        # GỌI HÀM HỢP NHẤT TRƯỚC KHI IN
                        consolidated_originals = consolidate_sub_pallets(pallet.original_pallets)
                        for original in sorted(consolidated_originals, key=lambda p: p.id):
                            print(f"       - {original}")
        
        if not found_split_combined:
            print("\nKhông tìm thấy pallet gộp nào bị tách trong kết quả cuối cùng.")

        print("\n" + "#"*80)
        print("PHÂN TÍCH HOÀN TẤT.")
        print("\n" + "#"*80)
        print("PHÂN TÍCH HOÀN TẤT.")
        if all_final_containers:
           run_packing_list_test(all_final_containers, file_path, sheet_name)
        
        