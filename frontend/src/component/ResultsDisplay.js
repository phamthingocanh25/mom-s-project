import React from 'react';
import './ResultsDisplay.css';

const ResultsDisplay = ({ results, maxPallets, maxWeight }) => {
    if (!results) {
        return <p>Vui lòng tải lên một tệp Excel và nhấn "Tối ưu hóa" để xem kết quả.</p>;
    }

    if (!results.containers || results.containers.length === 0) {
        return <p>Không có container nào được tạo. Vui lòng kiểm tra lại dữ liệu đầu vào.</p>;
    }

    return (
        <div className="results-container">
            <h3>Kết quả tối ưu hóa cho Sheet: {results.sheet_name}</h3>
            <p className="summary">Tổng số container cần sử dụng: <strong>{results.total_containers}</strong></p>
            <div className="containers-grid">
                {results.containers.map((container, index) => (
                    <div key={index} className="container-card">
                        <div className="container-header">
                            <h3>{container.id.replace('_', ' ')}</h3>
                            <span className="main-company-tag">Cty chính: {container.main_company}</span>
                        </div>
                        <div className="container-summary">
                            <p>Tổng số lượng: <br/><span>{container.total_quantity}</span> / {parseFloat(maxPallets).toFixed(2)} Pallets</p>
                            <p>Tổng khối lượng: <br/><span>{container.total_weight}</span> / {parseFloat(maxWeight).toLocaleString('de-DE')} kg</p>
                        </div>
                        <div className="pallet-details">
                            <h4>Chi tiết Pallet:</h4>
                            {container.pallets.map((pallet, pIndex) => (
                                <div key={pIndex} className="pallet-item">
                                    {/* *** LOGIC HIỂN THỊ MỚI *** */}
                                    {pallet.is_combined ? (
                                        <div className="combined-pallet-group">
                                            <p className="combined-title">
                                                <strong>{pallet.product_name} ({pallet.quantity} plts)</strong>
                                            </p>
                                            <div className="constituent-pallets">
                                                {pallet.original_pallets.map((orig_pallet, oIndex) => (
                                                    <div key={oIndex} className="constituent-pallet">
                                                        <p>
                                                            <strong>[{orig_pallet.product_code}]</strong> {orig_pallet.product_name}
                                                        </p>
                                                        <p className="constituent-details">
                                                            Cty: {orig_pallet.company} | {orig_pallet.quantity} plts | {orig_pallet.total_weight} kg
                                                        </p>
                                                    </div>
                                                ))}
                                            </div>
                                        </div>
                                    ) : (
                                        <div className="single-pallet-group">
                                            <p><strong>Pallet Đơn: {pallet.product_code}</strong></p>
                                            <p>{pallet.product_name}</p>
                                            <p>Công ty: {pallet.company}</p>
                                            <p>{pallet.quantity} plts</p>
                                            <p>{pallet.total_weight} kg</p>
                                        </div>
                                    )}
                                    <div className="tag-container">
                                        {pallet.is_split && <span className="tag split-tag">Bị chia nhỏ</span>}
                                        {pallet.is_cross_ship && <span className="tag cross-ship-tag">Ghép cont</span>}
                                    </div>
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