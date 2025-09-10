# test_p1.py
from data_processor import *
import pandas as pd
import math
import re

# --- HÀM MAIN ĐỂ CHẠY VÀ HIỂN THỊ KẾT QUẢ ---
if __name__ == "__main__":
    # --- BƯỚC 1: Cấu hình ---
    file_path = "C:\\Users\\admin\\Downloads\\Chia-cont-2025-filled-data-1.xlsx"
    sheet_name = "28 Apr"
    COMPANY_1 = "1"
    COMPANY_2 = "2"

    # --- BƯỚC 2: Tải và chuẩn bị dữ liệu ---
    print(f"Bắt đầu phân tích sheet: '{sheet_name}'...")
    all_pallets, error_message = load_and_prepare_pallets(file_path, sheet_name)
    
    # Tải dữ liệu thô cần thiết cho các giai đoạn tối ưu hóa
    raw_data_map, raw_data_error = load_and_map_raw_data_for_pkl(file_path, sheet_name)

    if error_message or raw_data_error:
        print(f"\nĐã xảy ra lỗi:")
        if error_message:
            print(f" - Lỗi tải pallet: {error_message}")
        if raw_data_error:
            print(f" - Lỗi tải dữ liệu thô: {raw_data_error}")
    else:
        print(f"Đã tải thành công {len(all_pallets)} pallet và {len(raw_data_map)} bản ghi dữ liệu thô.")
        
        # KHỞI TẠO CÁC BỘ ĐẾM TOÀN CỤC
        global_container_counter = {'count': 1}
        global_combination_counter = {'count': 1}

        # --- BƯỚC 3: Tách pallet theo công ty ---
        pallets_co1, pallets_co2 = separate_pallets_by_company(
            all_pallets, COMPANY_1, COMPANY_2
        )
        
        ###########################    GIAI ĐOẠN 0: TÁCH PALLET   ########################
        print("\n" + "="*80)
        print("KẾT QUẢ GIAI ĐOẠN 0: TÁCH PALLET THÀNH CÁC THÀNH PHẦN NGUYÊN VÀ LẺ")
        print("="*80)

        # Xử lý Công ty 1
        print(f"\n--- Tách pallet cho Công ty: '{COMPANY_1}' ({len(pallets_co1)} pallet thô) ---")
        integer_components_1, fractional_components_1 = split_pallets_into_components(pallets_co1)
        print(f"-> Kết quả: {len(integer_components_1)} thành phần nguyên, {len(fractional_components_1)} thành phần lẻ.")
        
        # Xử lý Công ty 2
        print(f"\n--- Tách pallet cho Công ty: '{COMPANY_2}' ({len(pallets_co2)} pallet thô) ---")
        integer_components_2, fractional_components_2 = split_pallets_into_components(pallets_co2)
        print(f"-> Kết quả: {len(integer_components_2)} thành phần nguyên, {len(fractional_components_2)} thành phần lẻ.")

        ####################    GIAI ĐOẠN 0.5: GỘP PALLET LẺ (LOGIC MỚI)    #########################
        print("\n" + "="*80)
        print("KẾT QUẢ GIAI ĐOẠN 0.5: GỘP CÁC THÀNH PHẦN LẺ THÀNH PALLET GỘP")
        print("="*80)

        # Chạy Giai đoạn 0.5 cho Công ty 1
        print(f"\n--- Gộp pallet lẻ cho Công ty: '{COMPANY_1}' ---")
        combined_pallets_1, single_float_pallets_1 = phase_0_5_combine_fractional_pallets(
            fractional_components_1,
            raw_data_map,
            global_combination_counter
        )
        print("  DANH SÁCH PALLET GỘP ĐÃ TẠO:")
        if not combined_pallets_1: print("  -> Không có.")
        for p in combined_pallets_1: print(f"    - {p}")

        # Chạy Giai đoạn 0.5 cho Công ty 2
        print(f"\n--- Gộp pallet lẻ cho Công ty: '{COMPANY_2}' ---")
        combined_pallets_2, single_float_pallets_2 = phase_0_5_combine_fractional_pallets(
            fractional_components_2,
            raw_data_map,
            global_combination_counter
        )
        print("  DANH SÁCH PALLET GỘP ĐÃ TẠO:")
        if not combined_pallets_2: print("  -> Không có.")
        for p in combined_pallets_2: print(f"    - {p}")
        
        #####################    GIAI ĐOẠN 1: XẾP HÀNG SƠ BỘ    ######################################
        print("\n" + "="*80)
        print("KẾT QUẢ GIAI ĐOẠN 1: XẾP HÀNG ƯU TIÊN THEO LỚP")
        print("="*80)

        # Chạy Giai đoạn 1 cho Công ty 1
        print(f"\n>>> Bắt đầu Giai đoạn 1 cho {COMPANY_1}...")
        initial_containers_c1 = layered_priority_packing(
            pallets_integer=integer_components_1,
            pallets_combined=combined_pallets_1,
            pallets_single_float=single_float_pallets_1,
            main_company=COMPANY_1, 
            container_id_counter=global_container_counter,
            initial_containers=[]
        )

        # Chạy Giai đoạn 1 cho Công ty 2
        print(f"\n>>> Bắt đầu Giai đoạn 1 cho {COMPANY_2}...")
        initial_containers_c2 = layered_priority_packing(
            pallets_integer=integer_components_2,
            pallets_combined=combined_pallets_2,
            pallets_single_float=single_float_pallets_2,
            main_company=COMPANY_2, 
            container_id_counter=global_container_counter,
            initial_containers=[]
        )
        print("\nHoàn thành Giai đoạn 1. Các container đã được xếp sơ bộ.")
    
        #####################         GIAI ĐOẠN 2: TỐI ƯU HÓA NỘI BỘ         #########################
        print("\n" + "="*80)
        print("BẮT ĐẦU GIAI ĐOẠN 2: TÁI CẤU TRÚC & HỢP NHẤT NỘI BỘ")
        print("="*80)
        
        print(f"\n>>> Đang chạy tối ưu hóa cho Công ty: '{COMPANY_1}'...")
        final_containers_c1, pallets_chuyen_di_c1 = defragment_and_consolidate(initial_containers_c1)
        print(f"-> Kết quả: {len(final_containers_c1)} container hiệu quả, {len(pallets_chuyen_di_c1)} pallet chờ vận chuyển chéo.")

        print(f"\n>>> Đang chạy tối ưu hóa cho Công ty: '{COMPANY_2}'...")
        final_containers_c2, pallets_chuyen_di_c2 = defragment_and_consolidate(initial_containers_c2)
        print(f"-> Kết quả: {len(final_containers_c2)} container hiệu quả, {len(pallets_chuyen_di_c2)} pallet chờ vận chuyển chéo.")

        #####################         GIAI ĐOẠN 3: VẬN CHUYỂN CHÉO         #########################
        print("\n" + "="*80)
        print("BẮT ĐẦU GIAI ĐOẠN 3: VẬN CHUYỂN CHÉO & HOÀN THIỆN")
        print("="*80)
        
        final_containers_after_phase3 = phase_3_cross_shipping_and_finalization(
            final_containers_c1, pallets_chuyen_di_c1,
            final_containers_c2, pallets_chuyen_di_c2,
            global_container_counter,
            raw_data_map
        )

        #####################         GIAI ĐOẠN 4: TỐI ƯU HÓA HỢP NHẤT CUỐI CÙNG (MỚI)         #########################
        print("\n" + "="*80)
        print("BẮT ĐẦU GIAI ĐOẠN 4: TỐI ƯU HÓA HỢP NHẤT CUỐI CÙNG")
        print("="*80)

        fully_optimized_containers = phase_4_final_consolidation(
            final_containers_after_phase3,
            raw_data_map
        )
        
        # Gán kết quả cuối cùng để chuẩn bị in
        all_final_containers = fully_optimized_containers
        
        # --- IN KẾT QUẢ CUỐI CÙNG ---
        print("\n\n" + "#"*80)
        print("KẾT QUẢ XẾP HÀNG CUỐI CÙNG (SAU KHI TỐI ƯU HÓA)")
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
                print(f"  - Tổng Pallet Logic:  {container.total_logical_pallets} / {int(MAX_PALLETS)}")
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
        for container in sorted(all_final_containers, key=lambda c: int(c.id.split('_')[-1])):
            for pallet in container.pallets:
                if pallet.is_combined and pallet.is_split:
                    found_split_combined = True
                    print("\n" + "-"*60)
                    print(f"Phát hiện Pallet Gộp Bị Tách trong CONTAINER ID: {container.id}")
                    print(f"  -> PHẦN PALLET HIỆN TẠI: {pallet}")
                    print("     Thành phần bên trong phần này:")
                    if not pallet.original_pallets:
                        print("       (Không có thông tin thành phần)")
                    else:
                        consolidated_originals = consolidate_sub_pallets(pallet.original_pallets)
                        for original in sorted(consolidated_originals, key=lambda p: p.id):
                            print(f"       - {original}")
        
        if not found_split_combined:
            print("\nKhông tìm thấy pallet gộp nào bị tách trong kết quả cuối cùng.")

        print("\n" + "#"*80)
        print("PHÂN TÍCH HOÀN TẤT.")