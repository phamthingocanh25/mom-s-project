import pandas as pd
import math
import copy

# --- HẰNG SỐ CẤU HÌNH ---
MAX_WEIGHT = 24000.0
MAX_PALLETS = 20.0

# --- CÁC LỚP ĐỐI TƯỢNG ---

class Pallet:
    """Đại diện cho một pallet hoặc một phần của pallet."""
    def __init__(self, p_id,product_code, product_name, company, quantity, weight_per_pallet):
        self.id = p_id
        self.product_code = product_code
        self.product_name = product_name
        self.company = company
        self.quantity = float(quantity)
        self.weight_per_pallet = float(weight_per_pallet)
        self.total_weight = self.quantity * self.weight_per_pallet
        self.is_combined = False
        self.original_pallets = [self]
        self.is_split = False
        self.is_cross_ship = False

    def __repr__(self):
        return f"Pallet(id={self.id},code={self.product_code}, qty={self.quantity:.2f}, wgt={self.total_weight:.2f}, Cty={self.company})"

class Container:
    """Đại diện cho một container."""
    def __init__(self, container_id, main_company):
        self.id = container_id
        self.main_company = main_company
        self.pallets = []
        self.total_quantity = 0.0
        self.total_weight = 0.0

    def can_fit(self, pallet):
        """Kiểm tra xem pallet có thể được thêm vào container không."""
        return (self.total_quantity + pallet.quantity <= MAX_PALLETS and
                self.total_weight + pallet.total_weight <= MAX_WEIGHT)

    def add_pallet(self, pallet):
        """Thêm pallet vào container."""
        self.pallets.append(pallet)
        self.total_quantity += pallet.quantity
        self.total_weight += pallet.total_weight

    @property
    def remaining_quantity(self):
        return MAX_PALLETS - self.total_quantity

    @property
    def remaining_weight(self):
        return MAX_WEIGHT - self.total_weight

# --- CÁC HÀM TIỆN ÍCH ---

def read_and_validate_data(filepath, sheet_name):
    """
    Đọc và làm sạch dữ liệu từ file Excel bằng vị trí cột cố định.
    - Cột B (1): product_code
    - Cột C (2): product_name
    - Cột D (3): company
    - Cột K (10): weight_per_pallet
    - Cột L (11): quantity
    """
    try:
        column_indices = [1, 2, 3, 10, 11]
        column_names = ['product_code', 'product_name', 'company', 'weight_per_pallet', 'quantity']

        df = pd.read_excel(
            filepath,
            sheet_name=sheet_name,
            header=None,
            skiprows=5,
            usecols=column_indices,
            names=column_names
        )

        df.dropna(subset=['product_name', 'company', 'weight_per_pallet', 'quantity'], how='any', inplace=True)

        for col in ['weight_per_pallet', 'quantity']:
            df[col] = pd.to_numeric(df[col], errors='coerce')

        df.dropna(subset=['weight_per_pallet', 'quantity'], inplace=True)

        df = df[df['quantity'] > 0].copy()
        
        # Giữ nguyên tên công ty dưới dạng chuỗi hoặc số, không chuyển đổi cứng
        df['company'] = df['company'].astype(str)

        if df.empty:
            return None, "Không tìm thấy dữ liệu hợp lệ tại các vị trí cột đã chỉ định (B, C, D, K, L)."

        pallets = [Pallet(f"P{i}",r['product_code'], r['product_name'], r['company'], r['quantity'], r['weight_per_pallet'])
                   for i, r in df.iterrows()]
        return pallets, None
    except Exception as e:
        return None, f"Lỗi xử lý file Excel: {e}"


# --- LOGIC TỐI ƯU HÓA ---

def pack_integer_pallets(containers, integer_pallets):
    """Bước 1: Xếp các pallet số nguyên."""
    for p in sorted(integer_pallets, key=lambda x: x.quantity, reverse=True):
        placed = False
        for c in sorted(containers, key=lambda x: x.main_company == p.company, reverse=True):
            if c.can_fit(p):
                c.add_pallet(p)
                placed = True
                break
        
        if not placed:
            new_container = Container(f"Container_{len(containers) + 1}", p.company)
            new_container.add_pallet(p)
            containers.append(new_container)
    return containers

def create_combined_pallets(float_pallets):
    """Bước 2: Gộp các pallet lẻ."""
    combined_pallets = []
    pallets_to_combine = sorted(float_pallets, key=lambda x: x.quantity)
    
    while pallets_to_combine:
        start_pallet = pallets_to_combine.pop(0)
        limit = math.floor(start_pallet.quantity) + 0.9
        
        current_combination = [start_pallet]
        current_sum = start_pallet.quantity
        
        remaining_for_this_combo = list(pallets_to_combine)
        for other_pallet in remaining_for_this_combo:
            if current_sum + other_pallet.quantity <= limit:
                current_combination.append(other_pallet)
                current_sum += other_pallet.quantity
                pallets_to_combine.remove(other_pallet)

        if len(current_combination) > 1:
            new_id = "+".join([p.id for p in current_combination])
            total_qty = sum(p.quantity for p in current_combination)
            total_wgt = sum(p.total_weight for p in current_combination)
            wgt_per_pallet = total_wgt / total_qty if total_qty > 0 else 0
            
            # === SỬA LỖI LOGIC TẠI ĐÂY ===
            # Một pallet gộp không có công ty riêng, ta có thể đặt là "Hàng gộp"
            # hoặc lấy công ty của pallet lớn nhất trong nhóm làm đại diện.
            main_company_in_combo = max(current_combination, key=lambda p: p.quantity).company
            combined_p = Pallet(new_id, "COMBINED", "Hàng gộp", main_company_in_combo, total_qty, wgt_per_pallet)
            combined_p.is_combined = True
            # Quan trọng nhất: Lưu lại danh sách các pallet gốc
            combined_p.original_pallets = current_combination
            combined_pallets.append(combined_p)
        else:
            combined_pallets.append(start_pallet)

    final_pallets = [p for p in combined_pallets if p.is_combined]
    remaining_singles = [p for p in combined_pallets if not p.is_combined]
    return final_pallets, remaining_singles

def pack_pallets_into_existing_containers(containers, pallets):
    """Hàm chung để xếp các pallet (không chia nhỏ) vào các container hiện có."""
    unpacked_pallets = []
    for p in sorted(pallets, key=lambda x: x.quantity, reverse=True):
        placed = False
        sorted_containers = sorted(
            containers,
            key=lambda c: (str(c.main_company) == str(p.company), -c.remaining_quantity) , reverse=True
        )

        for c in sorted_containers:
            if c.can_fit(p):
                c.add_pallet(p)
                placed = True
                break
        if not placed:
            unpacked_pallets.append(p)
    return containers, unpacked_pallets

def split_and_fill(containers, leftover_floats):
    """Bước 4: Chia nhỏ các pallet lẻ còn lại để lấp đầy các container."""
    pallets_to_split = sorted(leftover_floats, key=lambda p: p.quantity, reverse=True)
    
    for p in pallets_to_split:
        sorted_containers = sorted(containers, key=lambda c: c.remaining_quantity, reverse=True)
        
        for c in sorted_containers:
            if p.quantity <= 1e-6: break 
            if c.remaining_quantity > 1e-6:
                qty_by_space = c.remaining_quantity
                qty_by_weight = c.remaining_weight / p.weight_per_pallet if p.weight_per_pallet > 0 else float('inf')
                amount_to_pack = min(p.quantity, qty_by_space, qty_by_weight)
                
                if amount_to_pack > 1e-6:
                    split_part = Pallet(f"{p.id}-split", p.product_code, p.product_name, p.company, amount_to_pack, p.weight_per_pallet)
                    split_part.is_split = True
                    c.add_pallet(split_part)
                    
                    p.quantity -= amount_to_pack
                    p.total_weight = p.quantity * p.weight_per_pallet
        
        if p.quantity > 1e-6:
            new_cont = Container(f"Container_{len(containers) + 1}", p.company)
            new_cont.add_pallet(p)
            containers.append(new_cont)
            
    return containers

def format_results_new(containers):
    """
    Định dạng kết quả cuối cùng thành một cấu trúc JSON chi tiết cho frontend.
    """
    final_results = []
    for i, c in enumerate(sorted(containers, key=lambda c: c.id)):
        container_contents = []
        for p in c.pallets:
            pallet_data = {
                "is_cross_ship": str(p.company) != str(c.main_company),
                "company": p.company,
                "quantity": p.quantity,
                "total_weight": p.total_weight
            }

            if p.is_combined:
                pallet_data["type"] = "CombinedPallet"
                items_list = []
                # === SỬA LỖI CHÍNH TẠI ĐÂY ===
                # Duyệt qua các pallet gốc để lấy thông tin chi tiết
                for sub_p in p.original_pallets:
                    items_list.append({
                        "product_code": sub_p.product_code,
                        "product_name": sub_p.product_name,
                        "company": sub_p.company, # <-- THÊM DÒNG NÀY
                        "quantity": sub_p.quantity,
                        "total_weight": sub_p.total_weight,
                    })
                pallet_data["items"] = items_list
            else:
                pallet_data["type"] = "SinglePallet"
                pallet_data["is_split"] = p.is_split
                pallet_data["product_code"] = p.product_code
                pallet_data["product_name"] = p.product_name

            container_contents.append(pallet_data)

        final_results.append({
            'id': c.id,
            'main_company': str(c.main_company),
            'total_quantity': c.total_quantity,
            'total_weight': c.total_weight,
            'contents': sorted(container_contents, key=lambda x: x['type'])
        })
    return {"success": True, "results": final_results}


def process_uploaded_file(filepath, sheet_name):
    """Hàm chính điều phối toàn bộ quy trình tối ưu hóa."""
    all_pallets, error = read_and_validate_data(filepath, sheet_name)
    if error:
        return {"error": error}

    # Phân tách pallet
    integer_pallets = [p for p in all_pallets if p.quantity == int(p.quantity)]
    float_pallets = [p for p in all_pallets if p.quantity != int(p.quantity)]
    
    # Chia pallet lẻ theo công ty để xử lý gộp riêng, tránh gộp lẫn lộn
    companies = set(p.company for p in float_pallets)
    all_combined_pallets = []
    all_remaining_floats = []

    for company in companies:
        company_float_pallets = [p for p in float_pallets if p.company == company]
        combined, remaining = create_combined_pallets(company_float_pallets)
        all_combined_pallets.extend(combined)
        all_remaining_floats.extend(remaining)

    # Bước 1: Xếp pallet số nguyên
    containers = pack_integer_pallets([], integer_pallets)

    # Bước 2: Xếp các pallet đã gộp
    containers, unpacked_combined = pack_pallets_into_existing_containers(containers, all_combined_pallets)
    all_remaining_floats.extend(unpacked_combined)

    # Bước 3: Xếp các pallet lẻ còn lại (không chia)
    containers, leftover_floats = pack_pallets_into_existing_containers(containers, all_remaining_floats)

    # Bước 4: Chia nhỏ pallet lẻ để lấp đầy
    containers = split_and_fill(containers, leftover_floats)

    return format_results_new(containers)

