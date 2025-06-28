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
# Sửa lại định nghĩa hàm để nhận pallet_counter
def _prepare_data_for_pkl(container_data, raw_data_map, pallet_counter):
    """
    Chuẩn bị DataFrame cho một container duy nhất, tính toán các giá trị
    dựa trên quy tắc đã cho và dữ liệu gốc.
    """
    pkl_data_list = []
    
    # Sắp xếp pallet trong container, ưu tiên pallet gộp
    contents = sorted(container_data.get('contents', []), key=lambda x: x['type'] != 'CombinedPallet')

    for content in contents:
        # --- TRƯỜNG HỢP 1: PALLET ĐƠN (Integer hoặc Single Float) ---
        if content['type'] == 'SinglePallet':
            key = str(content['product_code']) + '||' + str(content['product_name'])
            raw_info = raw_data_map.get(key, {})
            
            optimized_pallet_qty = float(content.get('quantity', 0))
            
            # --- TÍNH TOÁN THEO CÔNG THỨC YÊU CẦU ---
            qty_per_box_val = float(raw_info.get('QtyPerBox', 0))
            box_per_pallet_val = float(raw_info.get('BoxPerPallet', 0))
            # Đây là Weight per BOX từ cột G, không phải per PC
            weight_per_box_raw_val = float(raw_info.get('WeightPerPc_Raw', 0))

            # Quantity (Boxes) (Cột H PKL)
            qty_boxes = optimized_pallet_qty * box_per_pallet_val

            # Quantity (Pcs) (Cột J PKL)
            qty_pcs = qty_boxes * qty_per_box_val
            
            # W/pc(kgs) (Cột K PKL) = Cột G / Cột F
            w_pc_kgs = (weight_per_box_raw_val / qty_per_box_val) if qty_per_box_val > 0 else 0
            
            # N.W(kgs) (Cột L PKL)
            nw_kgs = qty_pcs * w_pc_kgs
            
            # G.W (kgs) (Cột M PKL)
            gw_kgs = nw_kgs + (qty_boxes * 0.4) + 50
            
            # CBM để tính tổng
            cbm = optimized_pallet_qty * 1.15 * 1.15 * 0.8

            row = {
                'Item No.': pallet_counter['item_no'],
                'Pallet': f"No.{pallet_counter['pallet_no']:03d}",
                'Part Name': content['product_name'],
                'Part No.': content['product_code'],
                "Q'ty (boxes)": qty_boxes,
                "Q'ty (pcs)": qty_pcs,
                'W / pc (kgs)': w_pc_kgs,
                'N.W (kgs)': nw_kgs,
                'G.W (kgs)': gw_kgs,
                'MEAS. (m)': "1.15*1.15*0.8",
                'CBM': cbm, # Thêm CBM để tính tổng
                "Q'ty/box": qty_per_box_val,
                "Box/Pallet": box_per_pallet_val,
                "Box Spec": raw_info.get('BoxSpec', ''),
            }
            pkl_data_list.append(row)
            pallet_counter['item_no'] += 1
            pallet_counter['pallet_no'] += 1

        # --- TRƯỜNG HỢP 2: PALLET GỘP (Combined) ---
        elif content['type'] == 'CombinedPallet':
            total_nw_group = 0
            total_boxes_group = 0
            
            items_calculated = []
            for item in content['items']:
                key_item = str(item['product_code']) + '||' + str(item['product_name'])
                raw_info_item = raw_data_map.get(key_item, {})

                optimized_pallet_qty_item = float(item.get('quantity', 0))
                qty_per_box_item = float(raw_info_item.get('QtyPerBox', 0))
                box_per_pallet_item = float(raw_info_item.get('BoxPerPallet', 0))
                weight_per_box_raw_item = float(raw_info_item.get('WeightPerPc_Raw', 0))
                
                qty_boxes_item = optimized_pallet_qty_item * box_per_pallet_item
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
            cbm_group = 1 * 1.15 * 1.15 * 0.8 # Pallet gộp luôn là 1 pallet vật lý

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
                    'CBM': cbm_group if is_first_item_in_group else 0, # Thêm CBM
                    "Q'ty/box": item_data['raw_info'].get('QtyPerBox', ''),
                    "Box/Pallet": item_data['raw_info'].get('BoxPerPallet', ''),
                    "Box Spec": item_data['raw_info'].get('BoxSpec', ''),
                }
                pkl_data_list.append(row)
                is_first_item_in_group = False
            
            pallet_counter['item_no'] += 1
            pallet_counter['pallet_no'] += 1
            
    return pd.DataFrame(pkl_data_list)


def write_packing_list_to_sheet(ws, data_df, container_id_num):
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
    
    no_border_left = Border(
        right=Side(style='thin'), 
        top=Side(style='thin'), 
        bottom=Side(style='thin')
    )
    
    no_border_right = Border(
        left=Side(style='thin'), 
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
    
    # Thiết lập độ rộng cột cho 13 cột dữ liệu (A->M) + cột phụ (N, O, P, Q)
    column_widths = {
        'A': 5, 'B': 10, 'C': 35, 'D': 18, 'E': 10, 'F': 12, 'G': 10,
        'H': 12, 'I': 12, 'J': 15, 'K': 10, 'L': 10, 'M': 12
    }
    for col, width in column_widths.items():
        ws.column_dimensions[col].width = width

    # --- 3. TẠO TIÊU ĐỀ CHÍNH "PACKING LIST" ---
    ws.merge_cells('A1:M4')
    title_cell = ws['A1']
    title_cell.value = "PACKING LIST"
    title_cell.font = font_main_title
    title_cell.alignment = align_center
    ws.row_dimensions[1].height = 65

    # --- 4. TẠO CÁC Ô THÔNG TIN (SELLER, BUYER, INVOICE, FROM/TO) ---
    # Điều chỉnh các merge cell để phù hợp với layout 13 cột
    ws.merge_cells('A5:F11') # Seller
    apply_border_to_range('A5:F11', thin_border)
    ws.merge_cells('G5:M11') # Buyer
    apply_border_to_range('G5:M11', thin_border)
    ws.merge_cells('A12:F18') # Invoice
    apply_border_to_range('A12:F18', thin_border)
    ws.merge_cells('G12:M18') # From/To
    apply_border_to_range('G12:M18', thin_border)

    ws['A5'].value = "SELLER"
    ws['A5'].font = font_box_header
    seller_content = (
        "MINH QUANG IDS TRADING AND INDUSTRIES JOINT STOCK COMPANY\n"
        "Add: Plot CN 4 , Yen My Industrial zone, \n"
        "Tan Lap Commune ,Yen My District, Hung Yen Province, Vietnam\n"
        "Tel: (+84) 42 211 8360\n"
        "Fax: (+84) 43 965 2536"
    )
    ws['A6'].value = seller_content
    ws['A6'].font = font_content
    ws['A6'].alignment = align_top_left

    ws['G5'].value = "BUYER"
    ws['G5'].font = font_box_header

    ws['A12'].value = "INVOICE NO. & DATE:"
    ws['A12'].font = font_box_header
    ws.merge_cells('A13:F18')

    ws.merge_cells('G13:I18')
    ws.merge_cells('J13:M18')
    ws['G12'].value = "FROM:"
    ws['G12'].font = font_content_bold
    ws['G12'].alignment = align_center
    ws['J12'].value = "TO:"
    ws['J12'].font = font_content_bold
    ws['J12'].alignment = align_center
    from_cell = ws['G13']
    from_cell.value = "Haiphong, Vietnam"
    from_cell.font = font_content
    from_cell.alignment = align_center

    # --- 5. TẠO BẢNG DỮ LIỆU SẢN PHẨM ---
    start_row = 20
    
    # Tiêu đề bảng - 13 cột theo yêu cầu
    headers = [
        "Item No.", "Pallet", "Part Name", "Part No.", "Q'ty\n(boxes)", "Q'ty\n(pcs)",
        "W / pc\n(kgs)", "N.W\n(kgs)", "G.W\n(kgs)", "MEAS.\n(m)", "Q'ty/box",
        "Box/Pallet", "Box Spec"
    ]
    for i, header in enumerate(headers, 1):
        cell = ws.cell(row=start_row, column=i, value=header)
        cell.font = font_table_header
        cell.alignment = align_center
        cell.border = thin_border
        cell.fill = PatternFill(start_color="D9D9D9", end_color="D9D9D9", fill_type="solid")
    
    # Điền dữ liệu sản phẩm
    current_row = start_row + 1
    
    # Đảm bảo các cột số là numeric để tính tổng, thay thế giá trị không hợp lệ bằng 0
    numeric_cols = ["Q'ty (boxes)", "Q'ty (pcs)", "W / pc (kgs)", "N.W (kgs)", "G.W (kgs)", "CBM"]
    for col in numeric_cols:
        if col in data_df.columns:
            data_df[col] = pd.to_numeric(data_df[col], errors='coerce').fillna(0)
        else:
            data_df[col] = 0

    for _, row_data in data_df.iterrows():
        # Ánh xạ từ cột DataFrame sang thứ tự cột trong Excel
        row_values = [
            row_data.get('Item No.', ''),
            row_data.get('Pallet', ''),
            row_data.get('Part Name', ''),
            row_data.get('Part No.', ''),
            row_data.get("Q'ty (boxes)", 0),
            row_data.get("Q'ty (pcs)", 0),
            row_data.get('W / pc (kgs)', 0),
            row_data.get('N.W (kgs)', 0),
            row_data.get('G.W (kgs)', 0),
            row_data.get('MEAS. (m)', ''),
            row_data.get("Q'ty/box", ''),
            row_data.get("Box/Pallet", ''),
            row_data.get('Box Spec', '')
        ]
        
        for i, value in enumerate(row_values, 1):
            cell = ws.cell(row=current_row, column=i, value=value)
            cell.font = font_table_content
            cell.border = thin_border
            
            # Định dạng cho các cột
            # Cột E, F (boxes, pcs) - số nguyên
            if i in [5, 6]:
                cell.number_format = '#,##0'
                cell.alignment = align_right_center
            # Cột G, H, I (weights) - số thập phân
            elif i in [7, 8, 9]:
                cell.number_format = '#,##0.00'
                cell.alignment = align_right_center
            # Các cột khác - căn giữa
            else:
                cell.alignment = align_center
        current_row += 1

    # Dòng TOTAL
    total_row = current_row
    total_qty_boxes = data_df["Q'ty (boxes)"].sum()
    total_qty_pcs = data_df["Q'ty (pcs)"].sum()
    total_nw = data_df["N.W (kgs)"].sum()
    total_gw = data_df["G.W (kgs)"].sum()
    total_cbm = data_df["CBM"].sum()

    ws.merge_cells(f'A{total_row}:D{total_row}')
    total_label_cell = ws.cell(row=total_row, column=1, value="TOTAL:")
    total_label_cell.font = font_table_header_bold
    total_label_cell.alignment = align_top_right_bold
    ws['A' + str(total_row)].border = no_border_right
    ws['B' + str(total_row)].border = None
    ws['C' + str(total_row)].border = None
    ws['D' + str(total_row)].border = no_border_left


    # Điền giá trị tổng
    ws.cell(row=total_row, column=5, value=total_qty_boxes).number_format = '#,##0'
    ws.cell(row=total_row, column=6, value=total_qty_pcs).number_format = '#,##0'
    ws.cell(row=total_row, column=8, value=total_nw).number_format = '#,##0.00'
    ws.cell(row=total_row, column=9, value=total_gw).number_format = '#,##0.00'
    ws.cell(row=total_row, column=10, value=total_cbm).number_format = '#,##0.00' # Tổng MEAS (CBM)
    
    # Bỏ trống các cột không cần tổng
    ws.cell(row=total_row, column=7, value="")
    ws.cell(row=total_row, column=11, value="")
    ws.cell(row=total_row, column=12, value="")
    ws.cell(row=total_row, column=13, value="")


    # Định dạng dòng total
    for i in range(5, 14):
        cell = ws.cell(row=total_row, column=i)
        cell.font = font_table_header_bold
        cell.border = thin_border
        if i in [5, 6, 8, 9, 10]: # Các cột có giá trị tổng
            cell.alignment = align_right_center

    # --- 6. TẠO PHẦN CASE MARK (TỰ ĐỘNG CẬP NHẬT) ---
    case_mark_start_row = total_row + 2
    ws.merge_cells(f'A{case_mark_start_row}:F{case_mark_start_row + 6}')
    apply_border_to_range(f'A{case_mark_start_row}:F{case_mark_start_row + 6}', thin_border)

    ws.cell(row=case_mark_start_row, column=1, value="CASE MARK").font = font_box_header
    
    # Lấy tổng số pallet duy nhất để hiển thị
    total_pallets = data_df['Pallet'].nunique()

    case_mark_content = [
        f"CONTAINER NO.: {container_id_num}",
        f"TOTAL PALLET: {total_pallets} PLTS",
        f"TOTAL PACKAGE: {int(total_qty_boxes)} CTNS",
        f"TOTAL QUANTITY: {int(total_qty_pcs)} PCS",
        f"N.W: {total_nw:,.2f} KGS",
        f"G.W: {total_gw:,.2f} KGS"
    ]
    for i, line in enumerate(case_mark_content):
        # Merge cell cho mỗi dòng để canh lề trái đẹp hơn
        ws.merge_cells(f'B{case_mark_start_row + 1 + i}:F{case_mark_start_row + 1 + i}')
        cell = ws.cell(row=case_mark_start_row + 1 + i, column=2, value=line)
        cell.font = font_content_bold
        cell.alignment = align_top_left

    # --- 7. TẠO PHẦN CHỮ KÝ (CỐ ĐỊNH) ---
    signature_start_row = total_row + 10 # Điều chỉnh khoảng cách nếu cần
    
    # Chữ ký bên trái
    ws.merge_cells(f'B{signature_start_row}:D{signature_start_row}')
    cell_mq = ws.cell(row=signature_start_row, column=2, value="MINH QUANG IDS")
    cell_mq.font = font_content_bold
    cell_mq.alignment = align_bottom_center
    ws.merge_cells(f'B{signature_start_row-1}:D{signature_start_row-1}')
    ws[f'B{signature_start_row-1}'].border = Border(bottom=Side(style='thin'))

    # Chữ ký bên phải
    ws.merge_cells(f'J{signature_start_row}:L{signature_start_row}')
    cell_buyer = ws.cell(row=signature_start_row, column=10, value="BUYER")
    cell_buyer.font = font_content_bold
    cell_buyer.alignment = align_bottom_center
    ws.merge_cells(f'J{signature_start_row-1}:L{signature_start_row-1}')
    ws[f'J{signature_start_row-1}'].border = Border(bottom=Side(style='thin'))

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
            write_packing_list_to_sheet(ws, df_for_pkl, container_id_num)

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