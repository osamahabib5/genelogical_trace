import React, { useState } from 'react';
import axios from 'axios';
import './Chatbot.css';

function Chatbot({ apiUrl }) {
  const [messages, setMessages] = useState([
    {
      id: 1,
      text: "Hello! I'm your genealogy assistant. I can help you trace African American ancestry through historical documents and records. Ask me about family connections, dates, locations, or specific people!",
      sender: 'bot',
      timestamp: new Date()
    }
  ]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const handleSendMessage = async (e) => {
    e.preventDefault();
    if (!input.trim()) return;

    const userMessage = {
      id: messages.length + 1,
      text: input,
      sender: 'user',
      timestamp: new Date()
    };

    setMessages(prev => [...prev, userMessage]);
    setInput('');
    setLoading(true);
    setError('');

    try {
      const response = await axios.post(
        `${apiUrl}/queries/ask`,
        { query: input, include_context: true },
        { timeout: 300000 }
      );

      const botMessage = {
        id: messages.length + 2,
        text: response.data.response,
        sender: 'bot',
        timestamp: new Date(),
        sources: response.data.sources,
        responseTime: response.data.response_time_seconds
      };

      setMessages(prev => [...prev, botMessage]);
    } catch (err) {
      setError(`Error: ${err.response?.data?.detail || err.message}`);
    } finally {
      setLoading(false);
    }
  };

  const formatResponseTime = (seconds) => {
    if (seconds < 60) return `${seconds}s`;
    const mins = Math.floor(seconds / 60);
    const secs = (seconds % 60).toFixed(1);
    return `${mins}m ${secs}s`;
  };

  return (
    <div className="chatbot-container">
      <div className="chatbot-messages">
        {messages.map((message) => (
          <div key={message.id} className={`message message-${message.sender}`}>
            <div className="message-content">
              <p>{message.text}</p>

              {/* Response time */}
              {message.responseTime !== undefined && (
                <div className="response-time">
                  ⏱ Answered in {formatResponseTime(message.responseTime)}
                </div>
              )}

              {/* Sources with footnote citations */}
              {message.sources && message.sources.length > 0 && (
                <div className="message-sources">
                  <strong>Sources:</strong>
                  {message.sources.map((source, idx) => (
                    <div key={idx} className="source-item">

                      {source.document_title && (
                        <div className="source-doc-block">
                          <span className="source-doc">
                            📄 {source.document_title}
                            {source.similarity_score && (
                              <span className="source-score">
                                {' '}({(source.similarity_score * 100).toFixed(1)}% match)
                              </span>
                            )}
                          </span>

                          {/* Show footnote citations if available */}
                          {source.footnotes && source.footnotes.length > 0 ? (
                            <div className="source-footnotes">
                              {source.footnotes.map((fn, fnIdx) => (
                                <div key={fnIdx} className="footnote-citation">
                                  <span className="footnote-number">[{fn.number}]</span>
                                  <span className="footnote-text">{fn.citation}</span>
                                </div>
                              ))}
                            </div>
                          ) : (
                            source.page_number && (
                              <span className="source-page"> — Page {source.page_number}</span>
                            )
                          )}
                        </div>
                      )}

                      {source.person_name && (
                        <span className="source-person">👤 {source.person_name}</span>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>
            <span className="message-time">
              {message.timestamp.toLocaleTimeString()}
            </span>
          </div>
        ))}

        {loading && (
          <div className="message message-bot">
            <div className="message-content">
              <div className="typing-indicator">
                <span></span><span></span><span></span>
              </div>
              <p className="loading-text">Searching documents and generating response...</p>
            </div>
          </div>
        )}
      </div>

      {error && <div className="chatbot-error">{error}</div>}

      <form onSubmit={handleSendMessage} className="chatbot-form">
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Ask about ancestry, people, family connections..."
          className="chatbot-input"
          disabled={loading}
        />
        <button
          type="submit"
          className="chatbot-send-button"
          disabled={loading || !input.trim()}
        >
          {loading ? 'Thinking...' : 'Send'}
        </button>
      </form>
    </div>
  );
}

export default Chatbot;