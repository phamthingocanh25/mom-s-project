import React from 'react';

// CSS có thể giữ nguyên hoặc nhúng vào đây như trước
const Styles = () => (
  <style>{`
    /* Dán toàn bộ nội dung file ResultsDisplay.css của bạn vào đây */
    .results-container { background-color: #fff; border-radius: 8px; padding: 2rem; box-shadow: 0 4px 8px rgba(0, 0, 0, 0.05); }
    .results-title { text-align: center; font-size: 1.8rem; margin-bottom: 0.5rem; color: var(--text-color, #172b4d); }
    .results-summary { text-align: center; font-size: 1.1rem; color: #6b778c; margin-bottom: 2rem; }
    .containers-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(380px, 1fr)); gap: 1.5rem; }
    .container-card { border: 1px solid var(--border-color, #dfe1e6); border-radius: 8px; overflow: hidden; display: flex; flex-direction: column; }
    .container-header { background-color: var(--primary-color, #0052cc); color: white; padding: 0.8rem 1rem; }
    .container-header h3 { margin: 0; font-size: 1.2rem; }
    .container-stats { padding: 1rem; background-color: #fafbfc; border-bottom: 1px solid var(--border-color, #dfe1e6); }
    .stat-item { display: flex; justify-content: space-between; align-items: center; font-size: 0.9rem; }
    .stat-item:not(:last-child) { margin-bottom: 0.5rem; }
    .stat-item span { color: #42526e; }
    .container-content { padding: 1rem; flex-grow: 1; }
    .container-content h4 { margin-top: 0; margin-bottom: 1rem; font-size: 1rem; color: var(--text-color, #172b4d); }
    .content-item:not(:last-child) { margin-bottom: 1rem; }
    .pallet-info { font-size: 0.9rem; padding: 0.75rem; border-radius: 4px; line-height: 1.5; }
    .pallet-info strong { display: block; margin-bottom: 0.25rem; }
    .pallet-header { font-weight: 700; display: block; margin-bottom: 0.25rem; }
    .pallet-details { display: flex; justify-content: space-between; align-items: center; width: 100%; }
    .single-pallet { background-color: #e6fcff; border-left: 4px solid #00c7e6; }
    .combined-pallet { background-color: #e9e7fd; border-left: 4px solid #6554c0; }
    .combined-pallet ul { list-style-type: none; padding-left: 1rem; margin: 0.5rem 0 0 0; border-top: 1px dashed #c1c7d0; padding-top: 0.5rem; }
    .combined-pallet li { color: #42526e; margin-bottom: 0.25rem; }
    .cross-ship-label { font-size: 0.8rem; font-weight: bold; color: #ff991f; margin-left: 8px; }
    .split-label { font-size: 0.8rem; font-style: italic; color: #de350b; margin-left: 8px; }
  `}</style>
);

const ResultsDisplay = ({ results }) => {
  if (!results || !Array.isArray(results)) {
    return null; // Hoặc một trạng thái loading/chờ
  }

  if (results.length === 0) {
    return (
      <div className="results-container">
        <Styles />
        <h2 className="results-title">Không có kết quả</h2>
        <p className="results-summary">Không tìm thấy giải pháp tối ưu với dữ liệu được cung cấp.</p>
      </div>
    );
  }

  const formatNumber = (num) => {
    if (typeof num !== 'number' || isNaN(num)) return 'N/A';
    return num.toLocaleString('de-DE', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  };

  return (
    <div className="results-container">
      <Styles />
      <h2 className="results-title">Kết quả tối ưu hóa</h2>
      <p className="results-summary">
        Tổng số container cần sử dụng: <strong>{results.length}</strong>
      </p>

      <div className="containers-grid">
        {results.map((container) => (
          <div key={container.id} className="container-card">
            <div className="container-header">
              <h3>{container.id} (Cty chính: {container.main_company})</h3>
            </div>
            <div className="container-stats">
              <div className="stat-item">
                <span>Tổng số lượng:</span>
                <strong>{formatNumber(container.total_quantity)} / 20,00 Pallets</strong>
              </div>
              <div className="stat-item">
                <span>Tổng khối lượng:</span>
                <strong>{formatNumber(container.total_weight)} / 24.000,00 kg</strong>
              </div>
            </div>
            <div className="container-content">
              <h4>Chi tiết Pallet:</h4>
              {container.contents.map((content, index) => (
                <div key={index} className="content-item">
                  {content.type === 'SinglePallet' && (
                    <div className="pallet-info single-pallet">
                      <div className="pallet-details">
                         <div>
                            <strong className="pallet-header">[{content.product_code}] {content.product_name}</strong>
                            <span>Cty: {content.company}</span>
                         </div>
                         <div>
                            <strong>{formatNumber(content.quantity)} plls</strong>
                            <span>({formatNumber(content.total_weight)} kg)</span>
                         </div>
                      </div>
                      {content.is_cross_ship && <span className="cross-ship-label">[HÀNG GHÉP]</span>}
                      {content.is_split && <span className="split-label">(chia nhỏ)</span>}
                    </div>
                  )}
                  {content.type === 'CombinedPallet' && (
                     <div className="pallet-info combined-pallet">
                       <strong className="pallet-header">
                         Hàng gộp (Tổng: {formatNumber(content.quantity)} plls, {formatNumber(content.total_weight)} kg)
                         {content.is_cross_ship && <span className="cross-ship-label">[HÀNG GHÉP]</span>}
                       </strong>
                       <ul>
                         {content.items.map((item, subIndex) => (
                           <li key={subIndex}>
                             - <strong>[{item.product_code}]</strong> {item.product_name}: {formatNumber(item.quantity)} plls ({formatNumber(item.total_weight)} kg)
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