# backend/data_processor.py
import pandas as pd
import math
import warnings # Import the warnings library

# --- HIDE HARMLESS WARNINGS FROM openpyxl ---
from openpyxl.utils.exceptions import InvalidFileException
warnings.filterwarnings("ignore", category=UserWarning, module='openpyxl')
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
        self.split_from_id = None # ID của pallet gốc đã tạo ra nó
        self.sibling_id = None    # ID của pallet "anh em"

    def __repr__(self):
        type_info = ""
        if self.is_combined: type_info = " [Combined]"
        if self.is_split: type_info = " [Split]"
        if self.is_cross_ship: type_info += " [Cross-Ship]"
        return (f"Pallet(id={self.id}, qty={self.quantity:.2f}, "
                f"wgt={self.total_weight:.2f}, Cty={self.company}){type_info}")

    def split(self, split_quantity):
        if split_quantity <= EPSILON or split_quantity >= self.quantity:
           return None, None

    # --- LƯU LẠI THÔNG TIN GỐC ---
        original_id = self.id
        remaining_quantity = self.quantity - split_quantity

    # --- TẠO HAI PALLET MỚI THAY VÌ SỬA PALLET CŨ ---

    # 1. Tạo phần còn lại (remaining part)
        rem_part_id = f"{original_id}-rem"
        rem_part = Pallet(
                   p_id=rem_part_id,
                    product_code=self.product_code,
                    product_name=self.product_name,
                    company=self.company,
                     quantity=remaining_quantity,
                     weight_per_pallet=self.weight_per_pallet
                       )

    # 2. Tạo phần được tách ra (new part)
        new_part_id = f"{original_id}-part"
        new_part = Pallet(
        p_id=new_part_id,
        product_code=self.product_code,
        product_name=self.product_name,
        company=self.company,
        quantity=split_quantity,
        weight_per_pallet=self.weight_per_pallet
    )

    # --- THIẾT LẬP LIÊN KẾT VÀ LỊCH SỬ ---
        for p in [rem_part, new_part]:
            p.is_split = True
            p.split_from_id = original_id # Cả hai đều đến từ cùng một pallet gốc

    # Thiết lập liên kết "anh em" chéo
        rem_part.sibling_id = new_part_id
        new_part.sibling_id = rem_part_id

        return rem_part, new_part

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
        df['product_code'] = df['product_code'].fillna('Không có mã')
        df['product_name'] = df['product_name'].fillna('Không có tên')
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
    Chuyển đổi kết quả tối ưu hóa thành định dạng JSON để gửi về frontend,
    đảm bảo cấu trúc tương thích với component ResultsDisplay.
    """
    containers_list = []
    for container in sorted(final_containers, key=lambda c: int(c.id.split('_')[-1])):
        container_contents = []
        for pallet in container.pallets:
            if pallet.is_combined:
                items = []
                for p_orig in pallet.original_pallets:
                    items.append({
                        "product_code": p_orig.product_code,
                        "product_name": p_orig.product_name,
                        "company": p_orig.company,
                        "quantity": float(f"{p_orig.quantity:.2f}"),
                        "total_weight": float(f"{p_orig.total_weight:.2f}"),
                    })
                pallet_data = {
                    "type": "CombinedPallet",
                    "quantity": float(f"{pallet.quantity:.2f}"),
                    "items": items,
                    "is_cross_ship": pallet.is_cross_ship
                }
            else:
                pallet_data = {
                    "type": "SinglePallet",
                    "product_code": pallet.product_code,
                    "product_name": pallet.product_name,
                    "company": pallet.company,
                    "quantity": float(f"{pallet.quantity:.2f}"),
                    "total_weight": float(f"{pallet.total_weight:.2f}"),
                    "is_split": pallet.is_split,
                    "is_cross_ship": pallet.is_cross_ship
                }
            container_contents.append(pallet_data)

        container_details = {
            "id": container.id,
            "total_quantity": float(f"{container.total_quantity:.2f}"),
            "total_weight": float(f"{container.total_weight:.2f}"),
            "contents": container_contents  # Thay "pallets" bằng "contents"
        }
        containers_list.append(container_details)

    # Trả về đối tượng JSON với key "results" mà frontend mong đợi
    return {"results": containers_list}
def separate_pallets_by_company(all_pallets, company1_name, company2_name):

    pallets_company1 = [] # tên công ty 1
    pallets_company2 = [] # tên công ty 2

    for pallet in all_pallets:
        # Sử dụng .strip() để loại bỏ các khoảng trắng thừa ở đầu/cuối tên công ty
        company_name = pallet.company.strip()
        
        if company_name == company1_name:
            pallets_company1.append(pallet)
        else:
            pallets_company2.append(pallet)
            
    return pallets_company1, pallets_company2
#######################          GIAI ĐOẠN 0         ########################################
def preprocess_and_classify_pallets(pallets):
    """
    Giai đoạn 0: Tiền xử lý & Phân loại Pallet
    Đầu vào: Danh sách pallet thô của một công ty 
    Đầu ra: Ba danh sách - pallet số nguyên, pallet gộp, pallet float lẻ
    """
    # 1. Tách Pallet Số nguyên 
    pallets_integer = []
    float_pallets = []
    
    for pallet in pallets:
        if abs(pallet.quantity - round(pallet.quantity)) < EPSILON:
            pallets_integer.append(pallet)
        else:
            float_pallets.append(pallet)
    
    # 2. Gộp Pallet Theo Quy tắc 
    pallets_combined = []
    pallets_single_float = []
    
    # Sắp xếp pallet float từ lớn đến bé 
    float_pallets.sort(key=lambda p: p.quantity, reverse=True)
    
    while float_pallets:
        # Lấy pallet lớn nhất làm pallet chính 
        main_pallet = float_pallets.pop(0)
        main_value = main_pallet.quantity
        X = math.floor(main_value)
        # Xác định ngưỡng gộp là X.9 
        threshold = X + 0.9
        
        current_group = [main_pallet]
        current_total_quantity = main_value
        
        # Tìm pallet phụ để gộp 
        remaining_indices = []
        for i, pallet in enumerate(float_pallets):
            if current_total_quantity + pallet.quantity <= threshold + EPSILON:
                current_group.append(pallet)
                current_total_quantity += pallet.quantity
            else:
                remaining_indices.append(i)
        
        # Cập nhật danh sách pallet float cho vòng lặp tiếp theo 
        float_pallets = [float_pallets[i] for i in remaining_indices]
        
        # Nếu nhóm có nhiều hơn 1 pallet, tiến hành gộp 
        if len(current_group) > 1:
            # TÍNH TOÁN CHO PALLET GỘP MỚI
            # 1. Tổng số lượng là tổng số lượng của các pallet con.
            combined_quantity = sum(p.quantity for p in current_group)
            
            # 2. Tổng trọng lượng là tổng trọng lượng của các pallet con.
            combined_total_weight = sum(p.total_weight for p in current_group)
            
            # 3. Tính trọng lượng "hiệu dụng" trên một pallet để tạo đối tượng mới.
            #    Công thức: weight_per_pallet = total_weight / quantity
            effective_weight_per_pallet = combined_total_weight / combined_quantity if combined_quantity > 0 else 0

            # Tạo pallet gộp mới với các thông số đã tính toán
            combined_id = f"Combined_{len(pallets_combined)+1}"
            combined_pallet = Pallet(
                p_id=combined_id,
                product_code="GOP",
                product_name="Hàng gộp",
                company=main_pallet.company,
                quantity=combined_quantity,
                weight_per_pallet=effective_weight_per_pallet # Sử dụng trọng lượng hiệu dụng
            )
            
            # Gán lại tổng trọng lượng một cách tường minh để đảm bảo không có sai số
            combined_pallet.total_weight = combined_total_weight
            
            combined_pallet.is_combined = True
            combined_pallet.original_pallets = current_group # Lưu lại các pallet gốc
            
            pallets_combined.append(combined_pallet) # Thêm vào danh sách gộp 
        else:
            # Nếu không gộp được, đưa vào danh sách pallet lẻ 
            pallets_single_float.append(main_pallet)
    
    return pallets_integer, pallets_combined, pallets_single_float
#######################   TIỀN XỬ LÝ PALLET QUÁ KHỔ   #################################
def preprocess_oversized_pallets(all_pallets, container_id_counter):
    """
    Tiền xử lý danh sách pallet để xác định và chia nhỏ các pallet quá khổ.

    Một pallet được coi là quá khổ nếu số lượng của nó > MAX_PALLETS hoặc
    tổng trọng lượng của nó > MAX_WEIGHT.

    Hàm này sẽ:
    1. Tách các pallet quá khổ ra khỏi các pallet có kích thước bình thường.
    2. Đối với mỗi pallet quá khổ, nó sẽ tạo ra các container đầy và đóng gói chúng
       cho đến khi phần còn lại của pallet không còn quá khổ.
    3. Trả về một danh sách các container đã được đóng gói đầy và một danh sách
       các pallet còn lại (bao gồm các pallet bình thường và phần còn lại từ
       các pallet quá khổ) để xử lý tiếp.

    Args:
        all_pallets (list): Danh sách tất cả các đối tượng Pallet thô.
        container_id_counter (dict): Bộ đếm để tạo ID container duy nhất.

    Returns:
        tuple: Một tuple chứa:
            - list: Danh sách các Container đã được lấp đầy hoàn toàn.
            - list: Danh sách các Pallet còn lại cần được xử lý thêm.
    """
    pallets_normal_size = []
    pallets_oversized = []
    
    # Bước 1: Phân loại pallet thành 'bình thường' và 'quá khổ'
    for p in all_pallets:
        # Sử dụng EPSILON để so sánh số thực một cách an toàn
        is_over_weight = p.total_weight > MAX_WEIGHT + EPSILON
        is_over_quantity = p.quantity > MAX_PALLETS + EPSILON
        
        if is_over_weight or is_over_quantity:
            pallets_oversized.append(p)
        else:
            pallets_normal_size.append(p)

    if not pallets_oversized:
        # Nếu không có pallet nào quá khổ, trả về danh sách ban đầu
        return [], all_pallets

    finalized_containers = []
    remaining_split_parts = []
    
    # Bước 2: Xử lý từng pallet quá khổ
    for pallet_to_split in pallets_oversized:
        print(f"INFO: Phát hiện pallet quá khổ ID {pallet_to_split.id} (Qty: {pallet_to_split.quantity:.2f}, Wgt: {pallet_to_split.total_weight:.2f}). Bắt đầu chia nhỏ.")
        
        pallet_remains = pallet_to_split
        
        # Vòng lặp để liên tục tách ra các phần đủ để lấp đầy một container
        while (pallet_remains.quantity > MAX_PALLETS + EPSILON or 
               pallet_remains.total_weight > MAX_WEIGHT + EPSILON):
            
            # Tính toán số lượng tối đa có thể xếp vào một container mới mà không vi phạm
            # cả về số lượng lẫn trọng lượng.
            
            # Mặc định, số lượng tách ra là giới hạn tối đa của container
            split_qty = MAX_PALLETS
            
            # Nếu trọng lượng là yếu tố giới hạn, tính lại số lượng tách ra
            if pallet_remains.weight_per_pallet > EPSILON:
                qty_allowed_by_weight = MAX_WEIGHT / pallet_remains.weight_per_pallet
                # Lấy giá trị nhỏ hơn để đảm bảo không vi phạm cả hai điều kiện
                if qty_allowed_by_weight < split_qty:
                    split_qty = qty_allowed_by_weight

            # Thực hiện chia pallet
            # `rem_part` là phần còn lại, `new_part` là phần được tách ra để cho vào container mới
            rem_part, new_part = pallet_remains.split(split_qty)

            if new_part is None:
                # Không thể chia nhỏ hơn, dừng vòng lặp để tránh lặp vô hạn
                print(f"WARN: Không thể chia nhỏ pallet {pallet_remains.id} thêm nữa.")
                break

            # Tạo container mới và thêm phần pallet đã tách vào
            new_container_id = f"Cont_{container_id_counter['count']}"
            container_id_counter['count'] += 1
            
            new_container = Container(new_container_id, new_part.company)
            new_container.add_pallet(new_part)
            finalized_containers.append(new_container)
            
            print(f"  -> Đã tạo {new_container.id} với một phần của pallet (Qty: {new_part.quantity:.2f}, Wgt: {new_part.total_weight:.2f}).")

            # Cập nhật phần còn lại để tiếp tục vòng lặp
            pallet_remains = rem_part
        
        # Sau khi vòng lặp kết thúc, phần còn lại không còn quá khổ
        if pallet_remains and pallet_remains.quantity > EPSILON:
            print(f"  -> Phần còn lại của pallet {pallet_to_split.id} (Qty: {pallet_remains.quantity:.2f}, Wgt: {pallet_remains.total_weight:.2f}) sẽ được xử lý chung.")
            remaining_split_parts.append(pallet_remains)

    # Bước 3: Gộp danh sách pallet bình thường và các phần còn lại để xử lý tiếp
    pallets_for_next_phase = pallets_normal_size + remaining_split_parts
    
    return finalized_containers, pallets_for_next_phase

####################   GIAI ĐOẠN 1    #########################
def _pack_pallets_into_containers(pallets, containers, strategy, main_company, container_id_counter):
    """
    Hàm phụ trợ để xếp một danh sách pallet vào các container theo một chiến lược cụ thể.

    Args:
        pallets (list): Danh sách các đối tượng Pallet cần xếp.
        containers (list): Danh sách các container hiện có để xếp vào.
        strategy (str): Chiến lược xếp hàng ('first_fit' hoặc 'best_fit_by_quantity').
        main_company (str): Tên công ty chính của đợt xếp hàng này.
        container_id_counter (dict): Một dictionary để theo dõi và tăng ID cho container mới.
    """
    # Sắp xếp các pallet cần xếp theo thứ tự giảm dần về số lượng. 
    # Áp dụng cho cả ba loại pallet theo yêu cầu của Giai đoạn 1.
    pallets.sort(key=lambda p: p.quantity, reverse=True)

    for pallet in pallets:
        target_container = None

        if strategy == 'first_fit':
            # Chiến lược First-Fit: Tìm container đầu tiên có đủ chỗ. 
            for container in containers:
                if container.can_fit(pallet):
                    target_container = container
                    break
        
        elif strategy == 'best_fit_by_quantity':
            # Chiến lược Best-Fit: Tìm container vừa và để lại ít không gian trống nhất. 
            best_fit_container = None
            min_remaining_space = float('inf')
            
            # Sắp xếp các container theo ID để đảm bảo tính nhất quán (deterministic)
            # nếu có nhiều lựa chọn "best fit" tương đương nhau.
            sorted_containers = sorted(containers, key=lambda c: int(c.id.split('_')[-1]))

            for container in sorted_containers:
                if container.can_fit(pallet):
                    # Tính toán không gian pallet còn lại sau khi thêm pallet
                    remaining_space = container.remaining_quantity - pallet.quantity
                    # Tìm không gian nhỏ nhất (nhưng vẫn phải >= 0)
                    if 0 <= remaining_space < min_remaining_space:
                        min_remaining_space = remaining_space
                        best_fit_container = container
            target_container = best_fit_container
            
        # Thêm pallet vào container đã chọn hoặc tạo container mới.
        if target_container:
            target_container.add_pallet(pallet) # 
        else:
            # Nếu không có container nào phù hợp, mở một container mới. 
            new_container_id = f"Cont_{container_id_counter['count']}"
            container_id_counter['count'] += 1
            new_container = Container(new_container_id, main_company)
            new_container.add_pallet(pallet)
            containers.append(new_container)

def layered_priority_packing(pallets_integer, pallets_combined, pallets_single_float, main_company, container_id_counter):
    """
    Giai đoạn 1: Xếp hàng Ưu tiên theo Lớp (Layered Priority Packing). 
    Thực hiện xếp hàng ban đầu theo một chuỗi các quy tắc ưu tiên nghiêm ngặt.

    Args:
        pallets_integer (list): Danh sách pallet số nguyên từ Giai đoạn 0.
        pallets_combined (list): Danh sách pallet đã gộp từ Giai đoạn 0.
        pallets_single_float (list): Danh sách pallet float lẻ từ Giai đoạn 0.
        main_company (str): Tên công ty chính đang được xử lý.
        container_id_counter (dict): Bộ đếm để tạo ID container duy nhất.

    Returns:
        list: Một danh sách các đối tượng Container đã được xếp hàng sơ bộ. 
    """
    packed_containers = []

    # Bước 1.1: Xếp Pallet Số nguyên (Integer Pallet Packing) sử dụng First-Fit. 
    _pack_pallets_into_containers(
        pallets=pallets_integer,
        containers=packed_containers,
        strategy='first_fit',
        main_company=main_company,
        container_id_counter=container_id_counter
    )

    # Bước 1.2: Xếp Pallet Gộp (Combined Pallet Packing) sử dụng First-Fit. 
    _pack_pallets_into_containers(
        pallets=pallets_combined,
        containers=packed_containers,
        strategy='first_fit',
        main_company=main_company,
        container_id_counter=container_id_counter
    )

    # Bước 1.3: Xếp Pallet Lẻ (Single Float Packing) sử dụng Best-Fit theo số lượng. 
    _pack_pallets_into_containers(
        pallets=pallets_single_float,
        containers=packed_containers,
        strategy='best_fit_by_quantity',
        main_company=main_company,
        container_id_counter=container_id_counter
    )

    return packed_containers
####################   GIAI ĐOẠN 2    #########################
# --- HẰNG SỐ CẤU HÌNH CHO GIAI ĐOẠN 2 ---
THRESHOLD_FILL_RATE = 0.25 # Tỷ lệ lấp đầy tối thiểu (ví dụ: 25%) 
THRESHOLD_PALLET_COUNT = 2    # Số lượng pallet tối thiểu (ví dụ: 2) 

def defragment_and_consolidate(initial_packed_containers):

    # Bước 2.1: Xác định Container "Lãng phí" 
    good_containers = []
    wasteful_containers = []

    if not initial_packed_containers:
        return [], []

    for container in initial_packed_containers:
        fill_rate = container.total_quantity / MAX_PALLETS
        pallet_count = len(container.pallets)

        # Phân loại container: "tốt" nếu đạt cả hai ngưỡng 
        if fill_rate >= THRESHOLD_FILL_RATE and pallet_count >= THRESHOLD_PALLET_COUNT:
            good_containers.append(container)
        else:
            # Container bị coi là "lãng phí" nếu đạt ít nhất 1 trong 2 ngưỡng 
            wasteful_containers.append(container)

    # Bước 2.2: Tạo Bể Pallet Tái phân bổ 
    pallets_for_redeployment = []
    for container in wasteful_containers:
        # Dỡ tất cả các pallet từ container lãng phí và đưa vào bể tái phân bổ 
        pallets_for_redeployment.extend(container.pallets)
    # Các container lãng phí coi như bị loại bỏ 
    
    # Sắp xếp các pallet cần tái phân bổ từ lớn đến nhỏ để ưu tiên xử lý các pallet lớn trước
    pallets_for_redeployment.sort(key=lambda p: p.quantity, reverse=True)

    # Bước 2.3: Tách nhỏ và Lấp đầy 
    pallets_for_cross_shipping = []
    
    # Sắp xếp các container "tốt" để lấp đầy một cách nhất quán
    good_containers.sort(key=lambda c: c.remaining_quantity)

    for pallet_to_redeploy in pallets_for_redeployment:
        pallet_remains = pallet_to_redeploy
        
        # Vòng lặp để cố gắng xếp các phần của pallet vào các khoảng trống trong container "tốt" 
        for container in good_containers:
            if pallet_remains is None or pallet_remains.quantity < EPSILON:
                break # Pallet đã được xếp hết

            if container.remaining_quantity > EPSILON and container.remaining_weight > EPSILON:
                # Tính lượng tối đa có thể thêm theo trọng lượng
                max_qty_by_weight = float('inf')
                if pallet_remains.weight_per_pallet > 0:
                    max_qty_by_weight = container.remaining_weight / pallet_remains.weight_per_pallet
                
                # Lượng thực tế để tách là giá trị nhỏ nhất, thỏa mãn cả số lượng và trọng lượng
                split_quantity = min(container.remaining_quantity, max_qty_by_weight)

                if split_quantity >= pallet_remains.quantity - EPSILON:
                    # Nếu có thể xếp toàn bộ phần còn lại của pallet
                    container.add_pallet(pallet_remains)
                    pallet_remains = None 
                elif split_quantity > EPSILON:
                    # Nếu chỉ có thể xếp một phần, thực hiện tách pallet 
                    original_part, new_part = pallet_remains.split(split_quantity)
                    
                    if original_part and new_part:
                        container.add_pallet(new_part)
                        pallet_remains = original_part # Phần còn lại để tiếp tục xếp
        
        # Nếu sau khi thử tất cả các container "tốt" mà pallet vẫn còn,
        # nó sẽ được chuyển sang danh sách chờ vận chuyển chéo 
        if pallet_remains is not None and pallet_remains.quantity > EPSILON:
            pallets_for_cross_shipping.append(pallet_remains)

    final_containers = good_containers
    return final_containers, pallets_for_cross_shipping


####################   GIAI ĐOẠN 3    #########################
# --- CÁC HÀM PHỤ TRỢ CHO GIAI ĐOẠN 3 ---

def _find_pallet_sibling(pallet_to_find_sibling_for, all_containers):
    """
    Tìm pallet "anh em" (sibling) của một pallet đã bị tách.
    Hàm này rất quan trọng cho logic "truy hồi".
    
    """
    if not pallet_to_find_sibling_for.is_split or not pallet_to_find_sibling_for.sibling_id:
        return None, None

    for container in all_containers:
        for pallet in container.pallets:
            if pallet.id == pallet_to_find_sibling_for.sibling_id:
                return pallet, container # Trả về pallet anh em và container chứa nó
    return None, None

def _execute_lookback_and_roundup(pallet_to_round, all_containers):
    """
    Thực hiện logic "truy hồi" để làm tròn một pallet float lên số nguyên gần nhất.
    """
    if pallet_to_round.quantity >= math.floor(pallet_to_round.quantity) + EPSILON:
        target_quantity = math.ceil(pallet_to_round.quantity)
        needed_quantity = target_quantity - pallet_to_round.quantity

        sibling_pallet, sibling_container = _find_pallet_sibling(pallet_to_round, all_containers)

        # Đảm bảo có cả pallet anh em và container chứa nó
        if sibling_pallet and sibling_container and sibling_pallet.quantity > needed_quantity + EPSILON:
            
            # --- PHẦN SỬA LỖI ---
            # 1. Cập nhật container chứa pallet "anh em" TRƯỚC
            sibling_container.total_quantity -= needed_quantity
            sibling_container.total_weight -= needed_quantity * sibling_pallet.weight_per_pallet
            # --- KẾT THÚC SỬA LỖI ---

            # 2. Cập nhật chính pallet "anh em"
            sibling_pallet.quantity -= needed_quantity
            sibling_pallet.total_weight = sibling_pallet.quantity * sibling_pallet.weight_per_pallet
            
            # 3. Bù vào pallet cần làm tròn
            pallet_to_round.quantity = target_quantity
            pallet_to_round.total_weight = pallet_to_round.quantity * pallet_to_round.weight_per_pallet

            print(f"INFO: Truy hồi thành công. Pallet {pallet_to_round.id} được làm tròn thành {target_quantity}. "
                  f"Pallet anh em {sibling_pallet.id} còn lại {sibling_pallet.quantity:.2f}.")
            return True # Làm tròn thành công
            
    return False # Không thể làm tròn
def _attempt_cross_shipment(pallets_to_ship, receiving_containers, all_containers):
    """
    Cố gắng xếp các pallet cần vận chuyển chéo vào các container của đối tác.
    Bao gồm logic làm tròn (TH1), tách nhỏ (TH2), và trả về phần còn lại (TH3).
    """
    remaining_cross_ship_pallets = []
    
    # Sắp xếp pallet cần gửi từ lớn đến nhỏ
    pallets_to_ship.sort(key=lambda p: p.quantity, reverse=True)

    for pallet in pallets_to_ship:
        # Ưu tiên làm tròn pallet lên số nguyên nếu có thể 
        _execute_lookback_and_roundup(pallet, all_containers)
        
        # Sắp xếp các container nhận theo không gian trống ít nhất (Best-fit) để ưu tiên lấp đầy
        receiving_containers.sort(key=lambda c: c.remaining_quantity)
        
        # TH1: Tìm một container duy nhất có thể chứa toàn bộ pallet 
        perfect_fit_container = None
        for container in receiving_containers:
            if container.can_fit(pallet):
                perfect_fit_container = container
                break # Tìm thấy container phù hợp đầu tiên
        
        if perfect_fit_container:
            perfect_fit_container.add_pallet(pallet)
            print(f"INFO: Vận chuyển chéo (TH1) thành công. Pallet {pallet.id} ({pallet.quantity:.2f} qty) "
                  f"đã được xếp vào Container {perfect_fit_container.id}.")
            continue # Chuyển sang pallet tiếp theo

        # TH2: Nếu không có "perfect fit", kiểm tra xem tổng không gian có đủ để tách nhỏ không
        total_rem_qty = sum(c.remaining_quantity for c in receiving_containers)
        total_rem_wgt = sum(c.remaining_weight for c in receiving_containers)

        if total_rem_qty >= pallet.quantity - EPSILON and total_rem_wgt >= pallet.total_weight - EPSILON:
            print(f"INFO: Bắt đầu vận chuyển chéo (TH2) cho Pallet {pallet.id} ({pallet.quantity:.2f} qty).")
            pallet_remains_to_ship = pallet
            
            # Tách pallet và lấp đầy các khoảng trống
            for container in receiving_containers:
                if pallet_remains_to_ship is None or pallet_remains_to_ship.quantity < EPSILON:
                    break
                
                if container.remaining_quantity > EPSILON:
                    max_qty_by_weight = float('inf')
                    if pallet_remains_to_ship.weight_per_pallet > 0:
                         max_qty_by_weight = container.remaining_weight / pallet_remains_to_ship.weight_per_pallet
                    
                    split_quantity = min(container.remaining_quantity, max_qty_by_weight)
                    
                    if split_quantity >= pallet_remains_to_ship.quantity - EPSILON:
                        container.add_pallet(pallet_remains_to_ship)
                        pallet_remains_to_ship = None
                    elif split_quantity > EPSILON:
                        original_part, new_part = pallet_remains_to_ship.split(split_quantity)
                        if original_part and new_part:
                            container.add_pallet(new_part)
                            pallet_remains_to_ship = original_part
            
            if pallet_remains_to_ship and pallet_remains_to_ship.quantity > EPSILON:
                 # Về mặt lý thuyết, điều này không nên xảy ra nếu logic kiểm tra tổng không gian là đúng
                 remaining_cross_ship_pallets.append(pallet_remains_to_ship)
            
            continue # Chuyển sang pallet tiếp theo

        # TH3: Không có chỗ vừa vặn và tổng không gian cũng không đủ 
        print(f"INFO: Vận chuyển chéo (TH3) không thành công cho Pallet {pallet.id}. "
              f"Đưa vào danh sách chờ cuối cùng.")
        remaining_cross_ship_pallets.append(pallet)
        
    return remaining_cross_ship_pallets


def phase_3_cross_shipping_and_finalization(
    final_containers_c1, cross_ship_pallets_c1,
    final_containers_c2, cross_ship_pallets_c2,
    container_id_counter):
    """
    Giai đoạn 3: Xử lý vận chuyển chéo và hoàn thiện việc xếp hàng.
    """
    # Gom tất cả container vào một danh sách để dễ dàng truy hồi
    all_current_containers = final_containers_c1 + final_containers_c2
    
    pallets_for_new_shared_container = []

    # TH1: Cả hai công ty đều có pallet chờ vận chuyển chéo
    if cross_ship_pallets_c1 and cross_ship_pallets_c2:
        print("INFO: Cả hai công ty đều có pallet chờ. Gộp vào danh sách chờ container chung.")
        pallets_for_new_shared_container.extend(cross_ship_pallets_c1)
        pallets_for_new_shared_container.extend(cross_ship_pallets_c2)
    
    # TH2: Chỉ công ty 1 có pallet chờ, gửi sang công ty 2
    elif cross_ship_pallets_c1:
        print("INFO: Chỉ công ty 1 có pallet chờ. Thử vận chuyển chéo sang công ty 2.")
        remaining = _attempt_cross_shipment(
            pallets_to_ship=cross_ship_pallets_c1,
            receiving_containers=final_containers_c2,
            all_containers=all_current_containers
        )
        pallets_for_new_shared_container.extend(remaining)

    # TH2: Chỉ công ty 2 có pallet chờ, gửi sang công ty 1
    elif cross_ship_pallets_c2:
        print("INFO: Chỉ công ty 2 có pallet chờ. Thử vận chuyển chéo sang công ty 1.")
        remaining = _attempt_cross_shipment(
            pallets_to_ship=cross_ship_pallets_c2,
            receiving_containers=final_containers_c1,
            all_containers=all_current_containers
        )
        pallets_for_new_shared_container.extend(remaining)
        
    # TH cuối: Không có pallet nào cần vận chuyển chéo
    else:
        print("INFO: Không có pallet nào cần vận chuyển chéo. Quá trình kết thúc.")
        return all_current_containers # Trả về kết quả cuối cùng

    # Xếp các pallet còn lại vào các container chung mới
    if pallets_for_new_shared_container:
        print("INFO: Xếp các pallet còn dư vào container chung mới.")
        _pack_pallets_into_containers(
            pallets=pallets_for_new_shared_container,
            containers=all_current_containers,
            strategy='first_fit',
            main_company='SHARED', # Đánh dấu là container chung
            container_id_counter=container_id_counter
        )
        
    return all_current_containers


