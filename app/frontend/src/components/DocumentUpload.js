import React, { useState } from 'react';
import axios from 'axios';
import './DocumentUpload.css';

function DocumentUpload({ apiUrl, onDocumentUploaded }) {
  const [file, setFile] = useState(null);
  const [docType, setDocType] = useState('journal');
  const [uploading, setUploading] = useState(false);
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');

  const handleFileChange = (e) => {
    const selectedFile = e.target.files[0];
    if (selectedFile) {
      const validTypes = ['.pdf', '.docx', '.txt', '.json'];
      const fileExt = selectedFile.name.substring(selectedFile.name.lastIndexOf('.')).toLowerCase();
      
      if (!validTypes.includes(fileExt)) {
        setError(`Invalid file type. Supported: ${validTypes.join(', ')}`);
        setFile(null);
      } else if (selectedFile.size > 50 * 1024 * 1024) {
        setError('File too large. Maximum size: 50MB');
        setFile(null);
      } else {
        setFile(selectedFile);
        setError('');
      }
    }
  };

  const handleUpload = async (e) => {
    e.preventDefault();
    
    if (!file) {
      setError('Please select a file');
      return;
    }

    setUploading(true);
    setMessage('');
    setError('');

    try {
      const formData = new FormData();
      formData.append('file', file);
      formData.append('document_type', docType);

      const response = await axios.post(`${apiUrl}/documents/upload`, formData, {
        headers: {
          'Content-Type': 'multipart/form-data',
        },
      });

      setMessage(`✅ Document uploaded successfully! (ID: ${response.data.document_id})`);
      setFile(null);
      
      // Reset form
      document.getElementById('upload-form').reset();
      
      // Notify parent component
      if (onDocumentUploaded) {
        onDocumentUploaded();
      }
    } catch (err) {
      setError(`❌ Error uploading document: ${err.response?.data?.detail || err.message}`);
    } finally {
      setUploading(false);
    }
  };

  return (
    <div className="upload-container">
      <div className="upload-card">
        <h2>📤 Upload Genealogical Document</h2>
        
        <form id="upload-form" onSubmit={handleUpload} className="upload-form">
          <div className="form-group">
            <label htmlFor="doc-type">Document Type:</label>
            <select 
              id="doc-type"
              value={docType} 
              onChange={(e) => setDocType(e.target.value)}
              className="form-control"
            >
              <option value="journal">Journal Entry</option>
              <option value="application">Application</option>
              <option value="other">Other Document</option>
            </select>
          </div>

          <div className="form-group">
            <label htmlFor="file-input" className="file-label">
              <div className="file-input-wrapper">
                <span className="file-icon">📁</span>
                <span className="file-text">
                  {file ? file.name : 'Click to select file (PDF, DOCX, TXT, JSON)'}
                </span>
              </div>
              <input 
                id="file-input"
                type="file" 
                onChange={handleFileChange}
                accept=".pdf,.docx,.txt,.json"
                className="hidden-input"
              />
            </label>
          </div>

          <button 
            type="submit" 
            disabled={!file || uploading}
            className="upload-button"
          >
            {uploading ? '⏳ Uploading...' : '📤 Upload Document'}
          </button>
        </form>

        {message && <div className="success-message">{message}</div>}
        {error && <div className="error-message">{error}</div>}

        <div className="upload-info">
          <h3>Supported Formats:</h3>
          <ul>
            <li>📄 PDF - Portable Document Format</li>
            <li>📝 DOCX - Microsoft Word Document</li>
            <li>📋 TXT - Plain Text File</li>
            <li>🔧 JSON - Structured Data</li>
          </ul>
          <p><strong>Max file size:</strong> 50MB</p>
        </div>
      </div>
    </div>
  );
}

export default DocumentUpload;
