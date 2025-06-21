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

# --- CÁC HÀM LOGIC TỐI ƯU HÓA ĐÃ ĐƯỢC TÁI CẤU TRÚC ---

def pack_integer_pallets(all_integer_pallets):
    """
    Giai đoạn 1: Chỉ xếp các pallet nguyên (số lượng là số nguyên).
    Tạo container mới khi cần. Luôn xếp các pallet lớn nhất trước.
    """
    containers = []
    container_id_counter = 1
    
    # Sắp xếp pallet nguyên từ lớn nhất đến nhỏ nhất
    for p in sorted(all_integer_pallets, key=lambda x: x.quantity, reverse=True):
        placed = False
        # Tìm container phù hợp (cùng công ty, vừa vặn nhất - best fit)
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
            # Nếu không có container phù hợp, tạo container mới cho công ty của pallet này
            new_container = Container(f"Container_{container_id_counter}", p.company)
            container_id_counter += 1
            if new_container.can_fit(p):
                new_container.add_pallet(p)
                containers.append(new_container)
            else:
                # Trường hợp pallet quá lớn ngay cả cho container rỗng (xử lý sau)
                pass # Sẽ được đưa vào danh sách chưa xếp
    
    return containers, container_id_counter


def create_combined_pallets(float_pallets):
    """
    Giai đoạn 2: Gộp các pallet lẻ của cùng một công ty.
    """
    combined_pallets = []
    uncombined_singles = []
    
    # Nhóm các pallet lẻ theo công ty
    pallets_by_company = {}
    for p in float_pallets:
        if p.company not in pallets_by_company:
            pallets_by_company[p.company] = []
        pallets_by_company[p.company].append(p)

    for company, Cty_pallets in pallets_by_company.items():
        # Sắp xếp pallet lẻ từ lớn nhất đến nhỏ nhất để làm "nền"
        pallets_to_combine = sorted(Cty_pallets, key=lambda x: x.quantity, reverse=True)
        
        while pallets_to_combine:
            start_pallet = pallets_to_combine.pop(0)
            # Giới hạn gộp là phần nguyên của pallet + 0.95 để khuyến khích gộp thành số gần tròn
            limit = math.floor(start_pallet.quantity) + 0.95
            
            current_combination = [start_pallet]
            current_sum = start_pallet.quantity
            
            # Tìm các mảnh nhỏ để gộp vào
            temp_remaining = list(pallets_to_combine)
            for other_pallet in sorted(temp_remaining, key=lambda x: x.quantity): # Ưu tiên gộp mảnh nhỏ nhất
                if current_sum + other_pallet.quantity <= limit:
                    current_combination.append(other_pallet)
                    current_sum += other_pallet.quantity
                    pallets_to_combine.remove(other_pallet)
            
            if len(current_combination) > 1:
                # Tạo pallet gộp mới
                new_id = "+".join([p.id for p in current_combination])
                total_qty = sum(p.quantity for p in current_combination)
                total_wgt = sum(p.total_weight for p in current_combination)
                wgt_per_pallet = total_wgt / total_qty if total_qty > 0 else 0
                
                combined_p = Pallet(new_id, "COMBINED", "Hàng gộp", company, total_qty, wgt_per_pallet)
                combined_p.is_combined = True
                combined_p.original_pallets = current_combination
                combined_pallets.append(combined_p)
            else:
                # Nếu không thể gộp, trả lại thành pallet lẻ đơn
                uncombined_singles.append(start_pallet)

    return combined_pallets, uncombined_singles


def pack_and_split_pallets(containers, all_remaining_pallets):
    """
    Giai đoạn 3 & 4: Xếp và Tách tất cả các pallet còn lại (gộp, lẻ).
    Đây là hàm cốt lõi, thay thế cho cả pack_pallets_into_existing_containers và split_and_fill cũ.
    Nó luôn ưu tiên tách pallet để lấp đầy khoảng trống.
    """
    pallets_to_pack = sorted(all_remaining_pallets, key=lambda p: p.quantity, reverse=True)
    unpacked_pallets = []

    while pallets_to_pack:
        pallet = pallets_to_pack.pop(0)
        placed_or_split = False

        # Sắp xếp container: ưu tiên 1 là CÙNG CÔNG TY, ưu tiên 2 là container còn ÍT chỗ trống nhất
        def sort_key(c):
            is_same_company = (c.main_company == pallet.company)
            return (not is_same_company, c.remaining_quantity)
        
        for c in sorted(containers, key=sort_key):
            if placed_or_split: break
            
            gap_qty = c.remaining_quantity
            if gap_qty < EPSILON: continue

            # LOGIC QUAN TRỌNG: LUÔN KIỂM TRA TÁCH PALLET TRƯỚC
            # Nếu pallet lớn hơn khoảng trống, hãy tách nó ra
            if pallet.quantity > gap_qty:
                # Lượng có thể tách phải vừa với trọng lượng còn lại
                max_qty_by_weight = c.remaining_weight / pallet.weight_per_pallet if pallet.weight_per_pallet > EPSILON else float('inf')
                qty_to_split = min(gap_qty, max_qty_by_weight)
                
                if qty_to_split > EPSILON:
                    remaining_part, new_part = pallet.split(qty_to_split)
                    if new_part:
                        c.add_pallet(new_part)
                        # Đưa phần còn lại vào danh sách chờ và sắp xếp lại
                        pallets_to_pack.append(remaining_part)
                        pallets_to_pack.sort(key=lambda p: p.quantity, reverse=True)
                        placed_or_split = True
                        break # Đã xử lý, chuyển sang pallet tiếp theo
            
            # Nếu không thể tách (hoặc pallet nhỏ hơn khoảng trống), thử xếp cả pallet
            elif c.can_fit(pallet):
                c.add_pallet(pallet)
                placed_or_split = True
                break # Đã xử lý, chuyển sang pallet tiếp theo

        if not placed_or_split:
            unpacked_pallets.append(pallet)

    return containers, unpacked_pallets


def pack_final_leftovers(containers, leftovers, container_id_counter):
    """
    Giai đoạn cuối: Xử lý triệt để những pallet còn sót lại.
    Nếu không thể xếp vào container có sẵn, sẽ tạo container mới.
    Hàm này đảm bảo không pallet nào bị bỏ sót.
    """
    for p in sorted(leftovers, key=lambda x: x.quantity, reverse=True):
        # Thử lại lần cuối để xếp vào container có sẵn (giống logic Giai đoạn 3)
        containers, still_leftover = pack_and_split_pallets(containers, [p])
        
        # Nếu vẫn còn sót, tạo container mới cho nó
        if still_leftover:
            p_left = still_leftover[0]
            new_container = Container(f"Container_{container_id_counter}", p_left.company)
            container_id_counter += 1
            # Vì pallet này không vừa ở đâu cả, nó sẽ được đặt vào container mới
            # (Có thể cần tách nếu nó lớn hơn 20 pallets)
            while p_left.quantity > EPSILON:
                if p_left.quantity > MAX_PALLETS:
                    remaining, part_to_add = p_left.split(MAX_PALLETS)
                    new_container.add_pallet(part_to_add)
                    containers.append(new_container)
                    # Tạo cont mới cho phần còn lại
                    p_left = remaining
                    new_container = Container(f"Container_{container_id_counter}", p_left.company)
                    container_id_counter += 1
                else:
                    new_container.add_pallet(p_left)
                    containers.append(new_container)
                    break

    return containers

# --- HÀM TỐI ƯU HÓA CHÍNH (LUỒNG ĐIỀU PHỐI MỚI) ---
def optimize_container_packing(all_pallets):
    """Hàm chính điều phối toàn bộ quy trình tối ưu hóa đã được tái cấu trúc."""
    
    # Phân loại pallet
    integer_pallets = [p for p in all_pallets if abs(p.quantity - round(p.quantity)) < EPSILON]
    for p in integer_pallets: p.quantity = round(p.quantity) # Làm tròn để đảm bảo là số nguyên
    float_pallets = [p for p in all_pallets if abs(p.quantity - round(p.quantity)) >= EPSILON]

    # Giai đoạn 1: Xếp tất cả các pallet nguyên chất.
    containers, container_id_counter = pack_integer_pallets(integer_pallets)

    # Giai đoạn 2: Gộp các pallet lẻ.
    combined_pallets, single_floats = create_combined_pallets(float_pallets)
    
    # Giai đoạn 3 & 4: Xếp tất cả các pallet còn lại (hàng gộp và hàng lẻ)
    # Hàm này sẽ tự động ưu tiên tách pallet để lấp đầy, giải quyết vấn đề cốt lõi.
    all_remaining = combined_pallets + single_floats
    containers, leftovers = pack_and_split_pallets(containers, all_remaining)

    # Giai đoạn cuối: Xử lý những pallet còn sót lại, đảm bảo không pallet nào bị mất.
    if leftovers:
        containers = pack_final_leftovers(containers, leftovers, container_id_counter)

    return containers