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
    generate_response_data 
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
def _prepare_data_for_pkl(container_data, raw_data_map):
    """
    Chuẩn bị DataFrame cho một container duy nhất dựa trên dữ liệu đã tối ưu
    và dữ liệu thô từ file Excel gốc.
    """
    pkl_data_list = []
    item_no_counter = 1

    # Duyệt qua từng pallet (đơn hoặc gộp) trong container
    for content in container_data.get('contents', []):
        # --- TRƯỜNG HỢP 1: PALLET ĐƠN (Integer hoặc Single Float) ---
        if content['type'] == 'SinglePallet':
            key = str(content['product_code']) + '||' + str(content['product_name'])
            raw_info = raw_data_map.get(key, {})

            # Lấy số lượng pallet đã được tối ưu hóa từ data_processor.py
            optimized_pallet_qty = float(content.get('quantity', 0))
            
            # --- TÍNH TOÁN THEO FRAMEWORK ---
            # Quantity (boxes) = Số lượng pallet tối ưu * Số hộp trên mỗi pallet (cột H từ Excel gốc)
            qty_boxes = optimized_pallet_qty * float(raw_info.get('BoxPerPallet', 0))
            
            qty_per_box = float(raw_info.get('QtyPerBox', 0))
            qty_pcs = qty_boxes * qty_per_box
            w_pc_kgs = (float(raw_info.get('WeightPerPc_Raw', 0)) / qty_per_box) if qty_per_box > 0 else 0
            nw_kgs = qty_pcs * w_pc_kgs
            
            # G.W (kgs) cho pallet đơn
            gw_kgs = nw_kgs + (qty_boxes * 0.4) + 50

            row = {
                'Item No.': item_no_counter,
                'Pallet': f"No.{item_no_counter:03d}",
                'Part Name': content['product_name'],
                'Part No.': content['product_code'],
                "Q'ty (boxes)": f"{qty_boxes:.2f}",
                "Q'ty (pcs)": f"{qty_pcs:.2f}",
                'W / pc (kgs)': f"{w_pc_kgs:.4f}",
                'N.W (kgs)': f"{nw_kgs:.2f}",
                'G.W (kgs)': f"{gw_kgs:.2f}",
                'MEAS. (m)': "1.15*1.15*0.8",
                "Q'ty/box": raw_info.get('QtyPerBox', ''),
                "Box/Pallet": raw_info.get('BoxPerPallet', ''),
                "Box Spec": raw_info.get('BoxSpec', ''),
            }
            pkl_data_list.append(row)
            item_no_counter += 1

        # --- TRƯỜNG HỢP 2: PALLET GỘP (Combined) ---
        elif content['type'] == 'CombinedPallet':
            # --- TÍNH TOÁN TỔNG CHO CẢ PALLET GỘP (để điền G.W) ---
            total_nw_group = 0
            total_boxes_group = 0
            
            # Vòng lặp tạm để tính tổng trước
            for item in content['items']:
                key_item = str(item['product_code']) + '||' + str(item['product_name'])
                raw_info_item = raw_data_map.get(key_item, {})
                
                # Quantity (boxes) của từng mặt hàng trong pallet gộp
                qty_boxes_item = float(item['quantity']) * float(raw_info_item.get('BoxPerPallet', 0))
                qty_per_box_item = float(raw_info_item.get('QtyPerBox', 0))
                qty_pcs_item = qty_boxes_item * qty_per_box_item
                w_pc_kgs_item = (float(raw_info_item.get('WeightPerPc_Raw', 0)) / qty_per_box_item) if qty_per_box_item > 0 else 0
                nw_kgs_item = qty_pcs_item * w_pc_kgs_item
                
                total_nw_group += nw_kgs_item
                total_boxes_group += qty_boxes_item
            
            # G.W (kgs) cho pallet gộp (chỉ hiển thị ở dòng đầu tiên)
            gw_kgs_group = total_nw_group + (total_boxes_group * 0.4) + 50

            # --- TẠO CÁC DÒNG CHO TỪNG MẶT HÀNG TRONG PALLET GỘP ---
            is_first_item_in_group = True
            for item in content['items']:
                key = str(item['product_code']) + '||' + str(item['product_name'])
                raw_info = raw_data_map.get(key, {})

                # Lấy lại các giá trị đã tính
                qty_boxes_item = float(item['quantity']) * float(raw_info.get('BoxPerPallet', 0))
                qty_per_box_item = float(raw_info.get('QtyPerBox', 0))
                qty_pcs_item = qty_boxes_item * qty_per_box_item
                w_pc_kgs_item = (float(raw_info.get('WeightPerPc_Raw', 0)) / qty_per_box_item) if qty_per_box_item > 0 else 0
                nw_kgs_item = qty_pcs_item * w_pc_kgs_item

                row = {
                    'Item No.': item_no_counter if is_first_item_in_group else '',
                    'Pallet': f"No.{item_no_counter:03d}" if is_first_item_in_group else '',
                    'Part Name': item['product_name'],
                    'Part No.': item['product_code'],
                    "Q'ty (boxes)": f"{qty_boxes_item:.2f}",
                    "Q'ty (pcs)": f"{qty_pcs_item:.2f}",
                    'W / pc (kgs)': f"{w_pc_kgs_item:.4f}",
                    'N.W (kgs)': f"{nw_kgs_item:.2f}",
                    # G.W và MEAS chỉ điền ở dòng đầu tiên của nhóm
                    'G.W (kgs)': f"{gw_kgs_group:.2f}" if is_first_item_in_group else '',
                    'MEAS. (m)': "1.15*1.15*0.8" if is_first_item_in_group else '',
                    "Q'ty/box": raw_info.get('QtyPerBox', ''),
                    "Box/Pallet": raw_info.get('BoxPerPallet', ''),
                    "Box Spec": raw_info.get('BoxSpec', ''),
                }
                pkl_data_list.append(row)
                is_first_item_in_group = False
            
            item_no_counter += 1

    # Tạo DataFrame từ list các dictionary
    # Xóa các cột không cần thiết mà có thể được tạo ra từ file mẫu
    df = pd.DataFrame(pkl_data_list)
    cols_to_drop = ['Unnamed: 7', "Q'ty/ box"]
    df = df.drop(columns=[col for col in cols_to_drop if col in df.columns])
    
    return df


def write_packing_list_to_sheet(ws, data_df, container_id_num):
    """
    Ghi dữ liệu packing list của một container vào một worksheet (ws) cụ thể.
    Hàm này vẽ toàn bộ bố cục, bao gồm header, bảng dữ liệu, và footer.
    """
    # ==============================================================================
    # PHẦN 1: KHỞI TẠO VÀ TẠO HEADER CHO SHEET
    # ==============================================================================

    ws.sheet_view.showGridLines = False

    # --- ĐỊNH NGHĨA CÁC PHONG CÁCH ---
    font_main_title = Font(name='Arial', size=48, bold=True)
    font_box_header = Font(name='Arial', size=11, bold=True, underline='single')
    font_content = Font(name='Arial', size=11)
    font_bold = Font(name='Arial', size=12, bold=True)
    align_center = Alignment(horizontal='center', vertical='center')
    align_top_left = Alignment(horizontal='left', vertical='top', wrap_text=True)
    align_center_wrap = Alignment(horizontal='center', vertical='center', wrap_text=True)
    thick_side = Side(style='medium')
    thin_side = Side(style='thin')
    thin_border = Border(left=thin_side, right=thin_side, top=thin_side, bottom=thin_side)
    border_top_only = Border(top=thin_side)

    # --- ĐỊNH DẠNG BỐ CỤC PHẦN ĐẦU ---
    for col in ['D', 'E', 'F', 'G', 'H', 'I', 'J', 'K', 'L', 'M', 'N', 'O', 'P', 'Q']:
        ws.column_dimensions[col].width = 15

    ws.merge_cells('D1:M1')
    title_cell = ws['D1']
    title_cell.value = "PACKING LIST"
    title_cell.font = font_main_title
    title_cell.alignment = align_center
    ws.row_dimensions[1].height = 65

    # --- HÀM HELPER ĐỂ KẺ VIỀN NGOÀI ---
    def apply_outline(cell_range):
        rows = list(rows_from_range(cell_range))
        cols = list(cols_from_range(cell_range))
        
        # Sửa lỗi nếu range chỉ có 1 ô
        if not rows or not cols:
            return
            
        top_left_cell_coord = rows[0][0]
        top_right_cell_coord = rows[0][-1]
        bottom_left_cell_coord = rows[-1][0]
        bottom_right_cell_coord = rows[-1][-1]

        # Áp dụng viền
        for cell_coord in rows[0]: ws[cell_coord].border = Border(top=thick_side)
        for cell_coord in rows[-1]: ws[cell_coord].border = Border(bottom=thick_side)
        for cell_coord in cols[0]: ws[cell_coord].border = Border(left=thick_side)
        for cell_coord in cols[-1]: ws[cell_coord].border = Border(right=thick_side)

        # Sửa các góc
        ws[top_left_cell_coord].border = Border(top=thick_side, left=thick_side)
        ws[top_right_cell_coord].border = Border(top=thick_side, right=thick_side)
        ws[bottom_left_cell_coord].border = Border(bottom=thick_side, left=thick_side)
        ws[bottom_right_cell_coord].border = Border(bottom=thick_side, right=thick_side)

    # --- VẼ 4 Ô THÔNG TIN CHÍNH ---
    # Ô 1: SELLER
    apply_outline('D2:H10')
    ws.merge_cells('D3:H10')
    ws['D2'].value = "SELLER"
    ws['D2'].font = font_box_header
    content_seller = ws['D3']
    content_seller.value = ("Tên công ty ABC\n"
                            "123 Đường XYZ, Phường 1, Quận 2\n"
                            "Thành phố Hồ Chí Minh, Việt Nam\n"
                            "TEL: 028-1234-5678\n"
                            "FAX: 028-1234-5679")
    content_seller.alignment = align_top_left
    content_seller.font = font_content

    # Ô 2: INVOICE
    apply_outline('I2:M10')
    ws.merge_cells('I3:M5')
    ws.merge_cells('I7:M10')
    ws['I2'].value = "INVOICE NO. / DATE"
    ws['I2'].font = font_box_header
    ws['I6'].value = "PAYMENT"
    ws['I6'].font = font_box_header
    ws['I3'].value = f"INV-2025-001 / {pd.Timestamp.now().strftime('%B %d, %Y')}"
    ws['I3'].alignment = align_top_left
    ws['I3'].font = font_content
    ws['I7'].value = "T/T in advance"
    ws['I7'].alignment = align_top_left
    ws['I7'].font = font_content

    # Ô 3: BUYER
    apply_outline('D11:H18')
    ws.merge_cells('D12:H18')
    ws['D11'].value = "BUYER"
    ws['D11'].font = font_box_header
    content_buyer = ws['D12']
    content_buyer.value = ("Tên khách hàng DEF\n"
                           "456 Đại lộ JQK, Quận 5\n"
                           "Thành phố New York, Hoa Kỳ\n"
                           "TEL: 212-987-6543")
    content_buyer.alignment = align_top_left
    content_buyer.font = font_content

    # Ô 4: FROM/TO
    apply_outline('I11:M18')
    ws.merge_cells('I12:M13')
    ws.merge_cells('I15:M18')
    ws['I11'].value = "FROM:"
    ws['I11'].font = font_box_header
    ws['I14'].value = "TO:"
    ws['I14'].font = font_box_header
    ws['I12'].value = "Cảng Cát Lái, Việt Nam"
    ws['I12'].alignment = align_top_left
    ws['I12'].font = font_content
    ws['I15'].value = "Cảng Los Angeles, Hoa Kỳ"
    ws['I15'].alignment = align_top_left
    ws['I15'].font = font_content


    # ==============================================================================
    # PHẦN 2: XỬ LÝ DỮ LIỆU VÀ TẠO BẢNG HÀNG HÓA
    # ==============================================================================
    
    start_row = 20  # Bắt đầu từ hàng 20 để có khoảng cách
    start_col = 4   # Bắt đầu từ cột D

    # --- VẼ HEADER CỦA BẢNG ---
    headers = list(data_df.columns)
    ws.append([]) # Thêm một hàng trống trước header
    for c_idx, value in enumerate(headers, start=start_col):
        cell = ws.cell(row=start_row, column=c_idx, value=value)
        cell.font = Font(name='Arial', size=11, bold=True)
        cell.alignment = align_center_wrap
        cell.border = thin_border
        cell.fill = PatternFill(start_color="D9E1F2", end_color="D9E1F2", fill_type="solid")
    
    # --- GHI DỮ LIỆU VÀ GỘP Ô ---
    df_filled = data_df.copy()
    df_filled['pallet_group'] = df_filled['Pallet'].replace('', np.nan).ffill()
    grouped = df_filled.groupby('pallet_group', sort=False)
    
    current_row = start_row + 1
    for _, group in grouped:
        group_data = group.drop(columns=['pallet_group'])
        num_rows_in_group = len(group_data)

        # Ghi từng dòng dữ liệu của group
        for _, row_data in group_data.iterrows():
            row_to_write = list(row_data)
            for c_idx, value in enumerate(row_to_write, start=start_col):
                cell = ws.cell(row=current_row, column=c_idx, value=value)
                cell.border = thin_border
                cell.alignment = align_center_wrap
            current_row += 1
        
        # Gộp ô cho group nếu có nhiều hơn 1 dòng
        if num_rows_in_group > 1:
            row_start_merge = current_row - num_rows_in_group
            cols_to_merge = ['Item No.', 'Pallet', 'G.W (kgs)', 'MEAS. (m)']
            for col_name in cols_to_merge:
                if col_name in headers:
                    col_idx = headers.index(col_name) + start_col
                    ws.merge_cells(start_row=row_start_merge, start_column=col_idx,
                                   end_row=row_start_merge + num_rows_in_group - 1, end_column=col_idx)
                    ws.cell(row_start_merge, col_idx).alignment = align_center_wrap

    # --- ĐIỀU CHỈNH ĐỘ RỘNG CỘT ---
    for i, col_name in enumerate(headers, start=start_col):
        column_letter = get_column_letter(i)
        if col_name == 'Part Name': ws.column_dimensions[column_letter].width = 35
        elif col_name == 'Part No.': ws.column_dimensions[column_letter].width = 25
        elif 'Spec' in col_name: ws.column_dimensions[column_letter].width = 20
        else: ws.column_dimensions[column_letter].width = 14

    # ==============================================================================
    # PHẦN 3: TÍNH TỔNG, GHI FOOTER VÀ CHỮ KÝ
    # ==============================================================================

    total_row_num = current_row + 1 # Tạo một dòng trống
    
    def safe_to_numeric(series):
        return pd.to_numeric(series, errors='coerce').fillna(0)

    # --- TÍNH TOÁN TỔNG CỘNG ---
    total_qty_boxes = safe_to_numeric(data_df["Q'ty (boxes)"]).sum()
    total_qty_pcs = safe_to_numeric(data_df["Q'ty (pcs)"]).sum()
    total_nw = safe_to_numeric(data_df["N.W (kgs)"]).sum()
    total_gw = safe_to_numeric(data_df["G.W (kgs)"]).sum()
    totals_dict = {'boxes': total_qty_boxes, 'pcs': total_qty_pcs, 'nw': total_nw, 'gw': total_gw}

    # --- GHI DÒNG TOTAL ---
    total_label_cell = ws.cell(row=total_row_num, column=start_col, value=f'TOTAL CONTAINER {container_id_num}')
    ws.merge_cells(start_row=total_row_num, start_column=start_col, end_row=total_row_num, end_column=start_col + 4)
    total_label_cell.font = font_bold
    total_label_cell.alignment = align_center
    total_label_cell.border = thin_border

    # Ghi các giá trị tổng
    ws.cell(row=total_row_num, column=headers.index("Q'ty (boxes)") + start_col, value=f"{total_qty_boxes:.2f}").font = font_bold
    ws.cell(row=total_row_num, column=headers.index("Q'ty (pcs)") + start_col, value=f"{total_qty_pcs:.2f}").font = font_bold
    ws.cell(row=total_row_num, column=headers.index("N.W (kgs)") + start_col, value=f"{total_nw:.2f}").font = font_bold
    ws.cell(row=total_row_num, column=headers.index("G.W (kgs)") + start_col, value=f"{total_gw:.2f}").font = font_bold
    
    # Kẻ viền cho các ô tổng
    for c in range(start_col, start_col + len(headers)):
        ws.cell(row=total_row_num, column=c).border = thin_border


    # --- PHẦN CASE MARK ---
    case_mark_row = total_row_num + 3
    ws.cell(row=case_mark_row, column=4, value="CASE MARK").font = font_bold

    details_start_row = case_mark_row + 1
    ws.cell(row=details_start_row,     column=5, value="INVOICE NO.:").font = font_content
    ws.cell(row=details_start_row + 1, column=5, value="BRIGHT MANUFACTURING CO., LTD.").font = font_content
    ws.cell(row=details_start_row + 2, column=5, value="MADE IN VIETNAM").font = font_content
    ws.cell(row=details_start_row,     column=8, value="Package:").font = font_content
    ws.cell(row=details_start_row + 1, column=8, value="Quantity:").font = font_content
    ws.cell(row=details_start_row + 2, column=8, value="N.W:").font = font_content
    ws.cell(row=details_start_row + 3, column=8, value="G.W:").font = font_content

    ws.cell(row=details_start_row,     column=9, value=f"{int(totals_dict['boxes'])} BOXES").font = font_content
    ws.cell(row=details_start_row + 1, column=9, value=f"{int(totals_dict['pcs'])} PCS").font = font_content
    ws.cell(row=details_start_row + 2, column=9, value=f"{totals_dict['nw']:.2f} KGS").font = font_content
    ws.cell(row=details_start_row + 3, column=9, value=f"{totals_dict['gw']:.2f} KGS").font = font_content

    # --- PHẦN CHỮ KÝ ---
    signature_label_row = details_start_row + 8 
    signature_name_row = signature_label_row + 4 
    
    ws.cell(row=signature_label_row, column=11, value="Signature:").font = font_content
    signature_alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)
    ws.row_dimensions[signature_name_row].height = 35

    # Chữ ký 1
    ws.merge_cells(start_row=signature_name_row, start_column=10, end_row=signature_name_row, end_column=12) 
    cell_thu = ws.cell(row=signature_name_row, column=10)
    cell_thu.value = "NGUYEN DUC THU\nBusiness Director"
    cell_thu.font = font_content
    cell_thu.alignment = signature_alignment
    for i in range(10, 13): ws.cell(row=signature_name_row, column=i).border = border_top_only

    # Chữ ký 2
    ws.merge_cells(start_row=signature_name_row, start_column=15, end_row=signature_name_row, end_column=17) 
    cell_giang = ws.cell(row=signature_name_row, column=15)
    cell_giang.value = "LE MINH GIANG\nGeneral Director"
    cell_giang.font = font_content
    cell_giang.alignment = signature_alignment
    for i in range(15, 18): ws.cell(row=signature_name_row, column=i).border = border_top_only


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
    try:
        data = request.get_json()
        optimized_results = data.get('optimized_results') # Dữ liệu các container đã tối ưu
        original_filepath = data.get('original_filepath') # Đường dẫn file Excel gốc
        sheet_name = data.get('sheet_name')             # Tên sheet gốc

        if not all([optimized_results, original_filepath, sheet_name]):
            return jsonify({"success": False, "error": "Thiếu dữ liệu để tạo packing list."}), 400

        # Đọc dữ liệu thô từ file gốc một lần để tra cứu
        df_raw = pd.read_excel(
            original_filepath, sheet_name=sheet_name, header=None, skiprows=5,
            usecols=[1, 2, 5, 6, 7, 10, 48],
            names=['Part No', 'Part Name', 'QtyPerBox', 'WeightPerPc_Raw', 'BoxPerPallet', 'GrossWeightPerPallet', 'BoxSpec']
        ).fillna('')
        df_raw['lookup_key'] = df_raw['Part No'].astype(str) + '||' + df_raw['Part Name'].astype(str)
        raw_data_map = df_raw.set_index('lookup_key').to_dict('index')

        # Tạo một workbook mới trong bộ nhớ
        wb = Workbook()
        wb.remove(wb.active) # Xóa sheet mặc định

        # Lặp qua từng container để tạo một sheet packing list riêng
        for container_data in optimized_results:
            container_id_str = container_data['id']
            container_id_num = container_id_str.split('_')[-1]
            
            # Tạo sheet mới cho container
            ws = wb.create_sheet(title=f"PKL_Cont_{container_id_num}")

            # Chuẩn bị dữ liệu cho container hiện tại
            df_for_pkl = _prepare_data_for_pkl(container_data, raw_data_map)
            
            # Ghi dữ liệu và định dạng vào sheet (hàm này cần được triển khai chi tiết)
            # Vì logic vẽ sheet khá phức tạp, để đơn giản, tôi sẽ giả định một hàm
            # write_packing_list_to_sheet đã được định nghĩa ở trên.
            write_packing_list_to_sheet(ws, df_for_pkl, container_id_num)

        # Lưu workbook vào buffer bộ nhớ
        excel_buffer = io.BytesIO()
        wb.save(excel_buffer)
        excel_buffer.seek(0)
        
        # Dọn dẹp
        gc.collect()

        # Trả về file Excel cho người dùng tải xuống
        return send_file(
            excel_buffer,
            as_attachment=True,
            download_name=f'PackingList_{sheet_name}.xlsx',
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"success": False, "error": f"Lỗi hệ thống khi tạo packing list: {str(e)}"}), 500

# --- CHẠY ỨNG DỤNG ---
if __name__ == '__main__':
    from waitress import serve
    print("Starting server with Waitress on http://0.0.0.0:5001")
    serve(app, host='0.0.0.0', port=5001)