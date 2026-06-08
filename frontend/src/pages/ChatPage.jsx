import { useEffect, useState, useRef } from "react";
import { useLocation } from "react-router-dom";
import { useAuth } from "../hooks/useAuth";
import { useChat } from "../hooks/useChat";
import { useDocuments } from "../hooks/useDocuments";

const getDocName = (d) => d?.original_filename || d?.filename || "Untitled";
const getDocShort = (d, max = 30) => {
  const n = getDocName(d);
  return n.length > max ? n.slice(0, max) + "…" : n;
};

export default function ChatPage() {
  const { user } = useAuth();
  const location = useLocation();
  const {
    sessions, activeSession, messages, sending, loading,
    fetchSessions, openSession, createSession, updateTitle, deleteSession, sendMessage,
  } = useChat();
  const { documents, fetchDocuments } = useDocuments();

  const [input, setInput]                   = useState("");
  const [selectedDoc, setSelectedDoc]       = useState(null);
  const [editingTitle, setEditingTitle]     = useState(null);
  const [titleInput, setTitleInput]         = useState("");
  const [showDocPicker, setShowDocPicker]   = useState(false);
  const [hoveredSession, setHoveredSession] = useState(null);
  const bottomRef = useRef();

  useEffect(() => {
    fetchSessions();
    fetchDocuments();
  }, []);

  useEffect(() => {
    if (location.state?.documentId && documents.length > 0) {
      const doc = documents.find((d) => d.id === location.state.documentId);
      if (doc) setSelectedDoc(doc);
    }
  }, [location.state, documents]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  // Close doc picker on outside click
  useEffect(() => {
    if (!showDocPicker) return;
    const handler = () => setShowDocPicker(false);
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [showDocPicker]);

  const readyDocs = documents.filter((d) => d.status === "ready");

  const handleSend = async () => {
    if (!input.trim() || sending) return;
    const text = input.trim();
    setInput("");
    if (!activeSession) {
      const session = await createSession(selectedDoc?.id || null);
      if (session) await sendMessage(text, selectedDoc?.id || null);
    } else {
      await sendMessage(text, selectedDoc?.id || null);
    }
  };

  const handleKeyDown = (e) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); handleSend(); }
  };

  const handleTitleSave = async (sessionId) => {
    if (titleInput.trim()) await updateTitle(sessionId, titleInput.trim());
    setEditingTitle(null);
  };

  const formatTime = (iso) => {
    if (!iso) return "";
    return new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  };

  return (
    <div style={s.page}>
      <style>{`
        @keyframes bounce3 { 0%,80%,100%{transform:translateY(0)} 40%{transform:translateY(-6px)} }
        @keyframes fadeIn   { from{opacity:0;transform:translateY(6px)} to{opacity:1;transform:translateY(0)} }
      `}</style>

      {/* ── Sessions Sidebar ── */}
      <aside style={s.sidebar}>
        <div style={s.sideHead}>
          <span style={s.sideTitle}>Conversations</span>
          <button
            style={s.newBtn}
            title="New chat"
            onClick={() => createSession(selectedDoc?.id || null)}
          >
            <svg width="14" height="14" viewBox="0 0 20 20" fill="none">
              <path d="M10 4v12M4 10h12" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
            </svg>
          </button>
        </div>

        {/* Document context for new chats */}
        <div style={s.docSelectorWrap} onClick={(e) => e.stopPropagation()}>
          <button
            style={s.docSelectorBtn}
            onClick={() => setShowDocPicker(!showDocPicker)}
          >
            <svg width="12" height="12" viewBox="0 0 20 20" fill="none">
              <path d="M4 2h8l4 4v12a2 2 0 01-2 2H4a2 2 0 01-2-2V4a2 2 0 012-2z"
                stroke="currentColor" strokeWidth="1.7" />
            </svg>
            <span style={s.docSelectorLabel}>
              {selectedDoc ? getDocShort(selectedDoc, 22) : "No document selected"}
            </span>
            <svg width="9" height="9" viewBox="0 0 12 12" fill="none">
              <path d="M2 4l4 4 4-4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
            </svg>
          </button>

          {showDocPicker && (
            <div style={s.dropdown}>
              <div
                style={{ ...s.dropItem, ...(selectedDoc === null ? s.dropItemActive : {}) }}
                onClick={() => { setSelectedDoc(null); setShowDocPicker(false); }}
              >
                <svg width="12" height="12" viewBox="0 0 20 20" fill="none">
                  <path d="M2 4a2 2 0 012-2h12a2 2 0 012 2v8a2 2 0 01-2 2H6l-4 4V4z"
                    stroke="#64748b" strokeWidth="1.7" />
                </svg>
                <span style={{ flex: 1 }}>General chat</span>
                {!selectedDoc && <span style={s.checkMark}>✓</span>}
              </div>

              {readyDocs.length === 0 && (
                <div style={s.dropDisabled}>No ready documents</div>
              )}

              {readyDocs.map((d) => (
                <div
                  key={d.id}
                  style={{ ...s.dropItem, ...(selectedDoc?.id === d.id ? s.dropItemActive : {}) }}
                  onClick={() => { setSelectedDoc(d); setShowDocPicker(false); }}
                >
                  <svg width="12" height="12" viewBox="0 0 20 20" fill="none">
                    <path d="M4 2h8l4 4v12a2 2 0 01-2 2H4a2 2 0 01-2-2V4a2 2 0 012-2z"
                      stroke="#2563eb" strokeWidth="1.7" />
                  </svg>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ color: "#0f172a", fontSize: "12px", fontWeight: "500",
                      overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                      {getDocName(d)}
                    </div>
                    {d.ocr?.total_pages && (
                      <div style={{ color: "#94a3b8", fontSize: "10px" }}>{d.ocr.total_pages} pages</div>
                    )}
                  </div>
                  {selectedDoc?.id === d.id && <span style={s.checkMark}>✓</span>}
                </div>
              ))}
            </div>
          )}
        </div>

        <div style={s.sessionList}>
          {sessions.length === 0 && (
            <div style={s.noSessions}>No conversations yet.<br />Type a message to start.</div>
          )}

          {sessions.map((sess) => (
            <div
              key={sess.id}
              style={{
                ...s.sessionItem,
                ...(activeSession?.id === sess.id ? s.sessionActive : {}),
                background: activeSession?.id === sess.id
                  ? "#eff6ff"
                  : hoveredSession === sess.id ? "#f8fafc" : "transparent",
              }}
              onClick={() => openSession(sess.id)}
              onMouseEnter={() => setHoveredSession(sess.id)}
              onMouseLeave={() => setHoveredSession(null)}
            >
              {editingTitle === sess.id ? (
                <input
                  style={s.titleInput}
                  value={titleInput}
                  autoFocus
                  onChange={(e) => setTitleInput(e.target.value)}
                  onBlur={() => handleTitleSave(sess.id)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter")  handleTitleSave(sess.id);
                    if (e.key === "Escape") setEditingTitle(null);
                  }}
                  onClick={(e) => e.stopPropagation()}
                />
              ) : (
                <>
                  <div style={s.sessRow}>
                    <svg width="11" height="11" viewBox="0 0 20 20" fill="none" style={{ flexShrink: 0 }}>
                      <path d="M2 4a2 2 0 012-2h12a2 2 0 012 2v8a2 2 0 01-2 2H6l-4 4V4z"
                        stroke={activeSession?.id === sess.id ? "#2563eb" : "#94a3b8"}
                        strokeWidth="1.7" strokeLinejoin="round" />
                    </svg>
                    <span style={s.sessTitle}>{sess.title || "New Chat"}</span>
                    <div style={{
                      ...s.sessActions,
                      opacity: hoveredSession === sess.id || activeSession?.id === sess.id ? 1 : 0,
                    }}>
                      <button
                        style={s.iconBtn}
                        title="Rename"
                        onClick={(e) => {
                          e.stopPropagation();
                          setEditingTitle(sess.id);
                          setTitleInput(sess.title || "");
                        }}
                      >
                        <svg width="10" height="10" viewBox="0 0 16 16" fill="none">
                          <path d="M11 2l3 3-8 8H3v-3l8-8z" stroke="currentColor" strokeWidth="1.4" strokeLinejoin="round"/>
                        </svg>
                      </button>
                      <button
                        style={{ ...s.iconBtn, color: "#ef4444" }}
                        title="Delete"
                        onClick={(e) => { e.stopPropagation(); deleteSession(sess.id); }}
                      >
                        <svg width="10" height="10" viewBox="0 0 16 16" fill="none">
                          <path d="M3 4h10M6 2h4M5 4l.5 9h5l.5-9" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round"/>
                        </svg>
                      </button>
                    </div>
                  </div>
                  {sess.document_id && (
                    <div style={s.sessDoc}>
                      📄 {readyDocs.find((d) => d.id === sess.document_id)
                        ? getDocShort(readyDocs.find((d) => d.id === sess.document_id), 24)
                        : "Document"}
                    </div>
                  )}
                  {sess.message_count > 0 && (
                    <div style={s.sessMeta}>{sess.message_count} msg{sess.message_count > 1 ? "s" : ""}</div>
                  )}
                </>
              )}
            </div>
          ))}
        </div>
      </aside>

      {/* ── Chat Area ── */}
      <div style={s.chatArea}>

        {/* Document context banner */}
        {selectedDoc && (
          <div style={s.docBanner}>
            <div style={s.bannerLeft}>
              <svg width="13" height="13" viewBox="0 0 20 20" fill="none">
                <path d="M4 2h8l4 4v12a2 2 0 01-2 2H4a2 2 0 01-2-2V4a2 2 0 012-2z"
                  stroke="#2563eb" strokeWidth="1.7" />
              </svg>
              <span style={s.bannerMode}>RAG mode</span>
              <span style={s.bannerDoc}>— {getDocName(selectedDoc)}</span>
            </div>
            <button style={s.bannerClear} onClick={() => setSelectedDoc(null)}>✕ Clear</button>
          </div>
        )}

        {/* Messages */}
        <div style={s.messages}>
          {messages.length === 0 && (
            <div style={s.welcome}>
              <div style={s.welcomeIcon}>
                <svg width="28" height="28" viewBox="0 0 40 40" fill="none">
                  <path d="M4 8a4 4 0 014-4h24a4 4 0 014 4v16a4 4 0 01-4 4H12l-8 8V8z"
                    fill="#dbeafe" stroke="#93c5fd" strokeWidth="1.5" />
                </svg>
              </div>
              <h3 style={s.welcomeTitle}>
                {selectedDoc
                  ? `Ask anything about "${getDocShort(selectedDoc, 32)}"`
                  : "Start a conversation"}
              </h3>
              <p style={s.welcomeSub}>
                {selectedDoc
                  ? "I'll search through the document and give you accurate, sourced answers."
                  : "Select a document from the sidebar for grounded, RAG-powered answers."}
              </p>
              {!selectedDoc && readyDocs.length > 0 && (
                <p style={s.welcomeHint}>
                  💡 {readyDocs.length} document{readyDocs.length > 1 ? "s" : ""} ready — pick one in the sidebar for RAG mode
                </p>
              )}
            </div>
          )}

          {messages.map((msg, i) => {
            const isUser = msg.role === "user";
            return (
              <div key={msg.id || i} style={{ ...s.msgRow, ...(isUser ? s.msgRowUser : {}) }}>
                <div style={{
                  ...s.bubble,
                  ...(isUser ? s.bubbleUser : s.bubbleAI),
                  animation: "fadeIn 0.2s ease",
                }}>
                  <div style={{ ...s.msgRole, color: isUser ? "rgba(255,255,255,0.55)" : "#94a3b8" }}>
                    {isUser ? "You" : "DocAssist"}
                  </div>
                  <div style={{ ...s.msgContent, color: isUser ? "#fff" : "#0f172a" }}>
                    {msg.content}
                  </div>

                  {msg.sources && msg.sources.length > 0 && (
                    <div style={s.sources}>
                      <div style={s.sourcesTitle}>Sources</div>
                      {msg.sources.map((src, si) => (
                        <div key={si} style={s.sourceItem}>
                          <span style={s.srcBadge}>p.{src.page_number}</span>
                          <span style={s.srcSection}>{src.section_title}</span>
                          {src.score && (
                            <span style={s.srcScore}>{Math.round(src.score * 100)}%</span>
                          )}
                        </div>
                      ))}
                    </div>
                  )}

                  <div style={{ ...s.msgTime, color: isUser ? "rgba(255,255,255,0.35)" : "#cbd5e1" }}>
                    {formatTime(msg.created_at)}
                  </div>
                </div>
              </div>
            );
          })}

          {sending && (
            <div style={s.msgRow}>
              <div style={{ ...s.bubble, ...s.bubbleAI }}>
                <div style={s.typing}>
                  {[0, 1, 2].map((i) => (
                    <span key={i} style={{ ...s.dot3, animationDelay: `${i * 0.18}s` }} />
                  ))}
                </div>
              </div>
            </div>
          )}

          <div ref={bottomRef} />
        </div>

        {/* Input bar */}
        <div style={s.inputBar}>
          <div style={s.inputRow}>
            <textarea
              style={s.textarea}
              placeholder={selectedDoc
                ? `Ask about "${getDocShort(selectedDoc, 24)}"…`
                : "Type a message…"}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              rows={1}
            />
            <button
              style={{ ...s.sendBtn, opacity: (!input.trim() || sending) ? 0.4 : 1 }}
              onClick={handleSend}
              disabled={!input.trim() || sending}
            >
              <svg width="16" height="16" viewBox="0 0 20 20" fill="none">
                <path d="M3 10l14-7-5 7 5 7-14-7z" fill="white" />
              </svg>
            </button>
          </div>
          <div style={s.inputHint}>
            Enter to send · Shift+Enter for new line
            {selectedDoc ? " · RAG mode" : " · General mode"}
          </div>
        </div>
      </div>
    </div>
  );
}

const s = {
  page: {
    display: "flex",
    height: "100%",
    overflow: "hidden",
    background: "#f8fafc",
    fontFamily: "'Plus Jakarta Sans', 'DM Sans', system-ui, sans-serif",
  },

  /* Sessions sidebar */
  sidebar: {
    width: "240px",
    minWidth: "240px",
    borderRight: "1px solid #e2e8f0",
    display: "flex",
    flexDirection: "column",
    background: "#fff",
    flexShrink: 0,
    overflow: "hidden",
  },
  sideHead: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    padding: "14px 14px 8px",
    borderBottom: "1px solid #f1f5f9",
  },
  sideTitle: {
    color: "#374151",
    fontSize: "11px",
    fontWeight: "700",
    textTransform: "uppercase",
    letterSpacing: "0.6px",
  },
  newBtn: {
    width: "26px",
    height: "26px",
    background: "#eff6ff",
    border: "1px solid #bfdbfe",
    color: "#2563eb",
    borderRadius: "6px",
    cursor: "pointer",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
  },
  docSelectorWrap: {
    padding: "8px 10px",
    borderBottom: "1px solid #f1f5f9",
    position: "relative",
  },
  docSelectorBtn: {
    display: "flex",
    alignItems: "center",
    gap: "6px",
    width: "100%",
    background: "#f8fafc",
    border: "1px solid #e2e8f0",
    borderRadius: "7px",
    padding: "7px 10px",
    fontSize: "11px",
    color: "#64748b",
    cursor: "pointer",
    fontFamily: "inherit",
    textAlign: "left",
  },
  docSelectorLabel: {
    flex: 1,
    overflow: "hidden",
    textOverflow: "ellipsis",
    whiteSpace: "nowrap",
  },
  dropdown: {
    position: "absolute",
    top: "calc(100% - 4px)",
    left: "10px",
    right: "10px",
    background: "#fff",
    border: "1px solid #e2e8f0",
    borderRadius: "10px",
    padding: "6px",
    zIndex: 200,
    boxShadow: "0 8px 24px rgba(0,0,0,0.12)",
    maxHeight: "220px",
    overflowY: "auto",
  },
  dropItem: {
    display: "flex",
    alignItems: "center",
    gap: "8px",
    padding: "8px 9px",
    borderRadius: "6px",
    cursor: "pointer",
    color: "#374151",
    fontSize: "12px",
    transition: "background 0.1s",
  },
  dropItemActive: { background: "#eff6ff", color: "#1d4ed8" },
  dropDisabled: { padding: "8px 9px", color: "#94a3b8", fontSize: "11px" },
  checkMark: { color: "#2563eb", fontSize: "12px", fontWeight: "700", marginLeft: "auto" },

  sessionList: { flex: 1, overflowY: "auto", padding: "6px 8px" },
  noSessions: { color: "#94a3b8", fontSize: "12px", textAlign: "center", padding: "24px 12px", lineHeight: "1.7" },
  sessionItem: {
    padding: "9px 10px",
    borderRadius: "8px",
    cursor: "pointer",
    marginBottom: "2px",
    transition: "background 0.1s",
    border: "1px solid transparent",
  },
  sessionActive: { border: "1px solid #bfdbfe" },
  sessRow: { display: "flex", alignItems: "center", gap: "7px" },
  sessTitle: {
    color: "#0f172a", fontSize: "12px", fontWeight: "500", flex: 1,
    overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
  },
  sessActions: { display: "flex", gap: "2px", transition: "opacity 0.15s" },
  iconBtn: {
    background: "transparent", border: "none", cursor: "pointer",
    padding: "3px 4px", color: "#94a3b8", borderRadius: "4px",
    display: "flex", alignItems: "center", justifyContent: "center",
  },
  sessDoc: { color: "#2563eb", fontSize: "10px", marginTop: "3px", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" },
  sessMeta: { color: "#94a3b8", fontSize: "10px", marginTop: "1px" },
  titleInput: {
    background: "#fff", border: "1px solid #2563eb", color: "#0f172a",
    borderRadius: "5px", padding: "3px 7px", fontSize: "12px", width: "100%",
    outline: "none", fontFamily: "inherit",
  },

  /* Chat area */
  chatArea: {
    flex: 1,
    display: "flex",
    flexDirection: "column",
    overflow: "hidden",
    background: "#f8fafc",
    minWidth: 0,
  },
  docBanner: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    background: "#eff6ff",
    borderBottom: "1px solid #bfdbfe",
    padding: "8px 20px",
    flexShrink: 0,
  },
  bannerLeft: { display: "flex", alignItems: "center", gap: "7px" },
  bannerMode: { color: "#1d4ed8", fontSize: "12px", fontWeight: "700" },
  bannerDoc: { color: "#3b82f6", fontSize: "12px", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", maxWidth: "300px" },
  bannerClear: { background: "transparent", border: "none", color: "#3b82f6", cursor: "pointer", fontSize: "12px", fontFamily: "inherit" },

  messages: {
    flex: 1, overflowY: "auto", padding: "20px 24px",
    display: "flex", flexDirection: "column", gap: "14px",
  },
  welcome: {
    margin: "auto", textAlign: "center", maxWidth: "460px", padding: "40px 20px",
    display: "flex", flexDirection: "column", alignItems: "center", gap: "12px",
  },
  welcomeIcon: {
    width: "60px", height: "60px", background: "#eff6ff",
    border: "1px solid #bfdbfe", borderRadius: "16px",
    display: "flex", alignItems: "center", justifyContent: "center",
  },
  welcomeTitle: { color: "#0f172a", fontSize: "19px", fontWeight: "700", margin: 0, letterSpacing: "-0.4px" },
  welcomeSub: { color: "#64748b", fontSize: "14px", margin: 0, lineHeight: "1.65" },
  welcomeHint: {
    color: "#2563eb", fontSize: "13px",
    background: "#eff6ff", border: "1px solid #bfdbfe",
    borderRadius: "8px", padding: "10px 14px", margin: 0,
  },

  msgRow: { display: "flex", justifyContent: "flex-start" },
  msgRowUser: { justifyContent: "flex-end" },
  bubble: { maxWidth: "72%", borderRadius: "14px", padding: "12px 16px" },
  bubbleAI: { background: "#fff", border: "1px solid #e2e8f0", boxShadow: "0 1px 4px rgba(0,0,0,0.04)" },
  bubbleUser: { background: "#2563eb", border: "none" },
  msgRole: { fontSize: "10px", fontWeight: "700", marginBottom: "5px", textTransform: "uppercase", letterSpacing: "0.5px" },
  msgContent: { fontSize: "14px", lineHeight: "1.65", whiteSpace: "pre-wrap" },
  msgTime: { fontSize: "10px", marginTop: "7px", textAlign: "right" },

  sources: { marginTop: "10px", padding: "10px 12px", background: "#f8fafc", borderRadius: "8px", border: "1px solid #e2e8f0" },
  sourcesTitle: { color: "#64748b", fontSize: "10px", fontWeight: "700", textTransform: "uppercase", letterSpacing: "0.5px", marginBottom: "7px" },
  sourceItem: { display: "flex", alignItems: "center", gap: "7px", marginBottom: "5px" },
  srcBadge: { background: "#f0fdf4", border: "1px solid #86efac", color: "#16a34a", borderRadius: "4px", padding: "1px 6px", fontSize: "10px", fontWeight: "600", flexShrink: 0 },
  srcSection: { color: "#374151", fontSize: "11px", flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" },
  srcScore: { color: "#94a3b8", fontSize: "10px", flexShrink: 0 },

  typing: { display: "flex", gap: "4px", padding: "4px 2px", alignItems: "center" },
  dot3: { width: "7px", height: "7px", background: "#cbd5e1", borderRadius: "50%", display: "inline-block", animation: "bounce3 1.2s infinite" },

  inputBar: { borderTop: "1px solid #e2e8f0", padding: "14px 20px", background: "#fff", flexShrink: 0 },
  inputRow: { display: "flex", gap: "9px", alignItems: "flex-end" },
  textarea: {
    flex: 1, background: "#f8fafc", border: "1px solid #e2e8f0",
    borderRadius: "10px", padding: "11px 15px", color: "#0f172a",
    fontSize: "14px", outline: "none", resize: "none", fontFamily: "inherit",
    lineHeight: "1.5", minHeight: "44px", maxHeight: "130px",
  },
  sendBtn: {
    background: "#2563eb", border: "none", color: "#fff", borderRadius: "10px",
    width: "44px", height: "44px", cursor: "pointer",
    display: "flex", alignItems: "center", justifyContent: "center",
    flexShrink: 0, transition: "opacity 0.15s",
  },
  inputHint: { color: "#94a3b8", fontSize: "11px", marginTop: "6px", textAlign: "center" },
};
