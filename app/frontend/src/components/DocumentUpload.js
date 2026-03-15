import React, { useState, useRef } from 'react';
import axios from 'axios';
import './DocumentUpload.css';

function DocumentUpload({ apiUrl, onDocumentUploaded }) {
  const [file, setFile] = useState(null);
  const [docType, setDocType] = useState('journal');
  const [uploading, setUploading] = useState(false);
  const [progress, setProgress] = useState(0);
  const [result, setResult] = useState(null);
  const [error, setError] = useState('');
  const [dragOver, setDragOver] = useState(false);
  const fileInputRef = useRef(null);

  const VALID_TYPES = ['.pdf', '.docx', '.txt', '.json'];
  const MAX_SIZE_MB = 100;

  const validateFile = (selectedFile) => {
    const fileExt = selectedFile.name
      .substring(selectedFile.name.lastIndexOf('.'))
      .toLowerCase();

    if (!VALID_TYPES.includes(fileExt)) {
      return `Invalid file type. Supported: ${VALID_TYPES.join(', ')}`;
    }
    if (selectedFile.size > MAX_SIZE_MB * 1024 * 1024) {
      return `File too large. Maximum size: ${MAX_SIZE_MB}MB`;
    }
    return null;
  };

  const handleFileSelect = (selectedFile) => {
    if (!selectedFile) return;
    const validationError = validateFile(selectedFile);
    if (validationError) {
      setError(validationError);
      setFile(null);
    } else {
      setFile(selectedFile);
      setError('');
      setResult(null);
    }
  };

  const handleFileChange = (e) => {
    handleFileSelect(e.target.files[0]);
  };

  const handleDragOver = (e) => {
    e.preventDefault();
    setDragOver(true);
  };

  const handleDragLeave = () => setDragOver(false);

  const handleDrop = (e) => {
    e.preventDefault();
    setDragOver(false);
    handleFileSelect(e.dataTransfer.files[0]);
  };

  const formatFileSize = (bytes) => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  };

  const handleUpload = async (e) => {
    e.preventDefault();
    if (!file) { setError('Please select a file'); return; }

    setUploading(true);
    setProgress(0);
    setResult(null);
    setError('');

    try {
      const formData = new FormData();
      formData.append('file', file);
      formData.append('document_type', docType);

      const response = await axios.post(
        `${apiUrl}/documents/upload`,
        formData,
        {
          headers: { 'Content-Type': 'multipart/form-data' },
          timeout: 600000, // 10 minutes for large files
          onUploadProgress: (progressEvent) => {
            const pct = Math.round(
              (progressEvent.loaded * 100) / progressEvent.total
            );
            setProgress(pct);
          }
        }
      );

      setResult(response.data);
      setFile(null);
      if (fileInputRef.current) fileInputRef.current.value = '';

      if (onDocumentUploaded) onDocumentUploaded();

    } catch (err) {
      setError(`❌ Upload failed: ${err.response?.data?.detail || err.message}`);
    } finally {
      setUploading(false);
      setProgress(0);
    }
  };

  return (
    <div className="upload-container">
      <div className="upload-card">
        <h2>📤 Upload Genealogical Document</h2>
        <p className="upload-subtitle">
          Upload journals, applications, or historical records.
          Footnotes and citations will be automatically extracted.
        </p>

        <form onSubmit={handleUpload} className="upload-form">

          {/* Document type selector */}
          <div className="form-group">
            <label htmlFor="doc-type">Document Type</label>
            <select
              id="doc-type"
              value={docType}
              onChange={(e) => setDocType(e.target.value)}
              className="form-control"
              disabled={uploading}
            >
              <option value="journal">📔 Journal</option>
              <option value="application">📝 Member Application</option>
              <option value="other">📄 Other Document</option>
            </select>
          </div>

          {/* Drag and drop zone */}
          <div
            className={`drop-zone ${dragOver ? 'drag-over' : ''} ${file ? 'has-file' : ''}`}
            onDragOver={handleDragOver}
            onDragLeave={handleDragLeave}
            onDrop={handleDrop}
            onClick={() => fileInputRef.current?.click()}
          >
            <input
              ref={fileInputRef}
              type="file"
              onChange={handleFileChange}
              accept=".pdf,.docx,.txt,.json"
              className="hidden-input"
              disabled={uploading}
            />

            {file ? (
              <div className="file-selected">
                <span className="file-icon-large">
                  {file.name.endsWith('.docx') ? '📝' :
                   file.name.endsWith('.pdf')  ? '📕' :
                   file.name.endsWith('.txt')  ? '📄' : '🔧'}
                </span>
                <div className="file-info">
                  <span className="file-name">{file.name}</span>
                  <span className="file-size">{formatFileSize(file.size)}</span>
                </div>
                <button
                  type="button"
                  className="remove-file"
                  onClick={(e) => { e.stopPropagation(); setFile(null); setResult(null); }}
                >
                  ✕
                </button>
              </div>
            ) : (
              <div className="drop-zone-content">
                <span className="drop-icon">📁</span>
                <p className="drop-text">
                  <strong>Drag & drop</strong> your file here
                </p>
                <p className="drop-subtext">or click to browse</p>
                <p className="drop-formats">PDF · DOCX · TXT · JSON · Max {MAX_SIZE_MB}MB</p>
              </div>
            )}
          </div>

          {/* Progress bar */}
          {uploading && (
            <div className="progress-container">
              <div className="progress-bar">
                <div
                  className="progress-fill"
                  style={{ width: `${progress}%` }}
                />
              </div>
              <p className="progress-text">
                {progress < 100
                  ? `Uploading... ${progress}%`
                  : '⚙️ Processing document, extracting embeddings and footnotes...'}
              </p>
            </div>
          )}

          <button
            type="submit"
            disabled={!file || uploading}
            className="upload-button"
          >
            {uploading ? '⏳ Processing...' : '📤 Upload Document'}
          </button>
        </form>

        {/* Error message */}
        {error && <div className="error-message">{error}</div>}

        {/* Success result */}
        {result && (
          <div className="success-result">
            <h3>✅ Upload Successful</h3>
            <div className="result-stats">
              <div className="stat">
                <span className="stat-value">{result.chunks}</span>
                <span className="stat-label">Chunks</span>
              </div>
              <div className="stat">
                <span className="stat-value">{result.footnotes_extracted || 0}</span>
                <span className="stat-label">Footnotes</span>
              </div>
              <div className="stat">
                <span className="stat-value">{result.footnotes_linked_to_chunks || 0}</span>
                <span className="stat-label">Linked</span>
              </div>
              <div className="stat">
                <span className="stat-value">{result.embedding_errors || 0}</span>
                <span className="stat-label">Errors</span>
              </div>
            </div>
            <p className="result-title">📄 {result.title}</p>
            <p className="result-id">Document ID: {result.document_id}</p>
          </div>
        )}

        {/* Format info */}
        <div className="upload-info">
          <h3>Supported Formats</h3>
          <div className="format-grid">
            <div className="format-item">📕 <strong>PDF</strong> — Portable Document Format</div>
            <div className="format-item">📝 <strong>DOCX</strong> — Microsoft Word (footnotes extracted)</div>
            <div className="format-item">📄 <strong>TXT</strong> — Plain Text</div>
            <div className="format-item">🔧 <strong>JSON</strong> — Structured Data</div>
          </div>
        </div>
      </div>
    </div>
  );
}

export default DocumentUpload;