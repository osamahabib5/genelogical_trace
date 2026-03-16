import React, { useState, useEffect, useRef } from 'react';
import axios from 'axios';
import './FamilyTree.css';

const GENERATION_LABELS = [
  '4th great-grandparent',
  '3rd great-grandparent',
  '2nd great-grandparent',
  'great-grandparent',
  'grandparent',
  'parent',
  'self',
  'child',
  'grandchild',
  'great-grandchild',
];

const ANCESTOR_KEYWORDS = [
  'great-great-great-grandparent', '4th great', '3rd great', '2nd great',
  'great-grandparent', 'great-grandfather', 'great-grandmother',
  'grandparent', 'grandfather', 'grandmother',
  'parent', 'father', 'mother',
  'patriarch', 'matriarch', 'ancestor', 'founder',
  'self', 'subject',
  'son', 'daughter', 'child',
  'grandchild', 'grandson', 'granddaughter',
  'great-grandchild',
];

function getGenerationOrder(relation) {
  if (!relation) return 5;
  const r = relation.toLowerCase();
  if (r.includes('4th great') || r.includes('great-great-great')) return 0;
  if (r.includes('3rd great') || r.includes('great-great-grand')) return 1;
  if (r.includes('2nd great')) return 2;
  if (r.includes('great-grand')) return 3;
  if (r.includes('grand')) return 4;
  if (r.includes('parent') || r.includes('father') || r.includes('mother')) return 5;
  if (r.includes('patriarch') || r.includes('matriarch') || r.includes('ancestor') || r.includes('founder')) return 0;
  if (r.includes('self') || r.includes('subject')) return 6;
  if (r.includes('son') || r.includes('daughter') || r.includes('child')) return 7;
  if (r.includes('grandchild') || r.includes('grandson') || r.includes('granddaughter')) return 8;
  if (r.includes('great-grandchild')) return 9;
  return 5;
}

function LineageFlowchart({ people, anchorName }) {
  const canvasRef = useRef(null);
  const [animatedNodes, setAnimatedNodes] = useState([]);
  const [animatedLines, setAnimatedLines] = useState([]);

  // Group people by generation
  const grouped = {};
  people.forEach(p => {
    const gen = getGenerationOrder(p.relation_type);
    if (!grouped[gen]) grouped[gen] = [];
    grouped[gen].push(p);
  });

  // Add anchor person if not in records
  const hasAnchor = people.some(p => getGenerationOrder(p.relation_type) === 6);
  if (!hasAnchor) {
    if (!grouped[6]) grouped[6] = [];
    grouped[6].push({ person_name: anchorName, relation_type: 'self', isAnchor: true });
  }

  const generations = Object.keys(grouped).map(Number).sort((a, b) => a - b);
  const NODE_W = 180;
  const NODE_H = 56;
  const V_GAP = 80;
  const H_GAP = 20;
  const SVG_W = 680;
  const PADDING_TOP = 40;

  // Calculate positions
  const nodePositions = {};
  generations.forEach((gen, genIdx) => {
    const nodes = grouped[gen];
    const totalW = nodes.length * NODE_W + (nodes.length - 1) * H_GAP;
    const startX = (SVG_W - totalW) / 2;
    const y = PADDING_TOP + genIdx * (NODE_H + V_GAP);
    nodes.forEach((node, i) => {
      const key = `${gen}-${i}`;
      nodePositions[key] = {
        x: startX + i * (NODE_W + H_GAP),
        y,
        node,
        gen,
        idx: i
      };
    });
  });

  const SVG_H = PADDING_TOP + generations.length * (NODE_H + V_GAP) + 40;

  // Build connector lines between consecutive generations
  const lines = [];
  for (let i = 0; i < generations.length - 1; i++) {
    const topGen = generations[i];
    const botGen = generations[i + 1];
    const topNodes = grouped[topGen];
    const botNodes = grouped[botGen];

    topNodes.forEach((_, ti) => {
      const topKey = `${topGen}-${ti}`;
      const topPos = nodePositions[topKey];
      botNodes.forEach((_, bi) => {
        const botKey = `${botGen}-${bi}`;
        const botPos = nodePositions[botKey];
        lines.push({
          x1: topPos.x + NODE_W / 2,
          y1: topPos.y + NODE_H,
          x2: botPos.x + NODE_W / 2,
          y2: botPos.y,
          key: `${topKey}-${botKey}`
        });
      });
    });
  }

  // Animate nodes in sequence
  useEffect(() => {
    setAnimatedNodes([]);
    setAnimatedLines([]);
    const keys = Object.keys(nodePositions);
    keys.forEach((key, i) => {
      setTimeout(() => {
        setAnimatedNodes(prev => [...prev, key]);
      }, i * 120);
    });
    lines.forEach((line, i) => {
      setTimeout(() => {
        setAnimatedLines(prev => [...prev, line.key]);
      }, keys.length * 120 + i * 80);
    });
  }, [people.length, anchorName]);

  const getNodeColor = (node) => {
    const gen = getGenerationOrder(node.relation_type);
    if (node.isAnchor || gen === 6) return { fill: '#534AB7', stroke: '#3C3489', text: '#EEEDFE' };
    if (gen <= 2) return { fill: '#085041', stroke: '#0F6E56', text: '#E1F5EE' };
    if (gen <= 4) return { fill: '#0C447C', stroke: '#185FA5', text: '#E6F1FB' };
    if (gen <= 5) return { fill: '#185FA5', stroke: '#378ADD', text: '#E6F1FB' };
    return { fill: '#3B6D11', stroke: '#639922', text: '#EAF3DE' };
  };

  return (
    <svg
      width="100%"
      viewBox={`0 0 ${SVG_W} ${SVG_H}`}
      style={{ display: 'block' }}
    >
      <defs>
        <marker id="arr" viewBox="0 0 10 10" refX="8" refY="5"
          markerWidth="6" markerHeight="6" orient="auto">
          <path d="M2 1L8 5L2 9" fill="none" stroke="#888" strokeWidth="1.5"
            strokeLinecap="round" strokeLinejoin="round" />
        </marker>
      </defs>

      {/* Generation labels on left */}
      {generations.map((gen, genIdx) => {
        const y = PADDING_TOP + genIdx * (NODE_H + V_GAP) + NODE_H / 2;
        const label = GENERATION_LABELS[gen] || `generation ${gen}`;
        return (
          <text
            key={`label-${gen}`}
            x="10"
            y={y + 5}
            fontSize="11"
            fill="#888"
            fontFamily="sans-serif"
            fontStyle="italic"
          >
            {label}
          </text>
        );
      })}

      {/* Connector lines */}
      {lines.map(line => (
        <line
          key={line.key}
          x1={line.x1}
          y1={line.y1}
          x2={line.x2}
          y2={line.y2}
          stroke="#aaa"
          strokeWidth="1.5"
          markerEnd="url(#arr)"
          strokeDasharray="5 3"
          style={{
            opacity: animatedLines.includes(line.key) ? 1 : 0,
            transition: 'opacity 0.4s ease',
            strokeDashoffset: animatedLines.includes(line.key) ? 0 : 20,
          }}
        />
      ))}

      {/* Nodes */}
      {Object.entries(nodePositions).map(([key, pos]) => {
        const { x, y, node } = pos;
        const color = getNodeColor(node);
        const isVisible = animatedNodes.includes(key);
        const name = node.person_name || 'Unknown';
        const shortName = name.length > 20 ? name.substring(0, 18) + '…' : name;
        const relation = node.relation_type || '';
        const shortRelation = relation.length > 22 ? relation.substring(0, 20) + '…' : relation;

        return (
          <g
            key={key}
            style={{
              opacity: isVisible ? 1 : 0,
              transform: isVisible ? 'translateY(0)' : 'translateY(-10px)',
              transition: 'opacity 0.4s ease, transform 0.4s ease',
            }}
          >
            <rect
              x={x}
              y={y}
              width={NODE_W}
              height={NODE_H}
              rx="8"
              fill={color.fill}
              stroke={color.stroke}
              strokeWidth="1"
            />
            <text
              x={x + NODE_W / 2}
              y={y + 20}
              textAnchor="middle"
              fontSize="13"
              fontWeight="500"
              fill={color.text}
              fontFamily="sans-serif"
              dominantBaseline="central"
            >
              {shortName}
            </text>
            {shortRelation && (
              <text
                x={x + NODE_W / 2}
                y={y + 38}
                textAnchor="middle"
                fontSize="10"
                fill={color.text}
                fontFamily="sans-serif"
                dominantBaseline="central"
                opacity="0.8"
              >
                {shortRelation}
              </text>
            )}
          </g>
        );
      })}

      {/* Generation connector dots */}
      {generations.slice(0, -1).map((gen, genIdx) => {
        const y = PADDING_TOP + genIdx * (NODE_H + V_GAP) + NODE_H + V_GAP / 2;
        return (
          <circle key={`dot-${gen}`} cx={SVG_W / 2} cy={y} r="3" fill="#ccc" />
        );
      })}
    </svg>
  );
}

function FamilyTree({ apiUrl }) {
  const [personName, setPersonName] = useState('');
  const [familyData, setFamilyData] = useState(null);
  const [docChunks, setDocChunks] = useState([]);
  const [aiSummary, setAiSummary] = useState('');
  const [loading, setLoading] = useState(false);
  const [loadingAI, setLoadingAI] = useState(false);
  const [error, setError] = useState('');
  const [activeView, setActiveView] = useState('chart');

  const handleSearch = async (e) => {
    e.preventDefault();
    if (!personName.trim()) { setError('Please enter a name'); return; }

    setLoading(true);
    setError('');
    setFamilyData(null);
    setDocChunks([]);
    setAiSummary('');

    try {
      const [familyRes, searchRes] = await Promise.all([
        axios.get(`${apiUrl}/queries/family/${encodeURIComponent(personName)}`),
        axios.post(`${apiUrl}/queries/search`, {
          query: `${personName} family ancestors descendants lineage generation`,
          include_documents: true,
          include_ancestry_data: false
        })
      ]);

      setFamilyData(familyRes.data);
      setDocChunks(searchRes.data.document_chunks || []);
    } catch (err) {
      setError(`Error: ${err.response?.data?.detail || err.message}`);
    } finally {
      setLoading(false);
    }
  };

  const handleAskAI = async () => {
    setLoadingAI(true);
    setAiSummary('');
    try {
      const response = await axios.post(
        `${apiUrl}/queries/ask`,
        {
          query: `What is the complete family lineage of ${personName}? List each generation from the earliest ancestor down to descendants. Include names, dates, and relationships.`,
          include_context: true
        },
        { timeout: 300000 }
      );
      setAiSummary(response.data.response);
    } catch (err) {
      setAiSummary(`Error: ${err.response?.data?.detail || err.message}`);
    } finally {
      setLoadingAI(false);
    }
  };

  const people = familyData?.family_tree || [];
  const hasResults = people.length > 0 || docChunks.length > 0;

  return (
    <div className="family-tree-container">
      <div className="family-tree-header">
        <h2>👨‍👩‍👧‍👦 Family Lineage Explorer</h2>
        <p className="family-subtitle">
          Search for a person to see their animated generational lineage chart
        </p>
        <form onSubmit={handleSearch} className="search-form">
          <input
            type="text"
            value={personName}
            onChange={(e) => setPersonName(e.target.value)}
            placeholder="e.g. Henry Gowen, Caesar Russell, Joshua Perkins..."
            className="search-input"
            disabled={loading}
          />
          <button type="submit" disabled={loading || !personName.trim()} className="search-button">
            {loading ? '🔍 Searching...' : '🔍 Search'}
          </button>
        </form>
      </div>

      {error && <div className="error-message">{error}</div>}

      {hasResults && (
        <div className="results-container">
          <div className="results-summary">
            <div className="summary-stats">
              <span className="stat-pill">👤 {people.length} ancestry records</span>
              <span className="stat-pill">📄 {docChunks.length} document refs</span>
            </div>
            <button className="ai-button" onClick={handleAskAI} disabled={loadingAI}>
              {loadingAI ? '⏳ Generating...' : '🤖 Ask AI for Full Lineage'}
            </button>
          </div>

          {aiSummary && (
            <div className="ai-summary">
              <h4>🤖 AI Lineage Summary</h4>
              <p>{aiSummary}</p>
            </div>
          )}

          <div className="view-toggle">
            <button className={`toggle-btn ${activeView === 'chart' ? 'active' : ''}`} onClick={() => setActiveView('chart')}>
              🌳 Lineage Chart ({people.length})
            </button>
            <button className={`toggle-btn ${activeView === 'documents' ? 'active' : ''}`} onClick={() => setActiveView('documents')}>
              📄 Document References ({docChunks.length})
            </button>
          </div>

          {activeView === 'chart' && (
            <div className="chart-view">
              {people.length === 0 ? (
                <div className="empty-state">
                  <p>No structured ancestry records found for <strong>{personName}</strong>.</p>
                  <p>Check 📄 Document References or click 🤖 Ask AI for Full Lineage.</p>
                </div>
              ) : (
                <>
                  <div className="chart-legend">
                    <span className="legend-item ancestor">Earliest ancestors</span>
                    <span className="legend-item mid">Grandparents / Parents</span>
                    <span className="legend-item subject">Subject</span>
                    <span className="legend-item descendant">Descendants</span>
                  </div>
                  <div className="chart-container">
                    <LineageFlowchart people={people} anchorName={personName} />
                  </div>
                </>
              )}
            </div>
          )}

          {activeView === 'documents' && (
            <div className="doc-view">
              {docChunks.length === 0 ? (
                <div className="empty-state">
                  <p>No document references found for <strong>{personName}</strong>.</p>
                </div>
              ) : (
                docChunks.map((chunk, idx) => (
                  <div key={idx} className="doc-chunk">
                    <div className="chunk-header">
                      <span className="chunk-source">📄 {chunk.document_title}</span>
                      <span className="chunk-score">{(chunk.similarity_score * 100).toFixed(1)}% match</span>
                    </div>
                    <p className="chunk-text">{chunk.text}</p>
                    {chunk.footnotes && chunk.footnotes.length > 0 && (
                      <div className="chunk-footnotes">
                        {chunk.footnotes.map((fn, fnIdx) => (
                          <div key={fnIdx} className="footnote-ref">
                            <span className="fn-number">[{fn.number}]</span>
                            <span className="fn-text">{fn.citation}</span>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                ))
              )}
            </div>
          )}
        </div>
      )}

      {!hasResults && !loading && !error && (
        <div className="initial-state">
          <div className="initial-icon">🌳</div>
          <h3>Animated Lineage Flowchart</h3>
          <p>Search for any person to see their family tree as an animated generational chart — from earliest ancestors at the top down to descendants at the bottom.</p>
          <div className="suggested-searches">
            <p><strong>Try searching for:</strong></p>
            <div className="suggestions">
              {['Henry Gowen', 'Caesar Russell', 'Joshua Perkins', 'Harriet Gowen', 'Ishmael Roberts'].map(name => (
                <button key={name} className="suggestion-chip" onClick={() => setPersonName(name)}>
                  {name}
                </button>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default FamilyTree;