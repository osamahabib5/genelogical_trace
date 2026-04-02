import React, { useState, useEffect } from 'react';
import axios from 'axios';
import './App.css';
import DocumentUpload from './components/DocumentUpload';
import Chatbot from './components/Chatbot';
import DocumentList from './components/DocumentList';
import FamilyTree from './components/FamilyTree';

// Use the environment variable set during Docker build, or fallback to localhost
const API_URL = process.env.REACT_APP_API_URL || (
  process.env.NODE_ENV === 'production'
    ? 'https://genealogy-backend.orangeground-33df987d.eastus.azurecontainerapps.io/api'
    : 'http://localhost:8000/api'
);

console.log('API_URL configured as:', API_URL);

function App() {
  const [activeTab, setActiveTab] = useState('chat');
  const [documents, setDocuments] = useState([]);
  const [loadError, setLoadError] = useState(null);

  useEffect(() => {
    loadDocuments();
  }, []);

  const loadDocuments = async () => {
    try {
      setLoadError(null);
      const response = await axios.get(`${API_URL}/documents/list`);
      setDocuments(response.data.documents || []);
    } catch (error) {
      console.error('Error loading documents:', error);
      setLoadError('Failed to load documents. Check if backend is running.');
      setDocuments([]);
    }
  };

  const handleDocumentUploaded = () => {
    loadDocuments();
    // Switch to documents tab after upload so user sees their document
    setActiveTab('documents');
  };

  return (
    <div className="app">
      <header className="app-header">
        <h1>📚 SOFAFEA Genealogy Assistant</h1>
        <p>Trace African American genealogical ancestry through historical documents and records</p>
        {process.env.NODE_ENV === 'development' && (
          <p style={{ fontSize: '0.8em', color: '#666' }}>
            API: {API_URL}
          </p>
        )}
      </header>

      <nav className="app-nav">
        <button
          className={`nav-button ${activeTab === 'chat' ? 'active' : ''}`}
          onClick={() => setActiveTab('chat')}
        >
          💬 Chat
        </button>
        <button
          className={`nav-button ${activeTab === 'upload' ? 'active' : ''}`}
          onClick={() => setActiveTab('upload')}
        >
          📤 Upload
        </button>
        <button
          className={`nav-button ${activeTab === 'documents' ? 'active' : ''}`}
          onClick={() => setActiveTab('documents')}
        >
          📋 Documents
          {documents.length > 0 && (
            <span className="doc-count">{documents.length}</span>
          )}
        </button>
        <button
          className={`nav-button ${activeTab === 'family' ? 'active' : ''}`}
          onClick={() => setActiveTab('family')}
        >
          👨‍👩‍👧‍👦 Family Tree
        </button>
      </nav>

      {loadError && (
        <div className="error-banner">
          <p>⚠️ {loadError}</p>
        </div>
      )}

      <main className="app-main">
        {activeTab === 'chat' && <Chatbot apiUrl={API_URL} />}
        {activeTab === 'upload' && (
          <DocumentUpload
            apiUrl={API_URL}
            onDocumentUploaded={handleDocumentUploaded}
          />
        )}
        {activeTab === 'documents' && (
          <DocumentList
            apiUrl={API_URL}
            documents={documents}
            onDocumentsChanged={loadDocuments}
          />
        )}
        {activeTab === 'family' && <FamilyTree apiUrl={API_URL} />}
      </main>
    </div>
  );
}

export default App;