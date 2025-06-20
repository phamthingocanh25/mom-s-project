import React, { useState } from 'react';
import axios from 'axios';

const API_URL = 'http://localhost:5001';

// --- STYLES COMPONENT ---
const GlobalStyles = () => (
  <style>{`
    @import url('https://fonts.googleapis.com/css2?family=Be+Vietnam+Pro:wght@400;500;700&display=swap');
    :root {
      --primary-color: #0052cc; --secondary-color: #f4f5f7; --text-color: #172b4d;
      --background-color: #f4f5f7; --card-background: #ffffff; --border-color: #dfe1e6;
      --error-color: #de350b; --success-color: #00875a; --font-family: 'Be Vietnam Pro', sans-serif;
    }
    body {
      margin: 0; font-family: var(--font-family); background-color: var(--background-color);
      color: var(--text-color); -webkit-font-smoothing: antialiased; -moz-osx-font-smoothing: grayscale;
    }
    .App { display: flex; flex-direction: column; align-items: center; padding: 2rem; min-height: 100vh; }
    .container { width: 100%; max-width: 800px; }
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
    .results-container { background-color: #fff; border-radius: 8px; padding: 2rem; box-shadow: 0 4px 8px rgba(0, 0, 0, 0.05); }
    .results-title { text-align: center; font-size: 1.8rem; margin-bottom: 0.5rem; color: var(--text-color); }
    .results-summary { text-align: center; font-size: 1.1rem; color: #6b778c; margin-bottom: 2rem; }
    .containers-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(350px, 1fr)); gap: 1.5rem; }
    .container-card { border: 1px solid var(--border-color); border-radius: 8px; overflow: hidden; display: flex; flex-direction: column; }
    .container-header { background-color: var(--primary-color); color: white; padding: 0.8rem 1rem; }
    .container-header h3 { margin: 0; font-size: 1.2rem; }
    .container-stats { padding: 1rem; background-color: #fafbfc; border-bottom: 1px solid var(--border-color); }
    .stat-item { display: flex; justify-content: space-between; align-items: center; font-size: 0.9rem; }
    .stat-item:not(:last-child) { margin-bottom: 0.5rem; }
    .stat-item span { color: #42526e; }
    .container-content { padding: 1rem; flex-grow: 1; }
    .container-content h4 { margin-top: 0; margin-bottom: 1rem; font-size: 1rem; color: var(--text-color); }
    .content-item:not(:last-child) { margin-bottom: 1rem; }
    .pallet-info { font-size: 0.9rem; padding: 0.75rem; border-radius: 4px; }
    .pallet-info strong { display: block; margin-bottom: 0.25rem; }
    .single-pallet { background-color: #e6fcff; border-left: 4px solid #00c7e6; display: flex; justify-content: space-between; align-items: center; }
    .combined-pallet { background-color: #e9e7fd; border-left: 4px solid #6554c0; }
    .combined-pallet ul { list-style-type: none; padding-left: 1rem; margin: 0.5rem 0 0 0; }
    .combined-pallet li { color: #42526e; }
  `}</style>
);

const ResultsDisplay = ({ results }) => {
  if (!results || !Array.isArray(results)) return null;
  if (results.length === 0) {
    return (
      <div className="results-container">
        <h2 className="results-title">Không có kết quả</h2>
        <p className="results-summary">Không tìm thấy giải pháp tối ưu với dữ liệu được cung cấp.</p>
      </div>
    );
  }
  const formatNumber = (num) => {
    if (typeof num !== 'number' || isNaN(num)) return 'N/A';
    return num.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  };
  return (
    <div className="results-container">
      <h2 className="results-title">Kết quả tối ưu hóa</h2>
      <p className="results-summary">Tổng số container cần sử dụng: <strong>{results.length}</strong></p>
      <div className="containers-grid">
        {results.map((container) => (
          <div key={container.container_number} className="container-card">
            <div className="container-header"><h3>Container #{container.container_number}</h3></div>
            <div className="container-stats">
              <div className="stat-item"><span>Tổng số lượng:</span><strong>{formatNumber(container.total_boxes)} / 20.00 Pallets</strong></div>
              <div className="stat-item"><span>Tổng khối lượng:</span><strong>{formatNumber(container.total_weight)} / 24,000.00 kg</strong></div>
            </div>
            <div className="container-content">
              <h4>Chi tiết Pallet:</h4>
              {container.contents.map((content, index) => (
                <div key={index} className="content-item">
                  {content.type === 'SinglePallet' && (<div className="pallet-info single-pallet"><strong>Pallet Đơn:</strong><span>{formatNumber(content.items[0]?.number_of_boxes)} plls</span><span>({formatNumber(content.items[0]?.total_item_weight)} kg)</span></div>)}
                  {content.type === 'CombinedPallet' && (<div className="pallet-info combined-pallet"><strong>Pallet Kết hợp (Tổng: {formatNumber(content.total_boxes_count)} plls, {formatNumber(content.total_weight)} kg):</strong><ul>{content.items.map((item, subIndex) => (<li key={subIndex}>- {formatNumber(item?.number_of_boxes)} plls ({formatNumber(item?.total_item_weight)} kg)</li>))}</ul></div>)}
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};

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
        setConfig({ sheetName: response.data.sheets[0] || '' });
        setStep('configure');
      } else {
        setError(response.data.error || 'Lỗi: Không thể xử lý file tải lên.');
      }
    } catch (err) {
      const errorMsg = err.response?.data?.error || (err.code === 'ECONNABORTED' ? 'Thời gian tải lên quá lâu, vui lòng thử lại.' : 'Đã có lỗi xảy ra khi kết nối tới server.');
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
      if (response.data.success) {
        setResults(response.data.results);
        setStep('results');
      } else {
        setError(response.data.error || 'Lỗi: Không thể xử lý dữ liệu.');
      }
    } catch (err) {
      const errorMsg = err.response?.data?.error || (err.code === 'ECONNABORTED' ? 'Thời gian xử lý quá lâu, vui lòng thử lại.' : 'Đã có lỗi xảy ra khi kết nối tới server.');
      setError(errorMsg);
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
          {uploadedFileInfo.sheets.map(sheet => <option key={sheet} value={sheet}>{sheet}</option>)}
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
    <div>
      <button onClick={() => goBack('configure')} className="back-button">← Quay lại cấu hình</button>
      <ResultsDisplay results={results} />
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