import React, { useState, useCallback, useEffect } from 'react';
import axios from 'axios';

// URL của backend API
const API_URL = 'http://localhost:5001';

// --- CSS STYLES ---
// Để giải quyết lỗi, CSS được nhúng trực tiếp vào component.
const GlobalStyles = () => (
  <style>{`
    @import url('https://fonts.googleapis.com/css2?family=Be+Vietnam+Pro:wght@400;500;700&display=swap');

    :root {
      --primary-color: #0052cc;
      --secondary-color: #f4f5f7;
      --text-color: #172b4d;
      --background-color: #f4f5f7;
      --card-background: #ffffff;
      --border-color: #dfe1e6;
      --error-color: #de350b;
      --success-color: #00875a;
      --font-family: 'Be Vietnam Pro', sans-serif;
    }

    body {
      margin: 0;
      font-family: var(--font-family);
      background-color: var(--background-color);
      color: var(--text-color);
      -webkit-font-smoothing: antialiased;
      -moz-osx-font-smoothing: grayscale;
    }

    .App {
      display: flex;
      flex-direction: column;
      align-items: center;
      padding: 2rem;
      min-height: 100vh;
    }

    .container {
      width: 100%;
      max-width: 800px;
    }

    .card {
      background-color: var(--card-background);
      border-radius: 8px;
      padding: 2rem 2.5rem;
      box-shadow: 0 4px 8px rgba(0, 0, 0, 0.1);
      border: 1px solid var(--border-color);
      margin-bottom: 2rem;
      transition: box-shadow 0.3s ease;
    }

    .card:hover {
        box-shadow: 0 8px 16px rgba(0, 0, 0, 0.1);
    }

    .title {
      font-size: 2rem;
      font-weight: 700;
      margin: 0 0 0.5rem 0;
      text-align: center;
    }

    .subtitle {
      font-size: 1rem;
      color: #6b778c;
      margin: 0 0 2rem 0;
      text-align: center;
    }

    .sub-title {
      font-size: 1.2rem;
      font-weight: 500;
      margin-top: 2rem;
      margin-bottom: 1rem;
      border-bottom: 1px solid var(--border-color);
      padding-bottom: 0.5rem;
    }

    .input-group {
        margin-bottom: 1.5rem;
        text-align: center;
    }

    .file-input {
      width: 0.1px;
      height: 0.1px;
      opacity: 0;
      overflow: hidden;
      position: absolute;
      z-index: -1;
    }

    .file-label {
      display: inline-block;
      padding: 12px 20px;
      font-size: 1rem;
      font-weight: 500;
      color: var(--primary-color);
      background-color: var(--secondary-color);
      border: 2px dashed var(--border-color);
      border-radius: 6px;
      cursor: pointer;
      transition: all 0.3s ease;
      width: 80%;
    }

    .file-label:hover {
      background-color: #e9ecef;
      border-color: var(--primary-color);
    }

    .form-group {
      margin-bottom: 1rem;
    }

    .form-group label {
      display: block;
      font-weight: 500;
      margin-bottom: 0.5rem;
    }

    .form-group select,
    .form-group input {
      width: 100%;
      padding: 0.75rem;
      border: 1px solid var(--border-color);
      border-radius: 4px;
      font-size: 1rem;
      box-sizing: border-box;
    }

    button {
      background-color: var(--primary-color);
      color: white;
      border: none;
      padding: 0.8rem 1.5rem;
      font-size: 1rem;
      font-weight: 500;
      font-family: var(--font-family);
      border-radius: 6px;
      cursor: pointer;
      transition: background-color 0.2s ease, transform 0.1s ease;
      width: 100%;
    }

    button:hover:not(:disabled) {
      background-color: #0040a8;
      transform: translateY(-1px);
    }

    button:disabled {
      background-color: #a5adba;
      cursor: not-allowed;
    }

    .button-group {
        display: flex;
        gap: 1rem;
        margin-top: 2rem;
    }

    button.secondary {
        background-color: var(--secondary-color);
        color: var(--text-color);
        border: 1px solid var(--border-color);
    }

    button.secondary:hover:not(:disabled) {
        background-color: #dfe1e6;
    }

    .back-button {
        background: none;
        border: none;
        color: var(--primary-color);
        cursor: pointer;
        font-size: 1rem;
        padding: 0.5rem 0;
        margin-bottom: 1rem;
        width: auto;
    }

    .error-message {
      color: var(--error-color);
      background-color: #ffebe6;
      border: 1px solid var(--error-color);
      border-radius: 6px;
      padding: 1rem;
      text-align: center;
      margin-top: 1rem;
    }
    
    /* ResultsDisplay.css */
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
      color: var(--text-color);
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
      border: 1px solid var(--border-color);
      border-radius: 8px;
      overflow: hidden;
      display: flex;
      flex-direction: column;
    }

    .container-header {
      background-color: var(--primary-color);
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
      border-bottom: 1px solid var(--border-color);
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
      color: var(--text-color);
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


// --- RESULTS DISPLAY COMPONENT ---
// Component này được di chuyển vào đây để giải quyết lỗi import.
const ResultsDisplay = ({ results }) => {
  const formatNumber = (num) => {
    return Number(num).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  }

  return (
    <div className="results-container">
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
                      <span>{formatNumber(content.items[0].number_of_boxes)} plls</span>
                      <span>({formatNumber(content.items[0].total_item_weight)} kg)</span>
                    </div>
                  )}
                  {content.type === 'CombinedPallet' && (
                     <div className="pallet-info combined-pallet">
                       <strong>Pallet Kết hợp (Tổng: {formatNumber(content.total_boxes_count)} plls, {formatNumber(content.total_weight)} kg):</strong>
                       <ul>
                         {content.items.map((item, subIndex) => (
                           <li key={subIndex}>
                             - {formatNumber(item.number_of_boxes)} plls ({formatNumber(item.total_item_weight)} kg)
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


// --- MAIN APP COMPONENT ---
function App() {
  // --- STATE MANAGEMENT ---
  const [file, setFile] = useState(null);
  const [uploadedFileInfo, setUploadedFileInfo] = useState(null);
  const [config, setConfig] = useState({
    sheetName: '',
    quantityCol: '',
    weightCol: '',
    filterCol: '',
    filterVal: '',
    headerRow: 3,
    fileType: 'excel'
  });
  const [results, setResults] = useState(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState('');
  const [step, setStep] = useState('upload'); // 'upload', 'configure', 'results'
  const [fileColumns, setFileColumns] = useState([]);
  const [fileProcessing, setFileProcessing] = useState(false);

  // --- HANDLERS ---
  const handleFileChange = (e) => {
    const selectedFile = e.target.files[0];
    if (selectedFile && selectedFile.size > 100 * 1024 * 1024) {
      setError('File quá lớn. Vui lòng chọn file nhỏ hơn 100MB.');
      return;
    }
    setFile(selectedFile);
    setError('');
    setResults(null);
    setUploadedFileInfo(null);
  };

  const handleUpload = async () => {
    if (!file) {
      setError('Vui lòng chọn một file Excel hoặc CSV để tải lên.');
      return;
    }
    setIsLoading(true);
    setError('');
    const formData = new FormData();
    formData.append('file', file);
    
    try {
      const response = await axios.post(`${API_URL}/api/upload`, formData, {
        headers: { 
          'Content-Type': 'multipart/form-data',
        },
        timeout: 300000 // 5 phút timeout
      });
      
      if (response.data.success) {
        setUploadedFileInfo(response.data);
        setConfig(prev => ({
          ...prev,
          sheetName: response.data.sheets[0] || '',
          fileType: response.data.file_type || 'excel'
        }));
        setStep('configure');
      } else {
        setError(response.data.error || 'Đã có lỗi xảy ra khi tải file lên.');
      }
    } catch (err) {
      const errorMsg = err.response?.data?.error || 
                      (err.code === 'ECONNABORTED' ? 'Thời gian tải lên quá lâu' : 'Đã có lỗi xảy ra');
      setError(errorMsg);
    } finally {
      setIsLoading(false);
    }
  };

  // Hàm này lấy danh sách cột từ sheet đã chọn
  const fetchSheetColumns = useCallback(async () => {
    if (!uploadedFileInfo || !config.sheetName) return;
    
    setFileProcessing(true);
    try {
      const response = await axios.post(`${API_URL}/api/sheet-columns`, {
        filepath: uploadedFileInfo.filepath,
        sheetName: config.sheetName,
        headerRow: config.headerRow,
        fileType: config.fileType
      }, {
        timeout: 120000 // 2 phút timeout
      });
      
      if (response.data.success) {
        setFileColumns(response.data.columns);
      } else {
        setError(response.data.error || 'Không thể lấy danh sách cột.');
      }
    } catch (err) {
      setError(err.response?.data?.error || 'Lỗi khi lấy danh sách cột.');
    } finally {
      setFileProcessing(false);
    }
  }, [uploadedFileInfo, config]);

  // Khi sheet hoặc headerRow thay đổi, lấy lại danh sách cột
  useEffect(() => {
    if (step === 'configure' && uploadedFileInfo && config.sheetName) {
      fetchSheetColumns();
    }
  }, [step, uploadedFileInfo, config.sheetName, config.headerRow, fetchSheetColumns]);

  const handleConfigChange = (e) => {
    const { name, value } = e.target;
    setConfig(prev => ({ ...prev, [name]: value }));
  };
  
  const handleSubmit = async () => {
    if (!config.sheetName || !config.quantityCol || !config.weightCol) {
      setError('Vui lòng chọn sheet, cột số lượng và cột khối lượng.');
      return;
    }
    
    setIsLoading(true);
    setError('');
    setResults(null);
    
    try {
      const payload = {
        filepath: uploadedFileInfo.filepath,
        ...config
      };
      
      const response = await axios.post(`${API_URL}/api/process`, payload, {
        timeout: 300000 // 5 phút timeout
      });
      
      if (response.data.success) {
        setResults(response.data.results);
        setStep('results');
      } else {
        setError(response.data.error || 'Đã có lỗi xảy ra khi xử lý dữ liệu.');
      }
    } catch (err) {
      const errorMsg = err.response?.data?.error || 
                      (err.code === 'ECONNABORTED' ? 'Thời gian xử lý quá lâu' : 'Đã có lỗi xảy ra');
      setError(errorMsg);
    } finally {
      setIsLoading(false);
    }
  };

  const goBack = useCallback((targetStep) => {
      setStep(targetStep);
      setError('');
      setResults(null);
      if (targetStep === 'upload') {
          setFile(null);
          setUploadedFileInfo(null);
          setFileColumns([]);
      }
  }, []);

  // --- RENDER FUNCTIONS ---
  const renderUploadStep = () => (
    <div className="card">
      <h1 className="title">Tối ưu hóa xếp dỡ Container</h1>
      <p className="subtitle">Tải lên file Excel hoặc CSV của bạn để bắt đầu</p>
      <div className="input-group">
        <input 
          type="file" 
          id="file-upload" 
          className="file-input" 
          onChange={handleFileChange} 
          accept=".xlsx, .xls, .csv" 
        />
        <label htmlFor="file-upload" className="file-label">
            {file ? file.name : 'Chọn file...'}
        </label>
        {file && (
          <div style={{ marginTop: '10px', fontSize: '0.9rem' }}>
            Kích thước: {(file.size / (1024 * 1024)).toFixed(2)} MB
          </div>
        )}
      </div>
      <button onClick={handleUpload} disabled={isLoading || !file}>
        {isLoading ? 'Đang tải lên...' : 'Tải lên & Tiếp tục'}
      </button>
      {error && <p className="error-message">{error}</p>}
    </div>
  );

  const renderConfigureStep = () => {
    if (!uploadedFileInfo) return null;
    
    return (
      <div className="card">
        <h2 className="title">Cấu hình dữ liệu</h2>
        <p className="subtitle">Chọn sheet và các cột tương ứng để tính toán</p>
        
        <div className="form-group">
          <label>Chọn Sheet (Subtab)</label>
          <select 
            name="sheetName" 
            value={config.sheetName} 
            onChange={handleConfigChange}
            disabled={fileProcessing}
          >
            {uploadedFileInfo.sheets.map(sheet => (
              <option key={sheet} value={sheet}>{sheet}</option>
            ))}
          </select>
        </div>
        
        <div className="form-group">
          <label>Dòng tiêu đề (Header row - bắt đầu từ 0)</label>
          <input 
            type="number" 
            name="headerRow" 
            value={config.headerRow} 
            onChange={handleConfigChange} 
            min="0"
            disabled={fileProcessing}
          />
        </div>
        
        {fileProcessing ? (
          <p>Đang tải thông tin cột...</p>
        ) : (
          <>
            <h3 className="sub-title">Ánh xạ cột</h3>
            <div className="form-group">
              <label>Cột chứa Số lượng Pallet</label>
              <select 
                name="quantityCol" 
                value={config.quantityCol} 
                onChange={handleConfigChange}
                disabled={fileColumns.length === 0}
              >
                <option value="">-- Chọn cột --</option>
                {fileColumns.map(col => (
                  <option key={`qty-${col}`} value={col}>{col}</option>
                ))}
              </select>
            </div>
            
            <div className="form-group">
              <label>Cột chứa Khối lượng (GW/Pallet)</label>
              <select 
                name="weightCol" 
                value={config.weightCol} 
                onChange={handleConfigChange}
                disabled={fileColumns.length === 0}
              >
                <option value="">-- Chọn cột --</option>
                {fileColumns.map(col => (
                  <option key={`wgt-${col}`} value={col}>{col}</option>
                ))}
              </select>
            </div>
            
            <h3 className="sub-title">Lọc nâng cao (Tùy chọn)</h3>
            <div className="form-group">
              <label>Lọc theo cột</label>
              <select 
                name="filterCol" 
                value={config.filterCol} 
                onChange={handleConfigChange}
                disabled={fileColumns.length === 0}
              >
                <option value="">-- Không lọc --</option>
                {fileColumns.map(col => (
                  <option key={`flt-${col}`} value={col}>{col}</option>
                ))}
              </select>
            </div>
            
            {config.filterCol && (
              <div className="form-group">
                <label>Với giá trị là</label>
                <input 
                  type="text" 
                  name="filterVal" 
                  value={config.filterVal} 
                  onChange={handleConfigChange} 
                  placeholder="Nhập giá trị cần lọc" 
                />
              </div>
            )}
          </>
        )}
        
        <div className="button-group">
          <button onClick={() => goBack('upload')} className="secondary" disabled={isLoading}>
            Quay lại
          </button>
          <button onClick={handleSubmit} disabled={isLoading || fileProcessing || fileColumns.length === 0}>
            {isLoading ? 'Đang tính toán...' : 'Tối ưu hóa'}
          </button>
        </div>
        
        {error && <p className="error-message">{error}</p>}
      </div>
    );
  };

  return (
    <div className="App">
      <GlobalStyles />
      <main className="container">
        {step === 'upload' && renderUploadStep()}
        {step === 'configure' && uploadedFileInfo && renderConfigureStep()}
        {step === 'results' && results && (
            <div>
                <button onClick={() => goBack('configure')} className="back-button">
                  ← Quay lại cấu hình
                </button>
                <ResultsDisplay results={results} />
            </div>
        )}
      </main>
    </div>
  );
}

export default App;