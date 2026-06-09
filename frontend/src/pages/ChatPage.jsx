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

// Simple markdown renderer — handles bold, bullets, numbered lists, headings
function renderMarkdown(text) {
  if (!text) return null;
  const lines = text.split("\n");
  const out = [];
  let i = 0;
  while (i < lines.length) {
    const line = lines[i];
    // Heading
    const hMatch = line.match(/^(#{1,3})\s+(.+)/);
    if (hMatch) {
      const level = hMatch[1].length;
      const sz = level === 1 ? "16px" : level === 2 ? "14px" : "13px";
      out.push(
        <div key={i} style={{ fontWeight: "700", fontSize: sz, color: "#0f172a", marginTop: "10px", marginBottom: "4px" }}>
          {inlineMd(hMatch[2])}
        </div>
      );
      i++; continue;
    }
    // Bullet
    const bMatch = line.match(/^[\-\*]\s+(.*)/);
    if (bMatch) {
      out.push(
        <div key={i} style={{ display: "flex", gap: "6px", marginBottom: "3px" }}>
          <span style={{ color: "#2563eb", flexShrink: 0, marginTop: "1px" }}>•</span>
          <span>{inlineMd(bMatch[1])}</span>
        </div>
      );
      i++; continue;
    }
    // Numbered list
    const nMatch = line.match(/^(\d+)\.\s+(.*)/);
    if (nMatch) {
      out.push(
        <div key={i} style={{ display: "flex", gap: "6px", marginBottom: "3px" }}>
          <span style={{ color: "#2563eb", flexShrink: 0, fontWeight: "600", minWidth: "16px" }}>{nMatch[1]}.</span>
          <span>{inlineMd(nMatch[2])}</span>
        </div>
      );
      i++; continue;
    }
    // Empty line → spacer
    if (line.trim() === "") {
      if (out.length > 0) out.push(<div key={i} style={{ height: "6px" }} />);
      i++; continue;
    }
    // Normal paragraph
    out.push(<div key={i} style={{ marginBottom: "2px" }}>{inlineMd(line)}</div>);
    i++;
  }
  return out;
}

function inlineMd(text) {
  // Split on **bold** and (SOURCE X, ...) citation patterns
  const parts = text.split(/(\*\*[^*]+\*\*|\([^)]*SOURCE[^)]*\))/g);
  return parts.map((part, idx) => {
    if (part.startsWith("**") && part.endsWith("**")) {
      return <strong key={idx} style={{ fontWeight: "700", color: "#0f172a" }}>{part.slice(2, -2)}</strong>;
    }
    if (/^\([^)]*SOURCE[^)]*\)$/.test(part)) {
      return <span key={idx} style={{ color: "#2563eb", fontSize: "11px", fontWeight: "600" }}>{part}</span>;
    }
    return part;
  });
}

export default function ChatPage() {
  const { user } = useAuth();
  const location = useLocation();
  const {
    sessions, activeSession, messages, sending, loading, error: chatError,
    fetchSessions, openSession, createSession, updateTitle, deleteSession, sendMessage,
  } = useChat();
  const {
    documents, loading: docsLoading, error: docsError,
    fetchDocuments,
  } = useDocuments();

  const [input, setInput]                   = useState("");
  const [selectedDoc, setSelectedDoc]       = useState(null);
  const [editingTitle, setEditingTitle]     = useState(null);
  const [titleInput, setTitleInput]         = useState("");
  const [showDocPicker, setShowDocPicker]   = useState(false);
  const [hoveredSession, setHoveredSession] = useState(null);
  const bottomRef  = useRef();
  const pickerRef  = useRef();

  // ── Initial load ─────────────────────────────────────────────────────────
  useEffect(() => {
    fetchSessions();
    fetchDocuments();
  }, []);

  // ── Pre-select document when navigated from Documents page ────────────────
  useEffect(() => {
    if (!location.state?.documentId || documents.length === 0) return;
    const doc = documents.find((d) => d.id === location.state.documentId);
    if (doc) setSelectedDoc(doc);
  }, [location.state, documents]);

  // ── Sync selectedDoc when user switches to an existing session (Bug 3) ───
  useEffect(() => {
    if (!activeSession) return;
    if (activeSession.document_id) {
      const doc = documents.find((d) => d.id === activeSession.document_id);
      setSelectedDoc(doc ?? null);
    } else {
      setSelectedDoc(null);
    }
  }, [activeSession?.id]);   // only re-run when the session itself changes, not on every doc list update

  // ── Auto-scroll to latest message ────────────────────────────────────────
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  // ── Close doc picker on outside click (Bug 1 fix: use 'click', not 'mousedown') ──
  useEffect(() => {
    if (!showDocPicker) return;
    const handler = (e) => {
      // pickerRef wraps the entire picker widget; clicks inside it should not close it
      if (pickerRef.current && !pickerRef.current.contains(e.target)) {
        setShowDocPicker(false);
      }
    };
    // Use 'click' (fires after mouseup) so item onClick handlers run before the dropdown closes
    document.addEventListener("click", handler);
    return () => document.removeEventListener("click", handler);
  }, [showDocPicker]);

  const readyDocs = documents.filter((d) => d.status === "ready");

  // ── Send message ──────────────────────────────────────────────────────────
  const handleSend = async () => {
    if (!input.trim() || sending) return;
    const text = input.trim();
    const docId = selectedDoc?.id ?? null;
    setInput("");

    if (!activeSession) {
      // Bug 2 fix: createSession returns the new session object; pass its id
      // directly to sendMessage so the stale-closure activeSession check is bypassed.
      const session = await createSession(docId);
      if (session) await sendMessage(text, docId, session.id);
    } else {
      await sendMessage(text, docId);
    }
  };

  const handleKeyDown = (e) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); handleSend(); }
  };

  const handleTitleSave = async (sessionId) => {
    if (titleInput.trim()) await updateTitle(sessionId, titleInput.trim());
    setEditingTitle(null);
  };

  const handleSelectDoc = (doc) => {
    setSelectedDoc(doc);
    setShowDocPicker(false);
  };

  const handleClearDoc = () => {
    setSelectedDoc(null);
    setShowDocPicker(false);
  };

  const formatTime = (iso) => {
    if (!iso) return "";
    return new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  };

  const docPickerLabel = selectedDoc
    ? getDocShort(selectedDoc, 22)
    : docsLoading
    ? "Loading documents…"
    : "No document selected";

  return (
    <div style={s.page}>
      <style>{`
        @keyframes bounce3 { 0%,80%,100%{transform:translateY(0)} 40%{transform:translateY(-6px)} }
        @keyframes fadeIn   { from{opacity:0;transform:translateY(6px)} to{opacity:1;transform:translateY(0)} }
        @keyframes spin     { to{transform:rotate(360deg)} }
      `}</style>

      {/* ── Sessions Sidebar ── */}
      <aside style={s.sidebar}>
        <div style={s.sideHead}>
          <span style={s.sideTitle}>Conversations</span>
          <button
            style={s.newBtn}
            title="New chat"
            onClick={() => createSession(selectedDoc?.id ?? null)}
          >
            <svg width="14" height="14" viewBox="0 0 20 20" fill="none">
              <path d="M10 4v12M4 10h12" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
            </svg>
          </button>
        </div>

        {/* ── Document picker (Bug 1 fix: ref-based outside-click, click event) ── */}
        <div style={s.docSelectorWrap} ref={pickerRef}>
          <button
            style={{
              ...s.docSelectorBtn,
              borderColor: selectedDoc ? "#bfdbfe" : "#e2e8f0",
              background:  selectedDoc ? "#eff6ff" : "#f8fafc",
              color:       selectedDoc ? "#1d4ed8" : "#64748b",
            }}
            onClick={() => setShowDocPicker((v) => !v)}
            disabled={docsLoading}
          >
            {docsLoading ? (
              <span style={{ animation: "spin 1s linear infinite", display: "inline-block", fontSize: "12px" }}>⟳</span>
            ) : (
              <svg width="12" height="12" viewBox="0 0 20 20" fill="none">
                <path d="M4 2h8l4 4v12a2 2 0 01-2 2H4a2 2 0 01-2-2V4a2 2 0 012-2z"
                  stroke="currentColor" strokeWidth="1.7" />
              </svg>
            )}
            <span style={s.docSelectorLabel}>{docPickerLabel}</span>
            <svg width="9" height="9" viewBox="0 0 12 12" fill="none"
              style={{ transform: showDocPicker ? "rotate(180deg)" : "none", transition: "transform 0.15s" }}>
              <path d="M2 4l4 4 4-4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
            </svg>
          </button>

          {showDocPicker && (
            <div style={s.dropdown}>
              {/* General chat option */}
              <div
                style={{ ...s.dropItem, ...(selectedDoc === null ? s.dropItemActive : {}) }}
                onClick={handleClearDoc}
              >
                <svg width="12" height="12" viewBox="0 0 20 20" fill="none">
                  <path d="M2 4a2 2 0 012-2h12a2 2 0 012 2v8a2 2 0 01-2 2H6l-4 4V4z"
                    stroke="#64748b" strokeWidth="1.7" />
                </svg>
                <span style={{ flex: 1 }}>General chat (no document)</span>
                {selectedDoc === null && <span style={s.checkMark}>✓</span>}
              </div>

              <div style={s.dropDivider} />

              {docsError && (
                <div style={s.dropError}>⚠ {docsError}</div>
              )}

              {!docsLoading && readyDocs.length === 0 && (
                <div style={s.dropDisabled}>
                  No ready documents. Upload and process a PDF first.
                </div>
              )}

              {docsLoading && (
                <div style={s.dropDisabled}>
                  <span style={{ animation: "spin 1s linear infinite", display: "inline-block" }}>⟳</span>
                  {" "}Loading…
                </div>
              )}

              {readyDocs.map((d) => {
                const isActive = selectedDoc?.id === d.id;
                return (
                  <div
                    key={d.id}
                    style={{ ...s.dropItem, ...(isActive ? s.dropItemActive : {}) }}
                    onClick={() => handleSelectDoc(d)}
                  >
                    <div style={{
                      ...s.dropDocIcon,
                      background: isActive ? "#dbeafe" : "#f1f5f9",
                    }}>
                      <svg width="11" height="11" viewBox="0 0 20 20" fill="none">
                        <path d="M4 2h8l4 4v12a2 2 0 01-2 2H4a2 2 0 01-2-2V4a2 2 0 012-2z"
                          stroke={isActive ? "#2563eb" : "#64748b"} strokeWidth="1.7" />
                        <path d="M12 2v4h4" stroke={isActive ? "#2563eb" : "#64748b"} strokeWidth="1.4" />
                      </svg>
                    </div>
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{
                        color: isActive ? "#1d4ed8" : "#0f172a",
                        fontSize: "12px", fontWeight: "500",
                        overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
                      }}>
                        {getDocName(d)}
                      </div>
                      <div style={{ color: "#94a3b8", fontSize: "10px", marginTop: "1px" }}>
                        {[
                          d.ocr?.total_pages && `${d.ocr.total_pages} pages`,
                          d.chunking?.total_chunks && `${d.chunking.total_chunks} chunks`,
                        ].filter(Boolean).join(" · ")}
                      </div>
                    </div>
                    {isActive && <span style={s.checkMark}>✓</span>}
                  </div>
                );
              })}
            </div>
          )}
        </div>

        {/* ── Session list ── */}
        <div style={s.sessionList}>
          {sessions.length === 0 && !loading && (
            <div style={s.noSessions}>
              No conversations yet.<br />Type a message to start.
            </div>
          )}

          {loading && sessions.length === 0 && (
            <div style={s.noSessions}>
              <span style={{ animation: "spin 1s linear infinite", display: "inline-block" }}>⟳</span>
              {" "}Loading…
            </div>
          )}

          {sessions.map((sess) => {
            const isActive = activeSession?.id === sess.id;
            const isHovered = hoveredSession === sess.id;
            const sessDoc = readyDocs.find((d) => d.id === sess.document_id);
            return (
              <div
                key={sess.id}
                style={{
                  ...s.sessionItem,
                  ...(isActive ? s.sessionActive : {}),
                  background: isActive ? "#eff6ff" : isHovered ? "#f8fafc" : "transparent",
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
                          stroke={isActive ? "#2563eb" : "#94a3b8"}
                          strokeWidth="1.7" strokeLinejoin="round" />
                      </svg>
                      <span style={s.sessTitle}>{sess.title || "New Chat"}</span>
                      <div style={{ ...s.sessActions, opacity: isHovered || isActive ? 1 : 0 }}>
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
                            <path d="M11 2l3 3-8 8H3v-3l8-8z" stroke="currentColor" strokeWidth="1.4" strokeLinejoin="round" />
                          </svg>
                        </button>
                        <button
                          style={{ ...s.iconBtn, color: "#ef4444" }}
                          title="Delete"
                          onClick={(e) => { e.stopPropagation(); deleteSession(sess.id); }}
                        >
                          <svg width="10" height="10" viewBox="0 0 16 16" fill="none">
                            <path d="M3 4h10M6 2h4M5 4l.5 9h5l.5-9" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" />
                          </svg>
                        </button>
                      </div>
                    </div>
                    {sessDoc && (
                      <div style={s.sessDoc} title={getDocName(sessDoc)}>
                        📄 {getDocShort(sessDoc, 24)}
                      </div>
                    )}
                    {sess.message_count > 0 && (
                      <div style={s.sessMeta}>
                        {sess.message_count} msg{sess.message_count > 1 ? "s" : ""}
                      </div>
                    )}
                  </>
                )}
              </div>
            );
          })}
        </div>
      </aside>

      {/* ── Chat Area ── */}
      <div style={s.chatArea}>

        {/* Selected document banner */}
        {selectedDoc ? (
          <div style={s.docBanner}>
            <div style={s.bannerLeft}>
              <div style={s.bannerIconWrap}>
                <svg width="12" height="12" viewBox="0 0 20 20" fill="none">
                  <path d="M4 2h8l4 4v12a2 2 0 01-2 2H4a2 2 0 01-2-2V4a2 2 0 012-2z"
                    stroke="#2563eb" strokeWidth="1.7" />
                </svg>
              </div>
              <span style={s.bannerMode}>RAG mode</span>
              <span style={s.bannerSep}>·</span>
              <span style={s.bannerDoc}>{getDocName(selectedDoc)}</span>
            </div>
            <button style={s.bannerClear} onClick={handleClearDoc}>
              ✕ Clear
            </button>
          </div>
        ) : (
          <div style={s.generalBanner}>
            <span style={s.generalBannerText}>
              General chat mode — select a document in the sidebar to enable RAG
            </span>
            {readyDocs.length > 0 && (
              <button style={s.generalBannerBtn} onClick={() => setShowDocPicker(true)}>
                Select document
              </button>
            )}
          </div>
        )}

        {/* Error banner */}
        {chatError && (
          <div style={s.errorBanner}>{chatError}</div>
        )}

        {/* Messages */}
        <div style={s.messages}>
          {messages.length === 0 && !sending && (
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
                  ? "I'll retrieve the most relevant sections and give you accurate, sourced answers."
                  : "Select a document from the sidebar for grounded, RAG-powered answers."}
              </p>
              {!selectedDoc && readyDocs.length > 0 && (
                <button style={s.welcomeDocBtn} onClick={() => setShowDocPicker(true)}>
                  <svg width="12" height="12" viewBox="0 0 20 20" fill="none">
                    <path d="M4 2h8l4 4v12a2 2 0 01-2 2H4a2 2 0 01-2-2V4a2 2 0 012-2z"
                      stroke="currentColor" strokeWidth="1.7" />
                  </svg>
                  Select a document ({readyDocs.length} ready)
                </button>
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
                    {isUser ? msg.content : renderMarkdown(msg.content)}
                  </div>


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
          {/* Compact doc indicator inside input bar */}
          {selectedDoc && (
            <div style={s.inputDocChip}>
              <svg width="10" height="10" viewBox="0 0 20 20" fill="none">
                <path d="M4 2h8l4 4v12a2 2 0 01-2 2H4a2 2 0 01-2-2V4a2 2 0 012-2z"
                  stroke="#2563eb" strokeWidth="1.7" />
              </svg>
              <span>{getDocShort(selectedDoc, 28)}</span>
              <button style={s.chipClear} onClick={handleClearDoc} title="Clear document">✕</button>
            </div>
          )}
          <div style={s.inputRow}>
            <textarea
              style={s.textarea}
              placeholder={
                selectedDoc
                  ? `Ask about "${getDocShort(selectedDoc, 24)}"…`
                  : "Type a message… (select a document above for RAG mode)"
              }
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              rows={1}
            />
            <button
              style={{ ...s.sendBtn, opacity: (!input.trim() || sending) ? 0.4 : 1 }}
              onClick={handleSend}
              disabled={!input.trim() || sending}
              title="Send (Enter)"
            >
              <svg width="16" height="16" viewBox="0 0 20 20" fill="none">
                <path d="M3 10l14-7-5 7 5 7-14-7z" fill="white" />
              </svg>
            </button>
          </div>
          <div style={s.inputHint}>
            Enter to send · Shift+Enter for new line ·{" "}
            {selectedDoc ? <strong style={{ color: "#2563eb" }}>RAG mode</strong> : "General mode"}
          </div>
        </div>
      </div>
    </div>
  );
}

/* ─── styles ─────────────────────────────────────────────────────────────── */
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
    width: "250px",
    minWidth: "250px",
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
    padding: "14px 14px 10px",
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

  /* Document picker */
  docSelectorWrap: {
    padding: "8px 10px 6px",
    borderBottom: "1px solid #f1f5f9",
    position: "relative",
  },
  docSelectorBtn: {
    display: "flex",
    alignItems: "center",
    gap: "6px",
    width: "100%",
    border: "1px solid #e2e8f0",
    borderRadius: "8px",
    padding: "8px 10px",
    fontSize: "11px",
    cursor: "pointer",
    fontFamily: "inherit",
    textAlign: "left",
    transition: "background 0.1s, border-color 0.1s",
  },
  docSelectorLabel: {
    flex: 1,
    overflow: "hidden",
    textOverflow: "ellipsis",
    whiteSpace: "nowrap",
  },
  dropdown: {
    position: "absolute",
    top: "calc(100% + 2px)",
    left: "10px",
    right: "10px",
    background: "#fff",
    border: "1px solid #e2e8f0",
    borderRadius: "10px",
    padding: "6px",
    zIndex: 300,
    boxShadow: "0 8px 30px rgba(0,0,0,0.14)",
    maxHeight: "240px",
    overflowY: "auto",
  },
  dropDivider: { height: "1px", background: "#f1f5f9", margin: "4px 0" },
  dropItem: {
    display: "flex",
    alignItems: "center",
    gap: "8px",
    padding: "8px 9px",
    borderRadius: "7px",
    cursor: "pointer",
    color: "#374151",
    fontSize: "12px",
    userSelect: "none",
  },
  dropItemActive: { background: "#eff6ff", color: "#1d4ed8" },
  dropDocIcon: {
    width: "26px",
    height: "26px",
    borderRadius: "6px",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    flexShrink: 0,
  },
  dropDisabled: { padding: "8px 9px", color: "#94a3b8", fontSize: "11px", lineHeight: "1.5" },
  dropError:   { padding: "8px 9px", color: "#dc2626", fontSize: "11px" },
  checkMark: { color: "#2563eb", fontSize: "12px", fontWeight: "700", marginLeft: "auto", flexShrink: 0 },

  /* Session list */
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

  /* Document banner (active RAG mode) */
  docBanner: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    background: "#eff6ff",
    borderBottom: "1px solid #bfdbfe",
    padding: "8px 20px",
    flexShrink: 0,
    gap: "12px",
  },
  bannerLeft: { display: "flex", alignItems: "center", gap: "8px", minWidth: 0 },
  bannerIconWrap: {
    width: "24px", height: "24px", background: "#dbeafe", borderRadius: "6px",
    display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0,
  },
  bannerMode: { color: "#1d4ed8", fontSize: "12px", fontWeight: "700", flexShrink: 0 },
  bannerSep: { color: "#93c5fd", fontSize: "12px", flexShrink: 0 },
  bannerDoc: {
    color: "#3b82f6", fontSize: "12px",
    overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
  },
  bannerClear: {
    background: "transparent", border: "1px solid #bfdbfe", color: "#3b82f6",
    borderRadius: "6px", cursor: "pointer", fontSize: "11px", fontFamily: "inherit",
    padding: "3px 9px", flexShrink: 0,
  },

  /* General chat banner */
  generalBanner: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    background: "#f8fafc",
    borderBottom: "1px solid #e2e8f0",
    padding: "7px 20px",
    flexShrink: 0,
    gap: "12px",
  },
  generalBannerText: { color: "#94a3b8", fontSize: "11px" },
  generalBannerBtn: {
    background: "#fff", border: "1px solid #e2e8f0", color: "#374151",
    borderRadius: "6px", padding: "4px 10px", fontSize: "11px",
    cursor: "pointer", fontFamily: "inherit", flexShrink: 0,
  },

  /* Error banner */
  errorBanner: {
    background: "#fef2f2", borderBottom: "1px solid #fecaca",
    color: "#dc2626", padding: "8px 20px", fontSize: "12px", flexShrink: 0,
  },

  /* Messages */
  messages: {
    flex: 1, overflowY: "auto", padding: "20px 24px",
    display: "flex", flexDirection: "column", gap: "14px",
  },
  welcome: {
    margin: "auto", textAlign: "center", maxWidth: "460px", padding: "40px 20px",
    display: "flex", flexDirection: "column", alignItems: "center", gap: "14px",
  },
  welcomeIcon: {
    width: "60px", height: "60px", background: "#eff6ff",
    border: "1px solid #bfdbfe", borderRadius: "16px",
    display: "flex", alignItems: "center", justifyContent: "center",
  },
  welcomeTitle: { color: "#0f172a", fontSize: "19px", fontWeight: "700", margin: 0, letterSpacing: "-0.4px" },
  welcomeSub: { color: "#64748b", fontSize: "14px", margin: 0, lineHeight: "1.65" },
  welcomeDocBtn: {
    display: "flex", alignItems: "center", gap: "7px",
    background: "#eff6ff", color: "#2563eb",
    border: "1px solid #bfdbfe", borderRadius: "8px",
    padding: "9px 16px", fontSize: "13px", fontWeight: "600",
    cursor: "pointer", fontFamily: "inherit",
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
  sourcesTitle: {
    color: "#64748b", fontSize: "10px", fontWeight: "700", textTransform: "uppercase",
    letterSpacing: "0.5px", marginBottom: "8px", display: "flex", alignItems: "center",
  },
  sourceItem: { display: "flex", alignItems: "center", gap: "6px", marginBottom: "5px", minWidth: 0 },
  srcLeft: { display: "flex", gap: "4px", flexShrink: 0 },
  srcBadge: { background: "#f0fdf4", border: "1px solid #86efac", color: "#16a34a", borderRadius: "4px", padding: "1px 6px", fontSize: "10px", fontWeight: "600", flexShrink: 0 },
  srcSection: { color: "#374151", fontSize: "11px", flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" },

  typing: { display: "flex", gap: "4px", padding: "4px 2px", alignItems: "center" },
  dot3: { width: "7px", height: "7px", background: "#cbd5e1", borderRadius: "50%", display: "inline-block", animation: "bounce3 1.2s infinite" },

  /* Input bar */
  inputBar: { borderTop: "1px solid #e2e8f0", padding: "10px 20px 14px", background: "#fff", flexShrink: 0 },
  inputDocChip: {
    display: "inline-flex",
    alignItems: "center",
    gap: "5px",
    background: "#eff6ff",
    border: "1px solid #bfdbfe",
    color: "#1d4ed8",
    borderRadius: "6px",
    padding: "3px 8px",
    fontSize: "11px",
    fontWeight: "500",
    marginBottom: "8px",
  },
  chipClear: {
    background: "none", border: "none", cursor: "pointer",
    color: "#93c5fd", fontSize: "11px", padding: "0 0 0 2px",
    lineHeight: 1,
  },
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
  inputHint: { color: "#94a3b8", fontSize: "11px", marginTop: "6px" },
};
