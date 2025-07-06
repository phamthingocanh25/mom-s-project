import React, { useState } from 'react';
import axios from 'axios';


//const API_URL = process.env.REACT_APP_API_URL || "https://final-5-7.onrender.com";
const API_URL = "http://127.0.0.1:5001"
// --- BIỂU TƯỢỢNG (ICONS) ---
// Các component SVG cho biểu tượng để giao diện thêm trực quan.
const IconBox = () => <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"></path><polyline points="3.27 6.96 12 12.01 20.73 6.96"></polyline><line x1="12" y1="22.08" x2="12" y2="12"></line></svg>;
const IconCollection = () => <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><rect x="3" y="3" width="7" height="7"></rect><rect x="14" y="3" width="7" height="7"></rect><rect x="14" y="14" width="7" height="7"></rect><rect x="3" y="14" width="7" height="7"></rect></svg>;
const IconSplit = () => <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><path d="M12 2v5"/><path d="M12 17v5"/><path d="M5.4 7.8 2 12l3.4 4.2"/><path d="M18.6 7.8 22 12l-3.4 4.2"/><line x1="2" y1="12" x2="22" y2="12"/></svg>;
const IconTruck = () => <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><path d="M10 17h4V5H2v12h3"/><path d="M20 17h2v-3.34a4 4 0 0 0-1.17-2.83L19 9h-5"/><path d="M14 17H9"/><circle cx="6.5" cy="17.5" r="2.5"/><circle cx="16.5" cy="17.5" r="2.5"/></svg>;


// --- STYLES COMPONENT (ĐÃ CẬP NHẬT) ---
const GlobalStyles = () => (
  <style>{`
    @import url('https://fonts.googleapis.com/css2?family=Be+Vietnam+Pro:wght@400;500;700&display=swap');
    :root {
      --primary-color: #0052cc; --secondary-color: #f4f5f7; --text-color: #172b4d;
      --background-color: #f4f5f7; --card-background: #ffffff; --border-color: #dfe1e6;
      --error-color: #de350b; --success-color: #00875a; --font-family: 'Be Vietnam Pro', sans-serif;
      --single-pallet-color: #00b8d9; --single-pallet-bg: #e6fcff;
      --combined-pallet-color: #6554c0; --combined-pallet-bg: #e9e7fd;
      --split-tag-color: #bf2600; --split-tag-bg: #ffebe6;
      --cross-ship-tag-color: #ff8b00; --cross-ship-tag-bg: #fff4e6;
    }
    body {
      margin: 0; font-family: var(--font-family); background-color: var(--background-color);
      color: var(--text-color); -webkit-font-smoothing: antialiased; -moz-osx-font-smoothing: grayscale;
    }
    .App { display: flex; flex-direction: column; align-items: center; padding: 2rem; min-height: 100vh; }
    .container { width: 100%; max-width: 900px; }
    .card {
      background-color: var(--card-background); border-radius: 8px; padding: 2rem 2.5rem;
      box-shadow: 0 4px 8px rgba(0, 0, 0, 0.1); border: 1px solid var(--border-color);
      margin-bottom: 2rem; transition: box-shadow 0.3s ease;
    }
    .card:hover { box-shadow: 0 8px 16px rgba(0, 0, 0, 0.1); }
    .title { font-size: 2rem; font-weight: 700; margin: 0 0 0.5rem 0; text-align: center; }
    .subtitle { font-size: 1rem; color: #6b778c; margin: 0 0 2rem 0; text-align: center; }
    .input-group { margin-bottom: 1.5rem; text-align: center; }
    .file-input { width: 0.1px; height: 0.1px; opacity: 0; overflow: hidden; position: absolute; z-index: -1; }
    .file-label {
      display: inline-block; padding: 12px 20px; font-size: 1rem; font-weight: 500; color: var(--primary-color);
      background-color: var(--secondary-color); border: 2px dashed var(--border-color); border-radius: 6px;
      cursor: pointer; transition: all 0.3s ease; width: 80%;
    }
    .file-label:hover { background-color: #e9ecef; border-color: var(--primary-color); }
    .form-group { margin-bottom: 1rem; }
    .form-group label { display: block; font-weight: 500; margin-bottom: 0.5rem; }
    .form-group select { width: 100%; padding: 0.75rem; border: 1px solid var(--border-color); border-radius: 4px; font-size: 1rem; box-sizing: border-box; }
    button {
      background-color: var(--primary-color); color: white; border: none; padding: 0.8rem 1.5rem;
      font-size: 1rem; font-weight: 500; font-family: var(--font-family); border-radius: 6px;
      cursor: pointer; transition: background-color 0.2s ease, transform 0.1s ease; width: 100%;
    }
    button:hover:not(:disabled) { background-color: #0040a8; transform: translateY(-1px); }
    button:disabled { background-color: #a5adba; cursor: not-allowed; }
    .button-group { display: flex; gap: 1rem; margin-top: 2rem; }
    button.secondary { background-color: var(--secondary-color); color: var(--text-color); border: 1px solid var(--border-color); }
    button.secondary:hover:not(:disabled) { background-color: #dfe1e6; }
    .back-button { background: none; border: none; color: var(--primary-color); cursor: pointer; font-size: 1rem; padding: 0.5rem 0; margin-bottom: 1rem; width: auto; text-align: left; }
    .error-message { color: var(--error-color); background-color: #ffebe6; border: 1px solid var(--error-color); border-radius: 6px; padding: 1rem; text-align: center; margin-top: 1rem; }
    
    /* --- Styles for Results (NEW) --- */
    .results-container { background-color: var(--card-background); border-radius: 8px; padding: 2rem; box-shadow: 0 4px 8px rgba(0,0,0,0.05); }
    .results-title { text-align: center; font-size: 1.8rem; margin-bottom: 0.5rem; color: var(--text-color); }
    .results-summary { text-align: center; font-size: 1.1rem; color: #6b778c; margin-bottom: 2rem; }
    .containers-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(400px, 1fr)); gap: 1.5rem; }
    .container-card { border: 1px solid var(--border-color); border-radius: 8px; overflow: hidden; display: flex; flex-direction: column; background-color: #fafbfc; }
    .container-header { background-color: var(--primary-color); color: white; padding: 0.8rem 1.2rem; }
    .container-header h3 { margin: 0; font-size: 1.2rem; }
    .container-stats { padding: 1rem 1.2rem; border-bottom: 1px solid var(--border-color); background-color: #fff; display: flex; flex-direction: column; gap: 0.5rem;}
    .stat-item { display: flex; justify-content: space-between; align-items: center; font-size: 0.95rem; }
    .stat-item span { color: #42526e; }
    .container-content { padding: 1rem 1.2rem; flex-grow: 1; display: flex; flex-direction: column; gap: 1rem; }
    .container-content > h4 { margin-top: 0; margin-bottom: 0; font-size: 1rem; color: var(--text-color); }
    
    /* Pallet Card Styles */
    .pallet-card { border-radius: 6px; overflow: hidden; border: 1px solid var(--border-color); }
    .pallet-card-header { display: flex; align-items: center; gap: 0.75rem; padding: 0.75rem 1rem; font-weight: 700; }
    .pallet-card-body { padding: 1rem; font-size: 0.9rem; }
    .pallet-card-footer { padding: 0.5rem 1rem; display: flex; gap: 0.75rem; border-top: 1px solid var(--border-color); }

    /* Single Pallet */
    .pallet-card--single .pallet-card-header { background-color: var(--single-pallet-bg); color: var(--single-pallet-color); }
    .pallet-card--single .pallet-card-body { background-color: #fff; }
    .pallet-card--single .pallet-details { display: flex; justify-content: space-between; align-items: flex-start; }
    .pallet-card--single .product-info { font-weight: 500; }
    .pallet-card--single .product-company { color: #6b778c; font-size: 0.85rem; }
    .pallet-card--single .quantity-info { text-align: right; }
    .pallet-card--single .quantity-info strong { font-size: 1.1em; color: var(--text-color); }

    /* Combined Pallet */
    .pallet-card--combined .pallet-card-header { background-color: var(--combined-pallet-bg); color: var(--combined-pallet-color); }
    .pallet-card--combined .pallet-card-body { background-color: #fff; }
    .combined-items-list { list-style: none; padding: 0; margin: 0; display: flex; flex-direction: column; gap: 0.75rem; }
    .combined-item { display: flex; justify-content: space-between; padding-bottom: 0.5rem; border-bottom: 1px dashed #dfe1e6; }
    .combined-item:last-child { border-bottom: none; }
    .combined-item .product-name { font-weight: 500; }

    /* Tags */
    .pallet-tag { display: inline-flex; align-items: center; gap: 0.4rem; font-size: 0.8rem; font-weight: 700; padding: 0.2rem 0.6rem; border-radius: 4px; }
    .pallet-tag--split { background-color: var(--split-tag-bg); color: var(--split-tag-color); }
    .pallet-tag--cross-ship { background-color: var(--cross-ship-tag-bg); color: var(--cross-ship-tag-color); }
  `}</style>
);


// --- RESULTS DISPLAY COMPONENT (THIẾT KẾ LẠI) ---
const ResultsDisplay = ({ results, sheetName }) => {
  if (!results || !Array.isArray(results)) {
    return <p>Chưa có dữ liệu hoặc dữ liệu không hợp lệ.</p>;
  }

  if (results.length === 0) {
    return (
      <div className="results-container">
        <h2 className="results-title">Không có kết quả</h2>
        <p className="results-summary">Không tìm thấy giải pháp tối ưu cho sheet '{sheetName}'.</p>
      </div>
    );
  }

  const formatNumber = (num) => {
    if (typeof num !== 'number' || isNaN(num)) return 'N/A';
    return num.toLocaleString('de-DE', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  };
  
  // Component nội bộ để render chi tiết Pallet
  const PalletItem = ({ content }) => {
    if (content.type === 'SinglePallet') {
      return (
        <div className="pallet-card pallet-card--single">
          <div className="pallet-card-header">
            <IconBox />
            <span>Pallet Đơn: {content.product_code}</span>
          </div>
          <div className="pallet-card-body">
            <div className="pallet-details">
              <div>
                <div className="product-info">{content.product_name}</div>
                <div className="product-company">Công ty: {content.company}</div>
              </div>
              <div className="quantity-info">
                <strong>{formatNumber(content.quantity)} plts</strong>
                <div>{formatNumber(content.total_weight)} kg</div>
              </div>
            </div>
          </div>
          {(content.is_split || content.is_cross_ship) && (
            <div className="pallet-card-footer">
              {content.is_split && <span className="pallet-tag pallet-tag--split"><IconSplit /> Bị chia nhỏ</span>}
              {content.is_cross_ship && <span className="pallet-tag pallet-tag--cross-ship"><IconTruck /> Hàng ghép</span>}
            </div>
          )}
        </div>
      );
    }
  
    if (content.type === 'CombinedPallet') {
      return (
        <div className="pallet-card pallet-card--combined">
          <div className="pallet-card-header">
            <IconCollection />
            <span>Pallet Gộp ({formatNumber(content.quantity)} plts)</span>
          </div>
          <div className="pallet-card-body">
            <ul className="combined-items-list">
              {content.items.map((item, index) => (
                <li key={index} className="combined-item">
                  <div>
                    <div className="product-name">[{item.product_code}] {item.product_name}</div>
                    <div className="product-company">Cty: {item.company}</div>
                  </div>
                  <div className="quantity-info" style={{textAlign: 'right'}}>
                     <strong>{formatNumber(item.quantity)} plts</strong>
                     <div>{formatNumber(item.total_weight)} kg</div>
                  </div>
                </li>
              ))}
            </ul>
          </div>
           {content.is_cross_ship && (
            <div className="pallet-card-footer">
              <span className="pallet-tag pallet-tag--cross-ship"><IconTruck /> Hàng ghép</span>
            </div>
          )}
        </div>
      );
    }
  
    return null; // Không render gì nếu type không xác định
  };


  return (
    <div className="results-container">
      <h2 className="results-title">Kết quả tối ưu hóa cho Sheet: {sheetName}</h2>
      <p className="results-summary">Tổng số container cần sử dụng: <strong>{results.length}</strong></p>
      <div className="containers-grid">
        {results.map((container) => (
          <div key={container.id} className="container-card">
            <div className="container-header">
              <h3>{container.id} </h3>
            </div>
            <div className="container-stats">
              <div className="stat-item">
                <span>Tổng số lượng:</span>
                <strong>{formatNumber(container.total_quantity)} / 20.00 Pallets</strong>
              </div>
              <div className="stat-item">
                <span>Tổng khối lượng:</span>
                <strong>{formatNumber(container.total_weight)} / {formatNumber(24000)} kg</strong>
              </div>
            </div>
            <div className="container-content">
              <h4>Chi tiết Pallet:</h4>
              {/* Giả định container.contents có cấu trúc dữ liệu mới */}
              {Array.isArray(container.contents) ? (
                container.contents.map((content, index) => <PalletItem key={index} content={content} />)
              ) : (
                <p>Dữ liệu chi tiết pallet không có sẵn.</p>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};


// --- APP COMPONENT CHÍNH ---
// Component này gần như giữ nguyên, chỉ thay đổi giả định về dữ liệu trả về từ API
function App() {
  const [file, setFile] = useState(null);
  const [uploadedFileInfo, setUploadedFileInfo] = useState(null);
  const [config, setConfig] = useState({ sheetName: '' });
  const [results, setResults] = useState(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState('');
  const [step, setStep] = useState('upload'); // 'upload', 'configure', 'results'

  const handleFileChange = (e) => {
    setFile(e.target.files[0]);
    setError('');
    setResults(null);
    setUploadedFileInfo(null);
  };

  const handleUpload = async () => {
    if (!file) {
      setError('Vui lòng chọn một file Excel để tải lên.');
      return;
    }
    setIsLoading(true);
    setError('');
    const formData = new FormData();
    formData.append('file', file);
    try {
      const response = await axios.post(`${API_URL}/api/upload`, formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
        timeout: 300000
      });
      if (response.data.success) {
        setUploadedFileInfo(response.data);
        const sheets = response.data.sheets || [];
        setConfig({ sheetName: sheets[0] || '' });
        setStep('configure');
      } else {
        setError(response.data.error || 'Lỗi: Không thể xử lý file tải lên.');
      }
    } catch (err) {
      const errorMsg = err.response?.data?.error || (err.code === 'ECONNABORTED' ? 'Thời gian tải lên quá lâu.' : 'Lỗi kết nối tới server.');
      setError(errorMsg);
    } finally {
      setIsLoading(false);
    }
  };

  const handleConfigChange = (e) => {
    setConfig({ sheetName: e.target.value });
  };
  
  const handleSubmit = async () => {
    if (!config.sheetName) {
      setError('Vui lòng chọn một sheet để xử lý.');
      return;
    }
    setIsLoading(true);
    setError('');
    setResults(null);
    try {
      const payload = {
        filepath: uploadedFileInfo.filepath,
        sheetName: config.sheetName
      };
      const response = await axios.post(`${API_URL}/api/process`, payload, {
        timeout: 300000 
      });

      // === PHẦN SỬA LỖI NHỎ NHƯNG QUAN TRỌNG ===
      if (response.data && response.data.results) {
        // Thay vì lưu toàn bộ response, chỉ lưu những gì cần thiết
        setResults({
          optimizedContainers: response.data.results, 
          originalFilepath: uploadedFileInfo.filepath, // Lấy từ state đã có
          sheetName: config.sheetName // Lấy từ state đã có
        });
        setStep('results');
      } else if (response.data.error) {
        setError(response.data.error);
        setStep('configure'); 
      } else {
        setError('Lỗi: Phản hồi không hợp lệ từ server.');
      }

    } catch (err) {
      const errorMsg = err.response?.data?.error || (err.code === 'ECONNABORTED' ? 'Thời gian xử lý quá lâu.' : 'Lỗi kết nối tới server.');
      setError(errorMsg);
    } finally {
      setIsLoading(false);
    }
  };
  
  // *** HÀM MỚI: Xử lý xuất Packing List ***
  const handleExportPackingList = async () => {
    console.log("--- [FRONTEND] Bắt đầu quá trình xuất Packing List ---");
    setIsLoading(true);
    setError('');

    if (!results || !results.optimizedContainers) {
        const errorMsg = "Lỗi nghiêm trọng: Dữ liệu 'results' không tồn tại để xuất file.";
        console.error(`[FRONTEND] ${errorMsg}`);
        setError(errorMsg);
        setIsLoading(false);
        return;
    }

    try {
        const payload = {
            optimized_results: results.optimizedContainers,
            original_filepath: results.originalFilepath,
            sheet_name: results.sheetName
        };
        console.log("[FRONTEND] Dữ liệu gửi lên server (payload):", JSON.stringify(payload, null, 2));

        const response = await axios.post(`${API_URL}/api/generate_packing_list`, payload, {
            responseType: 'blob', // Rất quan trọng!
            timeout: 300000
        });

        console.log("[FRONTEND] Đã nhận phản hồi thành công từ server. Status:", response.status);
        console.log("[FRONTEND] Dữ liệu nhận về (blob):", response.data);

        // Kiểm tra lại dữ liệu blob
        if (!response.data || response.data.size === 0) {
            throw new Error("Server đã phản hồi nhưng file nhận về bị rỗng.");
        }

        // Tạo link và tải file
        const url = window.URL.createObjectURL(response.data);
        const link = document.createElement('a');
        link.href = url;
        const fileName = `PackingList_${results.sheetName || 'export'}.xlsx`;
        link.setAttribute('download', fileName);
        
        console.log(`[FRONTEND] Chuẩn bị tải file: ${fileName}`);
        document.body.appendChild(link);
        link.click();
        
        console.log("[FRONTEND] Đã kích hoạt tải xuống. Tiến hành dọn dẹp...");
        link.parentNode.removeChild(link);
        window.URL.revokeObjectURL(url);
        
        console.log("--- [FRONTEND] Quá trình hoàn tất thành công! ---");

    } catch (err) {
        console.error("--- [FRONTEND] !!! ĐÃ XẢY RA LỖI !!! ---");
        console.error("[FRONTEND] Đối tượng lỗi chi tiết:", err);

        let errorMsg = 'Lỗi không xác định khi tạo packing list.';

        // Xử lý lỗi khi server trả về mã lỗi (ví dụ: 400, 500)
        if (err.response) {
            console.error("[FRONTEND] Server đã phản hồi với mã lỗi:", err.response.status);
            console.error("[FRONTEND] Dữ liệu lỗi (có thể là blob):", err.response.data);
            
            // Vì responseType là 'blob', nên dữ liệu lỗi cũng là blob.
            // Chúng ta cần đọc blob này dưới dạng text để xem thông báo lỗi JSON từ server.
            if (err.response.data instanceof Blob) {
                try {
                    const errorJsonText = await err.response.data.text();
                    console.error("[FRONTEND] Thông báo lỗi từ server (dạng text):", errorJsonText);
                    const errorObj = JSON.parse(errorJsonText);
                    errorMsg = errorObj.error || 'Không thể phân tích lỗi JSON từ server.';
                } catch (parseError) {
                    console.error("[FRONTEND] Không thể chuyển đổi blob lỗi sang JSON.", parseError);
                    errorMsg = `Lỗi từ server (mã ${err.response.status}), không thể đọc chi tiết.`;
                }
            } else {
                 errorMsg = err.response.data.error || JSON.stringify(err.response.data);
            }

        } else if (err.request) {
            // Lỗi không nhận được phản hồi từ server
            console.error("[FRONTEND] Không nhận được phản hồi từ server. Kiểm tra kết nối mạng và địa chỉ API.");
            errorMsg = 'Không thể kết nối tới server. Vui lòng kiểm tra lại backend và CORS.';
        } else {
            // Lỗi xảy ra ở phía client trước khi gửi request
            console.error("[FRONTEND] Lỗi không xác định ở client:", err.message);
            errorMsg = err.message;
        }
        
        setError(errorMsg);
        console.error(`[FRONTEND] Hiển thị lỗi cho người dùng: ${errorMsg}`);
        console.error("-----------------------------------------");

    } finally {
        setIsLoading(false);
    }
};

  const goBack = (targetStep) => {
    setStep(targetStep);
    setError('');
    setResults(null);
    if (targetStep === 'upload') {
        setFile(null);
        setUploadedFileInfo(null);
    }
  };

  // Các hàm render step không thay đổi
  const renderUploadStep = () => (
    <div className="card">
      <h1 className="title">Tối ưu hóa xếp dỡ Container</h1>
      <p className="subtitle">Tải lên file Excel của bạn để bắt đầu</p>
      <div className="input-group">
        <input type="file" id="file-upload" className="file-input" onChange={handleFileChange} accept=".xlsx, .xls" />
        <label htmlFor="file-upload" className="file-label">{file ? file.name : 'Chọn file...'}</label>
        {file && <div style={{ marginTop: '10px', fontSize: '0.9rem' }}>Kích thước: {(file.size / (1024 * 1024)).toFixed(2)} MB</div>}
      </div>
      <button onClick={handleUpload} disabled={isLoading || !file}>{isLoading ? 'Đang tải lên...' : 'Tải lên & Tiếp tục'}</button>
      {error && <p className="error-message">{error}</p>}
    </div>
  );

  const renderConfigureStep = () => (
    <div className="card">
      <h2 className="title">Cấu hình dữ liệu</h2>
      <p className="subtitle">Chọn sheet chứa dữ liệu bạn muốn tối ưu hoá.</p>
      <div className="form-group">
        <label htmlFor="sheetName">Chọn Sheet (Subtab)</label>
        <select id="sheetName" name="sheetName" value={config.sheetName} onChange={handleConfigChange}>
          {uploadedFileInfo && Array.isArray(uploadedFileInfo.sheets) && uploadedFileInfo.sheets.map(sheet => <option key={sheet} value={sheet}>{sheet}</option>)}
        </select>
      </div>
      <div className="button-group">
        <button onClick={() => goBack('upload')} className="secondary" disabled={isLoading}>Quay lại</button>
        <button onClick={handleSubmit} disabled={isLoading || !config.sheetName}>{isLoading ? 'Đang tính toán...' : 'Tối ưu hóa'}</button>
      </div>
      {error && <p className="error-message">{error}</p>}
    </div>
  );

  const renderResultsStep = () => (
    <div className="container"> 
      <div className="button-group" style={{ justifyContent: 'space-between', marginBottom: '1rem' }}>
        <button onClick={() => goBack('configure')} className="secondary" style={{width: 'auto'}}>← Quay lại cấu hình</button>
        {/* NÚT MỚI ĐƯỢC THÊM VÀO ĐÂY */}
        <button onClick={handleExportPackingList} disabled={isLoading} style={{width: 'auto'}}>
          {isLoading ? 'Đang xử lý...' : 'Xuất Packing List'}
        </button>
      </div>
      <ResultsDisplay results={results.optimizedContainers} sheetName={config.sheetName} />
    </div>
  );
  
  return (
    <div className="App">
      <GlobalStyles />
      <main className="container">
        {step === 'upload' && renderUploadStep()}
        {step === 'configure' && uploadedFileInfo && renderConfigureStep()}
        {step === 'results' && results && renderResultsStep()}
      </main>
    </div>
  );
}

export default App;