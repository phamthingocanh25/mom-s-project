# backend/data_processor.py
import pandas as pd
import math
import warnings # Import the warnings library
import re 

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
        self.split_from_id = None
        self.sibling_id = None

    def __repr__(self):
        type_info = ""
        if self.is_combined:
            type_info = f" [Combined ({len(self.original_pallets)} items)]"
        if self.is_split:
            type_info += f" [Split from {self.split_from_id}]"
        if self.is_cross_ship:
            type_info += " [Cross-Ship]"
        return (f"Pallet(id={self.id}, qty={self.quantity:.2f}, "
                f"wgt={self.total_weight:.2f}, Cty={self.company}){type_info}")

    def split(self, split_quantity):
        """
        Tách pallet hiện tại thành hai phần một cách chính xác, đặc biệt đối với pallet gộp.
        Phiên bản này đảm bảo tổng các pallet con LUÔN LUÔN khớp với số lượng của phần pallet cha.
        """
        # --- BƯỚC 1: KIỂM TRA ĐIỀU KIỆN ĐẦU VÀO ---
        if not (EPSILON < split_quantity < self.quantity - EPSILON):
            return None, None

        # --- BƯỚC 2: KHỞI TẠO CÁC PHẦN PALLET MỚI (TẠM THỜI) ---
        original_id = self.id
        new_part = Pallet(
            p_id=f"{original_id}-part", product_code=self.product_code,
            product_name=self.product_name, company=self.company,
            quantity=split_quantity, weight_per_pallet=self.weight_per_pallet
        )
        new_part.is_combined = self.is_combined
        new_part.is_split = True
        new_part.split_from_id = original_id

        rem_part = Pallet(
            p_id=f"{original_id}-rem", product_code=self.product_code,
            product_name=self.product_name, company=self.company,
            quantity=self.quantity - split_quantity, weight_per_pallet=self.weight_per_pallet
        )
        rem_part.is_combined = self.is_combined
        rem_part.is_split = True
        rem_part.split_from_id = original_id
        new_part.sibling_id = rem_part.id
        rem_part.sibling_id = new_part.id

        # --- BƯỚC 3: PHÂN BỔ DANH SÁCH PALLET CON ---
        if not self.is_combined:
            new_part.original_pallets = [new_part]
            rem_part.original_pallets = [rem_part]
        else:
            new_part_originals_list = []
            rem_part_originals_list = []
            quantity_needed_for_new_part = split_quantity
            unassigned_originals = sorted(self.original_pallets, key=lambda p: p.quantity, reverse=True)
            temp_unassigned = []

            for sub_pallet in unassigned_originals:
                if sub_pallet.quantity <= quantity_needed_for_new_part + EPSILON:
                    new_part_originals_list.append(sub_pallet)
                    quantity_needed_for_new_part -= sub_pallet.quantity
                else:
                    temp_unassigned.append(sub_pallet)
            unassigned_originals = temp_unassigned

            if quantity_needed_for_new_part > EPSILON:
                unassigned_originals.sort(key=lambda p: p.quantity)
                boundary_pallet_to_split = None
                boundary_pallet_index = -1
                for i, p in enumerate(unassigned_originals):
                    if p.quantity > quantity_needed_for_new_part - EPSILON:
                        boundary_pallet_to_split = p
                        boundary_pallet_index = i
                        break

                if boundary_pallet_to_split:
                    # ### SỬA LỖI TRỌNG TÂM: TẠO TRỰC TIẾP CÁC MẢNH PALLET CON ###
                    # Loại bỏ việc gọi đệ quy `split()` để tránh lỗi tính toán.
                    # Thay vào đó, chúng ta tạo ra 2 mảnh mới một cách tường minh.

                    # Mảnh mới để lấp đầy phần còn thiếu
                    new_sub_part = Pallet(
                        p_id=f"{boundary_pallet_to_split.id}-part",
                        product_code=boundary_pallet_to_split.product_code,
                        product_name=boundary_pallet_to_split.product_name,
                        company=boundary_pallet_to_split.company,
                        quantity=quantity_needed_for_new_part, # Số lượng CHÍNH XÁC cần thiết
                        weight_per_pallet=boundary_pallet_to_split.weight_per_pallet
                    )
                    new_sub_part.is_split = True
                    new_sub_part.split_from_id = boundary_pallet_to_split.id

                    # Mảnh còn lại của pallet con
                    remaining_sub_part = Pallet(
                        p_id=f"{boundary_pallet_to_split.id}-rem",
                        product_code=boundary_pallet_to_split.product_code,
                        product_name=boundary_pallet_to_split.product_name,
                        company=boundary_pallet_to_split.company,
                        quantity=boundary_pallet_to_split.quantity - quantity_needed_for_new_part,
                        weight_per_pallet=boundary_pallet_to_split.weight_per_pallet
                    )
                    remaining_sub_part.is_split = True
                    remaining_sub_part.split_from_id = boundary_pallet_to_split.id
                    
                    # Liên kết 2 mảnh con với nhau
                    new_sub_part.sibling_id = remaining_sub_part.id
                    remaining_sub_part.sibling_id = new_sub_part.id

                    # Thêm các mảnh đã tách vào đúng danh sách
                    new_part_originals_list.append(new_sub_part)
                    rem_part_originals_list.append(remaining_sub_part)
                    unassigned_originals.pop(boundary_pallet_index)
                    # ### KẾT THÚC SỬA LỖI ###

            rem_part_originals_list.extend(unassigned_originals)
            new_part.original_pallets = new_part_originals_list
            rem_part.original_pallets = rem_part_originals_list

        # --- BƯỚC 4: TÍNH TOÁN LẠI ĐỂ ĐẢM BẢO TÍNH TOÀN VẸN (Vẫn giữ) ---
        new_part.quantity = sum(p.quantity for p in new_part.original_pallets)
        new_part.total_weight = sum(p.total_weight for p in new_part.original_pallets)
        if new_part.quantity > EPSILON:
            new_part.weight_per_pallet = new_part.total_weight / new_part.quantity

        rem_part.quantity = sum(p.quantity for p in rem_part.original_pallets)
        rem_part.total_weight = sum(p.total_weight for p in rem_part.original_pallets)
        if rem_part.quantity > EPSILON:
            rem_part.weight_per_pallet = rem_part.total_weight / rem_part.quantity

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

def load_and_map_raw_data_for_pkl(filepath, sheet_name):
    """
    Trích xuất và ánh xạ dữ liệu thô từ file Excel gốc để chuẩn bị cho việc tạo Packing List.
    Hàm này sẽ là nguồn cung cấp dữ liệu duy nhất cho PKL.
    """
    print(f"[DATA_PROCESSOR] Loading raw PKL data from: {filepath}, Sheet: {sheet_name}")
    try:
        # Xác định các cột cần thiết cho Packing List theo framework
        # B(1), C(2), F(5), G(6), H(7), AW(48)
        # Cột K(10) đã được xử lý ở bước tối ưu nhưng vẫn có thể lấy ở đây nếu cần
        column_indices_pkl = [1, 2, 4, 5, 6, 7,12, 48] 
        column_names_pkl = ['Part No', 'Part Name', 'Wpc_kgs','QtyPerBox', 'WeightPerPc_Raw', 'BoxPerPallet','TotalPcsFromM', 'BoxSpec']

        df_raw = pd.read_excel(
            filepath, 
            sheet_name=sheet_name, 
            header=None, 
            skiprows=5,
            usecols=column_indices_pkl,
            names=column_names_pkl
        ).fillna('')

        # 1. Tạo khóa tra cứu duy nhất từ Part No và Part Name
        df_raw['lookup_key'] = df_raw['Part No'].astype(str) + '||' + df_raw['Part Name'].astype(str)
        
        # 2. Loại bỏ các dòng bị trùng lặp, chỉ giữ lại dòng đầu tiên xuất hiện
        df_raw_unique = df_raw.drop_duplicates(subset='lookup_key', keep='first')
        
        # 3. Chuyển DataFrame đã được làm sạch thành một dictionary để tra cứu nhanh
        raw_data_map = df_raw_unique.set_index('lookup_key').to_dict('index')
        for key in raw_data_map:
            for field in ['QtyPerBox', 'BoxPerPallet', 'WeightPerPc_Raw','TotalPcsFromM', 'Wpc_kgs']:
                if field in raw_data_map[key]:
                   value = raw_data_map[key][field]
                   if value in ["", None]:
                      raw_data_map[key][field] = 0  # Gán giá trị mặc định
                   elif isinstance(value, str):
                # Loại bỏ ký tự đặc biệt
                        cleaned = re.sub(r'[^\d.]', '', value)
                        raw_data_map[key][field] = cleaned if cleaned else 0
        print(f"[DATA_PROCESSOR] Successfully created raw data map with {len(raw_data_map)} unique items.")
        return raw_data_map, None
    
    except Exception as e:
        error_msg = f"Lỗi khi đọc dữ liệu thô cho Packing List: {e}"
        print(f"[DATA_PROCESSOR] ERROR: {error_msg}")
        return None, error_msg
    
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
        
      # --- BẮT ĐẦU SỬA LỖI ĐỂ CHUẨN HÓA CỘT CÔNG TY ---
# 1. Chuyển đổi cột công ty sang dạng số, các giá trị không hợp lệ sẽ thành NaN
        df['company'] = pd.to_numeric(df['company'], errors='coerce')

# 2. Thay thế các giá trị NaN (ví dụ: ô trống) bằng một số mặc định, ở đây là 0
        df['company'] = df['company'].fillna(0)

# 3. Chuyển đổi cột số thành kiểu số nguyên để loại bỏ phần thập phân ".0"
        df['company'] = df['company'].astype(int)

# 4. Cuối cùng, chuyển đổi sang kiểu chuỗi để sử dụng trong logic so sánh
        df['company'] = df['company'].astype(str)
# --- KẾT THÚC SỬA LỖI ---

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
    PHIÊN BẢN SỬA ĐỔI: Chỉ thực hiện gộp (consolidate) các dòng trên Packing List
    cho các pallet gộp "thực sự" (có ID bắt đầu bằng 'Combined_').
    Các pallet đơn bị chia nhỏ sẽ được hiển thị chi tiết.
    """
    containers_list = []
    for container in sorted(final_containers, key=lambda c: int(c.id.split('_')[-1])):
        container_contents = []
        for pallet in container.pallets:
            pallet_data = {}
            if pallet.is_combined:
                items = []
                # --- LOGIC MỚI: Kiểm tra ID để quyết định có gộp hay không ---
                # Chỉ gộp nếu đây là pallet được tạo ra trong giai đoạn gộp hàng.
                is_true_combined_pallet = pallet.id.startswith('Combined_')

                list_to_process = []
                if is_true_combined_pallet:
                    # Với pallet gộp thực sự, ta làm gọn báo cáo
                    list_to_process = consolidate_sub_pallets(pallet.original_pallets)
                else:
                    # Với pallet đơn bị chia nhỏ, ta hiển thị chi tiết từng mảnh
                    list_to_process = pallet.original_pallets
                # --- KẾT THÚC LOGIC MỚI ---

                for p_orig in list_to_process:
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
                    "is_split": pallet.is_split,
                    "is_cross_ship": pallet.is_cross_ship
                }
            else: # Xử lý pallet đơn lẻ như cũ
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
            "contents": container_contents
        }
        containers_list.append(container_details)

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
            if current_total_quantity + pallet.quantity <= threshold + EPSILON and pallet.company == main_pallet.company:
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
def find_best_split_move(pallet_to_split, available_containers):
    """
    Tìm nước đi chia pallet tốt nhất (container và số lượng) dựa trên bộ quy tắc ưu tiên.
    
    Quy tắc:
    1. Ưu tiên tuyệt đối việc tách ra một số NGUYÊN các pallet (1.0, 2.0, ...)
       và đặt vào container có không gian vừa vặn nhất.
    2. Nếu không thể đi nước đi số nguyên, sẽ tìm cách chia để lấp đầy container
       một cách vừa vặn nhất (để lại ít khoảng trống nhất - chiến lược best-fit).

    Trả về: (container tốt nhất, số lượng pallet cần tách) hoặc (None, 0) nếu không có nước đi hợp lệ.
    """
    # --- QUY TẮC 1: TÌM NƯỚC ĐI SỐ NGUYÊN TỐT NHẤT ---
    best_integer_move = {'container': None, 'quantity': 0, 'wasted_space': float('inf')}
    
    # Chỉ xem xét nếu pallet gốc có thể tách ra ít nhất 1.0
    if pallet_to_split.quantity >= 1.0:
        for container in available_containers:
            # Số pallet nguyên tối đa có thể tách ra để cho vào container này
            possible_integer_pallets = math.floor(min(pallet_to_split.quantity, container.remaining_quantity))
            
            if possible_integer_pallets >= 1:
                # Kiểm tra xem có đủ tải trọng không
                weight_needed = possible_integer_pallets * pallet_to_split.weight_per_pallet
                if container.remaining_weight >= weight_needed:
                    # Tính điểm "lãng phí" (không gian còn thừa)
                    wasted_space = container.remaining_quantity - possible_integer_pallets
                    
                    # Lưu lại nếu nước đi này tốt hơn (ít lãng phí hơn) các nước đi số nguyên trước
                    if wasted_space < best_integer_move['wasted_space']:
                        best_integer_move.update({
                            'container': container,
                            'quantity': float(possible_integer_pallets),
                            'wasted_space': wasted_space
                        })
    
    # Nếu đã tìm được một nước đi số nguyên hợp lệ, đây là ưu tiên hàng đầu -> trả về ngay
    if best_integer_move['container']:
        return best_integer_move['container'], best_integer_move['quantity']

    # --- QUY TẮC 2: TÌM NƯỚC ĐI LẤP ĐẦY (BEST-FIT) TỐT NHẤT ---
    best_fill_move = {'container': None, 'quantity': 0, 'remaining_gap': float('inf')}

    for container in available_containers:
        # Tính lượng tối đa có thể cho vào container này (xét cả số lượng và tải trọng)
        max_qty_by_weight = container.remaining_weight / pallet_to_split.weight_per_pallet if pallet_to_split.weight_per_pallet > 0 else float('inf')
        possible_split_qty = min(container.remaining_quantity, max_qty_by_weight)

        # Bỏ qua nếu lượng có thể chia quá nhỏ
        if possible_split_qty < MIN_PRACTICAL_SPLIT_QTY:
            continue

        # Bỏ qua nếu việc chia sẽ tạo ra một mảnh thừa quá nhỏ và vô dụng
        remainder = pallet_to_split.quantity - possible_split_qty
        if remainder > EPSILON and remainder < MIN_PRACTICAL_SPLIT_QTY:
            continue
            
        # Tìm nước đi lấp đầy vừa vặn nhất (để lại khoảng trống trong cont nhỏ nhất)
        remaining_gap = container.remaining_quantity - possible_split_qty
        if remaining_gap < best_fill_move['remaining_gap']:
             best_fill_move.update({
                 'container': container,
                 'quantity': possible_split_qty,
                 'remaining_gap': remaining_gap
             })

    if best_fill_move['container']:
        return best_fill_move['container'], best_fill_move['quantity']
        
    # Nếu không tìm thấy bất kỳ nước đi hợp lệ nào
    return None, 0
def _place_pallet_with_priority(pallet, containers):
    """
    Cố gắng xếp một pallet vào các container theo logic ưu tiên mới, tập trung
    vào việc giữ các thành phần trong cùng công ty và giảm thiểu việc chia tách.

    Hàm này sẽ trả về phần pallet còn lại không thể xếp được (nếu có),
    hoặc trả về None nếu toàn bộ pallet đã được xếp thành công.

    --- LOGIC ƯU TIÊN MỚI (SỬA ĐỔI) ---
    1.  **Xếp nguyên vẹn:** Cố gắng xếp toàn bộ pallet vào một container duy nhất,
        ưu tiên container CÙNG CÔNG TY trước.

    2.  **Chia (Phần nguyên + Phần lẻ):** Nếu không thể xếp nguyên vẹn, thử chia pallet
        thành (phần nguyên, phần lẻ, và phần thừa). Cố gắng xếp CẢ PHẦN NGUYÊN
        và PHẦN LẺ vào các container CÙNG CÔNG TY. Phần thừa sau đó sẽ được xử lý
        theo một logic ưu tiên riêng.

    3.  **Xử lý phần thừa (sau Ưu tiên 2):**
        a. Cố gắng xếp nguyên vẹn phần thừa vào bất kỳ container nào (ưu tiên cùng công ty).
        b. Nếu không được, ưu tiên tách MỘT PHẦN NGUYÊN từ phần thừa để xếp vào container CÙNG CÔNG TY.
        c. Phần còn lại cuối cùng sẽ được xếp vào các container khác công ty, ưu tiên
           tách số nguyên ("sạch") trước, sau đó mới lấp đầy.

    4.  **Chia nhỏ lấp đầy (Biện pháp cuối):** Nếu các bước trên thất bại, chia nhỏ
        pallet để lấp đầy các khoảng trống còn lại trong các container, ưu tiên
        container cùng công ty trước.
    """
    # --- HÀM HỖ TRỢ ---
    def find_best_fit(p, cont_list):
        """Tìm container trong danh sách vừa vặn nhất cho pallet p."""
        best_cont = None
        min_rem_space = float('inf')
        for c in cont_list:
            if c.can_fit(p):
                rem_space = c.remaining_quantity - p.quantity
                if rem_space < min_rem_space:
                    min_rem_space = rem_space
                    best_cont = c
        return best_cont

    # --- KHỞI TẠO ---
    same_co_containers = sorted([c for c in containers if c.main_company == pallet.company], key=lambda c: c.remaining_quantity)
    other_co_containers = sorted([c for c in containers if c.main_company != pallet.company], key=lambda c: c.remaining_quantity)

    # --- ƯU TIÊN 1: CỐ GẮNG XẾP NGUYÊN VẸN ---
    all_available_containers_p1 = same_co_containers + other_co_containers
    target_container = find_best_fit(pallet, all_available_containers_p1)
    if target_container:
        target_container.add_pallet(pallet)
        return None  # Xếp thành công, không còn pallet thừa
    # --- LOGIC MỚI: KIỂM TRA KHẢ NĂNG XẾP NGUYÊN VẸN SANG CTY KHÁC ---
    target_container_other_co_full_fit = find_best_fit(pallet, other_co_containers)
    
    # --- ƯU TIÊN 2-B: TỐI ƯU HÓA TRƯỚC KHI VẬN CHUYỂN CHÉO ---
    if target_container_other_co_full_fit:
        # KÍCH HOẠT: Có thể vận chuyển chéo nguyên pallet. Thay vì làm ngay, hãy thử tối ưu.

        # a. Thử chia "sạch" theo số nguyên (ví dụ 6.7 -> 6.0 + 0.7)
        if pallet.quantity >= 1.0:
            original_int_q = math.floor(pallet.quantity)
            # Lặp ngược từ phần nguyên lớn nhất có thể
            for int_q_to_try in range(original_int_q, 0, -1):
                p_remainder, p_integer_part = pallet.split(float(int_q_to_try))
                if not p_integer_part or not p_remainder:
                    continue

                # Cố gắng xếp phần nguyên lớn vào container cùng công ty
                int_part_container_target = find_best_fit(p_integer_part, same_co_containers)
                if int_part_container_target:
                    # Nếu được, kiểm tra xem phần lẻ có thể xếp vào container khác công ty không
                    if target_container_other_co_full_fit.can_fit(p_remainder):
                        # THÀNH CÔNG: Đây là kịch bản tối ưu nhất
                        int_part_container_target.add_pallet(p_integer_part)
                        target_container_other_co_full_fit.add_pallet(p_remainder)
                        return None  # Xếp xong, kết thúc

        # b. Nếu chia số nguyên không được, thử giữ lại phần lớn nhất có thể ở cùng công ty
        best_split_option = {
            'part_for_same_co': None, 'rem_for_other_co': None,
            'same_co_container_target': None, 'qty_for_same_co': 0
        }
        for s_cont in same_co_containers:
            if s_cont.remaining_quantity < MIN_PRACTICAL_SPLIT_QTY:
                continue

            max_qty_by_weight = (s_cont.remaining_weight / pallet.weight_per_pallet) if pallet.weight_per_pallet > EPSILON else float('inf')
            possible_qty_to_place = min(s_cont.remaining_quantity, max_qty_by_weight, pallet.quantity)
            
            # Bỏ qua nếu việc chia tạo ra mảnh thừa quá nhỏ
            remainder_qty = pallet.quantity - possible_qty_to_place
            if remainder_qty > EPSILON and remainder_qty < MIN_PRACTICAL_SPLIT_QTY:
                continue

            # Ưu tiên giữ lại lượng lớn nhất có thể
            if possible_qty_to_place > best_split_option['qty_for_same_co']:
                rem_part, part_for_same_co = pallet.split(possible_qty_to_place)
                # Kiểm tra xem phần còn lại có vừa với cont khác công ty không
                if rem_part and part_for_same_co and target_container_other_co_full_fit.can_fit(rem_part):
                    best_split_option.update({
                        'part_for_same_co': part_for_same_co,
                        'rem_for_other_co': rem_part,
                        'same_co_container_target': s_cont,
                        'qty_for_same_co': possible_qty_to_place
                    })
        
        # Nếu tìm thấy một phương án chia tách tốt
        if best_split_option['part_for_same_co']:
            s_cont_target = best_split_option['same_co_container_target']
            s_cont_target.add_pallet(best_split_option['part_for_same_co'])
            target_container_other_co_full_fit.add_pallet(best_split_option['rem_for_other_co'])
            return None # Xếp xong, kết thúc

        # c. BIỆN PHÁP CUỐI: Nếu không tối ưu được, thực hiện vận chuyển chéo nguyên pallet
        target_container_other_co_full_fit.add_pallet(pallet)
        return None

    # --- ƯU TIÊN 2: CHIA (PHẦN NGUYÊN + PHẦN LẺ) VÀ XẾP VÀO CÙNG CÔNG TY ---
    is_float_pallet = abs(pallet.quantity - round(pallet.quantity)) > EPSILON
    if pallet.quantity >= 1.0 and is_float_pallet:
        original_int_q = math.floor(pallet.quantity)
        original_frac_q = pallet.quantity - original_int_q

        # Lặp ngược từ phần nguyên lớn nhất có thể tách ra
        for int_q_to_try in range(original_int_q, 0, -1):
            rem_after_int, p_int = pallet.split(int_q_to_try)
            if not p_int or not rem_after_int:
                continue

            p_leftover, p_frac = rem_after_int.split(original_frac_q)
            if not p_frac:
                continue

            int_cont = find_best_fit(p_int, same_co_containers)
            if not int_cont:
                continue

            # Tìm nơi cho phần lẻ, ưu tiên chính container chứa phần nguyên
            frac_cont = None
            if int_cont.can_fit(p_frac):
                 frac_cont = int_cont
            else:
                 # Nếu không, tìm ở các container cùng công ty còn lại
                 other_same_co_conts = [c for c in same_co_containers if c.id != int_cont.id]
                 frac_cont = find_best_fit(p_frac, other_same_co_conts)

            # Nếu tìm được nơi cho cả hai phần nguyên và lẻ
            if frac_cont:
                int_cont.add_pallet(p_int)
                frac_cont.add_pallet(p_frac)

                # --- BẮT ĐẦU LOGIC MỚI ĐỂ XỬ LÝ PHẦN THỪA (p_leftover) ---
                pallet_remains = p_leftover
                if pallet_remains and pallet_remains.quantity > EPSILON:
                    # BƯỚC 2.1 (Tương tự Ưu tiên 1): Cố gắng xếp nguyên vẹn phần thừa
                    all_available_containers_p2 = same_co_containers + other_co_containers
                    leftover_fit_container = find_best_fit(pallet_remains, all_available_containers_p2)
                    if leftover_fit_container:
                        leftover_fit_container.add_pallet(pallet_remains)
                        return None # Xếp xong toàn bộ, kết thúc

                    # BƯỚC 2.2: Ưu tiên tách phần NGUYÊN cho container CÙNG CÔNG TY
                    unplaced_part = pallet_remains
                    for container in same_co_containers:
                        if unplaced_part is None or unplaced_part.quantity < 1.0:
                            break

                        if container.remaining_quantity >= 1.0:
                            possible_int_qty = math.floor(min(unplaced_part.quantity, container.remaining_quantity))
                            weight_for_int_part = possible_int_qty * unplaced_part.weight_per_pallet

                            if container.remaining_weight >= weight_for_int_part and possible_int_qty > 0:
                                remaining_part, int_part = unplaced_part.split(float(possible_int_qty))
                                if int_part:
                                    container.add_pallet(int_part)
                                    unplaced_part = remaining_part

                    pallet_remains = unplaced_part

                # BƯỚC 2.3: Xử lý phần còn lại cuối cùng với container KHÁC CÔNG TY
                if pallet_remains and pallet_remains.quantity > EPSILON:
                    for container in other_co_containers:
                        if pallet_remains is None or pallet_remains.quantity < EPSILON:
                            break

                        # Logic "tách số thông minh": ưu tiên tách số nguyên
                        split_qty = 0
                        if pallet_remains.quantity >= 1.0 and container.remaining_quantity >= 1.0:
                            possible_int_qty = math.floor(min(pallet_remains.quantity, container.remaining_quantity))
                            weight_for_int_part = possible_int_qty * pallet_remains.weight_per_pallet
                            if container.remaining_weight >= weight_for_int_part and possible_int_qty > 0:
                                split_qty = float(possible_int_qty)

                        # Nếu không thể tách số nguyên, thì tách để lấp đầy
                        if split_qty == 0:
                            max_qty_by_weight = (container.remaining_weight / pallet_remains.weight_per_pallet) if pallet_remains.weight_per_pallet > EPSILON else float('inf')
                            possible_fill_qty = min(container.remaining_quantity, max_qty_by_weight)

                            if possible_fill_qty >= MIN_PRACTICAL_SPLIT_QTY:
                                if (pallet_remains.quantity - possible_fill_qty) < MIN_PRACTICAL_SPLIT_QTY and (pallet_remains.quantity - possible_fill_qty) > EPSILON:
                                    continue
                                else:
                                    split_qty = possible_fill_qty

                        if split_qty > EPSILON:
                            rem_part, new_part = pallet_remains.split(split_qty)
                            if new_part:
                                container.add_pallet(new_part)
                                pallet_remains = rem_part

                if pallet_remains and pallet_remains.quantity > EPSILON:
                     return pallet_remains
                else:
                     return None # Xếp thành công

    # --- ƯU TIÊN 4: CHIA NHỎ LẤP ĐẦY (BIỆN PHÁP CUỐI) ---
    # Logic này áp dụng cho các pallet không thể xử lý bằng các bước trên
    pallet_remains = pallet
    all_containers_sorted = same_co_containers + other_co_containers

    for container in all_containers_sorted:
        if not pallet_remains or pallet_remains.quantity < EPSILON:
            break

        if container.remaining_quantity < MIN_PRACTICAL_SPLIT_QTY:
            continue

        max_qty_by_weight = (container.remaining_weight / pallet_remains.weight_per_pallet) if pallet_remains.weight_per_pallet > EPSILON else float('inf')
        qty_to_fit = min(container.remaining_quantity, max_qty_by_weight)

        if qty_to_fit >= pallet_remains.quantity - EPSILON:
            container.add_pallet(pallet_remains)
            pallet_remains = None
            break

        if qty_to_fit >= MIN_PRACTICAL_SPLIT_QTY:
            if (pallet_remains.quantity - qty_to_fit) < MIN_PRACTICAL_SPLIT_QTY and (pallet_remains.quantity - qty_to_fit) > EPSILON:
                continue

            rem_part, new_part = pallet_remains.split(qty_to_fit)
            if rem_part and new_part:
                container.add_pallet(new_part)
                pallet_remains = rem_part

    if pallet_remains and pallet_remains.quantity > EPSILON:
        return pallet_remains
    return None

# --- HẰNG SỐ CẤU HÌNH CHO GIAI ĐOẠN 2 (CẬP NHẬT) ---
THRESHOLD_FILL_RATE = 0.25      # Tỷ lệ lấp đầy tối thiểu (ví dụ: 25%)
THRESHOLD_PALLET_COUNT = 2      # Số lượng pallet tối thiểu (ví dụ: 2)
# Ngưỡng tối thiểu cho một phần pallet được tách ra để được coi là hợp lý.
# Giá trị này ngăn việc tạo ra các mảnh pallet quá nhỏ (ví dụ: 0.01).
MIN_PRACTICAL_SPLIT_QTY = 0.25

def defragment_and_consolidate(initial_packed_containers):
    """
    Giai đoạn 2: Tối ưu hóa Container bằng cách Chống phân mảnh và Hợp nhất.
    Sử dụng logic phân bổ mới có thứ tự ưu tiên để giảm thiểu việc chia tách pallet không cần thiết.
    """
    # Bước 2.1: Xác định Container "Tốt" và "Lãng phí" (logic giữ nguyên)
    good_containers = []
    wasteful_containers = []

    if not initial_packed_containers:
        return [], []

    for container in initial_packed_containers:
        fill_rate = container.total_quantity / MAX_PALLETS
        pallet_count = len(container.pallets)
        if fill_rate >= THRESHOLD_FILL_RATE and pallet_count >= THRESHOLD_PALLET_COUNT:
            good_containers.append(container)
        else:
            wasteful_containers.append(container)

    if not wasteful_containers:
        return good_containers, []

    # Bước 2.2: Gom các pallet từ container lãng phí vào một danh sách để tái phân bổ
    pallets_for_redeployment = []
    for container in wasteful_containers:
        pallets_for_redeployment.extend(container.pallets)

    # Sắp xếp các pallet cần xếp lại từ lớn đến nhỏ để xử lý các pallet khó trước
    pallets_for_redeployment.sort(key=lambda p: p.quantity, reverse=True)


    # Bước 2.3: Tái phân bổ thông minh sử dụng logic ưu tiên mới
    pallets_still_unplaced = []
    for pallet in pallets_for_redeployment:
        # Gọi hàm phụ trợ để thực hiện việc xếp pallet
        unplaced_remainder = _place_pallet_with_priority(pallet, good_containers)
        
        # Nếu sau tất cả các bước vẫn còn phần dư -> đưa vào danh sách chờ cuối cùng
        if unplaced_remainder and unplaced_remainder.quantity > EPSILON:
            pallets_still_unplaced.append(unplaced_remainder)

    final_containers = good_containers
    pallets_for_cross_shipping = pallets_still_unplaced

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
    PHIÊN BẢN SỬA LỖI: Đảm bảo khi "mượn" số lượng từ pallet anh em, các pallet con
    (original_pallets) cũng được di chuyển và tách một cách chính xác để duy trì
    tính toàn vẹn dữ liệu.
    """
    # Chỉ làm tròn nếu pallet có phần thập phân đáng kể
    if pallet_to_round.quantity >= math.floor(pallet_to_round.quantity) + EPSILON:
        target_quantity = math.ceil(pallet_to_round.quantity)
        needed_quantity = target_quantity - pallet_to_round.quantity

        sibling_pallet, sibling_container = _find_pallet_sibling(pallet_to_round, all_containers)

        # Đảm bảo có pallet anh em, container chứa nó, và pallet anh em có đủ số lượng để cho đi
        if sibling_pallet and sibling_container and sibling_pallet.quantity > needed_quantity + EPSILON:

            # === BẮT ĐẦU PHẦN SỬA LỖI TRỌNG TÂM ===
            
            # Mục tiêu: Di chuyển `needed_quantity` từ `sibling_pallet` sang `pallet_to_round`
            # bằng cách di chuyển các pallet con (original_pallets).

            pallets_to_move = []
            quantity_left_to_take = needed_quantity
            
            # Sắp xếp các pallet con của sibling từ nhỏ đến lớn để ưu tiên di chuyển các pallet nhỏ trước
            # hoặc tách pallet lớn một cách hiệu quả hơn.
            sub_pallets_to_take_from = sorted(sibling_pallet.original_pallets, key=lambda p: p.quantity)
            
            # Danh sách mới sẽ chứa các pallet con còn lại của sibling sau khi đã "cho đi"
            new_sibling_originals = []

            while quantity_left_to_take > EPSILON and sub_pallets_to_take_from:
                # Lấy pallet con nhỏ nhất để xử lý
                sub_pallet = sub_pallets_to_take_from.pop(0)

                if sub_pallet.quantity <= quantity_left_to_take + EPSILON:
                    # Nếu pallet con này có thể được di chuyển toàn bộ
                    pallets_to_move.append(sub_pallet)
                    quantity_left_to_take -= sub_pallet.quantity
                else:
                    # Nếu pallet con này lớn hơn lượng cần lấy, chúng ta phải tách nó
                    # `split()` trả về (phần còn lại, phần bị tách ra)
                    # Chúng ta cần tách ra một lượng bằng `quantity_left_to_take`
                    remaining_sub_part, moved_sub_part = sub_pallet.split(quantity_left_to_take)
                    
                    if remaining_sub_part and moved_sub_part:
                        # Thêm phần đã tách vào danh sách di chuyển
                        pallets_to_move.append(moved_sub_part)
                        # Giữ lại phần còn lại cho sibling
                        new_sibling_originals.append(remaining_sub_part)
                        # Đã lấy đủ, dừng lại
                        quantity_left_to_take = 0
                    else:
                        # Nếu việc tách không thành công (trường hợp hiếm), giữ nguyên pallet
                        new_sibling_originals.append(sub_pallet)

            # Thêm các pallet con chưa được xử lý vào danh sách còn lại của sibling
            new_sibling_originals.extend(sub_pallets_to_take_from)

            # 1. CẬP NHẬT DANH SÁCH PALLET CON CỦA CẢ HAI BÊN
            sibling_pallet.original_pallets = new_sibling_originals
            pallet_to_round.original_pallets.extend(pallets_to_move)

            # 2. TÍNH TOÁN LẠI MỌI THỨ TỪ "SOURCE OF TRUTH" (original_pallets) ĐỂ ĐẢM BẢO NHẤT QUÁN
            # Cập nhật pallet anh em
            sibling_pallet.quantity = sum(p.quantity for p in sibling_pallet.original_pallets)
            sibling_pallet.total_weight = sum(p.total_weight for p in sibling_pallet.original_pallets)

            # Cập nhật pallet được làm tròn
            pallet_to_round.quantity = sum(p.quantity for p in pallet_to_round.original_pallets)
            pallet_to_round.total_weight = sum(p.total_weight for p in pallet_to_round.original_pallets)

            # 3. CẬP NHẬT CONTAINER CHỨA PALLET ANH EM DỰA TRÊN DỮ LIỆU MỚI
            # Cách cũ chỉ trừ đi một lượng ước tính, cách mới tính lại toàn bộ cho chính xác
            sibling_container.total_quantity = sum(p.quantity for p in sibling_container.pallets)
            sibling_container.total_weight = sum(p.total_weight for p in sibling_container.pallets)
            # === KẾT THÚC PHẦN SỬA LỖI ===

            print(f"INFO: Truy hồi thành công. Pallet {pallet_to_round.id} được làm tròn thành {pallet_to_round.quantity:.2f}. "
                  f"Pallet anh em {sibling_pallet.id} còn lại {sibling_pallet.quantity:.2f}.")
            return True # Làm tròn thành công

    return False # Không thể làm tròn
def consolidate_sub_pallets(sub_pallets_list):

    consolidated_map = {}

    # Bước 1: Nhóm các pallet theo key (product_code + product_name) và tính tổng
    for pallet in sub_pallets_list:
        key = f"{pallet.product_code}||{pallet.product_name}"
        if key not in consolidated_map:
            consolidated_map[key] = {
                'quantity': 0,
                'total_weight': 0,
                'base_pallet': pallet # Lưu lại pallet đầu tiên để lấy thông tin gốc
            }
        
        consolidated_map[key]['quantity'] += pallet.quantity
        consolidated_map[key]['total_weight'] += pallet.total_weight

    # Bước 2: Tạo danh sách kết quả đã được hợp nhất
    result_list = []
    for key, data in consolidated_map.items():
        base_pallet = data['base_pallet']
        
        # Sử dụng ID gốc của pallet (ví dụ: 'P39-rem' -> 'P39')
        clean_id = base_pallet.id.split('-')[0]
        
        # Lấy dữ liệu đã được hợp nhất
        total_quantity = data['quantity']
        total_weight = data['total_weight']
        
        # --- SỬA LỖI TRỌNG TÂM ---
        # Tính toán lại weight_per_pallet dựa trên tổng số liệu đã hợp nhất.
        # Việc này tránh sử dụng dữ liệu cũ từ một mảnh pallet đơn lẻ.
        new_weight_per_pallet = 0
        if total_quantity > 1e-6: # Sử dụng một ngưỡng nhỏ để so sánh số thực
            new_weight_per_pallet = total_weight / total_quantity
        # --- KẾT THÚC SỬA LỖI ---

        consolidated_pallet = Pallet(
            p_id=clean_id,
            product_code=base_pallet.product_code,
            product_name=base_pallet.product_name,
            company=base_pallet.company,
            quantity=total_quantity,
            weight_per_pallet=new_weight_per_pallet # Sử dụng giá trị mới, chính xác
        )
    
        consolidated_pallet.total_weight = total_weight
        
        result_list.append(consolidated_pallet)
        
    return result_list
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

