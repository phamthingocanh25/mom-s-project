# backend/optimizer.py
import math

# --- HẰNG SỐ CẤU HÌNH ---
MAX_WEIGHT = 24000.0
MAX_PALLETS = 20.0
EPSILON = 1e-6 # Ngưỡng để xử lý sai số dấu phẩy động

# --- CÁC LỚP ĐỐI TƯỢNG (Mô hình hóa dữ liệu) ---
# Giữ nguyên như file gốc

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

# --- CÁC HÀM LOGIC TỐI ƯU HÓA (Phần lớn giữ nguyên) ---

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

        # Tìm container vừa vặn nhất trong các container cùng công ty
        for c in containers:
            if c.main_company == p.company and c.can_fit(p):
                if c.remaining_quantity < min_remaining_space:
                    min_remaining_space = c.remaining_quantity
                    best_fit_container = c
        
        if best_fit_container:
            best_fit_container.add_pallet(p)
            placed = True

        # Nếu không có container nào phù hợp, tạo container mới
        if not placed:
            new_container = Container(f"Container_{container_id_counter}", p.company)
            container_id_counter += 1
            if new_container.can_fit(p):
                new_container.add_pallet(p)
                containers.append(new_container)
            else:
                # Pallet lớn hơn cả container, trường hợp này bỏ qua
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
    
    # Tạo tên mới bằng cách nối tên của các pallet con
               new_product_code = " + ".join([p.product_code for p in current_combination])
               new_product_name = " + ".join([p.product_name for p in current_combination])
    
    # Sử dụng tên mới khi tạo Pallet
               combined_p = Pallet(new_id, new_product_code, new_product_name, company, total_qty, wgt_per_pallet)
    
               combined_p.is_combined = True
               combined_p.original_pallets = current_combination
               combined_pallets.append(combined_p)
            else:
                uncombined_singles.append(start_pallet)

    return combined_pallets, uncombined_singles

def calculate_split_cost(wasted_space, messiness):
    """
    Tính toán tổng chi phí cho một phương án tách.
    Trọng số cho thấy mức độ ưu tiên của chúng ta.
    """
    # Trọng số:
    W_WASTED_SPACE = 1.0  # Chi phí cho mỗi đơn vị không gian lãng phí.
    W_MESSINESS = 5.0     # Chi phí cho sự "bừa bộn" của pallet lẻ.
                          # Việc đặt trọng số này cao cho thấy chúng ta rất ghét pallet lẻ.

    cost = (wasted_space * W_WASTED_SPACE) + (messiness * W_MESSINESS)
    return cost

# +++ HÀM TÌM KIẾM CÁCH TÁCH TỐT NHẤT MỚI +++
def find_best_split(pallet, target_container):
    """
    Tìm cách tách tốt nhất một pallet vào một container cụ thể bằng cách
    đánh giá các phương án và chọn phương án có chi phí thấp nhất.
    """
    best_split = {'cost': float('inf'), 'qty': 0}
    gap_qty = target_container.remaining_quantity
    
    # --- Phương án 1: Tách để lấp đầy (Greedy Fill) ---
    qty_to_split_1 = min(gap_qty, target_container.remaining_weight / pallet.weight_per_pallet if pallet.weight_per_pallet > EPSILON else float('inf'))
    if qty_to_split_1 > EPSILON:
        remaining_pallet_qty = pallet.quantity - qty_to_split_1
        messiness = abs(remaining_pallet_qty - round(remaining_pallet_qty))
        cost = calculate_split_cost(wasted_space=gap_qty - qty_to_split_1, messiness=messiness)
        if cost < best_split['cost']:
            best_split = {'cost': cost, 'qty': qty_to_split_1}

    # --- Phương án 2: Tách để phần còn lại là số nguyên (Integer Remainder) ---
    for possible_remainder in range(math.floor(pallet.quantity), 0, -1):
        qty_to_split_2 = pallet.quantity - possible_remainder
        if qty_to_split_2 > EPSILON and qty_to_split_2 <= gap_qty + EPSILON and \
           (qty_to_split_2 * pallet.weight_per_pallet <= target_container.remaining_weight + EPSILON):
            
            # Vì phần còn lại là số nguyên (ví dụ 5.0), messiness của nó là 0
            cost = calculate_split_cost(wasted_space=gap_qty - qty_to_split_2, messiness=0.0)
            if cost < best_split['cost']:
                best_split = {'cost': cost, 'qty': qty_to_split_2}

    if best_split['cost'] == float('inf'):
        return 0 # Không tìm thấy cách tách nào
    return best_split['qty']


# --- HÀM XẾP VÀ TÁCH PALLET ĐÃ ĐƯỢC NÂNG CẤP ---
def pack_and_split_pallets(containers, all_remaining_pallets,
                           pallets_to_pack_key=lambda p: p.quantity, reverse_sort=True):
    """
    Hàm tổng quát để xếp và tách pallet, giờ đây sử dụng logic tìm kiếm
    cách tách thông minh thay vì chiến lược cố định.
    """
    pallets_to_pack = sorted(all_remaining_pallets, key=pallets_to_pack_key, reverse=reverse_sort)
    unpacked_pallets = []

    while pallets_to_pack:
        pallet = pallets_to_pack.pop(0)
        placed_or_split = False

        # Sắp xếp container theo không gian còn lại ít nhất (best-fit)
        for c in sorted(containers, key=lambda c: c.remaining_quantity):
            if placed_or_split: break

            # Nếu pallet vừa vặn thì thêm vào
            if c.can_fit(pallet):
                c.add_pallet(pallet)
                placed_or_split = True
                break

            # --- LOGIC TÁCH MỚI, THÔNG MINH HƠN ---
            gap_qty = c.remaining_quantity
            if gap_qty > EPSILON and pallet.quantity > gap_qty and not pallet.is_combined:
                
                # Gọi bộ não "find_best_split" để tìm lượng tách tối ưu
                qty_to_split = find_best_split(pallet, c)
                
                # Thực hiện tách nếu tìm được lượng phù hợp
                if qty_to_split > EPSILON:
                    remaining_part, new_part = pallet.split(qty_to_split)
                    if new_part:
                        c.add_pallet(new_part)
                        if remaining_part:
                            pallets_to_pack.append(remaining_part)
                            pallets_to_pack.sort(key=pallets_to_pack_key, reverse=reverse_sort)
                        placed_or_split = True
                        break # Đã xếp xong, thoát vòng lặp container

        if not placed_or_split:
            unpacked_pallets.append(pallet)

    return containers, unpacked_pallets

# --- HÀM TỐI ƯU HÓA CHÍNH (LOGIC MỚI) ---
def optimize_container_packing(all_pallets):
    # ... (Hàm này giữ nguyên, chỉ có các lời gọi đến pack_and_split_pallets giờ sẽ tự động thông minh hơn) ...
    pallets_by_company = {}
    companies = []
    for p in all_pallets:
        company_key = str(p.company)
        if company_key not in pallets_by_company:
            pallets_by_company[company_key] = []
            companies.append(company_key)
        pallets_by_company[company_key].append(p)
    all_optimized_containers = []
    leftovers_by_company = {}
    container_id_counter = 1
    for company in sorted(companies):
        company_pallets = pallets_by_company[company]
        integer_pallets = [p for p in company_pallets if abs(p.quantity - round(p.quantity)) < EPSILON]
        for p in integer_pallets: p.quantity = round(p.quantity)
        float_pallets = [p for p in company_pallets if abs(p.quantity - round(p.quantity)) >= EPSILON]
        company_containers, temp_counter = pack_integer_pallets(integer_pallets, container_id_counter)
        container_id_counter = temp_counter
        combined_pallets, single_floats = create_combined_pallets(float_pallets)
        all_remaining_for_company = combined_pallets + single_floats
        company_containers_to_pack = [c for c in company_containers if c.main_company == company]
        other_containers = [c for c in company_containers if c.main_company != company]
        updated_company_containers, leftovers = pack_and_split_pallets(
            company_containers_to_pack, 
            all_remaining_for_company,
        )
        all_optimized_containers.extend(other_containers)
        all_optimized_containers.extend(updated_company_containers)
        if leftovers:
            leftovers_by_company[company] = leftovers
    if not leftovers_by_company:
        return all_optimized_containers
    if len(leftovers_by_company) == 1:
        company_with_leftovers = list(leftovers_by_company.keys())[0]
        pallets_to_place = leftovers_by_company[company_with_leftovers]
        same_company_containers = [c for c in all_optimized_containers if c.main_company == company_with_leftovers]
        _, pallets_after_internal_fill = pack_and_split_pallets(same_company_containers, pallets_to_place)
        if pallets_after_internal_fill:
            other_company_containers = [c for c in all_optimized_containers if c.main_company != company_with_leftovers]
            _, final_leftovers = pack_and_split_pallets(
                other_company_containers, 
                pallets_after_internal_fill,
            )
            if final_leftovers:
                sorted_leftovers = sorted(final_leftovers, key=lambda p: p.quantity, reverse=True)
                new_container = Container(f"Container_{container_id_counter}", sorted_leftovers[0].company)
                container_id_counter += 1
                _, _ = pack_and_split_pallets([new_container], sorted_leftovers, reverse_sort=False)
                all_optimized_containers.append(new_container)
        return all_optimized_containers
    if len(leftovers_by_company) >= 2:
        final_leftovers_to_combine = []
        for company, leftovers in leftovers_by_company.items():
            company_containers = [c for c in all_optimized_containers if c.main_company == company]
            _, remaining_leftovers = pack_and_split_pallets(
                company_containers, 
                leftovers,
            )
            if remaining_leftovers:
                final_leftovers_to_combine.extend(remaining_leftovers)
        if final_leftovers_to_combine:
            sorted_final_leftovers = sorted(final_leftovers_to_combine, key=lambda p: p.quantity, reverse=True)
            _, remaining_pallets = pack_and_split_pallets(
                all_optimized_containers, 
                sorted_final_leftovers,
            )
            while remaining_pallets:
                pallet_to_start = remaining_pallets.pop(0)
                new_container = Container(f"Container_{container_id_counter}", pallet_to_start.company)
                container_id_counter += 1
                new_container.add_pallet(pallet_to_start)
                temp_remaining_list = list(remaining_pallets)
                remaining_pallets = []
                for other_pallet in temp_remaining_list:
                    if new_container.can_fit(other_pallet):
                        new_container.add_pallet(other_pallet)
                    else:
                        remaining_pallets.append(other_pallet)
                all_optimized_containers.append(new_container)
    return all_optimized_containers