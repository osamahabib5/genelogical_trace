import React, { useState } from 'react';
import axios from 'axios';
import './FamilyTree.css';

function FamilyTree({ apiUrl }) {
  const [personName, setPersonName] = useState('');
  const [familyData, setFamilyData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const handleSearch = async (e) => {
    e.preventDefault();
    
    if (!personName.trim()) {
      setError('Please enter a name');
      return;
    }

    setLoading(true);
    setError('');
    setFamilyData(null);

    try {
      const response = await axios.get(`${apiUrl}/queries/family/${personName}`);
      setFamilyData(response.data);
    } catch (err) {
      setError(`Error searching family tree: ${err.response?.data?.detail || err.message}`);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="family-tree-container">
      <div className="family-tree-search">
        <h2>👨‍👩‍👧‍👦 Family Tree Search</h2>
        <form onSubmit={handleSearch}>
          <input
            type="text"
            value={personName}
            onChange={(e) => setPersonName(e.target.value)}
            placeholder="Enter person's name to find their family connections..."
            className="search-input"
            disabled={loading}
          />
          <button type="submit" disabled={loading || !personName.trim()} className="search-button">
            {loading ? '🔍 Searching...' : '🔍 Search'}
          </button>
        </form>
      </div>

      {error && <div className="error-message">{error}</div>}

      {familyData && (
        <div className="family-results">
          <h3>{familyData.anchor_person} - {familyData.connected_records} connected record(s)</h3>
          <div className="family-grid">
            {familyData.family_tree.map((person, idx) => (
              <div key={idx} className="family-card">
                <h4>{person.person_name}</h4>
                <div className="family-info">
                  {person.birth_date && <p><strong>Born:</strong> {person.birth_date}</p>}
                  {person.birth_location && <p><strong>Place:</strong> {person.birth_location}</p>}
                  {person.occupation && <p><strong>Occupation:</strong> {person.occupation}</p>}
                  {person.relation_type && <p><strong>Relation:</strong> {person.relation_type}</p>}
                  {person.death_date && <p><strong>Died:</strong> {person.death_date}</p>}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {!familyData && !error && !loading && (
        <div className="empty-state">
          <p>Enter a person's name to explore their family connections</p>
        </div>
      )}
    </div>
  );
}

export default FamilyTree;
