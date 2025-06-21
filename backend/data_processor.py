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