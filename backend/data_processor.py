import pandas as pd
import os
import math
import numpy as np

# Định nghĩa các hằng số
MAX_CONTAINER_WEIGHT = 24000 # Trọng lượng tối đa của một container (kg)
MAX_CONTAINER_BOXES = 20.0   # Số pallet tối đa (hoặc 'boxes') trong một container
EPSILON = 1e-6               # Một giá trị nhỏ để xử lý so sánh số thực

def get_excel_sheet_names(file_path):
    """
    Lấy danh sách tên các sheet từ một file Excel.
    """
    try:
        xls = pd.ExcelFile(file_path)
        return {"success": True, "sheet_names": xls.sheet_names}
    except FileNotFoundError:
        return {"success": False, "error": f"Không tìm thấy file: {file_path}"}
    except Exception as e:
        return {"success": False, "error": f"Lỗi khi đọc file Excel: {e}"}

def load_sheet_data(file_path, sheet_name, filters={}):
    """
    Tải dữ liệu từ một sheet cụ thể trong file Excel và áp dụng các bộ lọc.
    Trả về dữ liệu đã xử lý để truyền vào hàm tối ưu hóa.
    """
    try:
        # Đọc dữ liệu từ sheet, bỏ qua các hàng đầu tiên (header=3 dựa trên core_math.py)
        df = pd.read_excel(file_path, sheet_name=sheet_name, header=3)

        # Lọc dữ liệu theo cột 'Unnamed: 11' (số lượng pallet) phải lớn hơn 0
        # Đây là tiền xử lý cơ bản giống trong core_math.py
        filtered_df = df[df['Unnamed: 11'] > 0].copy()

        # Áp dụng các bộ lọc nâng cao từ người dùng
        # Filters sẽ có dạng: {'column_name': {'operator': '>', 'value': 100}, ...}
        for col, filter_params in filters.items():
            if col in filtered_df.columns:
                operator = filter_params.get('operator')
                value = filter_params.get('value')
                if operator and value is not None:
                    if operator == '=':
                        filtered_df = filtered_df[filtered_df[col] == value]
                    elif operator == '>':
                        filtered_df = filtered_df[filtered_df[col] > value]
                    elif operator == '<':
                        filtered_df = filtered_df[filtered_df[col] < value]
                    elif operator == '>=':
                        filtered_df = filtered_df[filtered_df[col] >= value]
                    elif operator == '<=':
                        filtered_df = filtered_df[filtered_df[col] <= value]
                    elif operator == 'contains': # Lọc chuỗi chứa
                        filtered_df = filtered_df[filtered_df[col].astype(str).str.contains(str(value), na=False)]
                    elif operator == 'not_contains': # Lọc chuỗi không chứa
                        filtered_df = filtered_df[~filtered_df[col].astype(str).str.contains(str(value), na=False)]
                    # Thêm các loại bộ lọc khác nếu cần

        # Chuẩn bị dữ liệu cho optimize_container_allocation
        # Giả sử 'Unnamed: 11' là số lượng pallet và 'Tổng\nK.lg/kiện\n(GW/pallet)' là khối lượng
        # Cần điều chỉnh nếu các cột này có tên khác hoặc cần tính toán khác
        if 'Unnamed: 11' not in filtered_df.columns or 'Tổng\nK.lg/kiện\n(GW/pallet)' not in filtered_df.columns:
            return {"success": False, "error": "Thiếu các cột 'Unnamed: 11' hoặc 'Tổng\\nK.lg/kiện\\n(GW/pallet)' trong dữ liệu. Vui lòng kiểm tra lại cấu trúc file Excel."}

        # Tạo danh sách các tuple (số lượng pallet, tổng trọng lượng)
        # Làm tròn số lượng pallet để tránh các vấn đề về dấu phẩy động không mong muốn
        pallets_data = list(zip(
            filtered_df['Unnamed: 11'].round(2), # Số lượng pallet
            (filtered_df['Unnamed: 11'] * filtered_df['Tổng\nK.lg/kiện\n(GW/pallet)']).round(2) # Tổng trọng lượng
        ))

        return {"success": True, "data": pallets_data, "num_rows": len(filtered_df)}

    except FileNotFoundError:
        return {"success": False, "error": f"Không tìm thấy file: {file_path}"}
    except ValueError as e:
        return {"success": False, "error": f"Lỗi khi đọc sheet '{sheet_name}': {e}. Có thể tên sheet không chính xác hoặc cấu trúc không khớp."}
    except Exception as e:
        return {"success": False, "error": f"Đã xảy ra lỗi không mong muốn khi xử lý dữ liệu: {e}"}

def process_uploaded_file(file_path):
    """
    Xử lý file khi được tải lên, trả về danh sách các sheet.
    """
    sheet_info = get_excel_sheet_names(file_path)
    return sheet_info

