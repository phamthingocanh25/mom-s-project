# backend/app.py
import os
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import werkzeug.utils
import gc
import io
import pandas as pd
import numpy as np
from openpyxl import Workbook
from openpyxl.styles import Font, Border, Side, Alignment,PatternFill
from openpyxl.utils import get_column_letter, rows_from_range, cols_from_range
import math
from copy import deepcopy
import datetime


# --- IMPORT CÁC MODULE XỬ LÝ ---
from data_processor import (
    load_and_prepare_pallets,
    preprocess_oversized_pallets, 
    separate_pallets_by_company,
    preprocess_and_classify_pallets,
    layered_priority_packing,
    defragment_and_consolidate,
    phase_3_cross_shipping_and_finalization,
    generate_response_data,
    load_and_map_raw_data_for_pkl
)

# --- KHỞI TẠO ỨNG DỤNG FLASK ---
app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024
CORS(app, resources={r"/api/*": {"origins": "https://phamthingocanh25.github.io"}})
UPLOAD_FOLDER = 'uploads'
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
############### Packing list #########
def _safe_float(value, default=0.0):
    """Chuyển đổi giá trị sang float một cách an toàn."""
    try:
        return float(value) if value not in [None, ""] else default
    except (ValueError, TypeError):
        return default

def _render_single_pallet_unit(item_content, raw_data_map, pallet_counter, pkl_data_list):
    """
    Tạo một dòng trong PKL cho một pallet đơn NGUYÊN (luôn có tỉ lệ là 1.0).
    Hàm này được gọi cho mỗi pallet trong phần nguyên của 'SinglePallet'.
    """
    key = str(item_content['product_code']) + '||' + str(item_content['product_name'])
    raw_info = raw_data_map.get(key, {})

    qty_per_box_val = _safe_float(raw_info.get('QtyPerBox'))
    box_per_pallet_val = _safe_float(raw_info.get('BoxPerPallet')) # Chính là cột H
    weight_per_pc_raw_val = _safe_float(raw_info.get('WeightPerPc_Raw'))

    # Theo yêu cầu: quantity (boxes) = cột H x 1
    qty_boxes = box_per_pallet_val * 1.0
    qty_pcs = qty_boxes * qty_per_box_val
    w_pc_kgs = (weight_per_pc_raw_val / qty_per_box_val) if qty_per_box_val > 0 else 0
    nw_kgs = qty_pcs * w_pc_kgs
    # G.W và CBM được tính cho 1 pallet đầy đủ
    gw_kgs = nw_kgs + (qty_boxes * 0.4) + 50
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
    # Tăng số thứ tự cho mỗi dòng pallet được tạo
    pallet_counter['item_no'] += 1
    pallet_counter['pallet_no'] += 1

def _render_combined_pallet_block(item_content, raw_data_map, pallet_counter, pkl_data_list, total_block_ratio): # <<-- CHANGED: Added total_block_ratio
    """
    Tạo một khối dòng trong PKL cho một pallet gộp (đủ hoặc lẻ).
    *** ĐÃ ĐƯỢC CẬP NHẬT ĐỂ CHUẨN HÓA TỈ LỆ VÀ THÊM TỔNG TỈ LỆ ***
    """
    total_nw_group = 0
    total_boxes_group = 0
    items_calculated = []

    total_original_proportion = sum(_safe_float(item.get('quantity', 0)) for item in item_content['items'])
    if total_original_proportion == 0:
        total_original_proportion = 1.0

    # BƯỚC 1: TÍNH TOÁN THÔNG SỐ CHO TỪNG SẢN PHẨM THÀNH PHẦN
    for item in item_content['items']:
        key_item = str(item['product_code']) + '||' + str(item['product_name'])
        raw_info_item = raw_data_map.get(key_item, {})
        
        original_item_proportion = _safe_float(item.get('quantity'))
        normalized_proportion = original_item_proportion / total_original_proportion
        # Sử dụng total_block_ratio thay vì block_quantity để tính toán
        individual_pallet_ratio = normalized_proportion * total_block_ratio

        qty_per_box_item = _safe_float(raw_info_item.get('QtyPerBox'))
        box_per_pallet_item = _safe_float(raw_info_item.get('BoxPerPallet'))
        weight_per_pc_raw_item = _safe_float(raw_info_item.get('WeightPerPc_Raw'))

        qty_boxes_item = individual_pallet_ratio * box_per_pallet_item
        qty_pcs_item = qty_boxes_item * qty_per_box_item
        w_pc_kgs_item = (weight_per_pc_raw_item / qty_per_box_item) if qty_per_box_item > 0 else 0
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

    # BƯỚC 2: TÍNH TOÁN TỔNG CHO CẢ KHỐI
    gw_kgs_group = total_nw_group + (total_boxes_group * 0.4) + 50
    cbm_group = total_block_ratio * 1.15 * 1.15 * 0.8

    # BƯỚC 3: GHI DỮ LIỆU VÀO DANH SÁCH
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

def _generate_dataframe_for_container(container_data, raw_data_map, pallet_counter):
    """
    Tạo DataFrame cho Packing List của một container duy nhất.
    PHIÊN BẢN 3 (Theo phản hồi mới nhất):
    1. Duyệt qua TỪNG DÒNG MÃ HÀNG trong kết quả tối ưu hóa.
    2. Tách phần nguyên/lẻ của SỐ LƯỢNG PALLET CỦA TỪNG MÃ HÀNG ĐÓ.
    3. Phần nguyên tạo thành các pallet ĐƠN, NGUYÊN (tỉ lệ 1.0).
    4. Tất cả các phần lẻ được gom vào "rổ chung" và xử lý bằng FFD.
    """
    pkl_data_list = []
    unprocessed_fractions = [] # <<-- "Rổ chung" chứa tất cả các mã hàng lẻ
    EPSILON = 1e-6 # Hằng số nhỏ để so sánh số thực

    # --- BƯỚC 1: TÁCH PHẦN NGUYÊN & LẺ TỪ TỪNG DÒNG SẢN PHẨM ---
    for content_block in container_data.get('contents', []):
        block_type = content_block.get('type')

        items_to_process = []
        # Thống nhất logic xử lý: coi Pallet Đơn như một Pallet Gộp có 1 item
        if block_type == 'SinglePallet':
            items_to_process.append({
                "product_code": content_block['product_code'],
                "product_name": content_block['product_name'],
                "company": content_block['company'],
                "quantity": content_block.get('quantity', 0)
            })
        else: # CombinedPallet
            items_to_process = content_block.get('items', [])

        # Xử lý từng dòng sản phẩm (item) bên trong khối
        for item in items_to_process:
            # Lấy số pallet của chính item này (ví dụ: 2.62)
            item_total_pallet = _safe_float(item.get('quantity'))
            if item_total_pallet < EPSILON:
                continue
            
            integer_part = math.floor(item_total_pallet)
            fractional_part = item_total_pallet - integer_part

            # 1a. Xử lý phần NGUYÊN: Tạo ra N pallet ĐƠN, NGUYÊN
            if integer_part > 0:
                # Tạo một "khối đơn" ảo chỉ chứa thông tin của item này
                pseudo_single_pallet_block = {
                    'type': 'SinglePallet',
                    'product_code': item['product_code'],
                    'product_name': item['product_name'],
                    'company': item['company']
                    # Các thông tin khác như weight, cbm sẽ được tra cứu trong hàm render
                }
                # Tạo ra N pallet NGUYÊN (N dòng trên PKL), mỗi pallet là 1 pallet ĐƠN
                for _ in range(int(integer_part)):
                    _render_single_pallet_unit(pseudo_single_pallet_block, raw_data_map, pallet_counter, pkl_data_list)
            
            # 1b. Xử lý phần LẺ: Thêm vào "rổ chung" để gom sau
            if fractional_part > EPSILON:
                unprocessed_fractions.append({
                    "product_code": item['product_code'],
                    "product_name": item['product_name'],
                    "company": item['company'],
                    "quantity": fractional_part # Tỉ lệ pallet lẻ (ví dụ: 0.62)
                })

    # --- BƯỚC 2: GOM CÁC MÃ HÀNG LẺ TRONG "RỔ CHUNG" BẰNG THUẬT TOÁN FFD (Giữ nguyên) ---
    # Sắp xếp các mã hàng lẻ theo tỉ lệ giảm dần (First Fit Decreasing)
    unprocessed_fractions.sort(key=lambda x: x['quantity'], reverse=True)
    
    while unprocessed_fractions:
        # Bắt đầu một pallet gộp mới với mã hàng lẻ lớn nhất
        current_group = [unprocessed_fractions.pop(0)]
        current_total_ratio = current_group[0]['quantity']
        
        # Tham lam tìm các mã hàng khác để lấp đầy pallet (không vượt quá 1.0)
        i = 0
        while i < len(unprocessed_fractions):
            if current_total_ratio + unprocessed_fractions[i]['quantity'] <= 1.0 + EPSILON:
                item_to_add = unprocessed_fractions.pop(i)
                current_total_ratio += item_to_add['quantity']
                current_group.append(item_to_add)
            else:
                i += 1
        
        # Tạo một pallet gộp "ảo" từ nhóm vừa tạo
        pseudo_combined_pallet = {'type': 'CombinedPallet', 'items': current_group}
        
        # Render khối pallet gộp "ảo" này ra PKL
        _render_combined_pallet_block(
            pseudo_combined_pallet, 
            raw_data_map, 
            pallet_counter, 
            pkl_data_list, 
            total_block_ratio=current_total_ratio
        )

    if not pkl_data_list:
        return None
    return pd.DataFrame(pkl_data_list)
def create_packing_list_data(final_optimized_containers_dicts, raw_data_map):
    """
    Điều phối việc tạo dữ liệu Packing List từ kết quả tối ưu hóa cuối cùng.
    Hàm này chấp nhận một danh sách các DICTIONARY, không phải object.
    """
    print("[BACKEND] Bắt đầu quy trình tạo dữ liệu Packing List (logic FFD)...")
    processed_dfs_for_pkl = {}
    
    # Khởi tạo bộ đếm pallet và item, đảm bảo tính liên tục qua các container
    pallet_counter = {'item_no': 1, 'pallet_no': 1}

    # Sắp xếp các container theo ID để đảm bảo thứ tự.
    # Sử dụng key 'id' thay vì 'container_id' để nhất quán.
    final_optimized_containers_dicts.sort(key=lambda x: int(x['id'].split('_')[-1]))

    for container_data in final_optimized_containers_dicts:
        container_id = container_data['id'] # Sử dụng key 'id'
        print(f"  - Đang xử lý Container ID: {container_id}")

        df_for_pkl = _generate_dataframe_for_container(
            container_data, 
            raw_data_map, 
            pallet_counter
        )
        
        if df_for_pkl is not None and not df_for_pkl.empty:
            processed_dfs_for_pkl[container_id] = df_for_pkl
        
    print("[BACKEND] Đã hoàn tất tạo dữ liệu Packing List.")
    return processed_dfs_for_pkl


def write_packing_list_to_sheet(ws, data_df, container_id_num,cumulative_pallet_count,cumulative_pcs, cumulative_nw, cumulative_gw):
    """
    Ghi dữ liệu Packing List đã được định dạng vào một worksheet của openpyxl.
    Hàm này được viết lại để khớp với yêu cầu chi tiết về cột và định dạng.
    """
    # --- 1. ĐỊNH NGHĨA CÁC STYLE SỬ DỤNG CHUNG ---
    font_main_title = Font(name='Arial', size=48, bold=True)
    font_box_header = Font(name='Arial', size=11, bold=True, underline='single')
    font_content = Font(name='Arial', size=11)
    font_content_bold = Font(name='Arial', size=11, bold=True)
    font_table_header = Font(name='Arial', size=10, bold=True)
    font_table_content = Font(name='Arial', size=10)
    thin_side = Side(style='thin')
    border_top_only = Border(top=thin_side)
    border_top_only = Border(top=Side(style='thin'))
    font_bold = Font(name='Arial', size=12, bold=True)
    
    align_center = Alignment(horizontal='center', vertical='center', wrap_text=True)
    align_top_left = Alignment(horizontal='left', vertical='top', wrap_text=True)
    align_right_center = Alignment(horizontal='right', vertical='center', wrap_text=True)
    align_top_right_bold = Alignment(horizontal='right', vertical='center', wrap_text=False)
    font_table_header_bold = Font(name='Arial', size=10, bold=True)
    align_bottom_center = Alignment(horizontal='center', vertical='bottom')

    thin_border = Border(
        left=Side(style='thin'), 
        right=Side(style='thin'), 
        top=Side(style='thin'), 
        bottom=Side(style='thin')
    )
    
    def apply_border_to_range(cell_range, border_style):
        rows = ws[cell_range]
        for row in rows:
            for cell in row:
                cell.border = border_style

    # --- 2. THIẾT LẬP CƠ BẢN CHO TRANG TÍNH ---
    ws.sheet_view.showGridLines = False
    
    column_widths = {
         'D': 10, 'E': 10, 'F': 35, 'G': 35,
        'H': 12, 'I': 12, 'J': 12, 'K': 12, 'L': 12, 'M': 18, 'N': 12, 'O': 12, 'P': 12, 'Q': 12, 'R':18
    }
    for col, width in column_widths.items():
        ws.column_dimensions[col].width = width

    # --- 3. TẠO TIÊU ĐỀ CHÍNH "PACKING LIST" ---
    ws.merge_cells('D1:P1')
    title_cell = ws['D1']
    title_cell.value = "PACKING LIST"
    title_cell.font = font_main_title
    title_cell.alignment = align_center
    ws.row_dimensions[1].height = 65

    # --- 4. TẠO CÁC Ô THÔNG TIN (SELLER, BUYER, INVOICE, FROM/TO) ---
    ws.merge_cells('D2:H2')
    ws.merge_cells('D3:H10')
    apply_border_to_range('D2:H10', thin_border)
    seller_header_cell = ws['D2']
    seller_header_cell.value = "SELLER"
    seller_header_cell.font = font_box_header
    seller_header_cell.alignment = Alignment(horizontal='left', vertical='top')
    seller_content_cell = ws['D3']
    seller_content = (
        "MINH QUANG IDS TRADING AND INDUSTRIES JOINT STOCK COMPANY\n"
        "Add: Plot CN 4 , Yen My Industrial zone, \n"
        "Tan Lap Commune ,Yen My District, Hung Yen Province, Vietnam\n"
        "Tel: (+84) 42 211 8360\n"
        "Fax: (+84) 43 965 2536"
    )
    seller_content_cell.value = seller_content
    seller_content_cell.font = font_content
    seller_content_cell.alignment = align_top_left

    ws.merge_cells('D11:H11')
    ws.merge_cells('D12:H18')
    apply_border_to_range('D11:H18', thin_border)
    buyer_header_cell = ws['D11']
    buyer_header_cell.value = "BUYER"
    buyer_header_cell.font = font_box_header
    buyer_header_cell.alignment = Alignment(horizontal='left', vertical='top')
    buyer_content_cell = ws['D12']
    buyer_content = ("  \n" " \n" " \n")
    buyer_content_cell.value = buyer_content
    buyer_content_cell.font = font_content
    buyer_content_cell.alignment = align_top_left
    
    ws.merge_cells('I2:P2')
    ws.merge_cells('I3:P10')
    apply_border_to_range('I2:P10', thin_border)
    invoice_header_cell = ws['I2']
    invoice_header_cell.value = "INVOICE NO. & DATE:"
    invoice_header_cell.font = font_box_header
    invoice_header_cell.alignment = Alignment(horizontal='left', vertical='top')
    invoice_content_cell = ws['I3']
    invoice_content = ("  \n" " \n" " \n")
    invoice_content_cell.value = invoice_content
    invoice_content_cell.font = font_content
    invoice_content_cell.alignment = align_top_left

    apply_border_to_range('I11:P18', thin_border)
    ws.merge_cells('I11:K11')
    ws.merge_cells('L11:P11')
    ws.merge_cells('I12:K18')
    ws.merge_cells('L12:P18')
    ws['I11'].value = "FROM:"
    ws['I11'].font = font_box_header
    ws['I11'].alignment = align_center
    ws['L11'].value = "TO:"
    ws['L11'].font = font_box_header
    ws['L11'].alignment = align_center
    from_cell = ws['I12']
    from_cell.value = "Haiphong, Vietnam"
    from_cell.font = font_content
    from_cell.alignment = align_center

    to_cell = ws['L12']
    to_cell.value = " "
    to_cell.font = font_content
    to_cell.alignment = align_center


    # --- 5. TẠO BẢNG DỮ LIỆU SẢN PHẨM ---
    start_row = 20
    start_col = 4 # Cột D

    headers = [
        "Item No.", "Pallet", "Part Name", "Part No.", "Q'ty\n(boxes)", "Q'ty\n(pcs)",
        "W / pc\n(kgs)", "N.W\n(kgs)", "G.W\n(kgs)", "MEAS.\n(m)", "Q'ty/box",
        "Box/Pallet", "Box Spec"
    ]
    end_col = start_col + len(headers) - 1
    for i, header in enumerate(headers, start=start_col):
        cell = ws.cell(row=start_row, column=i, value=header)
        cell.font = font_table_header
        cell.alignment = align_center
        cell.border = thin_border
        cell.fill = PatternFill(start_color="D9D9D9", end_color="D9D9D9", fill_type="solid")

    current_row = start_row + 1
    
    numeric_cols = ["Q'ty (boxes)", "Q'ty (pcs)", "W / pc (kgs)", "N.W (kgs)", "G.W (kgs)", "CBM", "Pallet Ratio"]
    for col in numeric_cols:
        if col in data_df.columns:
            data_df[col] = pd.to_numeric(data_df[col], errors='coerce').fillna(0)
        else:
            data_df[col] = 0

    for _, row_data in data_df.iterrows():
        # <<-- NEW: Xử lý giá trị cho cột mới trước khi ghi
        total_pallet_ratio_val = row_data.get('Total Pallet Ratio')
        if pd.isna(total_pallet_ratio_val):
            total_pallet_ratio_val = '' # Hiển thị ô trống nếu không có giá trị
        row_values = [
            row_data.get('Item No.', ''), row_data.get('Pallet', ''),
            row_data.get('Part Name', ''), row_data.get('Part No.', ''),
            row_data.get("Q'ty (boxes)", 0), row_data.get("Q'ty (pcs)", 0),
            row_data.get('W / pc (kgs)', 0), row_data.get('N.W (kgs)', 0),
            row_data.get('G.W (kgs)', 0), row_data.get('MEAS. (m)', ''),
            row_data.get("Q'ty/box", ''), row_data.get("Box/Pallet", ''),
            row_data.get('Box Spec', '')
        ]
        
        for i, value in enumerate(row_values, start=start_col):
            cell = ws.cell(row=current_row, column=i, value=value)
            cell.font = font_table_content
            cell.border = thin_border
            
            col_letter = get_column_letter(i)
            if col_letter in ['H', 'I']:
                cell.number_format = '#,##0'
                cell.alignment = align_right_center
            elif col_letter == 'J':
                cell.number_format = '#,##0.0000'
                cell.alignment = align_right_center
            elif col_letter in ['K', 'L']:
                cell.number_format = '#,##0.00'
                cell.alignment = align_right_center
            else:
                cell.alignment = align_center
        current_row += 1
    
    # --- 6. DÒNG TỔNG KẾT (TOTAL) ---
    total_row_num = current_row
    for col_idx in range(start_col, end_col + 1):
        ws.cell(row=total_row_num, column=col_idx).border = thin_border

    total_qty_boxes = data_df["Q'ty (boxes)"].sum()
    total_qty_pcs = data_df["Q'ty (pcs)"].sum()
    total_nw = data_df['N.W (kgs)'].sum()
    total_gw = data_df['G.W (kgs)'].sum()
    
    total_label_cell = ws.cell(row=total_row_num, column=start_col, value=f'TOTAL CONTAINER {container_id_num}')
    ws.merge_cells(start_row=total_row_num, start_column=start_col, end_row=total_row_num, end_column=start_col + 3)
    total_label_cell.font = font_bold
    total_label_cell.alignment = align_center

    totals_data = {
        "Q'ty\n(boxes)": {'value': total_qty_boxes, 'format': '#,##0'},
        "Q'ty\n(pcs)": {'value': total_qty_pcs, 'format': '#,##0'},
        "N.W\n(kgs)": {'value': total_nw, 'format': '#,##0.00'},
        "G.W\n(kgs)": {'value': total_gw, 'format': '#,##0.00'}
    }

    for header_text, data in totals_data.items():
        try:
            col_idx = headers.index(header_text) + start_col
            cell = ws.cell(row=total_row_num, column=col_idx, value=data['value'])
            cell.font = font_bold
            cell.number_format = data['format']
            cell.alignment = align_right_center
        except ValueError:
            print(f"LOGIC ERROR: Header '{header_text}' not found in `headers` list.")
            continue

    for i, col_name in enumerate(headers, start=start_col):
        column_letter = get_column_letter(i)
        if col_name == 'Part Name': ws.column_dimensions[column_letter].width = 35
        elif col_name == 'Part No.': ws.column_dimensions[column_letter].width = 35
        elif 'Spec' in col_name: ws.column_dimensions[column_letter].width = 20
        else: ws.column_dimensions[column_letter].width = 14


    # --- 7. PHẦN CASE MARK ---
    case_mark_row = total_row_num + 3
    ws.cell(row=case_mark_row, column=4, value="CASE MARK").font = font_bold
    details_start_row = case_mark_row + 1
    ws.cell(row=details_start_row,     column=5, value="INVOICE NO.:").font = font_content
    ws.cell(row=details_start_row + 1, column=5, value="").font = font_content
    ws.cell(row=details_start_row + 2, column=5, value="MADE IN VIETNAM").font = font_content
    ws.cell(row=details_start_row , column=8, value="Package:").font = font_content 
    ws.cell(row=details_start_row + 1, column=8, value="Quantity:").font = font_content 
    ws.cell(row=details_start_row + 2, column=8, value="N.W:").font = font_content      
    ws.cell(row=details_start_row + 3, column=8, value="G.W:").font = font_content      
    ws.cell(row=details_start_row , column=9, value=f"{cumulative_pallet_count} pallets").font = font_content
    ws.cell(row=details_start_row + 1, column=9, value=f"{int(cumulative_pcs)} pcs").font = font_content 
    ws.cell(row=details_start_row + 2, column=9, value=f"{cumulative_nw:.2f} kgs").font = font_content     
    ws.cell(row=details_start_row + 3, column=9, value=f"{cumulative_gw:.2f} kgs").font = font_content     

    # --- 8. PHẦN CHỮ KÝ ---
    signature_label_row = details_start_row + 8 
    signature_name_row = signature_label_row + 4
    ws.cell(row=signature_label_row, column=12, value="Signature").font = font_content
    signature_alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)
    ws.row_dimensions[signature_name_row].height = 35
    ws.merge_cells(start_row=signature_name_row, start_column=11, end_row=signature_name_row, end_column=13)
    cell_thu = ws.cell(row=signature_name_row, column=11)
    cell_thu.value = "NGUYEN DUC THU\nBusiness Director"
    cell_thu.font = font_content
    cell_thu.alignment = signature_alignment
    for i in range(11, 14):
        ws.cell(row=signature_name_row, column=i).border = border_top_only
    ws.merge_cells(start_row=signature_name_row, start_column=15, end_row=signature_name_row, end_column=17)
    cell_giang = ws.cell(row=signature_name_row, column=15)
    cell_giang.value = "LE MINH GIANG\nGeneral Director"
    cell_giang.font = font_content
    cell_giang.alignment = signature_alignment
    for i in range(15, 18):
        ws.cell(row=signature_name_row, column=i).border = border_top_only

@app.route('/api/upload', methods=['POST'])
def upload_file():
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


# backend/app.py

# backend/app.py

@app.route('/api/process', methods=['POST'])
def process_data():
    try:
        data = request.get_json()
        filepath = data.get('filepath')
        sheet_name = data.get('sheetName')
        
        # Lấy tên công ty, sử dụng giá trị mặc định nếu không có
        # Giữ nguyên logic này để tương thích với các bước xử lý
        company1_name = data.get('company1Name', '1.0').strip()
        company2_name = data.get('company2Name', '2.0').strip()

        if not all([filepath, sheet_name]):
            return jsonify({"success": False, "error": "Thiếu thông tin file hoặc sheet."}), 400

        # --- GIAI ĐOẠN 1: TẢI VÀ TỐI ƯU HÓA (LOGIC NÀY GIỮ NGUYÊN) ---
        all_pallets, error = load_and_prepare_pallets(filepath, sheet_name)
        if error:
            return jsonify({"success": False, "error": error}), 400
        if not all_pallets:
             return jsonify({"success": False, "error": "Không có dữ liệu pallet hợp lệ để xử lý."}), 400

        container_id_counter = {'count': 1}
        
        pre_packed_containers, pallets_to_process = preprocess_oversized_pallets(
            all_pallets, container_id_counter
        )
        
        pallets_c1, pallets_c2 = separate_pallets_by_company(
            pallets_to_process, company1_name, company2_name
        )
        
        int_p1, comb_p1, float_p1 = preprocess_and_classify_pallets(pallets_c1)
        packed_containers_c1 = layered_priority_packing(int_p1, comb_p1, float_p1, company1_name, container_id_counter)
        final_containers_c1, cross_ship_pallets_c1 = defragment_and_consolidate(packed_containers_c1)

        int_p2, comb_p2, float_p2 = preprocess_and_classify_pallets(pallets_c2)
        packed_containers_c2 = layered_priority_packing(int_p2, comb_p2, float_p2, company2_name, container_id_counter)
        final_containers_c2, cross_ship_pallets_c2 = defragment_and_consolidate(packed_containers_c2)

        final_optimized_containers = phase_3_cross_shipping_and_finalization(
            final_containers_c1, cross_ship_pallets_c1,
            final_containers_c2, cross_ship_pallets_c2,
            container_id_counter
        )
        
        all_final_containers = pre_packed_containers + final_optimized_containers

        # --- GIAI ĐOẠN 2: CHUYỂN ĐỔI KẾT QUẢ SANG JSON VÀ TRẢ VỀ ---
        # Sử dụng hàm generate_response_data đã có để tạo đúng định dạng JSON
        # mà frontend mong đợi.
        response_data = generate_response_data(all_final_containers)

        gc.collect() # Dọn dẹp bộ nhớ
        
        # Trả về kết quả dưới dạng JSON
        return jsonify(response_data)

    except Exception as e:
        import traceback
        traceback.print_exc()
        # Trả về lỗi dưới dạng JSON
        return jsonify({"success": False, "error": f"Đã xảy ra lỗi hệ thống không mong muốn: {str(e)}"}), 500

@app.route('/api/generate_packing_list', methods=['POST'])
def generate_packing_list_endpoint():
    print("\n[BACKEND] Bắt đầu xử lý /api/generate_packing_list")
    try:
        data = request.get_json()
        optimized_results = data.get('optimized_results')
        original_filepath = data.get('original_filepath')
        sheet_name = data.get('sheet_name')

        if not all([optimized_results, original_filepath, sheet_name]):
            return jsonify({"success": False, "error": "Thiếu dữ liệu để tạo packing list."}), 400

        raw_data_map, error = load_and_map_raw_data_for_pkl(original_filepath, sheet_name)
        required_fields = ['QtyPerBox', 'BoxPerPallet', 'WeightPerPc_Raw']
        for key, values in raw_data_map.items():
            for field in required_fields:
                if field not in values or values[field] in ["", None]:
                    raw_data_map[key][field] = 0.0
        if error:
            return jsonify({"success": False, "error": error}), 500

        wb = Workbook()
        wb.remove(wb.active)
        pallet_counter = {'item_no': 1, 'pallet_no': 1}
        
        # *** THAY ĐỔI: Khởi tạo dictionary để lưu trữ tổng dồn ***
        cumulative_totals = {'pcs': 0.0, 'nw': 0.0, 'gw': 0.0}

        for container_data in optimized_results:
            container_id_str = container_data.get('id', 'Unknown')
            container_id_num = ''.join(filter(str.isdigit, container_id_str))
            if not container_id_num:
               container_id_num = container_id_str.split('_')[-1]

            ws = wb.create_sheet(title=f"PKL_Cont_{container_id_num}")

            # Lưu ý: _prepare_data_for_pkl sẽ cập nhật pallet_counter
            df_for_pkl = _generate_dataframe_for_container(container_data, raw_data_map, pallet_counter)
            
            # *** THAY ĐỔI: Cập nhật các giá trị tổng dồn sau khi xử lý mỗi container ***
            cumulative_totals['pcs'] += df_for_pkl["Q'ty (pcs)"].sum()
            cumulative_totals['nw'] += df_for_pkl['N.W (kgs)'].sum()
            cumulative_totals['gw'] += df_for_pkl['G.W (kgs)'].sum()
            
            # Tổng số pallet tính đến thời điểm hiện tại là pallet_counter['pallet_no'] - 1
            cumulative_pallet_count_so_far = pallet_counter['pallet_no'] - 1

            # *** THAY ĐỔI: Truyền các giá trị tổng dồn vào hàm ghi sheet ***
            write_packing_list_to_sheet(
                ws, 
                df_for_pkl, 
                container_id_num,
                cumulative_pallet_count_so_far,
                cumulative_totals['pcs'],
                cumulative_totals['nw'],
                cumulative_totals['gw']
            )

        excel_buffer = io.BytesIO()
        wb.save(excel_buffer)
        excel_buffer.seek(0)

        gc.collect()

        print("[BACKEND] Đang gửi file về cho frontend...")
        return send_file(
            excel_buffer,
            as_attachment=True,
            download_name=f'PackingList_{sheet_name}.xlsx',
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )

    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        print(f"\n\n[BACKEND] !!! ĐÃ XẢY RA LỖI KHÔNG MONG MUỐN !!!")
        print(error_details)
        return jsonify({"success": False, "error": f"Lỗi nghiêm trọng ở backend: {str(e)}"}), 500

# --- CHẠY ỨNG DỤNG ---
if __name__ == '__main__':
    from waitress import serve
    print("Starting server with Waitress on http://0.0.0.0:5001")
    serve(app, host='0.0.0.0', port=5001)