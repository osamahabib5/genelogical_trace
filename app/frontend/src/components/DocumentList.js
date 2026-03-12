import React, { useState, useEffect } from 'react';
import axios from 'axios';
import './DocumentList.css';

function DocumentList({ apiUrl, documents }) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [filter, setFilter] = useState('all');

  const filteredDocs = documents.filter(doc => 
    filter === 'all' || doc.type === filter
  );

  const handleDelete = async (docId) => {
    if (window.confirm('Are you sure you want to delete this document?')) {
      try {
        await axios.delete(`${apiUrl}/documents/${docId}`);
        window.location.reload();
      } catch (err) {
        setError(`Error deleting document: ${err.message}`);
      }
    }
  };

  return (
    <div className="document-list-container">
      <div className="document-list-header">
        <h2>📋 Uploaded Documents</h2>
        <div className="document-filter">
          <button 
            className={filter === 'all' ? 'active' : ''}
            onClick={() => setFilter('all')}
          >
            All ({documents.length})
          </button>
          <button 
            className={filter === 'journal' ? 'active' : ''}
            onClick={() => setFilter('journal')}
          >
            Journals
          </button>
          <button 
            className={filter === 'application' ? 'active' : ''}
            onClick={() => setFilter('application')}
          >
            Applications
          </button>
        </div>
      </div>

      {error && <div className="error-message">{error}</div>}

      {filteredDocs.length === 0 ? (
        <div className="empty-state">
          <p>No documents found. Start by uploading a document!</p>
        </div>
      ) : (
        <div className="document-grid">
          {filteredDocs.map(doc => (
            <div key={doc.id} className="document-card">
              <div className="document-type-badge">
                {doc.type === 'journal' ? '📔' : '📝'} {doc.type}
              </div>
              <h3>{doc.title}</h3>
              <div className="document-meta">
                <p><strong>File:</strong> {doc.filename}</p>
                <p><strong>Chunks:</strong> {doc.chunks}</p>
                <p><strong>Ancestors Found:</strong> {doc.ancestors_found}</p>
                <p><strong>Uploaded:</strong> {new Date(doc.upload_date).toLocaleDateString()}</p>
              </div>
              <button 
                className="delete-button"
                onClick={() => handleDelete(doc.id)}
              >
                Delete
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export default DocumentList;
