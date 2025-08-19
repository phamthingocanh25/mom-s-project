import pandas as pd
import openpyxl
from openpyxl import Workbook
import os
import sys

# --- IMPORT CÁC HÀM TỪ FILE CỦA BẠN ---
# Để mã này chạy được, bạn cần đặt file test này cùng cấp với data_processor.py và app.py
# hoặc đảm bảo chúng có thể được import.

try:
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
    from app import (
        _generate_final_pkl_dataframe ,
        write_packing_list_to_sheet
    )
    print("INFO: Đã import thành công các hàm từ data_processor.py và app.py.")
except ImportError as e:
    print(f"ERROR: Không thể import các hàm cần thiết. Hãy chắc chắn rằng file test này")
    print(f"       được đặt cùng thư mục với 'app.py' và 'data_processor.py'.")
    print(f"Lỗi chi tiết: {e}")
    # Thoát nếu không import được
    sys.exit()

def run_optimization_process(filepath, sheet_name, company1_name, company2_name):
    """
    Thực thi toàn bộ quy trình tối ưu hóa pallet.
    """
    print("\n" + "="*20 + " BẮT ĐẦU QUY TRÌNH TỐI ƯU HÓA " + "="*20)

    # Kiểm tra file có tồn tại không
    if not os.path.exists(filepath):
        print(f"FATAL ERROR: Không tìm thấy file tại đường dẫn: '{filepath}'")
        print("Vui lòng kiểm tra lại biến INPUT_EXCEL_FILE.")
        return None

    # BƯỚC 1: Tải và chuẩn bị dữ liệu pallet
    print(f"\n[BƯỚC 1]: Tải dữ liệu từ '{filepath}' (Sheet: '{sheet_name}')...")
    all_pallets, error = load_and_prepare_pallets(filepath, sheet_name)
    if error:
        print(f"ERROR: {error}")
        return None
    if not all_pallets:
        print("WARNING: Không có dữ liệu pallet hợp lệ nào được tải lên.")
        return None
    print(f"-> Đã tải {len(all_pallets)} pallet.")

    container_id_counter = {'count': 1}

    # BƯỚC 2: Tiền xử lý pallet quá khổ
    print("\n[BƯỚC 2]: Tiền xử lý pallet quá khổ...")
    pre_packed_containers, pallets_to_process = preprocess_oversized_pallets(all_pallets, container_id_counter)
    print(f"-> Đã đóng gói sẵn {len(pre_packed_containers)} container từ pallet quá khổ.")
    print(f"-> Còn lại {len(pallets_to_process)} pallet để xử lý tiếp.")

    # BƯỚC 3: Phân tách pallet theo công ty
    print("\n[BƯỚC 3]: Phân tách pallet theo công ty...")
    pallets_c1, pallets_c2 = separate_pallets_by_company(pallets_to_process, company1_name, company2_name)
    print(f"-> Công ty 1 ({company1_name}): {len(pallets_c1)} pallet.")
    print(f"-> Công ty 2 ({company2_name}): {len(pallets_c2)} pallet.")

    # BƯỚC 4: Xử lý cho từng công ty (Giai đoạn 0, 1, 2)
    print("\n[BƯỚC 4]: Xử lý cho từng công ty...")
    # Công ty 1
    print("--- Đang xử lý Công ty 1 ---")
    int_p1, comb_p1, float_p1 = preprocess_and_classify_pallets(pallets_c1)
    packed_containers_c1 = layered_priority_packing(int_p1, comb_p1, float_p1, company1_name, container_id_counter)
    final_containers_c1, cross_ship_pallets_c1 = defragment_and_consolidate(packed_containers_c1)
    print(f"-> C1: {len(final_containers_c1)} container hoàn thiện, {len(cross_ship_pallets_c1)} pallet chờ gửi chéo.")

    # Công ty 2
    print("--- Đang xử lý Công ty 2 ---")
    int_p2, comb_p2, float_p2 = preprocess_and_classify_pallets(pallets_c2)
    packed_containers_c2 = layered_priority_packing(int_p2, comb_p2, float_p2, company2_name, container_id_counter)
    final_containers_c2, cross_ship_pallets_c2 = defragment_and_consolidate(packed_containers_c2)
    print(f"-> C2: {len(final_containers_c2)} container hoàn thiện, {len(cross_ship_pallets_c2)} pallet chờ gửi chéo.")

    # BƯỚC 5: Giai đoạn 3 - Vận chuyển chéo và hoàn thiện
    print("\n[BƯỚC 5]: Giai đoạn 3 - Vận chuyển chéo và hoàn thiện...")
    final_optimized_containers = phase_3_cross_shipping_and_finalization(
        final_containers_c1, cross_ship_pallets_c1,
        final_containers_c2, cross_ship_pallets_c2,
        container_id_counter
    )

    # Gộp các container đã đóng gói sẵn vào kết quả cuối cùng
    all_final_containers = pre_packed_containers + final_optimized_containers
    print(f"-> Tổng số container cuối cùng: {len(all_final_containers)}.")

    # BƯỚC 6: Định dạng kết quả
    print("\n[BƯỚC 6]: Định dạng kết quả đầu ra...")
    formatted_results = generate_response_data(all_final_containers)
    
    print("="*24 + " KẾT THÚC TỐI ƯU HÓA " + "="*25)
    return formatted_results


def run_packing_list_generation(optimized_results, original_filepath, sheet_name, output_filename):
    """
    Thực thi quy trình tạo Packing List từ kết quả tối ưu hóa.
    """
    print("\n" + "="*20 + " BẮT ĐẦU TẠO PACKING LIST " + "="*21)

    if not optimized_results or not optimized_results.get('results'):
        print("ERROR: Không có kết quả tối ưu hóa để tạo packing list.")
        return

    # BƯỚC 1: Tải và ánh xạ dữ liệu thô cho PKL
    print("\n[BƯỚC 1]: Tải và ánh xạ dữ liệu thô cho Packing List...")
    raw_data_map, error = load_and_map_raw_data_for_pkl(original_filepath, sheet_name)
    if error:
        print(f"ERROR: {error}")
        return
    print(f"-> Đã tạo map dữ liệu thô với {len(raw_data_map)} sản phẩm duy nhất.")

    # BƯỚC 2: Tạo file Excel và các sheet
    print("\n[BƯỚC 2]: Tạo file Excel và ghi dữ liệu cho từng container...")
    wb = Workbook()
    wb.remove(wb.active)
    pallet_counter = {'item_no': 1, 'pallet_no': 1}
    
    # --- START: SỬA LỖI ---
    # Khởi tạo dictionary để lưu trữ tổng dồn, giống như trong app.py
    cumulative_totals = {'pcs': 0.0, 'nw': 0.0, 'gw': 0.0}
    # --- END: SỬA LỖI ---

    containers_data = optimized_results['results']
    for container_data in containers_data:
        container_id_str = container_data.get('id', 'Unknown')
        # Trích xuất số từ ID container để đặt tên cho sheet
        container_id_num = ''.join(filter(str.isdigit, container_id_str))
        if not container_id_num:
           container_id_num = container_id_str.split('_')[-1]

        sheet_title = f"PKL_Cont_{container_id_num}"
        print(f"--- Đang xử lý {sheet_title} ---")
        ws = wb.create_sheet(title=sheet_title)

        # Chuẩn bị dữ liệu và ghi vào sheet
        df_for_pkl = _generate_final_pkl_dataframe(container_data, raw_data_map, pallet_counter)
        
        # --- START: SỬA LỖI ---
        # Cập nhật các giá trị tổng dồn sau khi xử lý mỗi container
        cumulative_totals['pcs'] += df_for_pkl["Q'ty (pcs)"].sum()
        cumulative_totals['nw'] += df_for_pkl['N.W (kgs)'].sum()
        cumulative_totals['gw'] += df_for_pkl['G.W (kgs)'].sum()
        
        # Tổng số pallet tính đến thời điểm hiện tại
        current_cumulative_pallets = pallet_counter['pallet_no'] - 1

        # Cập nhật lệnh gọi hàm để truyền đủ 7 tham số
        write_packing_list_to_sheet(
            ws, 
            df_for_pkl, 
            container_id_num,
            current_cumulative_pallets,
            cumulative_totals['pcs'],
            cumulative_totals['nw'],
            cumulative_totals['gw']
        )
        # --- END: SỬA LỖI ---
        print(f"-> Đã ghi dữ liệu cho {sheet_title}.")


    # BƯỚC 3: Lưu file Excel kết quả
    print(f"\n[BƯỚC 3]: Lưu kết quả vào file '{output_filename}'...")
    try:
        wb.save(output_filename)
        print(f"SUCCESS: Đã tạo file Packing List thành công: '{output_filename}'")
    except Exception as e:
        print(f"ERROR: Không thể lưu file Excel. Lỗi: {e}")

    print("="*24 + " KẾT THÚC TẠO PACKING LIST " + "="*24)


if __name__ == '__main__':
    # --- CÁC THAM SỐ CẤU HÌNH ---
    # !!! QUAN TRỌNG: THAY ĐỔI CÁC GIÁ TRỊ DƯỚI ĐÂY !!!
    
    # 1. Đường dẫn file Excel dữ liệu thô (giữ nguyên)
    INPUT_EXCEL_FILE = "C:\\Users\\emily\\Downloads\\Chia-cont-testing (1) (1) (1).xlsx"
    
    # 2. Tên Sheet muốn xử lý (giữ nguyên)
    SHEET_NAME = "18.08"

    # 3. Tên hai công ty (giữ nguyên)
    COMPANY_1_NAME = "1.0"
    COMPANY_2_NAME = "2.0"
    
    # -------------------------------------------------------------------------
    # --- PHẦN SỬA ĐỔI ĐỂ LƯU FILE VÀO VỊ TRÍ CỤ THỂ ---
    # -------------------------------------------------------------------------

    # 4. CHỌN THƯ MỤC LƯU FILE: Dán đường dẫn thư mục bạn muốn lưu vào đây.
    #    LƯU Ý: Trên Windows, hãy sử dụng dấu gạch chéo kép (\\) hoặc dấu gạch chéo đơn (/).
    #    Ví dụ: "C:\\Users\\emily\\Desktop" hoặc "C:/Users/emily/Documents/PackingLists"
    OUTPUT_DIRECTORY = "C:\\Users\\emily\\Downloads"

    # Script sẽ tự động tạo thư mục này nếu nó chưa tồn tại
    if not os.path.exists(OUTPUT_DIRECTORY):
        os.makedirs(OUTPUT_DIRECTORY)

    # Tên file vẫn được tạo tự động dựa trên tên sheet
    output_filename = f"Generated_Packing_List_for_{SHEET_NAME}.xlsx"

    # Kết hợp đường dẫn thư mục và tên file để có đường dẫn đầy đủ và chính xác
    OUTPUT_PKL_FILE = os.path.join(OUTPUT_DIRECTORY, output_filename)
    
    print(f"INFO: File Packing List sẽ được lưu tại: {OUTPUT_PKL_FILE}")

    # --- KẾT THÚC PHẦN SỬA ĐỔI ---


    # --- CHẠY QUY TRÌNH TỐI ƯU HÓA ---
    # (Phần này giữ nguyên không thay đổi)
    optimization_result = run_optimization_process(
        filepath=INPUT_EXCEL_FILE,
        sheet_name=SHEET_NAME,
        company1_name=COMPANY_1_NAME,
        company2_name=COMPANY_2_NAME
    )

    # --- CHẠY QUY TRÌNH TẠO PACKING LIST ---
    # (Phần này giữ nguyên không thay đổi)
    if optimization_result:
        run_packing_list_generation(
            optimized_results=optimization_result,
            original_filepath=INPUT_EXCEL_FILE,
            sheet_name=SHEET_NAME,
            output_filename=OUTPUT_PKL_FILE # Sử dụng biến đã được cập nhật ở trên
        )
    else:
        print("\nERROR: Quy trình tối ưu hóa thất bại. Bỏ qua bước tạo Packing List.")