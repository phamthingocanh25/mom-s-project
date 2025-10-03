from data_processor import *
import pandas as pd
import math
import re
from collections import Counter
import copy

# --- HÀM HỖ TRỢ IN ẤN TRẠNG THÁI (ĐÃ NÂNG CẤP) ---
def print_container_status(containers, step_name, integer_wait_list=None, fractional_wait_list=None):
    """
    In ra trạng thái chi tiết của container VÀ các danh sách pallet đang chờ.
    """
    print("\n" + "="*50)
    print(f"| TRẠNG THÁI HỆ THỐNG SAU: {step_name.upper()} |")
    print("="*50)
    
    # 1. In trạng thái các container
    if not containers:
        print("\n--> Chưa có container nào được tạo.")
    else:
        print("\n--- CHI TIẾT CÁC CONTAINER ---")
        sorted_containers = sorted(containers, key=lambda c: int(re.sub(r'[^0-9]', '', c.id)))
        for container in sorted_containers:
            print(f"\n  --- Container ID: {container.id} (Cty: {container.main_company}) ---")
            print(f"   - Tải trọng: {container.total_quantity:.2f}/{MAX_PALLETS} (qty) | {container.total_weight:.2f}/{MAX_WEIGHT} (wgt)")
            print(f"   - Số dòng P/L: {container.total_logical_pallets}/{int(MAX_PALLETS)}")
            print("   - Pallets bên trong:")
            if not container.pallets:
                print("     -> (Trống)")
            else:
                sorted_pallets = sorted(container.pallets, key=lambda p: (
                    int(re.sub(r'[^0-9]', '', (p.split_from_id if p.split_from_id else p.id))), p.id
                ))
                for p in sorted_pallets:
                    type_info = ""
                    if p.is_combined: type_info += " [Gộp]"
                    if p.is_split: type_info += f" [Tách từ {p.split_from_id}]"
                    if p.is_cross_ship: type_info += f" [Xếp chéo từ Cty {p.company}]"
                    print(f"     -> {p}{type_info}")

    # 2. In danh sách chờ pallet nguyên
    if integer_wait_list is not None:
        print("\n--- DANH SÁCH PALLET NGUYÊN ĐANG CHỜ ---")
        if not integer_wait_list:
            print("   -> (Trống)")
        else:
            sorted_integer_wait_list = sorted(integer_wait_list, key=lambda p: int(re.sub(r'[^0-9]', '', p.id)))
            for p in sorted_integer_wait_list:
                print(f"   -> {p}")

    # 3. In danh sách chờ pallet lẻ
    if fractional_wait_list is not None:
        print("\n--- DANH SÁCH PALLET LẺ/GỘP ĐANG CHỜ ---")
        if not fractional_wait_list:
            print("   -> (Trống)")
        else:
            sorted_fractional_wait_list = sorted(fractional_wait_list, key=lambda p: int(re.sub(r'[^0-9]', '', p.id)))
            for p in sorted_fractional_wait_list:
                print(f"   -> {p}")

    print("\n" + "="*50 + "\n")


# --- HÀM MAIN ĐỂ CHẠY VÀ HIỂN THỊ KẾT QUẢ ---
if __name__ == "__main__":
    # --- BƯỚC 1 & 2: Cấu hình và Tải dữ liệu ---Chia-cont-testing (1) (1) (1).xlsx    Chia-cont-2025-filled-data-1.xlsx
    file_path = "C:\\Users\\admin\\Downloads\\Chia cont - 2025(AutoRecovered).xlsx"
    sheet_name = "13Oct"
    COMPANY_1 = "1"
    COMPANY_2 = "2"
    
    print(f"Bắt đầu phân tích sheet: '{sheet_name}'...")
    all_pallets, error_message = load_and_prepare_pallets(file_path, sheet_name)

    if error_message:
        print(f"Lỗi tải pallet: {error_message}")
    else:
        print(f"Đã tải thành công {len(all_pallets)} pallet.")

        # --- BƯỚC 2 (LOGIC MỚI): TÁCH TOÀN BỘ PALLET THÀNH NGUYÊN VÀ LẺ NGAY TỪ ĐẦU ---
        print("\n# BƯỚC 2: TÁCH TOÀN BỘ PALLET THÀNH PHẦN NGUYÊN VÀ LẺ #")
        integer_pallets, fractional_pallets = split_integer_fractional_pallets(all_pallets)
        print(f" -> Đã tách thành {len(integer_pallets)} pallet nguyên và {len(fractional_pallets)} pallet lẻ.")

        # --- BƯỚC 3 (LOGIC MỚI): XỬ LÝ PALLET QUÁ KHỔ TỪ DANH SÁCH NGUYÊN ---
        print("\n# BƯỚC 3: XỬ LÝ PALLET NGUYÊN QUÁ KHỔ #")
        # Hàm này sẽ tìm các pallet quá khổ trong `integer_pallets`, chia nhỏ chúng và
        # trả về các container ĐÃ ĐƯỢC LẤP ĐẦY và danh sách các pallet nguyên CÓ KÍCH THƯỚC BÌNH THƯỜNG.
        oversized_containers, regular_sized_integer_pallets, container_id_counter = handle_all_oversized_pallets(
            all_pallets=integer_pallets, # Chỉ xử lý trên danh sách pallet nguyên
            start_container_id=1
        )
        # Các container được tạo ở đây là container cuối cùng, không cần phải làm rỗng nữa.
        print_container_status(oversized_containers, "BƯỚC 3: XỬ LÝ PALLET QUÁ KHỔ")

        # --- BƯỚC 4 (LOGIC MỚI): XẾP CÁC PALLET NGUYÊN CÒN LẠI ---
        print("\n# BƯỚC 4: XẾP PALLET NGUYÊN CÓ KÍCH THƯỚC BÌNH THƯỜNG #")
        # Bắt đầu với các container đã được tạo từ bước xử lý hàng quá khổ.
        final_containers = list(oversized_containers)
        
        # Bây giờ, chỉ cần xếp các pallet nguyên có kích thước bình thường vào các container hiện có hoặc tạo mới.
        final_containers, unplaced_integer_pallets, container_id_counter = pack_integer_pallets(
            regular_sized_integer_pallets, # Chỉ xếp các pallet nguyên còn lại
            final_containers, 
            container_id_counter
        )
        print_container_status(
            containers=final_containers,
            step_name="BƯỚC 4: XẾP PALLET NGUYÊN LẦN ĐẦU",
            integer_wait_list=unplaced_integer_pallets
        )

        # --- BƯỚC 5: GỘP VÀ XẾP PALLET LẺ (KHÔNG ĐỔI) ---
        print("\n# BƯỚC 5: GỘP VÀ XẾP PALLET LẺ #")
        print(f"==> Tổng số pallet lẻ cần xử lý: {len(fractional_pallets)}")
        combined_pallets, uncombined_pallets = combine_fractional_pallets(fractional_pallets)
        pallets_to_pack_fractional = combined_pallets + uncombined_pallets
        unplaced_fractional_pallets = pack_fractional_pallets(pallets_to_pack_fractional, final_containers)
        print_container_status(
            containers=final_containers,
            step_name="BƯỚC 5: XẾP PALLET LẺ/GỘP LẦN ĐẦU",
            integer_wait_list=unplaced_integer_pallets,
            fractional_wait_list=unplaced_fractional_pallets
        )

        # --- BƯỚC 6 (MỚI): VÒNG LẶP XỬ LÝ TOÀN BỘ PALLET CHỜ ---
        print("\n# BƯỚC 6 (MỚI): VÒNG LẶP XỬ LÝ TOÀN BỘ PALLET CHỜ #")
        loop_counter = 0
        while unplaced_integer_pallets or unplaced_fractional_pallets:
            loop_counter += 1
            print(f"\n--- Bắt đầu vòng lặp xử lý pallet chờ lần thứ {loop_counter} ---")

            # Cơ chế an toàn: Nếu số pallet chờ không thay đổi sau một vòng lặp, hãy thoát ra
            pallets_before_iteration = len(unplaced_integer_pallets) + len(unplaced_fractional_pallets)

            # === 6.1: ƯU TIÊN XỬ LÝ DANH SÁCH PALLET NGUYÊN CHỜ ===
            # Giữ nguyên toàn bộ logic của Bước 6 cũ
            if unplaced_integer_pallets:
                print(f"-> Đang xử lý {len(unplaced_integer_pallets)} pallet NGUYÊN trong danh sách chờ...")
                # 6.1.1: Cố gắng xếp vào container cùng công ty
                unplaced_integer_pallets = try_pack_pallets_into_same_company_containers(unplaced_integer_pallets, final_containers)

                if unplaced_integer_pallets:
                    # 6.1.2: Kiểm tra khả năng cross-ship toàn bộ và áp dụng logic phù hợp
                    can_cross_ship_all = check_cross_ship_capacity_for_list(unplaced_integer_pallets, final_containers, unplaced_fractional_pallets) 
                    
                    if can_cross_ship_all:
                        # Nếu có thể cross-ship hết, dùng logic chia tách thông minh để tối ưu
                        print(" -> Đủ chỗ để cross-ship. Áp dụng logic chia tách thông minh...")
                        unplaced_integer_pallets = handle_unplaced_pallets_with_smart_splitting(unplaced_integer_pallets, final_containers, unplaced_fractional_pallets)
                        
                        # Giải pháp cuối nếu smart splitting vẫn còn sót
                        if unplaced_integer_pallets:
                            final_containers, container_id_counter = handle_remaining_integers_iteratively(unplaced_integer_pallets, final_containers, container_id_counter)
                            unplaced_integer_pallets = []
                    else:
                        # Nếu không thể cross-ship toàn bộ, hãy thử tối ưu hóa từng phần trước.
                        unplaced_integer_pallets = attempt_partial_cross_ship(
                                   unplaced_integer_pallets, final_containers, unplaced_fractional_pallets
                                           )
                        
                        # CHỈ KHI bước tối ưu hóa trên vẫn còn lại pallet, lúc này mới tạo container mới.
                        if unplaced_integer_pallets:
                            print(" -> Sau khi tối ưu vẫn còn pallet. Tạo container mới một cách tiết kiệm...")
                            unplaced_integer_pallets, final_containers, container_id_counter = create_and_pack_one_new_container(
                             unplaced_integer_pallets, 
                            final_containers, 
                          container_id_counter,
                           unplaced_fractional_pallets  # Thêm tham số này để hàm có thể đưa ra quyết định ưu tiên
                              )

            # === 6.2: XỬ LÝ DANH SÁCH PALLET LẺ/GỘP CHỜ ===
            if unplaced_fractional_pallets:
                print(f"-> Đang xử lý {len(unplaced_fractional_pallets)} pallet LẺ/GỘP trong danh sách chờ...")
                
                # 6.2.1: Thử xếp nguyên vẹn pallet vào container cùng công ty trước (Ưu tiên hàng đầu).
                unplaced_fractional_pallets = try_pack_unplaced_fractionals_same_company(
                    unplaced_fractional_pallets, final_containers
                )

                # 6.2.2: Nếu vẫn còn, dùng logic lắp ghép nâng cao (xé nhỏ pallet để lấp đầy chỗ trống).
                if unplaced_fractional_pallets:
                    unplaced_fractional_pallets = repack_unplaced_pallets(unplaced_fractional_pallets, final_containers)
                
                # 6.2.3 (MỚI): Nếu lắp ghép vẫn không hết, bắt buộc phải chia nhỏ tỉ mỉ và xếp vào bất cứ đâu.
                if unplaced_fractional_pallets:
                   final_containers, container_id_counter, unplaced_fractional_pallets = split_and_fit_leftovers(
                           unplaced_fractional_pallets, final_containers, container_id_counter
                   )
                   
                # 6.2.4 (MỚI): Cuối cùng, mới thử đến phương án xếp chéo (cross-ship) nếu vẫn còn.
                if unplaced_fractional_pallets:
   # Sửa lại để nhận 2 giá trị và truyền đủ 4 tham số
                  unplaced_fractional_pallets, container_id_counter = cross_ship_remaining_pallets(
                  unplaced_pallets=unplaced_fractional_pallets, 
                  containers=final_containers, 
                  next_container_id=container_id_counter,
                  unplaced_integer_pallets=unplaced_integer_pallets # <-- Thêm tham số này
                 )
                   

            # === 6.3: KIỂM TRA TIẾN TRIỂN VÀ IN TRẠNG THÁI ===
            pallets_after_iteration = len(unplaced_integer_pallets) + len(unplaced_fractional_pallets)
            
            print_container_status(
                containers=final_containers,
                step_name=f"KẾT THÚC VÒNG LẶP {loop_counter}",
                integer_wait_list=unplaced_integer_pallets,
                fractional_wait_list=unplaced_fractional_pallets
            )
            
            # Kiểm tra xem có bị lặp vô hạn không
            if pallets_after_iteration > 0 and pallets_after_iteration == pallets_before_iteration:
                print("\n!!! CẢNH BÁO: Không thể xếp thêm pallet vào container. Vòng lặp dừng lại để tránh lặp vô hạn.")
                print("Các pallet còn lại không thể xử lý:")
                for p in unplaced_integer_pallets: print(f"  - {p}")
                for p in unplaced_fractional_pallets: print(f"  - {p}")
                break  # Thoát khỏi vòng lặp while

        #####################         GIAI ĐOẠN 4: TỐI ƯU HÓA HỢP NHẤT CUỐI CÙNG         #########################
        print("\n" + "="*80)
        print("BẮT ĐẦU GIAI ĐOẠN 4: TỐI ƯU HÓA HỢP NHẤT CUỐI CÙNG (v4 - Tích hợp chia tách)")
        print("="*80)

        # Với logic mới, không cần tải lại raw_data_map ở bước này nữa.
        # Chạy Giai đoạn 4 với hàm logic đã được cập nhật, chỉ cần truyền vào danh sách container.
        fully_optimized_containers = phase_4_final_consolidation(
            final_containers
        )

        # --- BƯỚC 7: KẾT QUẢ PHÂN BỔ CUỐI CÙNG (SAU GIAI ĐOẠN 4) ---
        print("\n# BƯỚC 7: KẾT QUẢ PHÂN BỔ CUỐI CÙNG #")
        print_container_status(
            containers=fully_optimized_containers, # <-- SỬ DỤNG KẾT QUẢ SAU TỐI ƯU
            step_name="HOÀN TẤT",
            integer_wait_list=unplaced_integer_pallets,
            fractional_wait_list=unplaced_fractional_pallets
        )