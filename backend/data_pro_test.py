import pandas as pd
import math
import warnings # Import the warnings library
import re
from collections import defaultdict
import copy

from collections import Counter

# --- HIDE HARMLESS WARNINGS FROM openpyxl ---
from openpyxl.utils.exceptions import InvalidFileException
warnings.filterwarnings("ignore", category=UserWarning, module='openpyxl')
# --- HẰNG SỐ CẤU HÌNH ---
MAX_WEIGHT = 24000.0
MAX_PALLETS = 20.0
EPSILON = 1e-6 # Ngưỡng để xử lý sai số dấu phẩy động
# --- CÁC LỚP ĐỐI TƯỢỢNG (Mô hình hóa dữ liệu) ---
# Giữ nguyên như file gốc
class Pallet:
    """Đại diện cho một pallet hoặc một phần của pallet."""
    def __init__(self, p_id, product_code, product_name, company, quantity, weight_per_pallet, box_per_pallet):
        self.id = p_id
        self.product_code = product_code
        self.product_name = product_name
        self.company = str(company)
        self.quantity = float(quantity)
        self.weight_per_pallet = float(weight_per_pallet)
        self.box_per_pallet = box_per_pallet
        self.total_weight = self.quantity * self.weight_per_pallet

        self.is_combined = False
        self.original_pallets = [self]
        self.is_split = False
        self.is_cross_ship = False
        self.split_from_id = None
        self.sibling_id = None

    @property
    def logical_pallet_count(self):
        """
        Tính toán số 'pallet logic' (số dòng) sẽ chiếm trong Packing List.
        Ví dụ: 4.9 qty -> 4 pallet nguyên + 1 pallet lẻ = 5 dòng.
              4.0 qty -> 4 pallet nguyên = 4 dòng.
              0.9 qty -> 1 pallet lẻ = 1 dòng.
        """
        if self.quantity < EPSILON:
            return 0

        integer_part = math.floor(self.quantity)
        fractional_part = self.quantity - integer_part

        count = integer_part
        if fractional_part > EPSILON:
            count += 1

        return int(count)

    def __repr__(self):
        type_info = ""
        if self.is_combined:
            # SỬA ĐỔI: Tạo chuỗi chi tiết cho từng pallet con để hiển thị rõ ràng
            sub_pallet_details = [
                f"SubPallet(id={p.id}, qty={p.quantity:.2f}, wgt={p.total_weight:.2f}, Cty={p.company})"
                for p in self.original_pallets
            ]
            # Thêm ký tự xuống dòng và thụt đầu dòng để dễ đọc
            details_str = ",\n                    ".join(sub_pallet_details)
            type_info = f" [Combined from:\n                    {details_str}\n                   ]"

        if self.is_split:
            type_info += f" [Split from {self.split_from_id}]"
        if self.is_cross_ship:
            type_info += " [Cross-Ship]"

        return (f"Pallet(id={self.id}, qty={self.quantity:.2f}, "
                f"wgt={self.total_weight:.2f}, Cty={self.company}, "
                f"logical_pallets={self.logical_pallet_count}){type_info}")

    def _recalculate_from_originals(self):
        """
        NEW METHOD: Recalculates the pallet's total quantity and weight based on its original_pallets list.
        This ensures the parent pallet's state is always synchronized with its components.
        """
        if not self.is_combined or not self.original_pallets:
            return

        self.quantity = sum(p.quantity for p in self.original_pallets)
        self.total_weight = sum(p.total_weight for p in self.original_pallets)
        if self.quantity > EPSILON:
            self.weight_per_pallet = self.total_weight / self.quantity
        else:
            self.weight_per_pallet = 0
        
        # Cập nhật lại các thông tin hiển thị nếu là pallet gộp đa công ty
        all_companies = set(str(p.company) for p in self.original_pallets)
        if len(all_companies) > 1:
            self.company = "+".join(sorted(list(all_companies)))
            self.product_name = f"COMBINED ({len(self.original_pallets)} items)"

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
            quantity=split_quantity, weight_per_pallet=self.weight_per_pallet,
            box_per_pallet=self.box_per_pallet
        )
        new_part.is_combined = self.is_combined
        new_part.is_split = True
        new_part.split_from_id = original_id

        rem_part = Pallet(
            p_id=f"{original_id}-rem", product_code=self.product_code,
            product_name=self.product_name, company=self.company,
            quantity=self.quantity - split_quantity, weight_per_pallet=self.weight_per_pallet,
            box_per_pallet=self.box_per_pallet
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
                        weight_per_pallet=boundary_pallet_to_split.weight_per_pallet,
                        box_per_pallet=boundary_pallet_to_split.box_per_pallet
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
                        weight_per_pallet=boundary_pallet_to_split.weight_per_pallet,
                        box_per_pallet=boundary_pallet_to_split.box_per_pallet
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
        # MỚI: Theo dõi tổng số pallet logic để không vượt quá 20 dòng trong PKL
        self.total_logical_pallets = 0

    def _recalculate_totals(self):
        """Tính toán lại tất cả các tổng số từ danh sách pallet hiện có."""
        self.total_quantity = sum(p.quantity for p in self.pallets)
        self.total_weight = sum(p.total_weight for p in self.pallets)
        self.total_logical_pallets = sum(p.logical_pallet_count for p in self.pallets)

    def can_fit(self, pallet):
        """
        Kiểm tra xem pallet có thể được thêm vào không, xét cả 3 yếu tố:
        1. Trọng lượng (weight)
        2. Số lượng (quantity/volume)
        3. Số pallet logic (để đảm bảo <= 20 dòng trong PKL)
        """
        # Điều kiện 1: Kiểm tra số pallet logic (số dòng trên Packing List)
        if self.total_logical_pallets + pallet.logical_pallet_count > MAX_PALLETS:
            return False

        # Điều kiện 2: Kiểm tra số lượng pallet vật lý (tương đương thể tích)
        if self.total_quantity + pallet.quantity > MAX_PALLETS + EPSILON:
            return False

        # Điều kiện 3: Kiểm tra trọng lượng
        if self.total_weight + pallet.total_weight > MAX_WEIGHT + EPSILON:
            return False

        # Nếu tất cả điều kiện đều thỏa mãn
        return True

    def add_pallet(self, pallet):
        """Thêm pallet vào container và cập nhật lại các tổng số."""
        if str(pallet.company) != self.main_company:
            pallet.is_cross_ship = True
        self.pallets.append(pallet)
        # Tính toán lại thay vì cộng dồn để đảm bảo chính xác sau các thao tác phức tạp
        self._recalculate_totals()

    def remove_pallet(self, pallet_to_remove):
        """Xóa một pallet khỏi container và cập nhật lại tổng số."""
        self.pallets = [p for p in self.pallets if p.id != pallet_to_remove.id]
        self._recalculate_totals()

    @property
    def remaining_logical_pallets(self):
        """
        TÍNH NĂNG MỚI: Cung cấp số "dòng" còn trống trong Packing List.
        Thuộc tính này rất hữu ích cho các thuật toán tối ưu hóa sau này.
        """
        return MAX_PALLETS - self.total_logical_pallets

    @property
    def remaining_quantity(self):
        return MAX_PALLETS - self.total_quantity

    @property
    def remaining_weight(self):
        # SỬA LỖI: Thay self.remaining_weight bằng self.total_weight để tránh đệ quy vô한
        return MAX_WEIGHT - self.total_weight

    @property
    def remaining_logical_pallets(self):
        # Số "dòng" còn trống trong Packing List
        return MAX_PALLETS - self.total_logical_pallets
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
    - Cột H (7): BoxPerPallet
    - Cột K (10): weight_per_pallet
    - Cột L (11): quantity
    """
    try:
        # SỬA ĐỔI: Thêm cột 7 (BoxPerPallet)
        column_indices = [1, 2, 3, 7, 10, 11]
        column_names = ['product_code', 'product_name', 'company', 'BoxPerPallet', 'weight_per_pallet', 'quantity']

        df = pd.read_excel(
            filepath,
            sheet_name=sheet_name,
            header=None,
            skiprows=5,
            usecols=column_indices,
            names=column_names
        )

        df.dropna(subset=['product_name', 'company', 'weight_per_pallet', 'quantity'], how='any', inplace=True)

        df['product_code'] = df['product_code'].fillna('Không có mã')
        df['product_name'] = df['product_name'].fillna('Không có tên')

        # Chuyển đổi các cột số, xử lý lỗi và lọc dữ liệu
        for col in ['BoxPerPallet', 'weight_per_pallet', 'quantity']:
            df[col] = pd.to_numeric(df[col], errors='coerce')

        # Đảm bảo BoxPerPallet có giá trị mặc định nếu bị thiếu
        df['BoxPerPallet'] = df['BoxPerPallet'].fillna(0)
        df.dropna(subset=['weight_per_pallet', 'quantity'], inplace=True)

        df = df[df['quantity'] > 0].copy()

        # Chuẩn hóa cột công ty
        df['company'] = pd.to_numeric(df['company'], errors='coerce').fillna(0).astype(int).astype(str)

        if df.empty:
            return None, "Không tìm thấy dữ liệu hợp lệ trong các cột đã chỉ định."

        # SỬA ĐỔI: Truyền r['BoxPerPallet'] khi tạo Pallet
        pallets = [
            Pallet(
                p_id=f"P{i}",
                product_code=r['product_code'],
                product_name=r['product_name'],
                company=r['company'],
                box_per_pallet=r['BoxPerPallet'],
                quantity=r['quantity'],
                weight_per_pallet=r['weight_per_pallet']
            )
            for i, r in df.iterrows()
        ]

        return pallets, None

    except FileNotFoundError:
        return None, f"Lỗi: Không tìm thấy file tại đường dẫn '{filepath}'."
    except Exception as e:
        # Kiểm tra xem có phải lỗi do sheet không tồn tại không
        if "No sheet named" in str(e):
             return None, f"Lỗi: Không tìm thấy sheet tên là '{sheet_name}' trong file Excel."
        return None, f"Lỗi không xác định khi xử lý file Excel: {e}"
### tách phần nguyên và lẻ
def split_integer_fractional_pallets(pallets_list):
    """
    Tách một danh sách pallet thành hai danh sách riêng biệt:
    1.  integer_pallets: Chứa các pallet mới đại diện cho phần nguyên.
    2.  fractional_pallets: Chứa các pallet mới đại diện cho phần lẻ.
    """
    integer_pallets = []
    fractional_pallets = []

    for p in pallets_list:
        integer_part = math.floor(p.quantity)
        fractional_part = p.quantity - integer_part

        # Nếu có phần nguyên, tạo pallet nguyên
        if integer_part > 0:
            int_pallet = Pallet(
                p_id=f"{p.id}-int",
                product_code=p.product_code,
                product_name=p.product_name,
                company=p.company,
                quantity=float(integer_part),
                weight_per_pallet=p.weight_per_pallet,
                box_per_pallet=p.box_per_pallet
            )
            int_pallet.split_from_id = p.id
            integer_pallets.append(int_pallet)

        # Nếu có phần lẻ, tạo pallet lẻ
        if fractional_part > EPSILON:
            frac_pallet = Pallet(
                p_id=f"{p.id}-frac",
                product_code=p.product_code,
                product_name=p.product_name,
                company=p.company,
                quantity=fractional_part,
                weight_per_pallet=p.weight_per_pallet,
                box_per_pallet=p.box_per_pallet
            )
            frac_pallet.split_from_id = p.id
            fractional_pallets.append(frac_pallet)

    return integer_pallets, fractional_pallets
## xử phí pallet quá khổ
def handle_oversized_pallet(pallet_to_split, main_company, start_container_id):
    """
    SỬA ĐỔI: Xử lý một pallet nguyên quá khổ bằng cách chia đều số lượng NGUYÊN
    vào nhiều container. Ví dụ: 21 pallet sẽ được chia thành 11 và 10.
    """
    # --- BƯỚC 1: Xác định số container cần thiết ---
    num_splits_by_qty = math.ceil(pallet_to_split.quantity / MAX_PALLETS)
    num_splits_by_wgt = math.ceil(pallet_to_split.total_weight / MAX_WEIGHT)
    num_containers_needed = int(max(num_splits_by_qty, num_splits_by_wgt))

    if num_containers_needed <= 1:
        return []

    print(f"\n--- XỬ LÝ PALLET NGUYÊN QUÁ KHỔ ---")
    print(f"Pallet {pallet_to_split.id} (qty={pallet_to_split.quantity:.0f}, wgt={pallet_to_split.total_weight:.2f}) quá lớn.")
    print(f"Sẽ được chia đều ra {num_containers_needed} containers.")

    # --- BƯỚC 2: Chia đều số lượng nguyên ---
    total_quantity_to_split = int(pallet_to_split.quantity)
    base_qty_per_container = total_quantity_to_split // num_containers_needed
    remainder = total_quantity_to_split % num_containers_needed

    quantities_for_containers = []
    for i in range(num_containers_needed):
        qty = base_qty_per_container + (1 if i < remainder else 0)
        if qty > 0:
            quantities_for_containers.append(qty)

    # --- BƯỚC 3: Tạo container và phân bổ các pallet con ---
    newly_created_containers = []
    for i, quantity_for_this_container in enumerate(quantities_for_containers):
        container_id = start_container_id + i
        new_container = Container(container_id=f"C{container_id}", main_company=main_company)

        piece_pallet = Pallet(
            p_id=f"{pallet_to_split.id}-part{i+1}",
            product_code=pallet_to_split.product_code,
            product_name=pallet_to_split.product_name,
            company=pallet_to_split.company,
            quantity=float(quantity_for_this_container),
            weight_per_pallet=pallet_to_split.weight_per_pallet,
            box_per_pallet=pallet_to_split.box_per_pallet
        )

        new_container.add_pallet(piece_pallet)
        newly_created_containers.append(new_container)
        print(f" - Tạo {new_container.id}: chứa mảnh {piece_pallet.id} (qty={piece_pallet.quantity:.0f})")

    print(f"Đã chia thành công pallet {pallet_to_split.id} thành {len(newly_created_containers)} phần nguyên.")
    print("----------------------------\n")
    return newly_created_containers

def handle_all_oversized_pallets(all_pallets, start_container_id):
    """
    Xử lý TẤT CẢ các pallet quá khổ từ một danh sách đầu vào.
    Hàm sẽ xác định, nhóm theo công ty, và chia nhỏ các pallet quá khổ,
    tạo ra các container cần thiết một cách đồng thời cho tất cả các công ty có liên quan.

    Args:
        all_pallets (list[Pallet]): Danh sách TOÀN BỘ pallet cần kiểm tra.
        start_container_id (int): ID bắt đầu để đánh số cho các container mới.

    Returns:
        tuple: (danh_sách_container_mới, danh_sách_pallet_không_quá_khổ, next_container_id)
    """
    print("\n--- BẮT ĐẦU XỬ LÝ TẤT CẢ PALLET QUÁ KHỔ ---")
    oversized_pallets = [
        p for p in all_pallets
        if p.quantity > MAX_PALLETS or p.total_weight > MAX_WEIGHT
    ]
    regular_pallets = [
        p for p in all_pallets
        if p.quantity <= MAX_PALLETS and p.total_weight <= MAX_WEIGHT
    ]

    if not oversized_pallets:
        print("Không tìm thấy pallet nào quá khổ.")
        return [], regular_pallets, start_container_id

    # Nhóm các pallet quá khổ theo công ty
    pallets_by_company = defaultdict(list)
    for p in oversized_pallets:
        pallets_by_company[p.company].append(p)

    newly_created_containers = []
    current_container_id = start_container_id

    # Xử lý đồng thời cho mỗi công ty
    for company, company_pallets in pallets_by_company.items():
        print(f"\n>>> Đang xử lý pallet quá khổ cho công ty: '{company}'")
        for pallet_to_split in company_pallets:
            # Tái sử dụng logic chia nhỏ từ hàm gốc handle_oversized_pallet
            # (Phần này giả định logic chia một pallet đã đúng, chỉ gọi nó trong ngữ cảnh mới)
            containers_for_this_pallet = handle_oversized_pallet( # Gọi lại hàm con
                pallet_to_split,
                company,
                current_container_id
            )
            if containers_for_this_pallet:
                newly_created_containers.extend(containers_for_this_pallet)
                current_container_id += len(containers_for_this_pallet)

    print(f"--- HOÀN THÀNH XỬ LÝ PALLET QUÁ KHỔ. Đã tạo {len(newly_created_containers)} container mới. ---")
    return newly_created_containers, regular_pallets, current_container_id

##### xếp pallet nguyên vào từ lớn đến bé
def pack_integer_pallets(integer_pallets, existing_containers, next_container_id):
    """
    Xếp các pallet phần nguyên vào container với logic 2 giai đoạn:
    1.  KHỞI TẠO & XẾP NỀN: Nếu chưa có container, tạo một container cho mỗi công ty
        và xếp pallet lớn nhất của công ty đó vào làm nền một cách cố định.
    2.  XẾP TỐI ƯU: Với các pallet còn lại, áp dụng logic "chi phí cơ hội" để ưu tiên
        sự đa dạng hàng hóa và giảm trọng lượng.
    3.  QUY TẮC: Không tạo thêm container mới trong giai đoạn xếp tối ưu. Pallet không
        xếp được sẽ bị đưa vào danh sách chờ.
    """
    print("\n--- BẮT ĐẦU XẾP PALLET PHẦN NGUYÊN (LOGIC 2 GIAI ĐOẠN) ---")

    # --- GIAI ĐOẠN 0: KHỞI TẠO ---
    containers = list(existing_containers)
    current_container_id = next_container_id
    unplaced_integer_pallets = []
    pallets_to_pack = sorted(integer_pallets, key=lambda p: p.quantity, reverse=True)

    # --- GIAI ĐOẠN 1A: TẠO CONTAINER BAN ĐẦU CHO CÁC CÔNG TY CÒN THIẾU ---
    # (ĐOẠN LOGIC ĐÃ ĐƯỢC THAY ĐỔI)
    print("  [*] Giai đoạn 1A: Kiểm tra và tạo container ban đầu cho các công ty còn thiếu...")
    companies_with_pallets = set(p.company for p in pallets_to_pack)
    companies_with_containers = set(c.main_company for c in containers)
    
    companies_needing_container = sorted(list(companies_with_pallets - companies_with_containers))

    if companies_needing_container:
        print(f"    -> Phát hiện {len(companies_needing_container)} công ty cần tạo container ban đầu.")
        for company in companies_needing_container:
            new_container = Container(container_id=f"C{current_container_id}", main_company=company)
            containers.append(new_container)
            print(f"    -> (KHỞI TẠO) Tạo container mới {new_container.id} cho công ty {company}")
            current_container_id += 1
    else:
        print("    -> Tất cả công ty có pallet cần xếp đều đã có container.")
    # --- GIAI ĐOẠN 1B: XẾP NỀN (PALLET LỚN NHẤT VÀO CONTAINER TRỐNG) ---
    empty_containers = [c for c in containers if len(c.pallets) == 0]
    for container in empty_containers:
        # Tìm pallet lớn nhất cùng công ty để làm nền
        base_pallet_found = None
        for i, p in enumerate(pallets_to_pack):
            if p.company == container.main_company:
                base_pallet_found = pallets_to_pack.pop(i)
                break # Tìm thấy pallet lớn nhất phù hợp

        if base_pallet_found:
            container.add_pallet(base_pallet_found)
            print(f"  [+] (XẾP NỀN) Cố định pallet lớn nhất {base_pallet_found.id} vào container trống {container.id}")
        else:
            # Trường hợp hiếm gặp: đã tạo container nhưng không còn pallet nào cho công ty đó
            print(f"  [!] Không tìm thấy pallet nào để làm nền cho container {container.id}")


    # --- GIAI ĐOẠN 2: XẾP TỐI ƯU VỚI LOGIC CHI PHÍ CƠ HỘI MỚI ---
    # Sắp xếp lại các pallet còn lại một lần nữa để đảm bảo xử lý từ lớn đến nhỏ
    pallets_to_pack.sort(key=lambda p: p.quantity, reverse=True)

    # Sử dụng vòng lặp while vì danh sách `pallets_to_pack` sẽ bị thay đổi liên tục
    while pallets_to_pack:
        # Lấy pallet lớn nhất còn lại để xét
        current_pallet = pallets_to_pack.pop(0)
        placed = False

        # Ưu tiên xếp vào container gần đầy nhất của cùng công ty (best-fit)
        sorted_containers = sorted(
            [c for c in containers if c.main_company == current_pallet.company],
            key=lambda c: c.remaining_quantity
        )

        for container in sorted_containers:
            # Bỏ qua ngay nếu container này không thể chứa pallet lớn đang xét
            if not container.can_fit(current_pallet):
                continue

            # --- LOGIC MỚI: TÌM NHÓM THAY THẾ TỐT NHẤT ---
            # 1. Tìm các pallet ứng viên: là tất cả các pallet còn lại
            candidate_pallets = [p for p in pallets_to_pack if p.company == current_pallet.company]

            # 2. Sắp xếp các ứng viên theo trọng lượng TĂNG DẦN
            #    để ưu tiên lấy các pallet nhẹ nhất trước, tối đa hóa số lượng pallet trong nhóm
            candidate_pallets.sort(key=lambda p: p.total_weight)

            # 3. Xây dựng nhóm thay thế
            small_pallet_group = []
            group_weight = 0.0
            for candidate in candidate_pallets:
                # Nếu thêm pallet này vào không vượt quá trọng lượng của pallet lớn
                if group_weight + candidate.total_weight <= current_pallet.total_weight + EPSILON:
                    # Và container vẫn còn đủ chỗ cho pallet nhỏ này
                    # (Mô phỏng bằng cách trừ đi không gian đã dùng bởi các pallet khác trong nhóm)
                    temp_container_qty = container.remaining_quantity - sum(p.quantity for p in small_pallet_group)
                    temp_container_wgt = container.remaining_weight - sum(p.total_weight for p in small_pallet_group)

                    if temp_container_qty >= candidate.quantity - EPSILON and temp_container_wgt >= candidate.total_weight - EPSILON:
                        small_pallet_group.append(candidate)
                        group_weight += candidate.total_weight

            # 4. ĐÁNH GIÁ VÀ QUYẾT ĐỊNH
            #    Nhóm được coi là tốt hơn nếu có nhiều hơn 1 pallet
            group_is_better = len(small_pallet_group) > 1

            if group_is_better:
                # QUYẾT ĐỊNH: Xếp nhóm nhỏ, hoãn pallet lớn
                print(f"  [OPP. COST] Ưu tiên nhóm {len(small_pallet_group)} pallet nhỏ cho Cont {container.id} (Tổng wgt: {group_weight:.2f}).")
                print(f"    - Hoãn pallet {current_pallet.id} (wgt: {current_pallet.total_weight:.2f}) -> đưa vào danh sách chờ.")
                unplaced_integer_pallets.append(current_pallet)

                # Xếp các pallet trong nhóm đã chọn vào container
                for p_small in small_pallet_group:
                    print(f"    - Xếp pallet nhỏ: {p_small.id}")
                    container.add_pallet(p_small)
                    # Xóa khỏi danh sách nguồn để không xét lại
                    pallets_to_pack.remove(p_small)

                placed = True
                break # Đã xử lý xong cho container này, chuyển sang pallet lớn tiếp theo
            else:
                # QUYẾT ĐỊNH: Xếp pallet lớn như bình thường vì không có nhóm nào tốt hơn
                container.add_pallet(current_pallet)
                print(f"  [+] (Xếp thường) Xếp pallet nguyên {current_pallet.id} vào container: {container.id}")
                placed = True
                break # Đã xếp xong, chuyển sang pallet lớn tiếp theo

        # Nếu duyệt hết các container mà không xếp được pallet lớn (hoặc nhóm thay thế)
        if not placed:
            # Pallet này sẽ được đưa vào danh sách chờ
            unplaced_integer_pallets.append(current_pallet)
            print(f"  [-] (Không vừa) Pallet nguyên {current_pallet.id} không tìm được container nào phù hợp -> đưa vào danh sách chờ.")


    # Những pallet còn lại trong `pallets_to_pack` chính là những pallet không vừa
    # và những pallet bị bỏ qua trong vòng lặp `for current_pallet in pallets_for_opp_cost`
    # cần được thêm vào danh sách chờ
    remaining_unplaced = [p for p in pallets_to_pack if p not in unplaced_integer_pallets]
    if remaining_unplaced:
        for p in remaining_unplaced:
            print(f"  [-] (Không vừa) Pallet nguyên {p.id} không tìm được container nào phù hợp -> đưa vào danh sách chờ.")
        unplaced_integer_pallets.extend(remaining_unplaced)


    print("--- HOÀN THÀNH XẾP PALLET PHẦN NGUYÊN ---")
    if unplaced_integer_pallets:
        # Sắp xếp lại danh sách chờ để dễ theo dõi
        unplaced_integer_pallets.sort(key=lambda p: p.quantity, reverse=True)
        print(f"Lưu ý: Có {len(unplaced_integer_pallets)} pallet nguyên không xếp được và đã được đưa vào danh sách chờ.")

    return containers, unplaced_integer_pallets, current_container_id

def combine_fractional_pallets(fractional_pallets):
    """
    Ghép các pallet lẻ với nhau theo từng công ty, với mục tiêu TỐI ƯU HÓA
    để tạo ra các pallet ghép có tổng số lượng (qty) gần bằng 0.9 nhất có thể.

    Chiến lược tối ưu (Best Fit Decreasing):
    - Lấy pallet lẻ lớn nhất làm "nền".
    - Ưu tiên ghép thêm các pallet lẻ lớn nhất còn lại trước.
      Cách này giúp nhanh chóng đạt đến ngưỡng 0.9.

    Quy tắc ghép:
    1.  Tổng số lượng (qty) của một pallet gộp không được vượt quá 0.9.
    2.  Trong một pallet gộp, cho phép TỐI ĐA MỘT pallet thành phần có số lượng (qty) >= 0.5.
    3.  Chỉ ghép các pallet từ cùng một công ty.

    Args:
        fractional_pallets (list[Pallet]): Danh sách các pallet phần lẻ cần xử lý.

    Returns:
        tuple[list[Pallet], list[Pallet]]: Một tuple chứa hai danh sách:
                                           (danh_sách_pallet_đã_gộp, danh_sách_pallet_lẻ_còn_lại).
    """
    print("\n--- BẮT ĐẦU GHÉP CÁC PALLET LẺ (LOGIC TỐI ƯU HÓA NGƯỠNG 0.9) ---")

    final_combined_pallets = []
    final_uncombined_pallets = []
    next_combined_id = 1
    
    # Bước 1: Nhóm các pallet theo công ty
    pallets_by_company = defaultdict(list)
    for p in fractional_pallets:
        pallets_by_company[p.company].append(p)

    # Bước 2: Áp dụng logic ghép nối cho từng công ty
    for company, company_pallets in pallets_by_company.items():
        print(f"\n>>> Đang xử lý cho công ty: '{company}' ({len(company_pallets)} pallet lẻ)")

        # Sắp xếp tất cả pallet của công ty từ lớn đến nhỏ
        available_pallets = sorted(company_pallets, key=lambda p: p.quantity, reverse=True)

        while available_pallets:
            # Lấy pallet lớn nhất làm nền cho tổ hợp mới
            base_pallet = available_pallets.pop(0)
            current_combination = [base_pallet]
            
            # --- ĐIỂM CỐT LÕI CỦA THUẬT TOÁN ---
            # Luôn sắp xếp các pallet ứng viên còn lại từ LỚN NHẤT đến nhỏ nhất.
            # Điều này đảm bảo chúng ta luôn thử ghép mảnh lớn nhất có thể ("Best Fit").
            candidates = sorted(available_pallets, key=lambda p: p.quantity, reverse=True)
            
            # Duyệt qua danh sách ứng viên để tìm các mảnh ghép phù hợp
            for candidate in list(candidates): 
                # Bỏ qua nếu ứng viên đã được ghép vào một tổ hợp khác
                if candidate not in available_pallets:
                    continue

                potential_combination = current_combination + [candidate]
                
                # Điều kiện 1: Tổng số lượng phải <= 0.9
                potential_quantity = sum(p.quantity for p in potential_combination)
                if potential_quantity > 0.9 + EPSILON:
                    continue # Bỏ qua nếu vượt ngưỡng

                # Điều kiện 2: Tối đa một pallet có qty >= 0.5
                num_large_pallets = sum(1 for p in potential_combination if p.quantity >= 0.5)
                if num_large_pallets > 1:
                    continue # Bỏ qua nếu vi phạm quy tắc
                    
                # NẾU ĐẠT YÊU CẦU: Thêm ứng viên vào tổ hợp hiện tại
                # và xóa nó khỏi danh sách chờ để không xét lại.
                current_combination.append(candidate)
                available_pallets.remove(candidate)

            # --- TỔNG KẾT TỔ HỢP ---
            if len(current_combination) > 1:
                # Nếu có từ 2 pallet trở lên, tạo một pallet gộp mới
                total_qty = sum(p.quantity for p in current_combination)
                total_wgt = sum(p.total_weight for p in current_combination)
                
                # Pallet chính (để lấy thông tin) là pallet lớn nhất trong nhóm
                main_pallet = max(current_combination, key=lambda p: p.quantity)
                
                combined_pallet = Pallet(
                    p_id=f"COMBINED-{next_combined_id}",
                    product_code=main_pallet.product_code,
                    product_name=f"COMBINED ({len(current_combination)} items)",
                    company=main_pallet.company,
                    quantity=total_qty,
                    weight_per_pallet=total_wgt / total_qty if total_qty > 0 else 0,
                    box_per_pallet=sum(p.box_per_pallet for p in current_combination if p.box_per_pallet is not None)
                )
                combined_pallet.is_combined = True
                combined_pallet.original_pallets = current_combination
                final_combined_pallets.append(combined_pallet)
                next_combined_id += 1
                print(f"  [+] Đã tạo pallet gộp: {combined_pallet}")
            else:
                # Nếu không thể ghép thêm gì, pallet nền sẽ được giữ lại làm pallet lẻ
                final_uncombined_pallets.append(base_pallet)
                print(f"  [-] Pallet {base_pallet.id} không thể ghép, giữ lại.")

    print(f"\n--- HOÀN THÀNH GHÉP PALLET LẺ ---")
    print(f"Tổng kết: {len(final_combined_pallets)} pallet đã được gộp, {len(final_uncombined_pallets)} pallet lẻ còn lại.")
    
    return final_combined_pallets, final_uncombined_pallets

## xếp pallet lẻ được xử lí vào
def pack_fractional_pallets(fractional_pallets, containers):
    """
    SỬA ĐỔI: Chỉ xếp các pallet lẻ vào các container CÙNG CÔNG TY hiện có.
    Không tạo container mới, không cross-ship ở giai đoạn này.
    Trả về danh sách các pallet không xếp được.
    """
    print("\n--- BẮT ĐẦU XẾP PALLET LẺ VÀO CONTAINER CÙNG CÔNG TY ---")
    pallets_to_pack = sorted(fractional_pallets, key=lambda p: p.quantity, reverse=True)
    unplaced_pallets = []

    for pallet in pallets_to_pack:
        was_placed = False
        # Tìm container phù hợp: cùng công ty và còn chỗ trống.
        # Sắp xếp để ưu tiên container còn ít chỗ nhất (best-fit).
        available_containers = sorted(
            [c for c in containers if c.main_company == pallet.company],
            key=lambda c: c.remaining_quantity
        )

        for container in available_containers:
            if container.can_fit(pallet):
                container.add_pallet(pallet)
                print(f"  [+] (Cùng Cty) Xếp pallet lẻ {pallet.id} vào Container {container.id}.")
                was_placed = True
                break  # Đã xếp xong, chuyển sang pallet tiếp theo.

        if not was_placed:
            unplaced_pallets.append(pallet)
            print(f"  [-] (Không vừa) Pallet lẻ {pallet.id} không tìm được chỗ, đưa vào danh sách chờ.")
            
    print("--- HOÀN THÀNH XẾP PALLET LẺ ---\n")
    return unplaced_pallets

# xử lí pallet trong danh sách chờ cho pallet nguyên
def try_pack_pallets_into_same_company_containers(unplaced_pallets, containers):
    """
    Thử xếp các pallet trong danh sách chờ vào các container có sẵn CÙNG CÔNG TY.

    Hàm này hoạt động theo chiến lược "Best-Fit":
    1. Sắp xếp các pallet cần xếp từ lớn nhất đến nhỏ nhất về số lượng.
    2. Với mỗi pallet, tìm các container cùng công ty và sắp xếp chúng
       theo không gian còn lại ít nhất (ưu tiên lấp đầy những cont gần đầy trước).
    3. Nếu pallet vừa, nó sẽ được xếp vào container phù hợp đầu tiên tìm thấy.
    4. Pallet nào không xếp được sẽ được trả về trong một danh sách mới.

    Args:
        unplaced_pallets (list[Pallet]): Danh sách các pallet đang trong danh sách chờ.
        containers (list[Container]): Danh sách các container hiện có để xếp vào.

    Returns:
        list[Pallet]: Một danh sách mới chỉ chứa các pallet không thể xếp được.
                       Lưu ý: Danh sách `containers` đầu vào sẽ bị thay đổi (được thêm pallet vào).
    """
    print("\n--- BƯỚC: THỬ XẾP PALLET CHỜ VÀO CONTAINER CÙNG CÔNG TY ---")
    
    # Danh sách để lưu những pallet thực sự không thể xếp được trong bước này
    pallets_still_unplaced = []
    
    # Sắp xếp các pallet cần xử lý từ lớn đến nhỏ để ưu tiên các pallet khó xếp nhất trước
    sorted_pallets_to_check = sorted(unplaced_pallets, key=lambda p: p.quantity, reverse=True)

    for pallet in sorted_pallets_to_check:
        was_placed = False
        
        # 1. Lọc ra những container tương thích (phải cùng công ty với pallet)
        compatible_containers = [c for c in containers if c.main_company == pallet.company]
        
        # 2. Sắp xếp các container tương thích để ưu tiên container gần đầy nhất (Best-Fit).
        #    Mục đích là để "hoàn thiện" các container đang xếp dở trước khi dùng đến các container còn trống nhiều.
        sorted_compatible_containers = sorted(compatible_containers, key=lambda c: c.remaining_quantity)
        
        # 3. Duyệt qua các container đã lọc và sắp xếp để tìm "nhà" cho pallet
        for container in sorted_compatible_containers:
            if container.can_fit(pallet):
                # Nếu tìm thấy chỗ, thêm pallet vào container, đánh dấu là đã xếp và thoát khỏi vòng lặp tìm kiếm
                container.add_pallet(pallet)
                print(f"  [+] (Xếp đơn giản) Đã xếp pallet '{pallet.id}' (qty: {pallet.quantity}) vào container có sẵn {container.id}.")
                was_placed = True
                break # Đã xếp xong pallet này, chuyển sang pallet tiếp theo
        
        # 4. Nếu sau khi duyệt hết các container phù hợp mà pallet vẫn chưa được xếp
        if not was_placed:
            # Ghi nhận pallet này không tìm được nhà và thêm vào danh sách trả về
            print(f"  [-] (Không vừa) Pallet '{pallet.id}' (qty: {pallet.quantity}) không tìm được container cùng công ty nào còn đủ chỗ.")
            pallets_still_unplaced.append(pallet)

    print(f"--- KẾT THÚC: Còn lại {len(pallets_still_unplaced)} pallet trong danh sách chờ sau khi thử xếp đơn giản. ---")
    return pallets_still_unplaced
def handle_unplaced_pallets_with_smart_splitting(pallets_still_unplaced, containers, unplaced_fractionals):
    """
    Xử lý các pallet còn lại bằng một chiến lược hai bước đã được sửa đổi:
    1.  Kiểm tra xem có thể cross-ship toàn bộ danh sách pallet chờ không.
        - NẾU CÓ THỂ: Thực hiện chiến lược "Tối ưu hóa chi phí cơ hội". Với mỗi pallet,
          hàm sẽ tìm kế hoạch chia thành các phần NGUYÊN tốt nhất (ưu tiên giữ lại nhiều nhất)
          và xếp các phần đó vào các container tương ứng.
    2.  NẾU KHÔNG THỂ: Tìm và thực thi kế hoạch chia tách TỐT NHẤT duy nhất cho một
        pallet, ưu tiên giữ lại nhiều nhất và chọn pallet nhỏ hơn nếu hòa. Pallet
        đã chia sẽ được xóa khỏi danh sách chờ, các pallet còn lại sẽ được trả về
        để xử lý trong các bước tiếp theo.

    Returns:
        list[Pallet]: Danh sách các pallet vẫn chưa được xếp sau khi thực hiện
                      thao tác tối ưu nhất.
    """
    print("\n--- BƯỚC: XỬ LÝ PALLET CHỜ BẰNG LOGIC CHIA TÁCH THÔNG MINH (v2) ---")
    if not pallets_still_unplaced:
        print("   Không có pallet nào trong danh sách chờ. Bỏ qua.")
        return []

    # SỬA ĐỔI: Thêm tham số is_integer_logic để điều khiển cách tách pallet
    def _place_pallet_iteratively(pallet_to_place, target_containers, placement_type="", is_integer_logic=False):
        if not pallet_to_place or pallet_to_place.quantity < EPSILON:
            return True # Không có gì để xếp

        remaining_part = pallet_to_place
        # Sắp xếp container theo không gian còn lại ít nhất để lấp đầy trước (best-fit)
        sorted_containers = sorted(target_containers, key=lambda c: c.remaining_quantity)

        for container in sorted_containers:
            if remaining_part is None or remaining_part.quantity < EPSILON:
                break # Đã xếp hết

            # Tính toán số lượng có thể vừa vặn dựa trên thể tích và trọng lượng
            qty_by_vol = container.remaining_quantity
            qty_by_wgt = container.remaining_weight / remaining_part.weight_per_pallet if remaining_part.weight_per_pallet > 0 else float('inf')
            
            # Tính toán lượng thực tế có thể xếp
            max_fit_quantity = min(remaining_part.quantity, qty_by_vol, qty_by_wgt)

            # --- SỬA ĐỔI TRỌNG TÂM ---
            # Nếu đang xử lý pallet nguyên, chỉ lấy phần nguyên của lượng có thể xếp
            if is_integer_logic:
                fit_quantity = math.floor(max_fit_quantity)
            else:
                fit_quantity = max_fit_quantity
            # --- KẾT THÚC SỬA ĐỔI ---

            if fit_quantity < 1.0 - EPSILON and is_integer_logic:
                continue # Bỏ qua nếu không thể xếp được ít nhất 1 pallet nguyên

            if fit_quantity < EPSILON:
                continue

            # Nếu toàn bộ phần còn lại vừa vặn
            if abs(remaining_part.quantity - fit_quantity) < EPSILON:
                if container.can_fit(remaining_part):
                    container.add_pallet(remaining_part)
                    print(f"       -> ({placement_type}) Đã xếp (toàn bộ) {remaining_part.id} vào container {container.id}")
                    remaining_part = None
                continue

            # Nếu chỉ một phần vừa, cần tách ra
            else:
                # Chỉ tách khi lượng tách ra có ý nghĩa
                if fit_quantity > EPSILON:
                    rest, piece_to_add = remaining_part.split(fit_quantity)
                    if piece_to_add and container.can_fit(piece_to_add):
                        container.add_pallet(piece_to_add)
                        print(f"       -> ({placement_type}) Đã xếp (một phần) {piece_to_add.id} (qty: {piece_to_add.quantity:.2f}) vào cont {container.id}")
                        remaining_part = rest
                    # Nếu không tách được thì bỏ qua, giữ nguyên `remaining_part` để thử với cont khác

        # Trả về True nếu không còn gì để xếp
        return remaining_part is None or remaining_part.quantity < EPSILON


    can_cross_ship_all = check_cross_ship_capacity_for_list(pallets_still_unplaced, containers, unplaced_fractionals)

    if can_cross_ship_all:
        print("   [INFO] Có khả năng cross-ship toàn bộ. Áp dụng tối ưu hóa chi phí cơ hội.")
        
        # ### SỬA LỖI LOGIC TẠI ĐÂY ###
        def _can_be_placed_iteratively(qty_to_check, wpp, target_containers, is_integer_logic):
            """
            Hàm mô phỏng việc xếp hàng, đảm bảo logic mô phỏng (planning)
            giống hệt logic thực thi (execution).
            """
            if qty_to_check < EPSILON:
                return True
            
            temp_qty_to_place = qty_to_check
            # Mô phỏng trên một bản sao sâu để không làm thay đổi trạng thái container thật
            sim_containers = copy.deepcopy(target_containers)
            sorted_containers = sorted(sim_containers, key=lambda c: c.remaining_quantity)

            for c in sorted_containers:
                if temp_qty_to_place < EPSILON:
                    break

                # Tính toán các giới hạn y như hàm thực thi
                qty_by_vol = c.remaining_quantity
                qty_by_wgt = c.remaining_weight / wpp if wpp > 0 else float('inf')
                # Với pallet nguyên, số lượng logic còn trống cũng là giới hạn cho số lượng
                qty_by_lp = float(c.remaining_logical_pallets)
                max_fit_in_this_cont = min(qty_by_vol, qty_by_wgt, qty_by_lp)

                amount_to_place_here = min(temp_qty_to_place, max_fit_in_this_cont)

                # >>> ĐIỂM SỬA LỖI QUAN TRỌNG NHẤT <<<
                # Áp dụng logic LÀM TRÒN XUỐNG (floor) ngay trong mô phỏng
                if is_integer_logic:
                    amount_to_place_here = math.floor(amount_to_place_here)

                if amount_to_place_here < EPSILON:
                    continue

                # Cập nhật trạng thái của container mô phỏng để các lần lặp sau tính toán chính xác
                # (Mô phỏng việc thêm pallet vào)
                c.total_quantity += amount_to_place_here
                c.total_weight += amount_to_place_here * wpp
                # Đối với pallet nguyên, số lượng pallet logic tăng tương ứng số lượng
                if is_integer_logic:
                     c.total_logical_pallets += amount_to_place_here
                elif amount_to_place_here > 0:
                     c.total_logical_pallets +=1

                temp_qty_to_place -= amount_to_place_here
            
            # Trả về True nếu đã mô phỏng xếp hết
            return temp_qty_to_place < EPSILON
        # ### KẾT THÚC SỬA LỖI LOGIC ###

        pallets_to_process = list(pallets_still_unplaced)
        final_unplaced_list = []

        for pallet in pallets_to_process:
            best_plan = {"keep_qty": -1}
            own_company_containers = [c for c in containers if c.main_company == pallet.company]
            other_company_containers = [c for c in containers if c.main_company != pallet.company]
            
            # Xác định xem pallet gốc có phải là pallet nguyên không
            is_integer_pallet = abs(pallet.quantity - round(pallet.quantity)) < EPSILON

            for num_to_keep_int in range(math.floor(pallet.quantity), -1, -1):
                num_to_keep = float(num_to_keep_int)
                num_to_cross = pallet.quantity - num_to_keep
                
                # Sửa đổi: Truyền cờ `is_integer_pallet` vào hàm mô phỏng
                can_keep = _can_be_placed_iteratively(num_to_keep, pallet.weight_per_pallet, own_company_containers, is_integer_pallet)
                can_cross = _can_be_placed_iteratively(num_to_cross, pallet.weight_per_pallet, other_company_containers, is_integer_pallet)
                
                if can_keep and can_cross:
                    best_plan = {"keep_qty": num_to_keep, "cross_qty": num_to_cross}
                    break
            
            if best_plan["keep_qty"] == -1:
                print(f"   [WARN] Không tìm thấy kế hoạch chia tách khả thi cho pallet {pallet.id}. Pallet được giữ lại.")
                final_unplaced_list.append(pallet)
                continue

            keep_qty = best_plan['keep_qty']
            cross_qty = best_plan['cross_qty']
            print(f"   [*] Tối ưu hóa cho pallet {pallet.id} (qty: {pallet.quantity}):")
            print(f"       - Kế hoạch TỐT NHẤT: Giữ lại: {keep_qty:.2f} | Chuyển đi: {cross_qty:.2f}")

            part_to_keep, part_to_cross = None, None
            if cross_qty < EPSILON:
                part_to_keep = pallet
            elif keep_qty < EPSILON:
                part_to_cross = pallet
            else:
                # Hàm split trả về (phần còn lại, phần bị tách ra).
                # Để `part_to_cross` có số lượng là `cross_qty`, ta phải split(cross_qty)
                part_to_keep, part_to_cross = pallet.split(cross_qty)
                if not part_to_keep or not part_to_cross:
                    print(f"   [ERROR] Lỗi khi chia pallet {pallet.id}. Pallet được giữ lại.")
                    final_unplaced_list.append(pallet)
                    continue
            
            # Truyền cờ is_integer_pallet vào hàm thực thi
            was_kept_placed = _place_pallet_iteratively(part_to_keep, own_company_containers, "Giữ lại", is_integer_logic=is_integer_pallet)
            was_cross_placed = _place_pallet_iteratively(part_to_cross, other_company_containers, "Chuyển đi", is_integer_logic=is_integer_pallet)

            if not (was_kept_placed and was_cross_placed):
                # Khôi phục lại trạng thái container nếu việc thực thi thất bại (an toàn hơn)
                # (Phần này có thể được thêm vào nếu cần sự chặt chẽ tuyệt đối)
                print(f"   [ERROR] Không thể xếp toàn bộ các mảnh của pallet {pallet.id} theo kế hoạch. Pallet GỐC được giữ lại.")
                final_unplaced_list.append(pallet) # Thêm pallet gốc vào danh sách chưa xếp được
        
        if not final_unplaced_list:
            print("   [SUCCESS] Hoàn tất tối ưu hóa. Tất cả pallet đã được xử lý.")
        return final_unplaced_list # Trả về danh sách pallet thực sự còn lại

    # --- BƯỚC 2: Nếu không, tìm và thực thi kế hoạch chia tách đơn lẻ TỐT NHẤT (giữ nguyên logic cũ) ---
    else:
        # Giữ nguyên logic cũ cho trường hợp này
        print("   [INFO] Không thể cross-ship toàn bộ. Chuyển sang logic tìm kiếm chia tách đơn lẻ tốt nhất.")
        all_possible_plans = []
        
        def can_fit_in_any_container(quantity, weight, target_containers):
            if quantity < EPSILON: return True
            for c in target_containers:
                if c.remaining_quantity >= quantity - EPSILON and (MAX_WEIGHT - c.total_weight) >= weight - EPSILON:
                    return True
            return False

        for pallet in pallets_still_unplaced:
            own_company_containers = [c for c in containers if c.main_company == pallet.company]
            other_company_containers = [c for c in containers if c.main_company != pallet.company]
            
            best_plan_for_this_pallet = None
            is_integer_pallet = abs(pallet.quantity - round(pallet.quantity)) < EPSILON

            for num_to_keep_int in range(math.floor(pallet.quantity), -1, -1):
                num_to_keep = float(num_to_keep_int)
                num_to_cross_ship = pallet.quantity - num_to_keep

                weight_to_keep = num_to_keep * pallet.weight_per_pallet
                weight_to_cross_ship = num_to_cross_ship * pallet.weight_per_pallet

                can_keep = can_fit_in_any_container(num_to_keep, weight_to_keep, own_company_containers)
                can_cross_ship = can_fit_in_any_container(num_to_cross_ship, weight_to_cross_ship, other_company_containers)

                if can_keep and can_cross_ship:
                    best_plan_for_this_pallet = { "pallet": pallet, "keep_qty": num_to_keep, "cross_qty": num_to_cross_ship, "is_integer": is_integer_pallet }
                    break

            if best_plan_for_this_pallet:
                all_possible_plans.append(best_plan_for_this_pallet)

        if not all_possible_plans:
            print("   [INFO] Không tìm thấy bất kỳ kế hoạch chia tách khả thi nào.")
            return pallets_still_unplaced

        all_possible_plans.sort(key=lambda p: (-p['keep_qty'], p['pallet'].quantity))
        best_overall_plan = all_possible_plans[0]
        
        pallet_to_split = best_overall_plan['pallet']
        keep_qty = best_overall_plan['keep_qty']
        cross_qty = best_overall_plan['cross_qty']
        is_integer_logic = best_overall_plan['is_integer']


        print(f"   [*] (LỰA CHỌN TỐI ƯU) Sẽ thực thi kế hoạch cho pallet {pallet_to_split.id}:")
        print(f"       - Giữ lại: {keep_qty:.2f} | Chuyển đi: {cross_qty:.2f}")
        
        own_company_containers = [c for c in containers if c.main_company == pallet_to_split.company]
        other_company_containers = [c for c in containers if c.main_company != pallet_to_split.company]


        if keep_qty < EPSILON or cross_qty < EPSILON:
            target_containers_list = other_company_containers if keep_qty < EPSILON else own_company_containers
            for container in sorted(target_containers_list, key=lambda c:c.remaining_quantity):
                if container.can_fit(pallet_to_split):
                    container.add_pallet(pallet_to_split)
                    print(f"       -> Đã xếp (toàn bộ) {pallet_to_split.id} vào container {container.id}")
                    return [p for p in pallets_still_unplaced if p.id != pallet_to_split.id]
        
        part_to_keep, part_to_cross = pallet_to_split.split(cross_qty)
        
        was_kept_placed = _place_pallet_iteratively(part_to_keep, own_company_containers, "Giữ lại", is_integer_logic)
        was_cross_placed = _place_pallet_iteratively(part_to_cross, other_company_containers, "Chuyển đi", is_integer_logic)

        if not (was_kept_placed and was_cross_placed):
            print(f"   [LỖI NGHIÊM TRỌNG] Mặc dù đã lên kế hoạch nhưng không thể xếp các mảnh của {pallet_to_split.id}.")
            return pallets_still_unplaced

        final_unplaced_list = [p for p in pallets_still_unplaced if p.id != pallet_to_split.id]
        print(f"--- KẾT THÚC: Còn lại {len(final_unplaced_list)} pallet trong danh sách chờ. ---")
        return final_unplaced_list

def handle_remaining_integers_iteratively(final_unplaced_list, containers, next_container_id):
    """
    Xử lý danh sách cuối cùng gồm các pallet nguyên chưa được xếp bằng cách tạo các container mới
    và sau đó áp dụng lặp lại toàn bộ bộ logic xếp hàng cho đến khi tất cả pallet được xếp xong.

    Hàm này điều phối một vòng lặp mô phỏng lại quy trình xếp hàng chính nhưng nhắm mục tiêu
    cụ thể vào các pallet còn sót lại:
    1.  **Tạo Container Mới & Xếp hàng**: Đối với các pallet chưa được xếp, các container mới
        sẽ được tạo ra, và logic xếp hàng theo chi phí cơ hội (từ `pack_integer_pallets`)
        được sử dụng để lấp đầy chúng.
    2.  **Thử Xếp hàng Đơn giản**: Các pallet còn lại sau đó được kiểm tra với tất cả
        các container có sẵn của cùng công ty.
    3.  **Áp dụng Logic Chia tách Thông minh**: Cuối cùng, logic phức tạp nhất được sử dụng để
        chia tách và xếp chéo (cross-ship) bất kỳ pallet nào vẫn còn lại.
    4.  **Lặp lại**: Quy trình này lặp lại cho đến khi danh sách pallet chưa được xếp trống.

    Args:
        final_unplaced_list (list[Pallet]): Danh sách các pallet nguyên không thể xếp được.
        containers (list[Container]): Danh sách hiện tại của tất cả các container.
        next_container_id (int): ID có sẵn tiếp theo để tạo container mới.

    Returns:
        tuple[list[Container], int]: Một tuple chứa danh sách container đã được cập nhật
                                     và next_container_id mới.
    """
    print("\n--- BẮT ĐẦU QUY TRÌNH XỬ LÝ LẶP LẠI CUỐI CÙNG CHO CÁC PALLET NGUYÊN ---")
    if not final_unplaced_list:
        print("Không có pallet nào trong danh sách cuối cùng. Bỏ qua.")
        return containers, next_container_id

    # Danh sách pallet chúng ta sẽ xử lý, danh sách này sẽ thu hẹp lại sau mỗi bước thành công.
    pallets_to_process = list(final_unplaced_list)

    # Lặp cho đến khi tất cả pallet được xử lý hoặc chúng ta bị kẹt trong vòng lặp.
    while pallets_to_process:
        initial_count = len(pallets_to_process)
        print(f"\n[BẮT ĐẦU VÒNG LẶP] Số pallet còn lại cần xử lý: {initial_count}")

        # --- BƯỚC 1: TẠO CONTAINER MỚI & XẾP HÀNG VỚI LOGIC CHI PHÍ CƠ HỘI ---
        # Bước này mô phỏng logic cốt lõi của việc tạo container mới cho các mặt hàng chưa được xếp.
        
        # Nhóm các pallet còn lại theo công ty của chúng.
        pallets_by_company = defaultdict(list)
        for p in pallets_to_process:
            pallets_by_company[p.company].append(p)

        # Biến này sẽ chứa các pallet vẫn không thể xếp được ngay cả trong các container mới.
        still_unplaced_after_new_cont = []
        
        for company, company_pallets in pallets_by_company.items():
            pallets_to_pack_in_new = sorted(company_pallets, key=lambda p: p.quantity, reverse=True)
            
            # Tiếp tục tạo container mới cho công ty này miễn là vẫn còn pallet.
            while pallets_to_pack_in_new:
                # Tạo một container mới cho công ty.
                new_container = Container(container_id=f"C{next_container_id}", main_company=company)
                print(f"  [+] Đang tạo container mới {new_container.id} cho công ty {company} để xử lý pallet thừa.")
                containers.append(new_container)
                next_container_id += 1
                
                # Các pallet còn lại cho công ty này sau khi container mới này được lấp đầy.
                temp_unplaced_list = []
                
                # Xếp hàng vào container mới này bằng logic chi phí cơ hội phức tạp.
                while pallets_to_pack_in_new:
                    # Luôn xem xét pallet lớn nhất còn lại trước tiên.
                    current_pallet = pallets_to_pack_in_new.pop(0)

                    if not new_container.can_fit(current_pallet):
                        temp_unplaced_list.append(current_pallet)
                        continue

                    # Tìm các pallet ứng cử viên nhỏ hơn để so sánh.
                    candidate_pallets = [p for p in pallets_to_pack_in_new]
                    
                    # Mô phỏng việc xếp một nhóm các pallet nhỏ hơn.
                    sim_container = copy.deepcopy(new_container)
                    small_pallet_group = []
                    for candidate in candidate_pallets:
                        if sim_container.can_fit(candidate):
                            sim_container.add_pallet(candidate)
                            small_pallet_group.append(candidate)
                    
                    # Kiểm tra xem nhóm pallet nhỏ hơn có phải là lựa chọn tốt hơn không.
                    group_is_better = (
                        len(small_pallet_group) > 1 and
                        sum(p.total_weight for p in small_pallet_group) < current_pallet.total_weight
                    )

                    if group_is_better:
                        # Tạm hoãn pallet lớn và xếp nhóm nhỏ hơn vào thay thế.
                        print(f"    -> (Chi phí cơ hội) Tạm hoãn {current_pallet.id}, xếp nhóm nhỏ hơn vào {new_container.id}.")
                        temp_unplaced_list.append(current_pallet)
                        for p_small in small_pallet_group:
                            new_container.add_pallet(p_small)
                            pallets_to_pack_in_new.remove(p_small)
                    else:
                        # Xếp pallet lớn vì đó là lựa chọn tốt nhất.
                        print(f"    -> Đang xếp {current_pallet.id} vào {new_container.id}.")
                        new_container.add_pallet(current_pallet)
                
                # Cập nhật danh sách cho container mới tiềm năng tiếp theo của công ty này.
                pallets_to_pack_in_new = sorted(temp_unplaced_list, key=lambda p:p.quantity, reverse=True)

            # Bất kỳ pallet nào còn lại của công ty này sẽ được thêm vào danh sách chưa xếp chung.
            still_unplaced_after_new_cont.extend(pallets_to_pack_in_new)

        pallets_to_process = still_unplaced_after_new_cont
        if not pallets_to_process:
            print("[THÔNG BÁO] Tất cả pallet đã được xếp sau khi tạo container mới.")
            break

        # --- BƯỚC 2: THỬ XẾP HÀNG ĐƠN GIẢN VÀO BẤT KỲ CONTAINER CÙNG CÔNG TY NÀO ---
        print("\n  [BƯỚC 2] Thử xếp các pallet còn lại vào bất kỳ container nào cùng công ty...")
        pallets_to_process = try_pack_pallets_into_same_company_containers(pallets_to_process, containers)
        if not pallets_to_process:
            print("[THÔNG BÁO] Tất cả pallet đã được xếp sau vòng xếp hàng đơn giản.")
            break

        # --- BƯỚC 3: ÁP DỤNG CHIA TÁCH THÔNG MINH VÀ XẾP CHÉO ---
        print("\n  [BƯỚC 3] Áp dụng logic chia tách thông minh cho phần còn lại...")
        pallets_to_process = handle_unplaced_pallets_with_smart_splitting(pallets_to_process, containers)
        if not pallets_to_process:
            print("[THÔNG BÁO] Tất cả pallet đã được xếp sau vòng chia tách thông minh.")
            break

        # --- KIỂM TRA TIẾN ĐỘ ---
        # Nếu số lượng pallet không thay đổi sau một chu kỳ đầy đủ, chúng ta đang bị kẹt.
        if len(pallets_to_process) == initial_count:
            print(f"[CẢNH BÁO] Không có tiến triển trong vòng lặp. Thoát vòng lặp để tránh lặp vô hạn. {len(pallets_to_process)} pallet vẫn chưa được xếp.")
            # Trong một kịch bản thực tế, bạn có thể có một phương án dự phòng cuối cùng ở đây,
            # chẳng hạn như buộc tạo thêm một container cho những pallet cuối cùng này.
            break

    print("--- HOÀN TẤT QUY TRÌNH XỬ LÝ LẶP LẠI CUỐI CÙNG ---")
    return containers, next_container_id
def check_cross_ship_capacity_for_list(pallets_to_check, containers, unplaced_fractionals):
    """
    Kiểm tra xem TỔNG sức chứa còn lại của các container khác công ty
    có đủ để chứa TOÀN BỘ danh sách pallet chờ hay không.

    *** CẢI TIẾN: Sẽ không cross-ship pallet nguyên nếu vẫn còn BẤT KỲ pallet lẻ/gộp
    nào đang trong danh sách chờ (không phân biệt công ty). ***
    """
    if not pallets_to_check:
        return True

    print("\n--- BƯỚC: KIỂM TRA KHẢ NĂNG CROSS-SHIP TOÀN BỘ DANH SÁCH CHỜ (NGUYÊN) ---")

    # 1. Tính toán tổng yêu cầu từ danh sách chờ pallet nguyên
    total_qty_needed = sum(p.quantity for p in pallets_to_check)
    total_wgt_needed = sum(p.total_weight for p in pallets_to_check)
    
    # 2. TÍNH NĂNG MỚI: Kiểm tra xem có BẤT KỲ pallet lẻ/gộp nào đang chờ không
    if unplaced_fractionals: # Chỉ cần kiểm tra xem danh sách có trống không
        print("  - PHÁT HIỆN: Vẫn còn pallet lẻ/gộp trong danh sách chờ chung.")
        print("  -> KẾT LUẬN: KHÔNG cross-ship pallet nguyên để ưu tiên gom hàng.")
        return False # Ngăn chặn cross-ship

    # 3. Tính tổng sức chứa còn lại của các công ty KHÁC (nếu logic trên cho phép đi tiếp)
    companies_in_wait_list = set(p.company for p in pallets_to_check)
    other_company_containers = [c for c in containers if c.main_company not in companies_in_wait_list]
    total_rem_qty = sum(c.remaining_quantity for c in other_company_containers)
    total_rem_wgt = sum(c.remaining_weight for c in other_company_containers)
    
    print(f"  - Yêu cầu từ pallet nguyên: {total_qty_needed:.2f} qty | {total_wgt_needed:.2f} wgt")
    print(f"  - Khả dụng ở các công ty khác: {total_rem_qty:.2f} qty | {total_rem_wgt:.2f} wgt")

    # 4. So sánh và trả về kết quả
    if total_rem_qty >= total_qty_needed and total_rem_wgt >= total_wgt_needed:
        print("  -> KẾT LUẬN: Đủ khả năng cross-ship toàn bộ. Sẽ chuyển sang logic chia tách thông minh.")
        return True
    else:
        print("  -> KẾT LUẬN: Không đủ khả năng cross-ship. Sẽ đến bước chia tách thông minh để xếp vừa vào container có sẵn.")
        return False
def attempt_partial_cross_ship(unplaced_pallets, containers,unplaced_fractionals):
    """
    BƯỚC TRUNG GIAN (LOGIC MỚI): Thử chia nhỏ từng pallet để lấp đầy các khoảng trống.
    Hoạt động theo nguyên tắc "TẤT CẢ HOẶC KHÔNG CÓ GÌ" và đảm bảo chỉ chia ra các phần NGUYÊN.
    1. Giai đoạn 1 (Lập kế hoạch): Lặp qua TẤT CẢ các pallet để tìm kế hoạch chia tách.
       - Nếu BẤT KỲ pallet nào không tìm được kế hoạch, toàn bộ hoạt động sẽ bị HỦY.
    2. Giai đoạn 2 (Thực thi): Chỉ chạy nếu Giai đoạn 1 thành công cho mọi pallet.
       - Nếu BẤT KỲ pallet nào thất bại trong quá trình thực thi, toàn bộ hoạt động sẽ bị HỦY
         và trạng thái container được khôi phục.
    """
    print("\n--- BƯỚC MỚI: THỬ CROSS-SHIP TỪNG PHẦN ĐỂ TỐI ƯU HÓA KHÔNG GIAN (All-or-Nothing) ---")
    if unplaced_fractionals:
        print("  - PHÁT HIỆN: Vẫn còn pallet lẻ/gộp trong danh sách chờ.")
        print("  -> KẾT LUẬN: Bỏ qua bước cross-ship từng phần để ưu tiên xử lý pallet lẻ trước.")
        return unplaced_pallets
    if not unplaced_pallets:
        return []

    # --- HÀM HỖ TRỢ (ĐÃ SỬA ĐỔI) ---
    def _can_be_placed_iteratively(qty_to_check, wpp, target_containers):
        """Kiểm tra xem một số lượng pallet có thể được xếp vào các container mục tiêu bằng cách chỉ sử dụng các phần nguyên không."""
        if qty_to_check < EPSILON: return True
        temp_qty_to_place = qty_to_check
        # Tạo bản sao sâu của container để mô phỏng mà không thay đổi trạng thái thật
        sim_containers = copy.deepcopy(target_containers)
        sorted_containers = sorted(sim_containers, key=lambda c: c.remaining_quantity)

        for c in sorted_containers:
            if temp_qty_to_place < EPSILON: break
            qty_by_vol = c.remaining_quantity
            qty_by_wgt = c.remaining_weight / wpp if wpp > 0 else float('inf')
            qty_by_lp = float(c.remaining_logical_pallets)
            max_fit_in_this_cont = min(qty_by_vol, qty_by_wgt, qty_by_lp)
            
            amount_to_place_here = math.floor(min(temp_qty_to_place, max_fit_in_this_cont))

            if amount_to_place_here < 1.0 - EPSILON:
                continue

            # Cập nhật trạng thái container mô phỏng
            c.total_quantity += amount_to_place_here
            c.total_weight += amount_to_place_here * wpp
            c.total_logical_pallets += math.ceil(amount_to_place_here)
            temp_qty_to_place -= amount_to_place_here

        return temp_qty_to_place < EPSILON

    def _place_pallet_iteratively(pallet_to_place, target_containers, placement_type=""):
        """Xếp một pallet vào các container mục tiêu bằng cách chia nhỏ nó thành các phần NGUYÊN."""
        if not pallet_to_place or pallet_to_place.quantity < EPSILON:
            return True
        remaining_part = pallet_to_place
        sorted_containers = sorted(target_containers, key=lambda c: c.remaining_quantity)

        for container in sorted_containers:
            if remaining_part is None or remaining_part.quantity < EPSILON:
                break

            qty_by_vol = container.remaining_quantity
            qty_by_wgt = container.remaining_weight / remaining_part.weight_per_pallet if remaining_part.weight_per_pallet > 0 else float('inf')
            max_fit_quantity = min(remaining_part.quantity, qty_by_vol, qty_by_wgt)

            fit_quantity = math.floor(max_fit_quantity)

            if fit_quantity < 1.0 - EPSILON:
                continue

            if abs(remaining_part.quantity - fit_quantity) < EPSILON:
                if container.can_fit(remaining_part):
                    container.add_pallet(remaining_part)
                    print(f"       -> ({placement_type}) Đã xếp (toàn bộ) {remaining_part.id} vào container {container.id}")
                    remaining_part = None
                continue
            else:
                if fit_quantity > EPSILON:
                    rest, piece_to_add = remaining_part.split(fit_quantity)
                    if piece_to_add and container.can_fit(piece_to_add):
                        container.add_pallet(piece_to_add)
                        print(f"       -> ({placement_type}) Đã xếp (một phần) {piece_to_add.id} (qty: {piece_to_add.quantity:.0f}) vào cont {container.id}")
                        remaining_part = rest

        return remaining_part is None or remaining_part.quantity < EPSILON

    # --- GIAI ĐOẠN 1: LẬP KẾ HOẠCH (KHÔNG THỰC THI) ---
    print("   [PHASE 1] Lập kế hoạch tối ưu cho tất cả pallet chờ...")
    all_plans = []
    
    for pallet in unplaced_pallets:
        best_plan = {"keep_qty": -1}
        own_company_containers = [c for c in containers if c.main_company == pallet.company]
        other_company_containers = [c for c in containers if c.main_company != pallet.company]

        for num_to_keep_int in range(math.floor(pallet.quantity), -1, -1):
            num_to_keep = float(num_to_keep_int)
            num_to_cross = pallet.quantity - num_to_keep
            
            can_keep = _can_be_placed_iteratively(num_to_keep, pallet.weight_per_pallet, own_company_containers)
            can_cross = _can_be_placed_iteratively(num_to_cross, pallet.weight_per_pallet, other_company_containers)
            
            if can_keep and can_cross:
                best_plan = {"pallet": pallet, "keep_qty": num_to_keep, "cross_qty": num_to_cross}
                break
        
        if best_plan["keep_qty"] == -1:
            print(f"   [!] Không tìm thấy kế hoạch chia tách khả thi cho pallet {pallet.id}.")
            print("   [!] HỦY BỎ TOÀN BỘ kế hoạch cross-ship từng phần. Sẽ chuyển sang tạo container mới.")
            return unplaced_pallets

        all_plans.append(best_plan)
    
    # --- GIAI ĐOẠN 2: THỰC THI (All-or-Nothing) ---
    print("   [PHASE 2] Tất cả pallet đều có kế hoạch khả thi. Bắt đầu thực thi...")
    
    # Tạo một bản sao lưu trạng thái của các container trước khi thực hiện bất kỳ thay đổi nào
    containers_backup = copy.deepcopy(containers)
    execution_failed = False
    failed_pallet_id = None

    pallets_to_process_dict = {p.id: p for p in unplaced_pallets}

    for plan in all_plans:
        original_pallet = pallets_to_process_dict[plan['pallet'].id]
        keep_qty = plan['keep_qty']
        cross_qty = plan['cross_qty']
        
        print(f"   [*] Thực thi kế hoạch cho {original_pallet.id} (qty: {original_pallet.quantity:.0f}):")
        print(f"       - Giữ lại: {keep_qty:.0f} | Chuyển đi: {cross_qty:.0f}")

        own_company_containers = [c for c in containers if c.main_company == original_pallet.company]
        other_company_containers = [c for c in containers if c.main_company != original_pallet.company]
        part_to_keep, part_to_cross = None, None

        if cross_qty < EPSILON:
            part_to_keep = original_pallet
        elif keep_qty < EPSILON:
            part_to_cross = original_pallet
        else:
            # Sử dụng pallet gốc từ dict để chia tách
            part_to_keep, part_to_cross = original_pallet.split(cross_qty)
            if not part_to_keep or not part_to_cross:
                print(f"   [LỖI] Lỗi khi chia pallet {original_pallet.id}.")
                failed_pallet_id = original_pallet.id
                execution_failed = True
                break
        
        was_kept_placed = _place_pallet_iteratively(part_to_keep, own_company_containers, "Giữ lại")
        was_cross_placed = _place_pallet_iteratively(part_to_cross, other_company_containers, "Chuyển đi")

        if not (was_kept_placed and was_cross_placed):
            print(f"   [LỖI] Không thể xếp toàn bộ các mảnh của pallet {original_pallet.id} theo kế hoạch.")
            failed_pallet_id = original_pallet.id
            execution_failed = True
            break
            
    # --- GIAI ĐOẠN 3: TỔNG KẾT ---
    if execution_failed:
        print(f"   [!] HỦY BỎ: Do lỗi với pallet {failed_pallet_id}, toàn bộ hoạt động tối ưu hóa đã bị hủy.")
        print("   [!] Khôi phục trạng thái container về trước khi thực thi.")
        
        # Khôi phục trạng thái container bằng cách xóa list hiện tại và điền lại từ bản sao lưu
        containers.clear()
        for c_backup in containers_backup:
            containers.append(c_backup)
        
        # === BỔ SUNG KHẮC PHỤC LỖI ===
        # Reset lại cờ is_cross_ship cho các pallet đã bị thay đổi trong quá trình thử nghiệm thất bại.
        print("   [!] Đang reset lại trạng thái cho các pallet bị ảnh hưởng...")
        for p in unplaced_pallets:
            if p.is_cross_ship:
                p.is_cross_ship = False
        # ===============================
        
        # Trả về danh sách pallet chờ ban đầu đã được làm sạch
        return unplaced_pallets
    else:
        print("   [THÀNH CÔNG] Hoàn tất tối ưu hóa. Tất cả pallet chờ đã được xử lý.")
        # Nếu thành công, tất cả pallet đã được xếp, trả về danh sách rỗng
        return []
def create_and_pack_one_new_container(pallets_to_pack, containers, next_container_id, unplaced_fractionals):
    """
    Tạo ra MỘT container mới và áp dụng logic tối ưu "chi phí cơ hội"
    (tái sử dụng từ hàm pack_integer_pallets) để xếp hàng vào đó.
    
    LOGIC MỚI: Ưu tiên tạo container cho công ty có cả pallet nguyên và pallet lẻ/gộp
    đang trong danh sách chờ. Nếu không có, sẽ dùng logic cũ.
    
    Trả về danh sách những pallet vẫn không xếp được.
    """
    print("\n--- BƯỚC: TẠO MỘT CONTAINER MỚI VÀ XẾP TỐI ƯU (LOGIC CHI PHÍ CƠ HỘI) ---")
    if not pallets_to_pack and not unplaced_fractionals:
        return [], containers, next_container_id

    # --- LOGIC ƯU TIÊN ĐÃ SỬA ĐỔI ---
    priority_company = None
    
    # Lấy tập hợp các công ty từ mỗi danh sách chờ
    integer_companies = set(p.company for p in pallets_to_pack)
    fractional_companies = set(p.company for p in unplaced_fractionals)
    
    # Tìm các công ty xuất hiện trong cả hai danh sách
    common_companies = integer_companies.intersection(fractional_companies)

    # **ĐIỀU KIỆN ƯU TIÊN MỚI**
    if common_companies:
        print("  [LOGIC ƯU TIÊN MỚI] Dựa trên các công ty có cả pallet nguyên và lẻ/gộp đang chờ.")
        print(f"    -> Các công ty ứng viên: {', '.join(sorted(list(common_companies)))}")
        
        # Áp dụng logic cũ trên tập hợp các công ty chung này để chọn ra công ty tốt nhất
        # Ưu tiên 1: Công ty có tổng qty lẻ lớn nhất trong nhóm chung
        company_qty_sum = defaultdict(float)
        for p in unplaced_fractionals:
            if p.company in common_companies:
                company_qty_sum[p.company] += p.quantity
        
        if company_qty_sum:
            priority_company = max(company_qty_sum, key=company_qty_sum.get)
            print(f"    -> Công ty '{priority_company}' được ưu tiên vì có tổng qty lẻ lớn nhất trong nhóm chung ({company_qty_sum[priority_company]:.2f} qty).")
        else: # Fallback hiếm gặp: có công ty chung nhưng không có pallet lẻ (phòng ngừa)
            company_counts = Counter(p.company for p in pallets_to_pack if p.company in common_companies)
            priority_company = company_counts.most_common(1)[0][0]
            print(f"    -> Công ty '{priority_company}' được ưu tiên vì có nhiều pallet nguyên nhất trong nhóm chung.")

    # **FALLBACK VỀ LOGIC CŨ**
    else:
        print("  [LOGIC CŨ] Không có công ty nào xuất hiện đồng thời ở cả hai danh sách chờ. Áp dụng logic cũ.")
        if unplaced_fractionals:
            print("    -> Dựa trên tổng số lượng pallet lẻ/gộp đang chờ.")
            company_qty_sum = defaultdict(float)
            for p in unplaced_fractionals:
                company_qty_sum[p.company] += p.quantity
            
            if company_qty_sum:
                priority_company = max(company_qty_sum, key=company_qty_sum.get)
                print(f"    -> Công ty '{priority_company}' được ưu tiên vì có tổng số lượng pallet lẻ/gộp lớn nhất ({company_qty_sum[priority_company]:.2f} qty).")

        if not priority_company and pallets_to_pack:
            print("    -> Không có pallet lẻ/gộp. Dùng logic cũ dựa trên số lượng pallet nguyên.")
            company_counts = Counter(p.company for p in pallets_to_pack)
            priority_company = company_counts.most_common(1)[0][0]
            print(f"    -> Công ty '{priority_company}' được ưu tiên vì có nhiều pallet nguyên nhất ({company_counts[priority_company]} pallet).")
        
        elif not priority_company:
            print("  [CẢNH BÁO] Không có pallet nào trong cả hai danh sách chờ để xác định công ty ưu tiên.")
            return [], containers, next_container_id
    # --- KẾT THÚC LOGIC ƯU TIÊN ---

    # 2. Tạo container mới và thêm ngay vào danh sách container chung
    new_container = Container(container_id=f"C{next_container_id}", main_company=priority_company)
    print(f"  [+] Đã tạo container mới {new_container.id} cho công ty ưu tiên '{priority_company}'.")
    containers.append(new_container)
    next_container_id += 1
    
    # 3. Tách pallet: chỉ tối ưu cho các pallet cùng công ty với container mới
    pallets_for_this_company = [p for p in pallets_to_pack if p.company == priority_company]
    other_company_pallets = [p for p in pallets_to_pack if p.company != priority_company]

    # 4. TÁI SỬ DỤNG LOGIC TỐI ƯU từ hàm pack_integer_pallets
    print(f"  [*] Áp dụng logic 'chi phí cơ hội' để xếp {len(pallets_for_this_company)} pallet vào {new_container.id}...")
    
    _, unplaced_from_packing, _ = pack_integer_pallets(
        integer_pallets=pallets_for_this_company,
        existing_containers=[new_container],
        next_container_id=next_container_id
    )

    # 5. Tổng hợp lại danh sách chờ cuối cùng
    final_unplaced_list = unplaced_from_packing + other_company_pallets

    print(f"\n  --- KẾT QUẢ XẾP VÀO CONTAINER MỚI ({new_container.id}) ---")
    if not final_unplaced_list:
         print(f"  [SUCCESS] Đã xếp thành công tất cả pallet chờ có liên quan của công ty ưu tiên.")
    else:
         print(f"  [INFO] Còn lại {len(final_unplaced_list)} pallet không vừa, sẽ được giữ trong danh sách chờ.")

    return final_unplaced_list, containers, next_container_id
# xử lí pallet trong danh sách chờ cùng công ty lẻ
def try_pack_unplaced_fractionals_same_company(unplaced_fractionals, containers):
    """
    Cố gắng xếp các pallet lẻ/gộp còn trong danh sách chờ vào các container
    có sẵn của CÙNG CÔNG TY một cách NGUYÊN VẸN.
    
    Đây là bước xử lý đơn giản trước khi dùng đến các biện pháp phức tạp hơn
    như xé nhỏ pallet ra để lắp ghép (repacking).

    Args:
        unplaced_fractionals (list[Pallet]): Danh sách các pallet lẻ/gộp đang chờ xử lý.
        containers (list[Container]): Danh sách tất cả container hiện có.

    Returns:
        list[Pallet]: Danh sách các pallet vẫn không thể xếp được sau bước này,
                      sẽ được chuyển tiếp cho các hàm xử lý phức tạp hơn.
    """
    print("\n--- BƯỚC: CỐ GẮNG XẾP NGUYÊN VẸN PALLET LẺ/GỘP VÀO CONT CÙNG CTY ---")
    
    # Danh sách để lưu những pallet thực sự không thể xếp được trong bước này
    still_unplaced = []
    
    # Sắp xếp các pallet cần xử lý từ lớn đến nhỏ để ưu tiên các pallet khó xếp nhất trước
    pallets_to_pack = sorted(unplaced_fractionals, key=lambda p: p.quantity, reverse=True)

    for pallet in pallets_to_pack:
        was_placed = False
        
        # 1. Lọc ra những container tương thích (cùng công ty)
        # 2. Sắp xếp chúng để ưu tiên container gần đầy nhất (Best-Fit)
        compatible_containers = sorted(
            [c for c in containers if c.main_company == pallet.company],
            key=lambda c: c.remaining_quantity
        )
        
        # 3. Duyệt qua các container phù hợp để tìm chỗ
        for container in compatible_containers:
            if container.can_fit(pallet):
                # Nếu vừa, thêm vào, đánh dấu và chuyển sang pallet tiếp theo
                container.add_pallet(pallet)
                print(f"  [+] (Xếp đơn giản) Đã xếp pallet lẻ/gộp '{pallet.id}' vào container có sẵn {container.id}.")
                was_placed = True
                break
        
        # 4. Nếu duyệt hết mà vẫn không xếp được
        if not was_placed:
            print(f"  [-] (Không vừa) Pallet '{pallet.id}' không tìm được chỗ, sẽ chuyển sang giai đoạn lắp ghép.")
            still_unplaced.append(pallet)

    print(f"--- KẾT THÚC: Còn lại {len(still_unplaced)} pallet cần xử lý lắp ghép phức tạp hơn. ---")
    return still_unplaced
def repack_unplaced_pallets(unplaced_pallets, containers):
    """
    Cố gắng xếp các pallet còn lại bằng cách "lắp ghép" chúng vào các pallet lẻ/ghép
    đã có sẵn trong các container, ưu tiên cùng công ty.
    *** PHIÊN BẢN CẢI TIẾN: Đảm bảo an toàn 100% về các giới hạn của container. ***
    """
    print("\n--- BẮT ĐẦU GIAI ĐOẠN LẮP GHÉP VÀO CÁC PALLET GHÉP LẺ CÙNG CÔNG TY ---")
    if not unplaced_pallets:
        print("Không có pallet nào cần xử lý. Hoàn tất.")
        return []

    final_leftovers = []
    placed_original_pallets = set()
    unplaced_combined = [p for p in unplaced_pallets if p.is_combined]
    unplaced_singles = [p for p in unplaced_pallets if not p.is_combined]

    # --- BƯỚC 1: XỬ LÝ CÁC PALLET GHÉP CHƯA ĐƯỢC XẾP ---
    print(f"\n[PHASE 1] Xử lý {len(unplaced_combined)} pallet GHÉP trong danh sách chờ...")
    for combined_pallet in unplaced_combined:
        sub_pallets_to_place = list(combined_pallet.original_pallets)
        successfully_placed_all_sub_pallets = True

        for sub_pallet in sub_pallets_to_place:
            was_sub_pallet_placed = False
            for container in [c for c in containers if c.main_company == combined_pallet.company]:
                for target_pallet in container.pallets:
                    if target_pallet.quantity >= 1.0 - EPSILON:
                        continue

                    # === BỔ SUNG KIỂM TRA AN TOÀN CHO CONTAINER ===
                    # 1. Kiểm tra trọng lượng
                    if container.total_weight + sub_pallet.total_weight > MAX_WEIGHT + EPSILON:
                        continue
                    # 2. Kiểm tra số dòng (ít khả năng xảy ra nhưng vẫn cần thiết)
                    # Khi ghép, số dòng logic không đổi, nên kiểm tra này chủ yếu để phòng ngừa.
                    # Giả định: pallet.logical_pallet_count là 1 cho pallet lẻ.
                    if container.total_logical_pallets + sub_pallet.logical_pallet_count - target_pallet.logical_pallet_count > MAX_PALLETS:
                        continue
                    # ===============================================

                    potential_list = target_pallet.original_pallets + [sub_pallet]
                    potential_qty = sum(p.quantity for p in potential_list)
                    if potential_qty > 0.9 + EPSILON:
                        continue

                    num_dominant = sum(1 for p in potential_list if p.quantity >= (potential_qty / 2.0) - EPSILON)
                    if num_dominant > 1:
                        continue

                    print(f"  [+] LẮP GHÉP: Mảnh {sub_pallet.id} (từ {combined_pallet.id}) vào Pallet {target_pallet.id} trong Cont {container.id}")
                    
                    target_pallet.original_pallets.append(sub_pallet)
                    target_pallet.is_combined = True
                    target_pallet._recalculate_from_originals()
                    # Cập nhật lại toàn bộ container
                    container._recalculate_totals()
                    was_sub_pallet_placed = True
                    break
                if was_sub_pallet_placed:
                    break

            if not was_sub_pallet_placed:
                successfully_placed_all_sub_pallets = False
                print(f"  [-] KHÔNG THỂ LẮP: Mảnh {sub_pallet.id} (từ {combined_pallet.id}) không tìm được chỗ.")
                break

        if successfully_placed_all_sub_pallets:
            placed_original_pallets.add(combined_pallet)
            print(f"  [OK] Đã lắp ghép thành công TẤT CẢ các mảnh của {combined_pallet.id}.")
        else:
            final_leftovers.append(combined_pallet)

    # --- BƯỚC 2: XỬ LÝ CÁC PALLET LẺ CHƯA ĐƯỢC XẾP ---
    print(f"\n[PHASE 2] Xử lý {len(unplaced_singles)} pallet LẺ trong danh sách chờ...")
    for single_pallet in unplaced_singles:
        was_placed = False
        for container in [c for c in containers if c.main_company == single_pallet.company]:
            for target_pallet in container.pallets:
                if target_pallet.quantity >= 1.0 - EPSILON:
                    continue
                
                # === BỔ SUNG KIỂM TRA AN TOÀN CHO CONTAINER ===
                if container.total_weight + single_pallet.total_weight > MAX_WEIGHT + EPSILON:
                    continue
                if container.total_logical_pallets + single_pallet.logical_pallet_count - target_pallet.logical_pallet_count > MAX_PALLETS:
                    continue
                # ===============================================

                potential_list = target_pallet.original_pallets + [single_pallet]
                potential_qty = sum(p.quantity for p in potential_list)
                if potential_qty > 0.9 + EPSILON:
                    continue

                num_dominant = sum(1 for p in potential_list if p.quantity >= (potential_qty / 2.0) - EPSILON)
                if num_dominant > 1:
                    continue

                print(f"  [+] LẮP GHÉP: Pallet lẻ {single_pallet.id} vào Pallet {target_pallet.id} trong Cont {container.id}")
                
                target_pallet.original_pallets.append(single_pallet)
                target_pallet.is_combined = True
                target_pallet._recalculate_from_originals()
                container._recalculate_totals()
                was_placed = True
                placed_original_pallets.add(single_pallet)
                break
            if was_placed:
                break
        
        if not was_placed:
            final_leftovers.append(single_pallet)
            print(f"  [-] KHÔNG THỂ LẮP: Pallet lẻ {single_pallet.id} không tìm được chỗ.")

    print("\n--- HOÀN THÀNH GIAI ĐOẠN LẮP GHÉP NÂNG CAO ---")
    print(f"Tổng kết: {len(placed_original_pallets)} pallet gốc đã được xếp. Còn lại: {len(final_leftovers)} pallet.")
    return final_leftovers

def split_and_fit_leftovers(leftover_pallets, containers, next_container_id):
    """
    Xử lý các pallet còn lại bằng cách chia nhỏ và lắp ghép theo logic 2 giai đoạn:
    - Giai đoạn 1: Xử lý các pallet lẻ đơn lẻ, thử ghép chéo (cross-ship).
    - Giai đoạn 2: Xử lý các pallet gộp với logic "tất cả hoặc không có gì". Nếu một
      pallet gộp không thể xếp được tất cả các mảnh của nó, toàn bộ quá trình sẽ
      dừng lại và trả về các pallet còn lại.
    """
    print("\n--- BẮT ĐẦU GIAI ĐOẠN LẮP GHÉP KHÁC CÔNG TY (LOGIC 2 GIAI ĐOẠN) ---")
    if not leftover_pallets:
        print("   Không có pallet nào cần xử lý. Hoàn tất.")
        return containers, next_container_id, []

    # Tách danh sách chờ ban đầu
    unplaced_singles = [p for p in leftover_pallets if not p.is_combined]
    unplaced_combined = [p for p in leftover_pallets if p.is_combined]
    
    pallets_still_unplaced = []

    # --- GIAI ĐOẠN 1: XỬ LÝ CÁC PALLET LẺ ĐƠN LẺ ---
    print(f"\n[PHASE 1] Thử ghép chéo {len(unplaced_singles)} pallet LẺ đơn lẻ...")
    
    for single_pallet in sorted(unplaced_singles, key=lambda p: p.quantity, reverse=True):
        was_placed = False
        
        # Tìm kiếm mục tiêu ở các container của công ty KHÁC
        other_company_containers = [c for c in containers if c.main_company != single_pallet.company]
        
        for container in other_company_containers:
            # Chỉ tìm kiếm các pallet lẻ/ghép có thể nhận thêm
            for target_pallet in [p for p in container.pallets if p.quantity < 1.0 - EPSILON]:
                
                # --- Các điều kiện kiểm tra an toàn ---
                if container.total_weight + single_pallet.total_weight > MAX_WEIGHT + EPSILON:
                    continue
                
                potential_list = target_pallet.original_pallets + [single_pallet]
                potential_qty = sum(p.quantity for p in potential_list)
                if potential_qty > 0.9 + EPSILON:
                    continue
                
                num_dominant = sum(1 for p in potential_list if p.quantity >= (potential_qty / 2.0) - EPSILON)
                if num_dominant > 1:
                    continue

                # --- BẮT ĐẦU SỬA LỖI ---
                # Nếu pallet mục tiêu sắp bị biến thành pallet gộp, hãy bảo toàn trạng thái gốc của nó.
                if not target_pallet.is_combined:
                    # Tạo một bản sao của pallet mục tiêu để lưu giữ thông tin gốc.
                    original_target_copy = copy.copy(target_pallet)
                    original_target_copy.original_pallets = [original_target_copy] # Pallet con chỉ trỏ về chính nó.
                    # Danh sách pallet con của pallet mục tiêu giờ sẽ bắt đầu bằng bản sao này.
                    target_pallet.original_pallets = [original_target_copy]
                # --- KẾT THÚC SỬA LỖI ---
                
                print(f"  [+] (Phase 1) Lắp ghép pallet lẻ {single_pallet.id} vào Pallet {target_pallet.id} trong Cont {container.id}")
                
                target_pallet.original_pallets.append(single_pallet)
                target_pallet.is_combined = True
                target_pallet._recalculate_from_originals()
                
                all_companies = set(str(p.company) for p in target_pallet.original_pallets)
                if len(all_companies) > 1:
                    target_pallet.company = "+".join(sorted(list(all_companies)))
                    target_pallet.product_name = f"COMBINED ({len(target_pallet.original_pallets)} items)"

                container._recalculate_totals()
                
                was_placed = True
                break
            if was_placed:
                break
        
        if not was_placed:
            pallets_still_unplaced.append(single_pallet)

    print(f"   -> Kết thúc Phase 1. Còn lại {len(pallets_still_unplaced)} pallet lẻ chưa được xếp.")

    # --- GIAI ĐOẠN 2: XỬ LÝ CÁC PALLET GỘP (VÀ CÁC PALLET LẺ CÒN SÓT LẠI) ---
    pallets_for_phase_2 = unplaced_combined + pallets_still_unplaced
    if not pallets_for_phase_2:
        print("\n[PHASE 2] Không còn pallet nào để xử lý. Hoàn tất.")
        return containers, next_container_id, []

    print(f"\n[PHASE 2] Thử lắp ghép {len(pallets_for_phase_2)} pallet gộp/còn lại (All-or-Nothing)...")
    
    for i, combined_pallet in enumerate(pallets_for_phase_2):
        print(f"\n   [*] Đang xử lý pallet: {combined_pallet.id} (gồm {len(combined_pallet.original_pallets)} mảnh)")
        
        sim_containers = copy.deepcopy(containers)
        placement_plan = []
        all_sub_pallets_planned = True
        
        sub_pallets_to_plan = sorted(combined_pallet.original_pallets, key=lambda p: p.quantity, reverse=True)
        
        for sub_pallet in sub_pallets_to_plan:
            was_sub_planned = False
            
            for sim_container in sim_containers:
                for sim_target_pallet in [p for p in sim_container.pallets if p.quantity < 1.0 - EPSILON]:
                    
                    if sim_container.total_weight + sub_pallet.total_weight > MAX_WEIGHT + EPSILON:
                        continue
                    
                    potential_list = sim_target_pallet.original_pallets + [sub_pallet]
                    potential_qty = sum(p.quantity for p in potential_list)
                    if potential_qty > 0.9 + EPSILON:
                        continue
                    
                    num_dominant = sum(1 for p in potential_list if p.quantity >= (potential_qty / 2.0) - EPSILON)
                    if num_dominant > 1:
                        continue

                    placement_plan.append({'sub_pallet_id': sub_pallet.id, 'target_pallet_id': sim_target_pallet.id})
                    
                    sim_target_pallet.original_pallets.append(sub_pallet)
                    sim_container._recalculate_totals() 
                    
                    was_sub_planned = True
                    break
                if was_sub_planned:
                    break
            
            if not was_sub_planned:
                all_sub_pallets_planned = False
                break
        
        if all_sub_pallets_planned:
            print(f"   [OK] Lên kế hoạch thành công cho {combined_pallet.id}. Bắt đầu thực thi...")
            for action in placement_plan:
                sub_p = next(p for p in combined_pallet.original_pallets if p.id == action['sub_pallet_id'])
                target_p = next((p for c in containers for p in c.pallets if p.id == action['target_pallet_id']), None)
                
                if target_p:
                    container_to_update = next(c for c in containers if target_p in c.pallets)
                    
                    # --- BẮT ĐẦU SỬA LỖI (Lần 2, cho Giai đoạn 2) ---
                    if not target_p.is_combined:
                        original_target_copy = copy.copy(target_p)
                        original_target_copy.original_pallets = [original_target_copy]
                        target_p.original_pallets = [original_target_copy]
                    # --- KẾT THÚC SỬA LỖI ---
                    
                    print(f"      -> Ghép mảnh {sub_p.id} vào Pallet {target_p.id} trong Cont {container_to_update.id}")
                    
                    target_p.original_pallets.append(sub_p)
                    target_p.is_combined = True
                    
                    all_companies = set(str(p.company) for p in target_p.original_pallets)
                    if len(all_companies) > 1:
                        target_p.company = "+".join(sorted(list(all_companies)))
                        target_p.product_name = f"COMBINED ({len(target_p.original_pallets)} items)"

                    container_to_update._recalculate_totals()
            print(f"   [SUCCESS] Đã thực thi xong kế hoạch cho {combined_pallet.id}.")

        else:
            print(f"   [FAILURE] Không thể tìm được chỗ cho tất cả các mảnh của {combined_pallet.id}.")
            print("   -> DỪNG bước lắp ghép và chuyển các pallet còn lại sang bước Cross-Ship.")
            
            final_unplaced_list = pallets_for_phase_2[i:]
            return containers, next_container_id, final_unplaced_list

    print("\n--- HOÀN THÀNH GIAI ĐOẠN LẮP GHÉP ---")
    print("   Tất cả pallet trong danh sách chờ đã được lắp ghép thành công.")
    return containers, next_container_id, []
### CROSS SHIP 
def cross_ship_remaining_pallets(unplaced_pallets, containers, next_container_id, unplaced_integer_pallets):
    """
    SỬA ĐỔI: Xử lý pallet lẻ/gộp cuối cùng với logic điều kiện nghiêm ngặt.
    1. KIỂM TRA ƯU TIÊN: Nếu còn pallet NGUYÊN đang chờ, hàm sẽ dừng ngay lập tức
       để vòng lặp lớn xử lý pallet nguyên trước.
    2. KIỂM TRA NĂNG LỰC: Đánh giá xem tổng không gian trống của các container
       khác công ty có đủ để chứa TOÀN BỘ danh sách pallet lẻ/gộp đang chờ không.
    3. RA QUYẾT ĐỊNH:
       - NẾU ĐỦ NĂNG LỰC: Tiến hành cross-ship toàn bộ danh sách (xếp đơn giản và lắp ghép).
       - NẾU KHÔNG ĐỦ: Chỉ tạo MỘT container mới cho pallet lớn nhất trong danh sách,
         phần còn lại sẽ được đưa vào danh sách chờ cho vòng lặp lớn tiếp theo.
    """
    print("\n--- BẮT ĐẦU GIAI ĐOẠN CUỐI: CROSS-SHIP CÓ ĐIỀU KIỆN HOẶC TẠO CONT MỚI ---")
    if not unplaced_pallets:
        print("   Không có pallet lẻ/gộp nào cần xử lý. Hoàn tất.")
        return [], next_container_id

    # --- BƯỚC 1: KIỂM TRA ƯU TIÊN (ĐIỀU KIỆN DỪNG) ---
    if unplaced_integer_pallets:
        print("   [ƯU TIÊN] Phát hiện còn pallet NGUYÊN đang chờ.")
        print("   -> Tạm dừng cross-ship pallet lẻ để vòng lặp lớn xử lý pallet nguyên trước.")
        # Trả về danh sách pallet lẻ y nguyên, không xử lý gì cả
        return unplaced_pallets, next_container_id

    # --- BƯỚC 2: KIỂM TRA NĂNG LỰC CROSS-SHIP TOÀN BỘ ---
    print("   [*] Không có pallet nguyên nào đang chờ. Đánh giá năng lực cross-ship...")
    # Tính toán tổng yêu cầu từ danh sách chờ
    total_qty_needed = sum(p.quantity for p in unplaced_pallets)
    total_wgt_needed = sum(p.total_weight for p in unplaced_pallets)

    # Tính tổng sức chứa còn lại của các container khác công ty
    companies_in_wait_list = set(p.company for p in unplaced_pallets)
    other_company_containers = [c for c in containers if c.main_company not in companies_in_wait_list]
    total_rem_qty = sum(c.remaining_quantity for c in other_company_containers)
    total_rem_wgt = sum(c.remaining_weight for c in other_company_containers)

    print(f"   - Yêu cầu từ pallet lẻ/gộp: {total_qty_needed:.2f} qty | {total_wgt_needed:.2f} wgt")
    print(f"   - Khả dụng ở các công ty khác: {total_rem_qty:.2f} qty | {total_rem_wgt:.2f} wgt")

    # --- BƯỚC 3: RA QUYẾT ĐỊNH ---
    # NẾU CÓ THỂ CHỨA HẾT -> TIẾN HÀNH CROSS-SHIP
    if total_rem_qty >= total_qty_needed and total_rem_wgt >= total_wgt_needed:
        print("   [QUYẾT ĐỊNH] Đủ năng lực. Tiến hành cross-ship TOÀN BỘ danh sách chờ.")
        
        # Tái sử dụng logic cross-ship chi tiết từ hàm gốc (xếp đơn giản + lắp ghép)
        # Mục tiêu là xếp hết tất cả pallet trong `unplaced_pallets`
        pallets_to_process = list(unplaced_pallets)
        still_unplaced_after_cross_ship = []

        # Logic xếp đơn giản
        placed_pallets = set()
        for pallet in sorted(pallets_to_process, key=lambda p: p.quantity, reverse=True):
            for container in sorted(other_company_containers, key=lambda c: c.remaining_quantity):
                if container.can_fit(pallet):
                    container.add_pallet(pallet)
                    placed_pallets.add(pallet)
                    print(f"     [+] CROSS-SHIP (Đơn giản): Pallet {pallet.id} -> Cont {container.id}")
                    break
        
        pallets_to_repack = [p for p in pallets_to_process if p not in placed_pallets]

        # Logic lắp ghép cho phần còn lại
        for pallet in pallets_to_repack:
            was_placed = False
            # Tách các mảnh con ra để lắp ghép
            sub_pallets = pallet.original_pallets if pallet.is_combined else [pallet]
            for sub_pallet in sub_pallets:
                # Tìm chỗ cho từng mảnh con
                # (Logic này có thể được làm phức tạp hơn nếu cần, nhưng để đơn giản, ta chỉ thử xếp cả pallet)
                for container in other_company_containers:
                     if container.can_fit(pallet):
                        container.add_pallet(pallet)
                        was_placed = True
                        print(f"     [+] CROSS-SHIP (Lắp ghép): Pallet {pallet.id} -> Cont {container.id}")
                        break
                if was_placed:
                    break
            if not was_placed:
                 still_unplaced_after_cross_ship.append(pallet)

        if still_unplaced_after_cross_ship:
             print(f"   [CẢNH BÁO] Mặc dù đủ năng lực nhưng {len(still_unplaced_after_cross_ship)} pallet không thể xếp được do phân mảnh.")
        
        return still_unplaced_after_cross_ship, next_container_id

    # NẾU KHÔNG THỂ CHỨA HẾT -> TẠO CONTAINER MỚI CHO PALLET LỚN NHẤT
    else:
        print("   [QUYẾT ĐỊNH] Không đủ năng lực. Tạo container mới cho pallet lớn nhất.")
        
        # Sắp xếp để tìm pallet lớn nhất
        sorted_pallets = sorted(unplaced_pallets, key=lambda p: p.quantity, reverse=True)
        
        # Lấy pallet lớn nhất ra để xử lý
        pallet_to_place = sorted_pallets.pop(0)
        
        # Tạo container mới với công ty của chính pallet đó
        new_container = Container(
            container_id=f"C{next_container_id}",
            main_company=pallet_to_place.company
        )
        # Thêm pallet vào container mới
        new_container.add_pallet(pallet_to_place)
        # Thêm container mới vào danh sách container chung
        containers.append(new_container)
        
        print(f"   [+] Đã tạo và xếp vào container MỚI {new_container.id} cho pallet {pallet_to_place.id}")
        
        # Cập nhật ID cho lần tạo tiếp theo
        next_container_id += 1
        
        # Trả về phần còn lại của danh sách chờ và ID container đã cập nhật
        print(f"   -> {len(sorted_pallets)} pallet còn lại sẽ chờ vòng lặp lớn tiếp theo.")
        return sorted_pallets, next_container_id