# backend/optimizer.py
import math

# --- HẰNG SỐ CẤU HÌNH ---
MAX_WEIGHT = 24000.0
MAX_PALLETS = 20.0
EPSILON = 1e-6 # Ngưỡng để xử lý sai số dấu phẩy động

# --- CÁC LỚP ĐỐI TƯỢNG (Mô hình hóa dữ liệu) ---

class Pallet:
    """Đại diện cho một pallet hoặc một phần của pallet."""
    def __init__(self, p_id, product_code, product_name, company, quantity, weight_per_pallet):
        self.id = p_id
        self.product_code = product_code
        self.product_name = product_name
        self.company = str(company)
        self.quantity = float(quantity)
        self.weight_per_pallet = float(weight_per_pallet)
        self.total_weight = self.quantity * self.weight_per_pallet
        self.is_combined = False
        self.original_pallets = [self]
        self.is_split = False
        self.is_cross_ship = False

    def __repr__(self):
        type_info = ""
        if self.is_combined: type_info = " [Combined]"
        if self.is_split: type_info = " [Split]"
        if self.is_cross_ship: type_info += " [Cross-Ship]"
        return (f"Pallet(id={self.id}, qty={self.quantity:.2f}, "
                f"wgt={self.total_weight:.2f}, Cty={self.company}){type_info}")

    def split(self, split_quantity):
        """
        Tách pallet hiện tại thành hai phần.
        Trả về (phần còn lại, phần mới được tách ra).
        """
        if split_quantity <= EPSILON or split_quantity >= self.quantity:
            return None, None

        # Tạo phần mới được tách ra
        new_part_id = f"{self.id}-part"
        new_part = Pallet(new_part_id, self.product_code, self.product_name, self.company,
                          split_quantity, self.weight_per_pallet)
        new_part.is_split = True
        
        # Cập nhật phần còn lại của pallet gốc
        self.quantity -= split_quantity
        self.total_weight = self.quantity * self.weight_per_pallet
        self.id = f"{self.id}-rem"
        self.is_split = True
        
        return self, new_part

class Container:
    """Đại diện cho một container."""
    def __init__(self, container_id, main_company):
        self.id = container_id
        self.main_company = str(main_company)
        self.pallets = []
        self.total_quantity = 0.0
        self.total_weight = 0.0

    def can_fit(self, pallet):
        """Kiểm tra xem pallet có thể được thêm vào container không."""
        return (self.total_quantity + pallet.quantity <= MAX_PALLETS + EPSILON and
                self.total_weight + pallet.total_weight <= MAX_WEIGHT + EPSILON)

    def add_pallet(self, pallet):
        """Thêm pallet vào container."""
        if str(pallet.company) != self.main_company:
            pallet.is_cross_ship = True
        self.pallets.append(pallet)
        self.total_quantity += pallet.quantity
        self.total_weight += pallet.total_weight

    @property
    def remaining_quantity(self):
        return MAX_PALLETS - self.total_quantity

    @property
    def remaining_weight(self):
        return MAX_WEIGHT - self.total_weight

# --- CÁC HÀM LOGIC TỐI ƯU HÓA (GIỮ NGUYÊN) ---

def pack_integer_pallets(all_integer_pallets, container_id_counter, existing_containers=None):
    """
    Giai đoạn 1: Chỉ xếp các pallet nguyên (số lượng là số nguyên).
    Tạo container mới khi cần. Luôn xếp các pallet lớn nhất trước.
    """
    containers = existing_containers if existing_containers is not None else []
    
    for p in sorted(all_integer_pallets, key=lambda x: x.quantity, reverse=True):
        placed = False
        best_fit_container = None
        min_remaining_space = float('inf')

        for c in containers:
            if c.main_company == p.company and c.can_fit(p):
                if c.remaining_quantity < min_remaining_space:
                    min_remaining_space = c.remaining_quantity
                    best_fit_container = c
        
        if best_fit_container:
            best_fit_container.add_pallet(p)
            placed = True

        if not placed:
            new_container = Container(f"Container_{container_id_counter}", p.company)
            container_id_counter += 1
            if new_container.can_fit(p):
                new_container.add_pallet(p)
                containers.append(new_container)
            else:
                pass 
    
    return containers, container_id_counter


def create_combined_pallets(float_pallets):
    """
    Giai đoạn 2: Gộp các pallet lẻ của cùng một công ty.
    """
    combined_pallets = []
    uncombined_singles = []
    
    pallets_by_company = {}
    for p in float_pallets:
        if p.company not in pallets_by_company:
            pallets_by_company[p.company] = []
        pallets_by_company[p.company].append(p)

    for company, Cty_pallets in pallets_by_company.items():
        pallets_to_combine = sorted(Cty_pallets, key=lambda x: x.quantity, reverse=True)
        
        while pallets_to_combine:
            start_pallet = pallets_to_combine.pop(0)
            limit = math.floor(start_pallet.quantity) + 0.95
            
            current_combination = [start_pallet]
            current_sum = start_pallet.quantity
            
            temp_remaining = list(pallets_to_combine)
            for other_pallet in sorted(temp_remaining, key=lambda x: x.quantity):
                if current_sum + other_pallet.quantity <= limit:
                    current_combination.append(other_pallet)
                    current_sum += other_pallet.quantity
                    pallets_to_combine.remove(other_pallet)
            
            if len(current_combination) > 1:
                new_id = "+".join([p.id for p in current_combination])
                total_qty = sum(p.quantity for p in current_combination)
                total_wgt = sum(p.total_weight for p in current_combination)
                wgt_per_pallet = total_wgt / total_qty if total_qty > 0 else 0
                
                combined_p = Pallet(new_id, "COMBINED", "Hàng gộp", company, total_qty, wgt_per_pallet)
                combined_p.is_combined = True
                combined_p.original_pallets = current_combination
                combined_pallets.append(combined_p)
            else:
                uncombined_singles.append(start_pallet)

    return combined_pallets, uncombined_singles


def pack_and_split_pallets(containers, all_remaining_pallets):
    """
    Giai đoạn 3 & 4: Xếp và Tách tất cả các pallet còn lại vào các container CÙNG CÔNG TY.
    """
    pallets_to_pack = sorted(all_remaining_pallets, key=lambda p: p.quantity, reverse=True)
    unpacked_pallets = []

    while pallets_to_pack:
        pallet = pallets_to_pack.pop(0)
        placed_or_split = False

        # Chỉ tìm trong các container cùng công ty
        for c in sorted([c for c in containers if c.main_company == pallet.company], key=lambda c: c.remaining_quantity):
            if placed_or_split: break
            
            gap_qty = c.remaining_quantity
            if gap_qty < EPSILON: continue

            if pallet.quantity > gap_qty:
                best_qty_to_split = 0
                for possible_remainder in range(math.floor(pallet.quantity), -1, -1):
                    qty_to_split_candidate = pallet.quantity - possible_remainder
                    
                    if qty_to_split_candidate > gap_qty + EPSILON: continue
                    
                    weight_of_candidate = qty_to_split_candidate * pallet.weight_per_pallet
                    if weight_of_candidate <= c.remaining_weight + EPSILON:
                        if qty_to_split_candidate > best_qty_to_split:
                            best_qty_to_split = qty_to_split_candidate

                if best_qty_to_split > EPSILON:
                    remaining_part, new_part = pallet.split(best_qty_to_split)
                    if new_part:
                        c.add_pallet(new_part)
                        pallets_to_pack.append(remaining_part)
                        pallets_to_pack.sort(key=lambda p: p.quantity, reverse=True)
                        placed_or_split = True
                        break 
            
            elif c.can_fit(pallet):
                c.add_pallet(pallet)
                placed_or_split = True
                break

        if not placed_or_split:
            unpacked_pallets.append(pallet)

    return containers, unpacked_pallets


# --- HÀM MỚI ---
def cross_ship_leftovers(all_containers, all_leftovers, container_id_counter):
    """
    Giai đoạn 5: Xử lý hàng thừa xuyên công ty (Cross-shipping).
    Cố gắng xếp các pallet còn sót lại từ tất cả các công ty vào các container hiện có.
    Nếu không được, đóng gói chúng vào các container mới một cách hiệu quả.
    """
    # Sắp xếp pallet thừa từ lớn nhất đến nhỏ nhất
    pallets_to_pack = sorted(all_leftovers, key=lambda p: p.quantity, reverse=True)
    still_unpacked = []

    # Vòng 1: Cố gắng lấp đầy các container hiện có (không phân biệt công ty)
    while pallets_to_pack:
        pallet = pallets_to_pack.pop(0)
        placed_or_split = False

        # Ưu tiên lấp đầy các container gần đầy nhất trước (best-fit)
        for c in sorted(all_containers, key=lambda c: c.remaining_quantity):
            if placed_or_split: break

            gap_qty = c.remaining_quantity
            if gap_qty < EPSILON: continue
            
            if c.can_fit(pallet):
                c.add_pallet(pallet)
                placed_or_split = True
                break
            elif pallet.quantity > gap_qty: # Logic tách pallet
                best_qty_to_split = 0
                for possible_remainder in range(math.floor(pallet.quantity), -1, -1):
                    qty_to_split_candidate = pallet.quantity - possible_remainder
                    if qty_to_split_candidate > gap_qty + EPSILON: continue
                    weight_of_candidate = qty_to_split_candidate * pallet.weight_per_pallet
                    if weight_of_candidate <= c.remaining_weight + EPSILON and qty_to_split_candidate > best_qty_to_split:
                        best_qty_to_split = qty_to_split_candidate
                
                if best_qty_to_split > EPSILON:
                    remaining_part, new_part = pallet.split(best_qty_to_split)
                    if new_part:
                        c.add_pallet(new_part)
                        pallets_to_pack.append(remaining_part)
                        pallets_to_pack.sort(key=lambda p: p.quantity, reverse=True)
                        placed_or_split = True
                        break
        
        if not placed_or_split:
            still_unpacked.append(pallet)

    # Vòng 2: Logic mới để xử lý các pallet cuối cùng không thể ghép
    # Đóng gói chúng vào các container mới một cách hiệu quả thay vì mỗi pallet một container.
    final_leftovers = sorted(still_unpacked, key=lambda p: p.quantity, reverse=True)
    while final_leftovers:
        # Bắt đầu một container mới với pallet lớn nhất còn lại
        pallet_to_start_new_container = final_leftovers.pop(0)
        
        new_container = Container(f"Container_{container_id_counter}", pallet_to_start_new_container.company)
        container_id_counter += 1
        new_container.add_pallet(pallet_to_start_new_container)
        all_containers.append(new_container)

        # Cố gắng lấp đầy container vừa tạo bằng các pallet còn lại (First-Fit)
        remaining_after_fill = []
        for other_pallet in final_leftovers:
            if new_container.can_fit(other_pallet):
                new_container.add_pallet(other_pallet)
            else:
                remaining_after_fill.append(other_pallet)
        
        # Cập nhật danh sách pallet còn lại cho vòng lặp tiếp theo
        final_leftovers = sorted(remaining_after_fill, key=lambda p: p.quantity, reverse=True)

    return all_containers


# --- HÀM TỐI ƯU HÓA CHÍNH (LUỒNG ĐIỀU PHỐI MỚI) ---
def optimize_container_packing(all_pallets):
    """
    Hàm chính điều phối toàn bộ quy trình tối ưu hóa.
    Tách biệt luồng xử lý cho từng công ty, sau đó ghép hàng thừa.
    """
    
    # 1. Tách pallet theo công ty
    pallets_by_company = {}
    for p in all_pallets:
        company_key = str(p.company)
        if company_key not in pallets_by_company:
            pallets_by_company[company_key] = []
        pallets_by_company[company_key].append(p)

    all_optimized_containers = []
    all_leftover_pallets = []
    container_id_counter = 1

    # 2. Chạy tối ưu hóa độc lập cho từng công ty
    sorted_companies = sorted(pallets_by_company.keys()) # Xử lý theo thứ tự alphabet để kết quả ổn định

    for company in sorted_companies:
        company_pallets = pallets_by_company[company]
        
        # Phân loại pallet cho công ty hiện tại
        integer_pallets = [p for p in company_pallets if abs(p.quantity - round(p.quantity)) < EPSILON]
        for p in integer_pallets: p.quantity = round(p.quantity)
        float_pallets = [p for p in company_pallets if abs(p.quantity - round(p.quantity)) >= EPSILON]

        # Giai đoạn 1: Xếp pallet nguyên
        company_containers, temp_counter = pack_integer_pallets(integer_pallets, container_id_counter)
        container_id_counter = temp_counter
        
        # Giai đoạn 2: Gộp pallet lẻ
        combined_pallets, single_floats = create_combined_pallets(float_pallets)
        
        # Giai đoạn 3 & 4: Xếp và tách các pallet còn lại
        all_remaining = combined_pallets + single_floats
        company_containers, leftovers = pack_and_split_pallets(company_containers, all_remaining)
        
        # Thu thập kết quả
        all_optimized_containers.extend(company_containers)
        all_leftover_pallets.extend(leftovers)

    # 3. Giai đoạn cuối: Xử lý hàng thừa xuyên công ty (Cross-Shipping)
    if all_leftover_pallets:
        final_containers = cross_ship_leftovers(all_optimized_containers, all_leftover_pallets, container_id_counter)
        return final_containers

    return all_optimized_containers