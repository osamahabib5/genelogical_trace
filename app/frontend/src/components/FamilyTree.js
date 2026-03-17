import React, { useState, useEffect, useRef, useCallback } from 'react';
import axios from 'axios';

// ── Generation helpers ──────────────────────────────────────────────────────
const GENERATION_LABELS = [
  '4th great-grandparent', '3rd great-grandparent', '2nd great-grandparent',
  'great-grandparent', 'grandparent', 'parent', 'self',
  'child', 'grandchild', 'great-grandchild',
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

// ── Colour palette per generation ──────────────────────────────────────────
const GEN_COLORS = [
  { bg: '#1a0a2e', border: '#7c3aed', text: '#e9d5ff', glow: 'rgba(124,58,237,0.5)' },
  { bg: '#0d1f3c', border: '#2563eb', text: '#bfdbfe', glow: 'rgba(37,99,235,0.5)' },
  { bg: '#0f2a1e', border: '#059669', text: '#a7f3d0', glow: 'rgba(5,150,105,0.5)' },
  { bg: '#1c1a0a', border: '#d97706', text: '#fde68a', glow: 'rgba(217,119,6,0.5)' },
  { bg: '#1a1030', border: '#7c3aed', text: '#ddd6fe', glow: 'rgba(124,58,237,0.4)' },
  { bg: '#0c2233', border: '#0ea5e9', text: '#bae6fd', glow: 'rgba(14,165,233,0.5)' },
  { bg: '#4c1d95', border: '#a78bfa', text: '#ffffff', glow: 'rgba(167,139,250,0.8)' }, // self — brightest
  { bg: '#064e3b', border: '#34d399', text: '#d1fae5', glow: 'rgba(52,211,153,0.5)' },
  { bg: '#1e3a1e', border: '#4ade80', text: '#bbf7d0', glow: 'rgba(74,222,128,0.4)' },
  { bg: '#14291a', border: '#22c55e', text: '#dcfce7', glow: 'rgba(34,197,94,0.4)' },
];

function getNodeColors(node) {
  const gen = getGenerationOrder(node.relation_type);
  if (node.isAnchor || gen === 6) return GEN_COLORS[6];
  return GEN_COLORS[Math.min(gen, GEN_COLORS.length - 1)];
}



// ── LineageFlowchart ────────────────────────────────────────────────────────
function LineageFlowchart({ people, anchorName }) {
  const [visibleNodes, setVisibleNodes] = useState(new Set());
  const [visibleLines, setVisibleLines] = useState(new Set());
  const [tooltip, setTooltip] = useState(null);

  const grouped = {};
  people.forEach(p => {
    const gen = getGenerationOrder(p.relation_type);
    if (!grouped[gen]) grouped[gen] = [];
    grouped[gen].push(p);
  });

  const hasAnchor = people.some(p => getGenerationOrder(p.relation_type) === 6);
  if (!hasAnchor) {
    if (!grouped[6]) grouped[6] = [];
    grouped[6].push({ person_name: anchorName, relation_type: 'self', isAnchor: true });
  }

  const generations = Object.keys(grouped).map(Number).sort((a, b) => a - b);
  const NODE_W = 172;
  const NODE_H = 60;
  const V_GAP  = 90;
  const H_GAP  = 16;
  const LABEL_W = 130;
  const PADDING_TOP = 50;
  const SVG_W = 900;

  const nodePositions = {};
  generations.forEach((gen, genIdx) => {
    const nodes = grouped[gen];
    const totalW = nodes.length * NODE_W + (nodes.length - 1) * H_GAP;
    const startX = LABEL_W + (SVG_W - LABEL_W - totalW) / 2;
    const y = PADDING_TOP + genIdx * (NODE_H + V_GAP);
    nodes.forEach((node, i) => {
      const key = `${gen}-${i}`;
      nodePositions[key] = { x: startX + i * (NODE_W + H_GAP), y, node, gen };
    });
  });

  const SVG_H = PADDING_TOP + generations.length * (NODE_H + V_GAP) + 60;

  // Build lines — only connect adjacent gens
  const lines = [];
  for (let i = 0; i < generations.length - 1; i++) {
    const topGen = generations[i];
    const botGen = generations[i + 1];
    const topNodes = grouped[topGen];
    const botNodes = grouped[botGen];
    topNodes.forEach((_, ti) => {
      const tp = nodePositions[`${topGen}-${ti}`];
      botNodes.forEach((_, bi) => {
        const bp = nodePositions[`${botGen}-${bi}`];
        lines.push({
          x1: tp.x + NODE_W / 2, y1: tp.y + NODE_H,
          x2: bp.x + NODE_W / 2, y2: bp.y,
          key: `${topGen}-${ti}--${botGen}-${bi}`,
          topGen
        });
      });
    });
  }

  // Staggered entrance animation
  useEffect(() => {
    setVisibleNodes(new Set());
    setVisibleLines(new Set());
    const nodeKeys = Object.keys(nodePositions);
    nodeKeys.forEach((key, i) => {
      setTimeout(() => setVisibleNodes(prev => new Set([...prev, key])), 80 + i * 100);
    });
    lines.forEach((line, i) => {
      setTimeout(() => setVisibleLines(prev => new Set([...prev, line.key])), 80 + nodeKeys.length * 100 + i * 40);
    });
  }, [people.length, anchorName]);

  const handleMouseEnter = useCallback((e, node) => {
    setTooltip({ x: e.clientX + 14, y: e.clientY - 10, node });
  }, []);
  const handleMouseMove = useCallback((e) => {
    setTooltip(prev => prev ? { ...prev, x: e.clientX + 14, y: e.clientY - 10 } : prev);
  }, []);
  const handleMouseLeave = useCallback(() => setTooltip(null), []);

  return (
    <>
      <svg width="100%" viewBox={`0 0 ${SVG_W} ${SVG_H}`} style={{ display: 'block', minWidth: 640 }}>
        <defs>
          <marker id="arr-purple" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto">
            <path d="M2 1L8 5L2 9" fill="none" stroke="#7c3aed" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
          </marker>
          <marker id="arr-blue" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto">
            <path d="M2 1L8 5L2 9" fill="none" stroke="#0ea5e9" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
          </marker>
          <filter id="glow-purple" x="-40%" y="-40%" width="180%" height="180%">
            <feGaussianBlur stdDeviation="4" result="blur"/>
            <feMerge><feMergeNode in="blur"/><feMergeNode in="SourceGraphic"/></feMerge>
          </filter>
          <filter id="glow-gold" x="-40%" y="-40%" width="180%" height="180%">
            <feGaussianBlur stdDeviation="6" result="blur"/>
            <feMerge><feMergeNode in="blur"/><feMergeNode in="SourceGraphic"/></feMerge>
          </filter>
          {GEN_COLORS.map((c, i) => (
            <linearGradient key={i} id={`ng-${i}`} x1="0%" y1="0%" x2="100%" y2="100%">
              <stop offset="0%" stopColor={c.bg}/>
              <stop offset="100%" stopColor={c.bg} stopOpacity="0.7"/>
            </linearGradient>
          ))}
        </defs>

        {/* Generation labels */}
        {generations.map((gen, gi) => {
          const y = PADDING_TOP + gi * (NODE_H + V_GAP) + NODE_H / 2;
          const label = GENERATION_LABELS[gen] || `gen ${gen}`;
          return (
            <text key={`lbl-${gen}`} x={LABEL_W - 12} y={y + 5}
              fontSize="10" fill="rgba(139,122,168,0.7)"
              fontFamily="Raleway, sans-serif" fontStyle="italic"
              textAnchor="end">
              {label}
            </text>
          );
        })}

        {/* Connector lines */}
        {lines.map(line => {
          const isSubjectLine = line.topGen === 6 || generations[generations.indexOf(line.topGen) + 1] === 6;
          const col = isSubjectLine ? '#7c3aed' : 'rgba(255,255,255,0.12)';
          const marker = isSubjectLine ? 'url(#arr-purple)' : 'url(#arr-blue)';
          const vis = visibleLines.has(line.key);
          const mx = (line.x1 + line.x2) / 2;
          const my = (line.y1 + line.y2) / 2;
          return (
            <path
              key={line.key}
              d={`M${line.x1},${line.y1} C${line.x1},${my} ${line.x2},${my} ${line.x2},${line.y2}`}
              fill="none"
              stroke={col}
              strokeWidth={isSubjectLine ? 1.5 : 0.8}
              strokeDasharray="4 3"
              markerEnd={marker}
              style={{
                opacity: vis ? 1 : 0,
                transition: 'opacity 0.5s ease',
              }}
            />
          );
        })}

        {/* Nodes */}
        {Object.entries(nodePositions).map(([key, pos]) => {
          const { x, y, node, gen } = pos;
          const isSubject = node.isAnchor || gen === 6;
          const colors = getNodeColors(node);
          const vis = visibleNodes.has(key);
          const name = node.person_name || 'Unknown';
          const shortName = name.length > 19 ? name.substring(0, 17) + '…' : name;
          const rel = node.relation_type || '';
          const shortRel = rel.length > 20 ? rel.substring(0, 18) + '…' : rel;
          const colorIdx = Math.min(gen, GEN_COLORS.length - 1);

          return (
            <g
              key={key}
              className={isSubject ? 'node-subject' : ''}
              style={{
                opacity: vis ? 1 : 0,
                transform: vis ? 'none' : 'translateY(-8px)',
                transition: `opacity 0.45s ease, transform 0.45s ease`,
                cursor: 'pointer',
              }}
              onMouseEnter={e => handleMouseEnter(e, node)}
              onMouseMove={handleMouseMove}
              onMouseLeave={handleMouseLeave}
            >
              {/* Glow halo for subject */}
              {isSubject && (
                <rect x={x - 4} y={y - 4} width={NODE_W + 8} height={NODE_H + 8}
                  rx="14" fill="none"
                  stroke="rgba(167,139,250,0.4)" strokeWidth="1.5"
                  filter="url(#glow-purple)"
                  style={{ animation: 'pulseBorder 2s ease-in-out infinite' }}
                />
              )}
              {/* Node background */}
              <rect x={x} y={y} width={NODE_W} height={NODE_H} rx="10"
                fill={`url(#ng-${colorIdx})`}
                stroke={colors.border}
                strokeWidth={isSubject ? 2 : 1}
                filter={isSubject ? 'url(#glow-purple)' : undefined}
              />
              {/* Shimmer line at top */}
              <rect x={x + 12} y={y} width={NODE_W - 24} height="2" rx="1"
                fill={colors.border} opacity="0.6"/>
              {/* Name */}
              <text x={x + NODE_W / 2} y={y + (shortRel ? 22 : 32)}
                textAnchor="middle" fontSize="13" fontWeight="600"
                fill={colors.text} fontFamily="Raleway, sans-serif"
                dominantBaseline="central">
                {shortName}
              </text>
              {/* Relation */}
              {shortRel && (
                <text x={x + NODE_W / 2} y={y + 43}
                  textAnchor="middle" fontSize="10"
                  fill={colors.border} fontFamily="Raleway, sans-serif"
                  dominantBaseline="central" opacity="0.9">
                  {shortRel}
                </text>
              )}
            </g>
          );
        })}

        {/* Timeline dots between gens */}
        {generations.slice(0, -1).map((gen, gi) => {
          const cy = PADDING_TOP + gi * (NODE_H + V_GAP) + NODE_H + V_GAP / 2;
          return (
            <g key={`dot-${gen}`}>
              <circle cx={SVG_W / 2} cy={cy} r="4" fill="none" stroke="rgba(255,255,255,0.15)" strokeWidth="1"/>
              <circle cx={SVG_W / 2} cy={cy} r="2" fill="rgba(124,58,237,0.5)"/>
            </g>
          );
        })}
      </svg>

      {/* Floating tooltip */}
      {tooltip && (
        <div className="ft-tooltip" style={{ left: tooltip.x, top: tooltip.y }}>
          <div className="ft-tooltip-name">{tooltip.node.person_name || 'Unknown'}</div>
          <div className="ft-tooltip-rel">{tooltip.node.relation_type || '—'}</div>
          {tooltip.node.birth_date && <div style={{ fontSize: '0.72rem', color: '#d4a843', marginTop: 3 }}>b. {tooltip.node.birth_date}</div>}
          {tooltip.node.birth_location && <div style={{ fontSize: '0.72rem', color: '#9ca3af' }}>{tooltip.node.birth_location}</div>}
        </div>
      )}
    </>
  );
}

// ── Legend ──────────────────────────────────────────────────────────────────
const LEGEND_ITEMS = [
  { label: 'Earliest ancestors', color: GEN_COLORS[0].border },
  { label: 'Grandparents / Parents', color: GEN_COLORS[4].border },
  { label: 'Subject', color: GEN_COLORS[6].border },
  { label: 'Descendants', color: GEN_COLORS[7].border },
];

// ── Main FamilyTree component ───────────────────────────────────────────────
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
    setLoading(true); setError(''); setFamilyData(null); setDocChunks([]); setAiSummary('');
    try {
      const [familyRes, searchRes] = await Promise.all([
        axios.get(`${apiUrl}/queries/family/${encodeURIComponent(personName)}`),
        axios.post(`${apiUrl}/queries/search`, {
          query: `${personName} family ancestors descendants lineage generation`,
          include_documents: true, include_ancestry_data: false
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
    setLoadingAI(true); setAiSummary('');
    try {
      const res = await axios.post(`${apiUrl}/queries/ask`, {
        query: `What is the complete family lineage of ${personName}? List each generation from the earliest ancestor down to descendants. Include names, dates, and relationships.`,
        include_context: true
      }, { timeout: 300000 });
      setAiSummary(res.data.response);
    } catch (err) {
      setAiSummary(`Error: ${err.response?.data?.detail || err.message}`);
    } finally {
      setLoadingAI(false);
    }
  };

  const people = familyData?.family_tree || [];
  const hasResults = people.length > 0 || docChunks.length > 0;

  return (
    <div className="ft-wrap">
      <div className="ft-inner">

        {/* Header */}
        <div className="ft-header">
          <h1 className="ft-title">Family Lineage Explorer</h1>
          <p className="ft-subtitle">Trace ancestral lines across generations</p>
          <form onSubmit={handleSearch} className="ft-search-form">
            <input
              type="text" value={personName}
              onChange={e => setPersonName(e.target.value)}
              placeholder="e.g. Henry Gowen, Caesar Russell, Joshua Perkins…"
              className="ft-search-input" disabled={loading}
            />
            <button type="submit" disabled={loading || !personName.trim()} className="ft-search-btn">
              {loading ? 'Searching…' : 'Search'}
            </button>
          </form>
        </div>

        {error && <div className="ft-error">{error}</div>}

        {loading && (
          <div className="ft-loading">
            <div className="ft-spinner"/>
            Tracing lineage…
          </div>
        )}

        {hasResults && !loading && (
          <>
            {/* Stats + AI button */}
            <div className="ft-stats">
              <div className="ft-pills">
                <span className="ft-pill">👤 {people.length} ancestry records</span>
                <span className="ft-pill">📄 {docChunks.length} document refs</span>
              </div>
              <button className="ft-ai-btn" onClick={handleAskAI} disabled={loadingAI}>
                {loadingAI ? '⏳ Generating…' : '✦ Ask AI for Full Lineage'}
              </button>
            </div>

            {/* AI Summary */}
            {aiSummary && (
              <div className="ft-ai-summary">
                <h4>✦ AI LINEAGE SUMMARY</h4>
                <p>{aiSummary}</p>
              </div>
            )}

            {/* View toggle */}
            <div className="ft-toggle">
              <button className={`ft-toggle-btn ${activeView === 'chart' ? 'active' : ''}`} onClick={() => setActiveView('chart')}>
                🌳 Lineage Chart ({people.length})
              </button>
              <button className={`ft-toggle-btn ${activeView === 'documents' ? 'active' : ''}`} onClick={() => setActiveView('documents')}>
                📄 Document References ({docChunks.length})
              </button>
            </div>

            {/* Chart view */}
            {activeView === 'chart' && (
              <>
                {people.length === 0 ? (
                  <div className="ft-empty">
                    <div className="ft-empty-icon">🔍</div>
                    <h3>No ancestry records found</h3>
                    <p>No structured records found for <strong>{personName}</strong>. Try Document References or Ask AI.</p>
                  </div>
                ) : (
                  <>
                    <div className="ft-legend">
                      {LEGEND_ITEMS.map(item => (
                        <div key={item.label} className="ft-legend-item">
                          <div className="ft-legend-dot" style={{ background: item.color }}/>
                          <span>{item.label}</span>
                        </div>
                      ))}
                    </div>
                    <div className="ft-chart-scroll">
                      <LineageFlowchart people={people} anchorName={personName}/>
                    </div>
                  </>
                )}
              </>
            )}

            {/* Documents view */}
            {activeView === 'documents' && (
              <>
                {docChunks.length === 0 ? (
                  <div className="ft-empty">
                    <div className="ft-empty-icon">📄</div>
                    <h3>No document references</h3>
                    <p>No documents found for <strong>{personName}</strong>.</p>
                  </div>
                ) : (
                  docChunks.map((chunk, idx) => (
                    <div key={idx} className="ft-doc-chunk">
                      <div className="ft-doc-header">
                        <span className="ft-doc-source">📄 {chunk.document_title}</span>
                        <span className="ft-doc-score">{(chunk.similarity_score * 100).toFixed(1)}% match</span>
                      </div>
                      <p className="ft-doc-text">{chunk.text}</p>
                      {chunk.footnotes?.length > 0 && (
                        <div style={{ marginTop: '0.75rem', borderTop: '1px solid rgba(255,255,255,0.06)', paddingTop: '0.5rem' }}>
                          {chunk.footnotes.map((fn, fi) => (
                            <div key={fi} className="ft-footnote">
                              <span className="ft-fn-num">[{fn.number}]</span>
                              <span>{fn.citation}</span>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  ))
                )}
              </>
            )}
          </>
        )}

        {/* Initial state */}
        {!hasResults && !loading && !error && (
          <div className="ft-empty" style={{ marginTop: '2rem' }}>
            <div className="ft-empty-icon">🌳</div>
            <h3>Animated Lineage Flowchart</h3>
            <p>Search for any person to see their family tree as an animated generational chart — earliest ancestors at top, descendants below.</p>
            <div className="ft-suggestions">
              {['Henry Gowen', 'Caesar Russell', 'Joshua Perkins', 'Harriet Gowen', 'Ishmael Roberts'].map(name => (
                <button key={name} className="ft-suggestion" onClick={() => setPersonName(name)}>{name}</button>
              ))}
            </div>
          </div>
        )}

      </div>
    </div>
  );
}

export default FamilyTree;