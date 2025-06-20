import React from 'react';

// Để giải quyết lỗi không tìm thấy tệp, CSS được nhúng trực tiếp vào đây.
const Styles = () => (
  <style>{`
    .results-container {
      background-color: #fff;
      border-radius: 8px;
      padding: 2rem;
      box-shadow: 0 4px 8px rgba(0, 0, 0, 0.05);
    }

    .results-title {
      text-align: center;
      font-size: 1.8rem;
      margin-bottom: 0.5rem;
      color: var(--text-color, #172b4d);
    }

    .results-summary {
      text-align: center;
      font-size: 1.1rem;
      color: #6b778c;
      margin-bottom: 2rem;
    }

    .containers-grid {
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(350px, 1fr));
      gap: 1.5rem;
    }

    .container-card {
      border: 1px solid var(--border-color, #dfe1e6);
      border-radius: 8px;
      overflow: hidden;
      display: flex;
      flex-direction: column;
    }

    .container-header {
      background-color: var(--primary-color, #0052cc);
      color: white;
      padding: 0.8rem 1rem;
    }

    .container-header h3 {
      margin: 0;
      font-size: 1.2rem;
    }

    .container-stats {
      padding: 1rem;
      background-color: #fafbfc;
      border-bottom: 1px solid var(--border-color, #dfe1e6);
    }

    .stat-item {
      display: flex;
      justify-content: space-between;
      align-items: center;
      font-size: 0.9rem;
    }

    .stat-item:not(:last-child) {
      margin-bottom: 0.5rem;
    }

    .stat-item span {
      color: #42526e;
    }

    .container-content {
      padding: 1rem;
      flex-grow: 1;
    }

    .container-content h4 {
      margin-top: 0;
      margin-bottom: 1rem;
      font-size: 1rem;
      color: var(--text-color, #172b4d);
    }

    .content-item:not(:last-child) {
      margin-bottom: 1rem;
    }

    .pallet-info {
      font-size: 0.9rem;
      padding: 0.75rem;
      border-radius: 4px;
    }

    .pallet-info strong {
      display: block;
      margin-bottom: 0.25rem;
    }

    .single-pallet {
      background-color: #e6fcff;
      border-left: 4px solid #00c7e6;
      display: flex;
      justify-content: space-between;
      align-items: center;
    }

    .combined-pallet {
      background-color: #e9e7fd;
      border-left: 4px solid #6554c0;
    }

    .combined-pallet ul {
      list-style-type: none;
      padding-left: 1rem;
      margin: 0.5rem 0 0 0;
    }

    .combined-pallet li {
      color: #42526e;
    }
  `}</style>
);


const ResultsDisplay = ({ results }) => {

  // FIX: Thêm một bộ kiểm tra để xử lý trường hợp `results` không được định nghĩa hoặc không phải là một mảng.
  // Điều này ngăn ngừa lỗi "Cannot read properties of undefined (reading 'length')".
  if (!results || !Array.isArray(results)) {
    // Hiển thị một trạng thái chờ hoặc thông báo lỗi thay vì làm sập ứng dụng.
    return (
        <div className="results-container">
          <Styles />
          <h2 className="results-title">Đang chờ dữ liệu...</h2>
          <p className="results-summary">Vui lòng hoàn tất các bước trước để xem kết quả.</p>
        </div>
      );
  }
  
  // Xử lý trường hợp có kết quả nhưng là một mảng rỗng.
  if (results.length === 0) {
      return (
        <div className="results-container">
          <Styles />
          <h2 className="results-title">Không có kết quả</h2>
          <p className="results-summary">Không tìm thấy giải pháp tối ưu nào với dữ liệu được cung cấp.</p>
        </div>
      );
  }

  const formatNumber = (num) => {
    // Thêm kiểm tra để đảm bảo `num` là một số trước khi định dạng.
    if (typeof num !== 'number') return 'N/A';
    return Number(num).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  }

  return (
    <div className="results-container">
      <Styles />
      <h2 className="results-title">Kết quả tối ưu hóa</h2>
      <p className="results-summary">
        Tổng số container cần sử dụng: <strong>{results.length}</strong>
      </p>

      <div className="containers-grid">
        {results.map((container) => (
          <div key={container.container_number} className="container-card">
            <div className="container-header">
              <h3>Container #{container.container_number}</h3>
            </div>
            <div className="container-stats">
              <div className="stat-item">
                <span>Tổng số lượng:</span>
                <strong>{formatNumber(container.total_boxes)} / 20.00 Pallets</strong>
              </div>
              <div className="stat-item">
                <span>Tổng khối lượng:</span>
                <strong>{formatNumber(container.total_weight)} / 24,000.00 kg</strong>
              </div>
            </div>
            <div className="container-content">
              <h4>Chi tiết Pallet:</h4>
              {container.contents.map((content, index) => (
                <div key={index} className="content-item">
                  {content.type === 'SinglePallet' && (
                    <div className="pallet-info single-pallet">
                      <strong>Pallet Đơn:</strong>
                      <span>{formatNumber(content.items[0]?.number_of_boxes)} plls</span>
                      <span>({formatNumber(content.items[0]?.total_item_weight)} kg)</span>
                    </div>
                  )}
                  {content.type === 'CombinedPallet' && (
                     <div className="pallet-info combined-pallet">
                       <strong>Pallet Kết hợp (Tổng: {formatNumber(content.total_boxes_count)} plls, {formatNumber(content.total_weight)} kg):</strong>
                       <ul>
                         {content.items.map((item, subIndex) => (
                           <li key={subIndex}>
                             - {formatNumber(item?.number_of_boxes)} plls ({formatNumber(item?.total_item_weight)} kg)
                           </li>
                         ))}
                       </ul>
                     </div>
                  )}
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};

export default ResultsDisplay;
