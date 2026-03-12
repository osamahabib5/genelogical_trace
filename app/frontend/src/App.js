import React, { useState, useEffect } from 'react';
import axios from 'axios';
import './App.css';
import DocumentUpload from './components/DocumentUpload';
import Chatbot from './components/Chatbot';
import DocumentList from './components/DocumentList';
import FamilyTree from './components/FamilyTree';

// const API_URL = process.env.REACT_APP_API_URL || 'http://localhost:8000/api';
const API_URL = process.env.REACT_APP_API_URL || 'http://localhost:8000/api';

function App() {
  const [activeTab, setActiveTab] = useState('chat');
  const [documents, setDocuments] = useState([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    loadDocuments();
  }, []);

  const loadDocuments = async () => {
    try {
      const response = await axios.get(`${API_URL}/documents/list`);
      setDocuments(response.data.documents);
    } catch (error) {
      console.error('Error loading documents:', error);
    }
  };

  const handleDocumentUploaded = () => {
    loadDocuments();
  };

  return (
    <div className="app">
      <header className="app-header">
        <h1>📚 Genealogy Ancestry Chatbot</h1>
        <p>Trace African American genealogical ancestry through historical documents and records</p>
      </header>

      <nav className="app-nav">
        <button 
          className={`nav-button ${activeTab === 'chat' ? 'active' : ''}`}
          onClick={() => setActiveTab('chat')}
        >
          💬 Chat
        </button>
        {/* <button 
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
        </button>
        <button 
          className={`nav-button ${activeTab === 'family' ? 'active' : ''}`}
          onClick={() => setActiveTab('family')}
        >
          👨‍👩‍👧‍👦 Family Tree
        </button> */}
      </nav>

      <main className="app-main">
        {activeTab === 'chat' && <Chatbot apiUrl={API_URL} />}
        {activeTab === 'upload' && <DocumentUpload apiUrl={API_URL} onDocumentUploaded={handleDocumentUploaded} />}
        {activeTab === 'documents' && <DocumentList apiUrl={API_URL} documents={documents} />}
        {activeTab === 'family' && <FamilyTree apiUrl={API_URL} />}
      </main>
    </div>
  );
}

export default App;
