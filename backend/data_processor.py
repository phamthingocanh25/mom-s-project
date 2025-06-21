import pandas as pd
import math
import copy

# --- CÁC HẰNG SỐ CẤU HÌNH ---
MAX_CONTAINER_WEIGHT_KG = 24000
MAX_CONTAINER_QUANTITY = 20.0 # Giả định giới hạn 20 pallets

class Pallet:
    """Lớp đối tượng cho một pallet hoặc một phần của pallet."""
    def __init__(self, p_id, quantity, weight_kg, company_id, original_quantity=None):
        self.id = p_id
        self.quantity = quantity
        self.weight_kg = weight_kg
        self.company_id = company_id
        # Lưu lại số lượng gốc nếu pallet này đã bị chia nhỏ
        self.original_quantity = original_quantity if original_quantity else quantity

    def __repr__(self):
        return (f"Pallet(id={self.id}, qty={self.quantity:.2f}, "
                f"wgt={self.weight_kg:.2f}, Cty={self.company_id})")

    def split(self, required_quantity):
        """Chia pallet hiện tại thành hai phần."""
        if self.quantity <= required_quantity:
            return None, None

        weight_per_pallet = self.weight_kg / self.quantity
        
        # Phần được tách ra
        part1 = Pallet(self.id, required_quantity, required_quantity * weight_per_pallet, 
                       self.company_id, self.original_quantity)
        
        # Phần còn lại
        self.quantity -= required_quantity
        self.weight_kg -= part1.weight_kg
        
        return part1, self

class Container:
    """Lớp đối tượng đại diện cho một container."""
    def __init__(self, container_id, company_id):
        self.id = container_id
        self.pallets = []
        self.company_id = company_id # Công ty "chủ" của container
        self.total_quantity = 0.0
        self.total_weight_kg = 0.0

    def add_pallet(self, pallet):
        self.pallets.append(pallet)
        self.total_quantity += pallet.quantity
        self.total_weight_kg += pallet.weight_kg

    def can_fit(self, pallet):
        return (self.total_quantity + pallet.quantity <= MAX_CONTAINER_QUANTITY and
                self.total_weight_kg + pallet.weight_kg <= MAX_CONTAINER_WEIGHT_KG)

    def fullness_score(self):
        # Trả về điểm "đầy" của container, dùng để sắp xếp
        return (self.total_weight_kg / MAX_CONTAINER_WEIGHT_KG) + \
               (self.total_quantity / MAX_CONTAINER_QUANTITY)


# --- LÕI TOÁN MỚI ---

def pack_pallets_basic(pallets, company_id):
    """Gói hàng cơ bản cho một công ty, không chia nhỏ."""
    containers = []
    # Sắp xếp pallet từ lớn nhất đến nhỏ nhất
    for p in sorted(pallets, key=lambda x: x.quantity, reverse=True):
        placed = False
        for c in containers:
            if c.can_fit(p):
                c.add_pallet(p)
                placed = True
                break
        if not placed:
            new_cont = Container(f"C{company_id}-{len(containers)+1}", company_id)
            new_cont.add_pallet(p)
            containers.append(new_cont)
    return containers

def optimize_shipping_with_cost(pallets_c1, pallets_c2):
    """Thuật toán tối ưu hóa chính, có xem xét chi phí vận chuyển chéo."""
    
    # 1. Gói hàng riêng cho từng công ty
    containers_c1 = pack_pallets_basic(pallets_c1, 1)
    containers_c2 = pack_pallets_basic(pallets_c2, 2)
    all_containers = containers_c1 + containers_c2
    
    # Lặp lại quá trình tối ưu hóa một vài lần
    for _ in range(5):
        if len(all_containers) <= 1:
            break

        # Sắp xếp để đưa container ít đầy nhất lên đầu
        all_containers.sort(key=lambda c: c.fullness_score())
        
        source_cont = all_containers[0]
        target_conts = all_containers[1:]
        
        pallets_to_repack = list(source_cont.pallets)
        source_cont.pallets.clear()
        
        # Cố gắng xếp lại các pallet vào các container hiện có
        for pallet in sorted(pallets_to_repack, key=lambda p: p.quantity, reverse=True):
            placed = False
            # Ưu tiên xếp vào cont CÙNG công ty trước
            for target in sorted(target_conts, key=lambda c: c.company_id == pallet.company_id, reverse=True):
                if target.can_fit(pallet):
                    target.add_pallet(pallet)
                    placed = True
                    break
            
            # Nếu không thể xếp nguyên vẹn, thử chia nhỏ (với chi phí thấp nhất)
            if not placed:
                best_split_option = None
                
                for target in target_conts:
                    if target.fullness_score() > 1.8: # Không chia nhỏ cho cont đã gần đầy
                        continue

                    needed_qty = MAX_CONTAINER_QUANTITY - target.total_quantity
                    needed_wgt = MAX_CONTAINER_WEIGHT_KG - target.total_weight_kg
                    
                    if needed_qty <= 0 or needed_wgt <= 0: continue

                    weight_per_pallet = pallet.weight_kg / pallet.quantity if pallet.quantity > 0 else 0
                    fittable_qty = min(needed_qty, needed_wgt / weight_per_pallet if weight_per_pallet > 0 else needed_qty)
                    
                    if fittable_qty >= pallet.quantity: continue

                    # Chi phí là lượng hàng phải di chuyển chéo
                    cost = fittable_qty if target.company_id != pallet.company_id else 0
                    
                    if fittable_qty > 0.1 and (best_split_option is None or cost < best_split_option['cost']):
                        best_split_option = {'target': target, 'quantity': fittable_qty, 'cost': cost, 'original_pallet': pallet}

                if best_split_option:
                    part1, _ = best_split_option['original_pallet'].split(best_split_option['quantity'])
                    best_split_option['target'].add_pallet(part1)
                    # Pallet gốc (phần còn lại) sẽ được xử lý tiếp
                
        # Loại bỏ các container rỗng
        all_containers = [c for c in all_containers if c.pallets]

    return all_containers

# --- PHẦN XỬ LÝ FILE VÀ ĐỊNH DẠNG KẾT QUẢ ---

def process_uploaded_file(file_path, sheet_name):
    try:
        df = load_and_clean_data(file_path, sheet_name)
        if isinstance(df, dict): # Nếu load_and_clean_data trả về lỗi
            return df
            
        pallets_c1 = [Pallet(f"P{i}", r['SoLuongPallet'], r['SoLuongPallet'] * r['TrongLuongPerPallet_kg'], 1)
                      for i, r in df[df['CongTy'] == 1].iterrows()]
        pallets_c2 = [Pallet(f"P{i}", r['SoLuongPallet'], r['SoLuongPallet'] * r['TrongLuongPerPallet_kg'], 2)
                      for i, r in df[df['CongTy'] == 2].iterrows()]

        final_containers = optimize_shipping_with_cost(pallets_c1, pallets_c2)
        
        return format_results(final_containers)

    except Exception as e:
        return {"error": f"Lỗi không xác định: {e}"}

def load_and_clean_data(file_path, sheet_name):
    df_full = pd.read_excel(file_path, sheet_name=sheet_name, header=None)
    start_row_index = find_data_start_row(df_full, [10, 11])
    if start_row_index is None:
        return {"error": "Không thể tự động xác định dòng bắt đầu của dữ liệu."}

    df = df_full[start_row_index:].copy()
    df.reset_index(drop=True, inplace=True)
    df.rename(columns={3: 'CongTy', 10: 'TrongLuongPerPallet_kg', 11: 'SoLuongPallet'}, inplace=True)
    
    df['SoLuongPallet'] = pd.to_numeric(df['SoLuongPallet'], errors='coerce')
    df['TrongLuongPerPallet_kg'] = pd.to_numeric(df['TrongLuongPerPallet_kg'], errors='coerce')
    df.dropna(subset=['SoLuongPallet', 'TrongLuongPerPallet_kg', 'CongTy'], inplace=True)
    df = df[(df['SoLuongPallet'] > 0) & (df['TrongLuongPerPallet_kg'] > 0)]
    
    if df.empty:
        return {"error": "Không tìm thấy dữ liệu hợp lệ (số lượng > 0, trọng lượng > 0 và có mã công ty)."}
    return df

def find_data_start_row(df, columns_to_check):
    for index, row in df.iterrows():
        try:
            pd.to_numeric(row[columns_to_check])
            return index
        except (ValueError, TypeError):
            continue
    return None

def format_results(containers):
    output = []
    for i, c in enumerate(sorted(containers, key=lambda x: x.fullness_score(), reverse=True)):
        cont_data = {
            "id": f"Container #{i + 1}",
            "total_weight": c.total_weight_kg,
            "total_quantity": c.total_quantity,
            "pallets": []
        }
        # Đánh dấu công ty "chủ" của container
        main_company_load = sum(p.weight_kg for p in c.pallets if p.company_id == c.company_id)
        if (c.total_weight_kg > 0 and main_company_load / c.total_weight_kg < 0.5):
             main_company_id = c.pallets[0].company_id if c.pallets else c.company_id
        else:
             main_company_id = c.company_id
        cont_data["main_company"] = main_company_id


        for p in sorted(c.pallets, key=lambda x: x.weight_kg, reverse=True):
            pallet_info = f"{p.quantity:.2f} plls ({p.weight_kg:.2f} kg) - từ Cty {int(p.company_id)}"
            
            # Ghi chú rõ nếu là hàng vận chuyển chéo
            if int(p.company_id) != main_company_id:
                pallet_info += " [HÀNG GHÉP]"

            # Ghi chú nếu là hàng bị tách
            if abs(p.quantity - p.original_quantity) > 0.01:
                 pallet_info += f" (tách từ {p.original_quantity:.2f} plls)"

            cont_data["pallets"].append(pallet_info)
        output.append(cont_data)
    
    return {"results": output}