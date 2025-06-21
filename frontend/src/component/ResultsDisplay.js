import React from 'react';
import './ResultsDisplay.css';

const ResultsDisplay = ({ data, sheetName }) => {
  if (!data || !data.results) {
    if (data && data.error) {
      return (
        <div className="results-container error">
          <h2>Đã xảy ra lỗi</h2>
          <p><strong>Chi tiết:</strong> {data.error}</p>
        </div>
      );
    }
    return <p>Chưa có dữ liệu để hiển thị. Vui lòng tải file và chọn sheet.</p>;
  }

  const { results } = data;

  return (
    <div className="results-container">
      <h2>Kết quả tối ưu hóa cho Sheet: {sheetName}</h2>
      <h3>Tổng số container cần sử dụng: {results.length}</h3>
      {results.map((container) => (
        <div key={container.id} className="container-card">
          {/* Thay đổi ở đây: Hiển thị công ty chính của container */}
          <h4>{container.id} (Ưu tiên cho Công ty {container.main_company})</h4>
          <p>
            <strong>Tổng số lượng: </strong>
            {container.total_quantity.toFixed(2)} / {20.00} Pallets
          </p>
          <p>
            <strong>Tổng khối lượng: </strong>
            {container.total_weight.toLocaleString('de-DE', { maximumFractionDigits: 2 })} / {24000..toLocaleString('de-DE')} kg
          </p>
          <h5>Chi tiết Pallet:</h5>
          <ul>
            {container.pallets.map((pallet, index) => (
              // Thêm class 'cross-shipped' cho hàng ghép để có thể định dạng màu khác
              <li 
                key={index} 
                className={pallet.includes('[HÀNG GHÉP]') ? 'cross-shipped' : ''}
              >
                {pallet}
              </li>
            ))}
          </ul>
        </div>
      ))}
    </div>
  );
};

export default ResultsDisplay;