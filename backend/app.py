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
    generate_response_data,
    load_and_map_raw_data_for_pkl
)

# --- KHỞI TẠO ỨNG DỤNG FLASK ---
app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024
#CORS(app, resources={r"/api/*": {"origins": "https://phamthingocanh25.github.io"}})
CORS(app)
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
    Tạo một dòng trong PKL cho một đơn vị pallet đơn (luôn có số lượng là 1).
    """
    key = str(item_content['product_code']) + '||' + str(item_content['product_name'])
    raw_info = raw_data_map.get(key, {})

    # Tính toán cho một pallet duy nhất (số lượng = 1.0)
    qty_per_box_val = _safe_float(raw_info.get('QtyPerBox'))
    box_per_pallet_val = _safe_float(raw_info.get('BoxPerPallet'))
    weight_per_box_raw_val = _safe_float(raw_info.get('WeightPerPc_Raw'))

    qty_boxes = box_per_pallet_val
    qty_pcs = qty_boxes * qty_per_box_val
    w_pc_kgs = (weight_per_box_raw_val / qty_per_box_val) if qty_per_box_val > 0 else 0
    nw_kgs = qty_pcs * w_pc_kgs
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
    # Tăng số đếm cho mỗi pallet riêng lẻ
    pallet_counter['item_no'] += 1
    pallet_counter['pallet_no'] += 1

def _render_combined_pallet_block(item_content, raw_data_map, pallet_counter, pkl_data_list, block_quantity):
    """
    Tạo một khối dòng trong PKL cho một pallet gộp với số lượng được chỉ định (block_quantity).
    block_quantity có thể là 1.0 (cho phần nguyên) hoặc số lẻ (0.9, 0.7, v.v.).
    """
    total_nw_group = 0
    total_boxes_group = 0
    items_calculated = []

    for item in item_content['items']:
        key_item = str(item['product_code']) + '||' + str(item['product_name'])
        raw_info_item = raw_data_map.get(key_item, {})

        # Lấy số lượng pallet gốc của sản phẩm con này trong pallet gộp
        original_item_qty = _safe_float(item.get('quantity'))

        # Tính toán các giá trị dựa trên số lượng của khối pallet gộp đang xét (block_quantity)
        # và tỷ lệ của sản phẩm con này trong pallet gộp gốc
        effective_pallet_qty = original_item_qty * block_quantity

        qty_per_box_item = _safe_float(raw_info_item.get('QtyPerBox'))
        box_per_pallet_item = _safe_float(raw_info_item.get('BoxPerPallet'))
        weight_per_box_raw_item = _safe_float(raw_info_item.get('WeightPerPc_Raw'))

        qty_boxes_item = effective_pallet_qty * box_per_pallet_item
        qty_pcs_item = qty_boxes_item * qty_per_box_item
        w_pc_kgs_item = (weight_per_box_raw_item / qty_per_box_item) if qty_per_box_item > 0 else 0
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

    gw_kgs_group = total_nw_group + (total_boxes_group * 0.4) + 50
    cbm_group = block_quantity * 1.15 * 1.15 * 0.8

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
            'G.W (kgs)': gw_kgs_group if is_first_item_in_group else '',
            'MEAS. (m)': "1.15*1.15*0.8" if is_first_item_in_group else '',
            'CBM': cbm_group if is_first_item_in_group else 0,
            "Q'ty/box": item_data['raw_info'].get('QtyPerBox', ''),
            "Box/Pallet": item_data['raw_info'].get('BoxPerPallet', ''),
            "Box Spec": item_data['raw_info'].get('BoxSpec', ''),
        }
        pkl_data_list.append(row)
        is_first_item_in_group = False

    # Tăng số đếm một lần cho cả khối
    pallet_counter['item_no'] += 1
    pallet_counter['pallet_no'] += 1

# ==============================================================================
# HÀM CHÍNH _prepare_data_for_pkl ĐƯỢC CẬP NHẬT
# ==============================================================================

def _prepare_data_for_pkl(container_data, raw_data_map, pallet_counter):
    """
    Chuẩn bị DataFrame cho một container duy nhất, áp dụng logic tách pallet
    theo phần nguyên và phần lẻ trước khi tạo dòng.
    """
    pkl_data_list = []
    fractional_waiting_area = []
    EPSILON = 1e-6

    # Sắp xếp pallet để xử lý nhất quán
    contents = sorted(container_data.get('contents', []), key=lambda x: x['type'] != 'CombinedPallet')

    # --- BƯỚC 1: TÁCH PHẦN NGUYÊN VÀ GOM PHẦN LẺ ---
    for content in contents:
        original_quantity = _safe_float(content.get('quantity'))
        
        # Xử lý sai số dấu phẩy động
        if abs(original_quantity - round(original_quantity)) < EPSILON:
            integer_part = int(round(original_quantity))
            fractional_part = 0.0
        else:
            integer_part = math.floor(original_quantity)
            fractional_part = original_quantity - integer_part

        # --- XỬ LÝ PHẦN NGUYÊN (TH1, TH2, TH3) ---
        if integer_part > 0:
            if content['type'] == 'SinglePallet':
                for _ in range(integer_part):
                    _render_single_pallet_unit(content, raw_data_map, pallet_counter, pkl_data_list)
            elif content['type'] == 'CombinedPallet':
                for _ in range(integer_part):
                    _render_combined_pallet_block(content, raw_data_map, pallet_counter, pkl_data_list, 1.0)

        # --- XỬ LÝ PHẦN LẺ (TH2, TH3) ---
        if fractional_part > EPSILON:
            frac_pallet_unit = deepcopy(content)
            frac_pallet_unit['quantity'] = fractional_part
            
            is_combined = content['type'] == 'CombinedPallet'
            is_point_nine = abs(original_quantity - (integer_part + 0.9)) < EPSILON

            # TH3.1: Pallet gộp dạng X.9 -> hiển thị phần 0.9 ngay
            if is_combined and is_point_nine:
                _render_combined_pallet_block(frac_pallet_unit, raw_data_map, pallet_counter, pkl_data_list, fractional_part)
            else:
                # TH2 & TH3.2: Đưa phần lẻ vào khu vực chờ
                fractional_waiting_area.append(frac_pallet_unit)

    # --- BƯỚC 2: GOM NHÓM VÀ HIỂN THỊ CÁC PHẦN LẺ TRONG KHU VỰC CHỜ ---
    fractional_waiting_area.sort(key=lambda p: p['quantity'], reverse=True)
    
    while fractional_waiting_area:
        main_pallet_frac = fractional_waiting_area.pop(0)
        current_group = [main_pallet_frac]
        current_total_quantity = main_pallet_frac['quantity']
        
        remaining_indices_to_keep = []
        for i, other_pallet_frac in enumerate(fractional_waiting_area):
            if current_total_quantity + other_pallet_frac['quantity'] <= 0.9 + EPSILON:
                current_group.append(other_pallet_frac)
                current_total_quantity += other_pallet_frac['quantity']
            else:
                remaining_indices_to_keep.append(i)
        
        fractional_waiting_area = [fractional_waiting_area[i] for i in remaining_indices_to_keep]

        # Hiển thị nhóm đã gom được như một khối pallet gộp mới
        # Tạo một 'item_content' giả để tương thích với hàm _render_combined_pallet_block
        group_items = []
        for pallet_part in current_group:
            if pallet_part['type'] == 'SinglePallet':
                group_items.append({
                    "product_code": pallet_part['product_code'],
                    "product_name": pallet_part['product_name'],
                    "company": pallet_part['company'],
                    "quantity": pallet_part['quantity'] / current_total_quantity, # Tỷ lệ trong nhóm mới
                })
            elif pallet_part['type'] == 'CombinedPallet':
                # Nếu một phần tử trong nhóm đã là pallet gộp, ta cần lấy các sản phẩm con của nó
                original_part_qty = pallet_part['quantity']
                for sub_item in pallet_part['items']:
                     group_items.append({
                        "product_code": sub_item['product_code'],
                        "product_name": sub_item['product_name'],
                        "company": sub_item['company'],
                        # Tính lại tỷ lệ của sản phẩm con trong nhóm mới
                        "quantity": (_safe_float(sub_item.get('quantity')) * original_part_qty) / current_total_quantity,
                    })
        
        pseudo_content = {'type': 'CombinedPallet', 'items': group_items}
        _render_combined_pallet_block(pseudo_content, raw_data_map, pallet_counter, pkl_data_list, current_total_quantity)

    return pd.DataFrame(pkl_data_list)


# Thay thế toàn bộ hàm này trong file app.py của bạn

def write_packing_list_to_sheet(ws, data_df, container_id_num,cumulative_pallet_count):
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
         'D': 10, 'E': 10, 'F': 20, 'G': 20,
        'H': 12, 'I': 12, 'J': 12, 'K': 12, 'L': 12, 'M': 18, 'N': 12, 'O': 12, 'P': 18
    }
    for col, width in column_widths.items():
        ws.column_dimensions[col].width = width

    # --- 3. TẠO TIÊU ĐỀ CHÍNH "PACKING LIST" ---
    ws.merge_cells('D1:O1')
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
    buyer_header_cell = ws['D11']
    buyer_header_cell.font = font_box_header
    buyer_header_cell.alignment = Alignment(horizontal='left', vertical='top')
    buyer_content_cell = ws['D12']
    buyer_content = ("  \n"
                      " \n"
                      " \n")
    buyer_content_cell.value = buyer_content
    buyer_content_cell.font = font_content
    buyer_content_cell.alignment = align_top_left
    
    
    ws.merge_cells('I2:O2')
    ws.merge_cells('I3:O10')
    apply_border_to_range('I2:O10', thin_border)
    invoice_header_cell = ws['I2']
    invoice_header_cell.value = "INVOICE NO. & DATE:"
    invoice_header_cell.font = font_box_header
    invoice_header_cell.alignment = Alignment(horizontal='left', vertical='top')
    invoice_content_cell = ws['I3']
    invoice_content = ("  \n"
                      " \n"
                      " \n")
    invoice_content_cell.value = invoice_content
    invoice_content_cell.font = font_content
    invoice_content_cell.alignment = align_top_left




    apply_border_to_range('I11:O18', thin_border)
    ws.merge_cells('I11:K11')
    ws.merge_cells('L11:O11')
    ws.merge_cells('I12:K18')
    ws.merge_cells('L12:O18')
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
    
    # Chuyển đổi kiểu dữ liệu để tính toán
    numeric_cols = ["Q'ty (boxes)", "Q'ty (pcs)", "W / pc (kgs)", "N.W (kgs)", "G.W (kgs)", "CBM"]
    for col in numeric_cols:
        if col in data_df.columns:
            data_df[col] = pd.to_numeric(data_df[col], errors='coerce').fillna(0)
        else:
            data_df[col] = 0

    # Lặp qua dữ liệu và ghi vào sheet
    for _, row_data in data_df.iterrows():
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
            # Cột J,K,L,M,N gốc -> cột H->L mới
            col_letter = get_column_letter(i)
            # Cột số lượng (boxes, pcs) - H, I
            if col_letter in ['H', 'I']:
                cell.number_format = '#,##0'
                cell.alignment = align_right_center
            # Cột trọng lượng - J, K, L
            elif col_letter in ['J', 'K', 'L']:
                cell.number_format = '#,##0.00'
                cell.alignment = align_right_center
            else:
                cell.alignment = align_center
        current_row += 1
    
# --- 6. DÒNG TỔNG KẾT (TOTAL) ---
    total_row_num = current_row
    for col_idx in range(start_col, end_col + 1):
        ws.cell(row=total_row_num, column=col_idx).border = thin_border

    # Tính toán các giá trị tổng từ DataFrame
    total_qty_boxes = data_df["Q'ty (boxes)"].sum()
    total_qty_pcs = data_df["Q'ty (pcs)"].sum()
    total_nw = data_df['N.W (kgs)'].sum()
    total_gw = data_df['G.W (kgs)'].sum()

    # Ghi nhãn tổng. SỬA LỖI: Chỉ gộp các cột nhãn (D đến G),
    # không gộp chồng lấn lên cột dữ liệu số đầu tiên (H).
    total_label_cell = ws.cell(row=total_row_num, column=start_col, value=f'Total container ({container_id_num})')
    # Phạm vi gộp đúng là 4 cột nhãn, kết thúc ở cột G (start_col + 3)
    ws.merge_cells(start_row=total_row_num, start_column=start_col, end_row=total_row_num, end_column=start_col + 3)
    total_label_cell.font = font_bold
    total_label_cell.alignment = align_center

    # TỐI ƯU: Ghi các giá trị tổng vào đúng cột và áp dụng đầy đủ định dạng
    # Sử dụng một dictionary để quản lý dữ liệu tổng một cách rõ ràng và tránh lặp code.
    totals_data = {
        "Q'ty\n(boxes)": {'value': total_qty_boxes, 'format': '#,##0'},
        "Q'ty\n(pcs)": {'value': total_qty_pcs, 'format': '#,##0'},
        "N.W\n(kgs)": {'value': total_nw, 'format': '#,##0.00'},
        "G.W\n(kgs)": {'value': total_gw, 'format': '#,##0.00'}
    }

    for header_text, data in totals_data.items():
        try:
            # Tìm vị trí cột chính xác dựa trên danh sách `headers`
            col_idx = headers.index(header_text) + start_col
            cell = ws.cell(row=total_row_num, column=col_idx, value=data['value'])
            
            # Áp dụng nhất quán style cho các ô tổng
            cell.font = font_bold
            cell.number_format = data['format']
            cell.alignment = align_right_center
        except ValueError:
            # Báo lỗi nếu có sự không nhất quán giữa `totals_data` và `headers`
            print(f"LỖI LOGIC: Không tìm thấy tiêu đề '{header_text}' trong danh sách `headers`.")
            continue

    # Điều chỉnh lại độ rộng cột một lần nữa để đảm bảo khớp
    for i, col_name in enumerate(headers, start=start_col):
        column_letter = get_column_letter(i)
        if col_name == 'Part Name': ws.column_dimensions[column_letter].width = 35
        elif col_name == 'Part No.': ws.column_dimensions[column_letter].width = 35
        elif 'Spec' in col_name: ws.column_dimensions[column_letter].width = 20
        else: ws.column_dimensions[column_letter].width = 14

    # --- 7. PHẦN CASE MARK ---
    case_mark_row = total_row_num + 3
    ws.cell(row=case_mark_row, column=4, value="CASE MARK").font = font_bold # Cột D

    details_start_row = case_mark_row + 1
    # Thông tin bên trái (Cột E)
    ws.cell(row=details_start_row,     column=5, value="INVOICE NO.:").font = font_content
    ws.cell(row=details_start_row + 1, column=5, value="").font = font_content
    ws.cell(row=details_start_row + 2, column=5, value="MADE IN VIETNAM").font = font_content
    
    # Thông tin bên phải (Cột H, I)
    ws.cell(row=details_start_row , column=8, value="Pallets:").font = font_content 
    ws.cell(row=details_start_row + 1,  column=8, value="Package:").font = font_content
    ws.cell(row=details_start_row + 2, column=8, value="Quantity:").font = font_content # Dịch xuống
    ws.cell(row=details_start_row + 3, column=8, value="N.W:").font = font_content      # Dịch xuống
    ws.cell(row=details_start_row + 4, column=8, value="G.W:").font = font_content      # Dịch xuống

    ws.cell(row=details_start_row , column=9, value=f"{cumulative_pallet_count} pallets").font = font_content
    ws.cell(row=details_start_row+ 1, column=9, value=f"{int(total_qty_boxes)} boxes").font = font_content
    ws.cell(row=details_start_row + 2, column=9, value=f"{int(total_qty_pcs)} pcs").font = font_content # Dịch xuống
    ws.cell(row=details_start_row + 3, column=9, value=f"{total_nw:.2f} kgs").font = font_content     # Dịch xuống
    ws.cell(row=details_start_row + 4, column=9, value=f"{total_gw:.2f} kgs").font = font_content     # Dịch xuống
    # --- KẾT THÚC THAY ĐỔI ---

    # --- 8. PHẦN CHỮ KÝ (CẬP NHẬT VỊ TRÍ) ---
    # Vị trí dòng chữ ký được tính toán lại để không bị đè lên phần Case Mark đã mở rộng
    signature_label_row = details_start_row + 8 # Giữ nguyên khoảng cách tương đối
    signature_name_row = signature_label_row + 4
    ws.cell(row=signature_label_row, column=11, value="Signature:").font = font_content
    signature_alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)
    ws.row_dimensions[signature_name_row].height = 35
    ws.merge_cells(start_row=signature_name_row, start_column=10, end_row=signature_name_row, end_column=12)
    cell_thu = ws.cell(row=signature_name_row, column=10)
    cell_thu.value = "NGUYEN DUC THU\nBusiness Director"
    cell_thu.font = font_content
    cell_thu.alignment = signature_alignment
    for i in range(10, 13):
        ws.cell(row=signature_name_row, column=i).border = border_top_only
    ws.merge_cells(start_row=signature_name_row, start_column=15, end_row=signature_name_row, end_column=17)
    cell_giang = ws.cell(row=signature_name_row, column=15)
    cell_giang.value = "LE MINH GIANG\nGeneral Director"
    cell_giang.font = font_content
    cell_giang.alignment = signature_alignment
    for i in range(15, 18):
        ws.cell(row=signature_name_row, column=i).border = border_top_only


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

        # === THAY ĐỔI CHÍNH: GỌI HÀM TỪ DATA_PROCESSOR ===
        # Logic đọc file Excel và tạo map giờ được ủy quyền hoàn toàn.
        raw_data_map, error = load_and_map_raw_data_for_pkl(original_filepath, sheet_name)
        required_fields = ['QtyPerBox', 'BoxPerPallet', 'WeightPerPc_Raw']
        for key, values in raw_data_map.items():
            for field in required_fields:
                if field not in values or values[field] in ["", None]:
                    print(f"WARNING: Missing value for {field} in product: {key}")
                    # Gán giá trị mặc định an toàn
                    raw_data_map[key][field] = 0.0
        if error:
            return jsonify({"success": False, "error": error}), 500
        # =======================================================

        wb = Workbook()
        wb.remove(wb.active)
        pallet_counter = {'item_no': 1, 'pallet_no': 1}

        for container_data in optimized_results:
            container_id_str = container_data.get('id', 'Unknown')
            container_id_num = ''.join(filter(str.isdigit, container_id_str))
            if not container_id_num:
               container_id_num = container_id_str.split('_')[-1]

            ws = wb.create_sheet(title=f"PKL_Cont_{container_id_num}")

            df_for_pkl = _prepare_data_for_pkl(container_data, raw_data_map, pallet_counter)
            current_cumulative_pallets = pallet_counter['pallet_no'] - 1
            write_packing_list_to_sheet(ws, df_for_pkl, container_id_num, current_cumulative_pallets)

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