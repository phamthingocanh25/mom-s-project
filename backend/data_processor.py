# backend/data_processor.py
import pandas as pd
from optimizer import Pallet # Quan trọng: import lớp Pallet từ optimizer.py

def load_and_prepare_pallets(filepath, sheet_name):
    """
    Đọc và làm sạch dữ liệu từ file Excel, trả về một danh sách các đối tượng Pallet.
    - Cột B (1): product_code
    - Cột C (2): product_name
    - Cột D (3): company
    - Cột K (10): weight_per_pallet
    - Cột L (11): quantity
    """
    try:
        column_indices = [1, 2, 3, 10, 11]
        column_names = ['product_code', 'product_name', 'company', 'weight_per_pallet', 'quantity']

        # Đọc dữ liệu từ hàng thứ 6 (bỏ qua 5 hàng đầu)
        df = pd.read_excel(
            filepath,
            sheet_name=sheet_name,
            header=None,
            skiprows=5,
            usecols=column_indices,
            names=column_names
        )

        # Xóa các hàng không có dữ liệu cần thiết ở các cột quan trọng
        df.dropna(subset=['product_name', 'company', 'weight_per_pallet', 'quantity'], how='any', inplace=True)
        
        # --- SỬA LỖI: Điền các giá trị bị thiếu (NaN) bằng một chuỗi mặc định ---
        # Điều này đảm bảo mọi pallet đều có mã và tên hợp lệ.
        df['product_code'].fillna('Không có mã', inplace=True)
        df['product_name'].fillna('Không có tên', inplace=True)
        # --- KẾT THÚC SỬA LỖI ---

        # Chuyển đổi sang kiểu số, loại bỏ các giá trị không hợp lệ
        for col in ['weight_per_pallet', 'quantity']:
            df[col] = pd.to_numeric(df[col], errors='coerce')
        df.dropna(subset=['weight_per_pallet', 'quantity'], inplace=True)

        # Lọc bỏ các pallet có số lượng bằng 0 hoặc âm
        df = df[df['quantity'] > 0].copy()
        
        # Đảm bảo cột công ty là chuỗi
        df['company'] = df['company'].astype(str)

        if df.empty:
            return None, "Không tìm thấy dữ liệu hợp lệ trong các cột đã chỉ định (B, C, D, K, L)."

        # Tạo danh sách các đối tượng Pallet, đảm bảo không có giá trị null
        pallets = [Pallet(f"P{i}", r['product_code'], r['product_name'], r['company'], r['quantity'], r['weight_per_pallet'])
                   for i, r in df.iterrows()]
        
        return pallets, None # Trả về danh sách pallets và không có lỗi
        
    except Exception as e:
        return None, f"Lỗi xử lý file Excel: {e}"

def generate_response_data(final_containers):
    """
    Chuyển đổi kết quả tối ưu hóa thành định dạng JSON để gửi về frontend.
    Khi một pallet được gộp, nó sẽ bao gồm danh sách các pallet gốc.
    """
    results = {
        "total_containers": len(final_containers),
        "containers": []
    }

    for container in sorted(final_containers, key=lambda c: int(c.id.split('_')[-1])):
        container_details = {
            "id": container.id,
            "main_company": container.main_company,
            "total_quantity": f"{container.total_quantity:.2f}",
            "total_weight": f"{container.total_weight:.2f}",
            "pallets": []
        }
        for pallet in container.pallets:
            pallet_details = {
                "id": pallet.id,
                "product_code": pallet.product_code,
                "product_name": pallet.product_name,
                "company": pallet.company,
                "quantity": f"{pallet.quantity:.2f}",
                "total_weight": f"{pallet.total_weight:.2f}",
                "is_combined": pallet.is_combined,
                "is_split": pallet.is_split,
                "is_cross_ship": pallet.is_cross_ship,
                # Thêm một trường mới để chứa các pallet gốc
                "original_pallets": []
            }

            # *** LOGIC MỚI: Nếu pallet là hàng gộp, thêm chi tiết các pallet con ***
            if pallet.is_combined:
                # Đặt tên cho pallet gộp để dễ nhận biết hơn
                pallet_details["product_name"] = "Hàng gộp" 
                
                for p_orig in pallet.original_pallets:
                    original_pallet_info = {
                        "id": p_orig.id,
                        "product_code": p_orig.product_code,
                        "product_name": p_orig.product_name,
                        "company": p_orig.company,
                        "quantity": f"{p_orig.quantity:.2f}",
                        "total_weight": f"{p_orig.total_weight:.2f}",
                    }
                    pallet_details["original_pallets"].append(original_pallet_info)

            container_details["pallets"].append(pallet_details)
        results["containers"].append(container_details)
    
    return results
