# test_def.py
from data_processor import *
# Giả sử bạn đã thêm hàm preprocess_oversized_pallets vào file data_processor.py

# --- HÀM MAIN ĐỂ CHẠY VÀ HIỂN THỊ KẾT QUẢ ---
if __name__ == "__main__":
    # --- BƯỚC 1: Cấu hình ---
    file_path = "C:\\Users\\emily\\Documents\\Zalo Received Files\\Chia cont- testing.xlsx"
    sheet_name = "23 Jun "
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
        print("\n" + "#"*80)
        print("PHÂN TÍCH HOÀN TẤT.")