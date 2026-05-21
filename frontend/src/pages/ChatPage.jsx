import { useEffect, useState, useRef } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../hooks/useAuth";
import { useChat } from "../hooks/useChat";
import { useDocuments } from "../hooks/useDocuments";

export default function ChatPage() {
  const { user, logout }  = useAuth();
  const navigate          = useNavigate();
  const {
    sessions, activeSession, messages, sending, loading,
    fetchSessions, openSession, createSession, updateTitle, deleteSession, sendMessage,
  } = useChat();
  const { documents, fetchDocuments } = useDocuments();

  const [input, setInput]             = useState("");
  const [selectedDoc, setSelectedDoc] = useState(null);
  const [editingTitle, setEditingTitle] = useState(null);
  const [titleInput, setTitleInput]   = useState("");
  const [showDocPicker, setShowDocPicker] = useState(false);
  const bottomRef = useRef();

  useEffect(() => { fetchSessions(); fetchDocuments(); }, []);
  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: "smooth" }); }, [messages]);

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

  const readyDocs = documents.filter((d) => d.status === "ready");

  return (
    <div style={s.page}>
      {/* ── Top Nav ── */}
      <nav style={s.nav}>
        <div style={s.navLeft}>
          <div style={s.logoBox} onClick={() => navigate("/dashboard")} title="Back to Dashboard">
            <svg width="18" height="18" viewBox="0 0 28 28" fill="none">
              <path d="M4 6h20M4 12h14M4 18h18M4 24h10" stroke="#60a5fa" strokeWidth="2.2" strokeLinecap="round"/>
            </svg>
          </div>
          <span style={s.brandName}>DocAssist</span>
          <span style={s.pageBadge}>Chat</span>
        </div>
        <div style={s.navRight}>
          {/* Document selector */}
          <div style={s.docSelectorWrap}>
            <button style={s.docSelector} onClick={() => setShowDocPicker(!showDocPicker)}>
              📄 {selectedDoc ? selectedDoc.original_filename.slice(0, 25) + "..." : "No document selected"}
              <span style={s.chevron}>▾</span>
            </button>
            {showDocPicker && (
              <div style={s.docDropdown}>
                <div
                  style={s.docOption}
                  onClick={() => { setSelectedDoc(null); setShowDocPicker(false); }}
                >
                  <span>💬</span> General chat (no document)
                </div>
                {readyDocs.length === 0 && (
                  <div style={s.docOptionDisabled}>No ready documents — upload one first</div>
                )}
                {readyDocs.map((d) => (
                  <div
                    key={d.document_id}
                    style={{ ...s.docOption, ...(selectedDoc?.document_id === d.document_id ? s.docOptionActive : {}) }}
                    onClick={() => { setSelectedDoc(d); setShowDocPicker(false); }}
                  >
                    <span>📄</span>
                    <div>
                      <div style={s.docOptionName}>{d.filename}</div>
                      <div style={s.docOptionMeta}>{d.ocr?.total_pages} pages · {d.chunking?.total_chunks} chunks</div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
          <span style={s.userChip}>{user?.full_name}</span>
          <button style={s.logoutBtn} onClick={() => { logout(); navigate("/login"); }}>Sign out</button>
        </div>
      </nav>

      <div style={s.layout}>
        {/* ── Sessions Sidebar ── */}
        <div style={s.sidebar}>
          <div style={s.sidebarHeader}>
            <span style={s.sidebarTitle}>Conversations</span>
            <button style={s.newChatBtn} onClick={() => createSession(selectedDoc?.id || null)} title="New Chat">
              ＋
            </button>
          </div>

          <div style={s.sessionList}>
            {sessions.length === 0 && (
              <div style={s.noSessions}>No conversations yet.<br/>Start by typing a message.</div>
            )}
            {sessions.map((s_) => (
              <div
                key={s_.id}
                style={{ ...s.sessionItem, ...(activeSession?.id === s_.id ? s.sessionItemActive : {}) }}
                onClick={() => openSession(s_.id)}
              >
                {editingTitle === s_.id ? (
                  <input
                    style={s.titleInput}
                    value={titleInput}
                    autoFocus
                    onChange={(e) => setTitleInput(e.target.value)}
                    onBlur={() => handleTitleSave(s_.id)}
                    onKeyDown={(e) => e.key === "Enter" && handleTitleSave(s_.id)}
                    onClick={(e) => e.stopPropagation()}
                  />
                ) : (
                  <>
                    <div style={s.sessionMeta}>
                      <span style={s.sessionTitle}>{s_.title}</span>
                      <div style={s.sessionActions}>
                        <span style={s.iconBtn} title="Rename"
                          onClick={(e) => { e.stopPropagation(); setEditingTitle(s_.id); setTitleInput(s_.title); }}>✏</span>
                        <span style={s.iconBtnRed} title="Delete"
                          onClick={(e) => { e.stopPropagation(); deleteSession(s_.id); }}>🗑</span>
                      </div>
                    </div>
                    {s_.last_message && <div style={s.sessionPreview}>{s_.last_message.slice(0, 60)}...</div>}
                    {s_.document_id && <div style={s.sessionDoc}>📄 Document attached</div>}
                  </>
                )}
              </div>
            ))}
          </div>
        </div>

        {/* ── Chat Area ── */}
        <div style={s.chatArea}>
          {/* Messages */}
          <div style={s.messages}>
            {!activeSession && messages.length === 0 && (
              <div style={s.welcomeBox}>
                <div style={s.welcomeIcon}>🤖</div>
                <h2 style={s.welcomeTitle}>Contract Intelligence Assistant</h2>
                <p style={s.welcomeSub}>
                  {selectedDoc
                    ? `Ask anything about "${selectedDoc.original_filename}"`
                    : "Select a document above to ask questions about it, or chat generally."}
                </p>
                <div style={s.suggestions}>
                  {["What are the payment terms?", "What are the termination clauses?", "Summarize this contract", "What is the contract duration?"].map((q) => (
                    <button key={q} style={s.suggBtn} onClick={() => setInput(q)}>{q}</button>
                  ))}
                </div>
              </div>
            )}

            {messages.map((msg, i) => (
              <div key={msg.id || i} style={{ ...s.msgRow, ...(msg.role === "user" ? s.msgRowUser : {}) }}>
                <div style={{ ...s.msgBubble, ...(msg.role === "user" ? s.msgBubbleUser : s.msgBubbleAI) }}>
                  <div style={s.msgRole}>{msg.role === "user" ? "You" : "🤖 Assistant"}</div>
                  <div style={s.msgContent}>{msg.content}</div>

                  {/* Sources */}
                  {msg.sources?.length > 0 && (
                    <div style={s.sources}>
                      <div style={s.sourcesTitle}>📎 Sources used:</div>
                      {msg.sources.slice(0, 3).map((src, j) => (
                        <div key={j} style={s.sourceItem}>
                          <span style={s.sourceBadge}>{src.relevance_pct?.toFixed(0)}%</span>
                          {src.section_title && <span style={s.sourceSection}>{src.section_title}</span>}
                          <span style={s.sourcePage}>p.{src.page}</span>
                        </div>
                      ))}
                    </div>
                  )}

                  <div style={s.msgTime}>
                    {new Date(msg.created_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
                  </div>
                </div>
              </div>
            ))}

            {sending && (
              <div style={s.msgRow}>
                <div style={s.msgBubbleAI}>
                  <div style={s.msgRole}>🤖 Assistant</div>
                  <div style={s.typing}><span/><span/><span/></div>
                </div>
              </div>
            )}
            <div ref={bottomRef} />
          </div>

          {/* Input bar */}
          <div style={s.inputBar}>
            {selectedDoc && (
              <div style={s.docBadge}>
                📄 {selectedDoc.original_filename.slice(0, 30)}
                <span style={s.docBadgeRemove} onClick={() => setSelectedDoc(null)}>✕</span>
              </div>
            )}
            <div style={s.inputRow}>
              <textarea
                style={s.textarea}
                placeholder={selectedDoc ? `Ask about ${selectedDoc.original_filename}...` : "Type a message..."}
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={handleKeyDown}
                rows={1}
              />
              <button style={{ ...s.sendBtn, opacity: (!input.trim() || sending) ? 0.4 : 1 }}
                onClick={handleSend} disabled={!input.trim() || sending}>
                {sending ? "⏳" : "➤"}
              </button>
            </div>
            <div style={s.inputHint}>Enter to send · Shift+Enter for new line · Model: {selectedDoc ? "RAG + qwen2.5:7b" : "qwen2.5:7b"}</div>
          </div>
        </div>
      </div>

      <style>{`
        @keyframes bounce { 0%,80%,100%{transform:translateY(0)} 40%{transform:translateY(-6px)} }
      `}</style>
    </div>
  );
}

const s = {
  page:       { height:"100vh", display:"flex", flexDirection:"column", background:"#0f1117", fontFamily:"'Inter',sans-serif", overflow:"hidden" },
  nav:        { display:"flex", alignItems:"center", justifyContent:"space-between", padding:"10px 24px", borderBottom:"1px solid #1e2130", flexShrink:0 },
  navLeft:    { display:"flex", alignItems:"center", gap:"10px" },
  logoBox:    { width:"32px", height:"32px", background:"rgba(96,165,250,0.1)", border:"1px solid rgba(96,165,250,0.2)", borderRadius:"7px", display:"flex", alignItems:"center", justifyContent:"center", cursor:"pointer" },
  brandName:  { color:"#f1f5f9", fontWeight:"700", fontSize:"15px" },
  pageBadge:  { background:"rgba(59,130,246,0.15)", color:"#60a5fa", borderRadius:"5px", padding:"2px 8px", fontSize:"11px", fontWeight:"600" },
  navRight:   { display:"flex", alignItems:"center", gap:"10px" },
  docSelectorWrap: { position:"relative" },
  docSelector: { background:"#1a1d27", border:"1px solid #2a2d3d", color:"#94a3b8", borderRadius:"8px", padding:"6px 12px", fontSize:"13px", cursor:"pointer", display:"flex", alignItems:"center", gap:"8px", maxWidth:"280px" },
  chevron:    { color:"#475569", fontSize:"10px" },
  docDropdown:{ position:"absolute", top:"calc(100% + 6px)", right:0, background:"#1a1d27", border:"1px solid #2a2d3d", borderRadius:"10px", padding:"6px", minWidth:"280px", zIndex:100, boxShadow:"0 8px 24px rgba(0,0,0,0.4)" },
  docOption:  { display:"flex", alignItems:"flex-start", gap:"10px", padding:"10px 12px", borderRadius:"7px", cursor:"pointer", color:"#94a3b8", fontSize:"13px", transition:"background 0.15s" },
  docOptionActive: { background:"rgba(59,130,246,0.12)", color:"#60a5fa" },
  docOptionDisabled: { padding:"10px 12px", color:"#475569", fontSize:"12px" },
  docOptionName: { color:"#f1f5f9", fontSize:"13px", fontWeight:"500" },
  docOptionMeta: { color:"#64748b", fontSize:"11px" },
  userChip:   { background:"#1a1d27", border:"1px solid #2a2d3d", color:"#94a3b8", borderRadius:"20px", padding:"4px 12px", fontSize:"12px" },
  logoutBtn:  { background:"transparent", border:"1px solid #2a2d3d", color:"#64748b", borderRadius:"6px", padding:"5px 12px", fontSize:"12px", cursor:"pointer" },

  layout:     { display:"flex", flex:1, overflow:"hidden" },

  // Sidebar
  sidebar:    { width:"260px", borderRight:"1px solid #1e2130", display:"flex", flexDirection:"column", flexShrink:0 },
  sidebarHeader: { display:"flex", alignItems:"center", justifyContent:"space-between", padding:"14px 16px", borderBottom:"1px solid #1e2130" },
  sidebarTitle: { color:"#94a3b8", fontSize:"12px", fontWeight:"600", textTransform:"uppercase", letterSpacing:"0.5px" },
  newChatBtn: { background:"rgba(59,130,246,0.15)", border:"1px solid rgba(59,130,246,0.3)", color:"#60a5fa", borderRadius:"6px", width:"28px", height:"28px", cursor:"pointer", fontSize:"16px", display:"flex", alignItems:"center", justifyContent:"center" },
  sessionList:{ flex:1, overflowY:"auto", padding:"8px" },
  noSessions: { color:"#475569", fontSize:"12px", textAlign:"center", padding:"24px 12px", lineHeight:"1.6" },
  sessionItem:{ padding:"10px 12px", borderRadius:"8px", cursor:"pointer", marginBottom:"4px", transition:"background 0.15s" },
  sessionItemActive: { background:"rgba(59,130,246,0.12)", border:"1px solid rgba(59,130,246,0.2)" },
  sessionMeta:{ display:"flex", alignItems:"center", justifyContent:"space-between" },
  sessionTitle: { color:"#f1f5f9", fontSize:"13px", fontWeight:"500", flex:1, overflow:"hidden", textOverflow:"ellipsis", whiteSpace:"nowrap" },
  sessionActions: { display:"flex", gap:"4px", opacity:0, transition:"opacity 0.15s" },
  iconBtn:    { cursor:"pointer", fontSize:"12px", padding:"2px 4px", borderRadius:"4px", color:"#64748b" },
  iconBtnRed: { cursor:"pointer", fontSize:"12px", padding:"2px 4px", borderRadius:"4px", color:"#f87171" },
  sessionPreview: { color:"#64748b", fontSize:"11px", marginTop:"3px", overflow:"hidden", textOverflow:"ellipsis", whiteSpace:"nowrap" },
  sessionDoc: { color:"#60a5fa", fontSize:"10px", marginTop:"3px" },
  titleInput: { background:"#0f1117", border:"1px solid #3b82f6", color:"#f1f5f9", borderRadius:"5px", padding:"3px 7px", fontSize:"12px", width:"100%", outline:"none" },

  // Chat
  chatArea:   { flex:1, display:"flex", flexDirection:"column", overflow:"hidden" },
  messages:   { flex:1, overflowY:"auto", padding:"24px 32px", display:"flex", flexDirection:"column", gap:"16px" },

  welcomeBox: { margin:"auto", textAlign:"center", maxWidth:"500px", padding:"48px 24px" },
  welcomeIcon:{ fontSize:"48px", marginBottom:"16px" },
  welcomeTitle: { color:"#f1f5f9", fontSize:"22px", fontWeight:"700", margin:"0 0 8px" },
  welcomeSub: { color:"#64748b", fontSize:"14px", margin:"0 0 28px", lineHeight:"1.6" },
  suggestions:{ display:"flex", flexWrap:"wrap", gap:"8px", justifyContent:"center" },
  suggBtn:    { background:"#1a1d27", border:"1px solid #2a2d3d", color:"#94a3b8", borderRadius:"8px", padding:"8px 14px", fontSize:"13px", cursor:"pointer", transition:"border-color 0.2s" },

  msgRow:     { display:"flex", justifyContent:"flex-start" },
  msgRowUser: { justifyContent:"flex-end" },
  msgBubble:  { maxWidth:"72%", borderRadius:"12px", padding:"12px 16px" },
  msgBubbleAI:{ background:"#1a1d27", border:"1px solid #2a2d3d" },
  msgBubbleUser: { background:"rgba(59,130,246,0.15)", border:"1px solid rgba(59,130,246,0.25)" },
  msgRole:    { fontSize:"11px", fontWeight:"600", color:"#64748b", marginBottom:"6px", textTransform:"uppercase", letterSpacing:"0.5px" },
  msgContent: { color:"#e2e8f0", fontSize:"14px", lineHeight:"1.65", whiteSpace:"pre-wrap" },
  msgTime:    { color:"#475569", fontSize:"10px", marginTop:"8px", textAlign:"right" },

  sources:    { marginTop:"12px", padding:"10px", background:"rgba(0,0,0,0.2)", borderRadius:"8px" },
  sourcesTitle: { color:"#64748b", fontSize:"11px", fontWeight:"600", marginBottom:"6px" },
  sourceItem: { display:"flex", alignItems:"center", gap:"8px", marginBottom:"4px" },
  sourceBadge:{ background:"rgba(34,197,94,0.15)", color:"#4ade80", borderRadius:"4px", padding:"1px 6px", fontSize:"10px", fontWeight:"600" },
  sourceSection: { color:"#94a3b8", fontSize:"11px" },
  sourcePage: { color:"#475569", fontSize:"10px" },

  typing:     { display:"flex", gap:"4px", padding:"4px 0", "& span": { width:"6px", height:"6px", background:"#64748b", borderRadius:"50%", animation:"bounce 1.2s infinite" } },

  // Input
  inputBar:   { borderTop:"1px solid #1e2130", padding:"16px 24px", background:"#0f1117" },
  docBadge:   { display:"inline-flex", alignItems:"center", gap:"8px", background:"rgba(59,130,246,0.1)", border:"1px solid rgba(59,130,246,0.2)", color:"#60a5fa", borderRadius:"6px", padding:"4px 10px", fontSize:"12px", marginBottom:"10px" },
  docBadgeRemove: { cursor:"pointer", opacity:0.7, fontSize:"10px" },
  inputRow:   { display:"flex", gap:"10px", alignItems:"flex-end" },
  textarea:   { flex:1, background:"#1a1d27", border:"1px solid #2a2d3d", borderRadius:"10px", padding:"12px 16px", color:"#f1f5f9", fontSize:"14px", outline:"none", resize:"none", fontFamily:"inherit", lineHeight:"1.5", minHeight:"44px", maxHeight:"140px" },
  sendBtn:    { background:"#3b82f6", border:"none", color:"#fff", borderRadius:"10px", width:"44px", height:"44px", fontSize:"18px", cursor:"pointer", display:"flex", alignItems:"center", justifyContent:"center", flexShrink:0 },
  inputHint:  { color:"#334155", fontSize:"11px", marginTop:"6px", textAlign:"center" },
};