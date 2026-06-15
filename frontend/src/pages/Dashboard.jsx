import { useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../hooks/useAuth.jsx";
import { useUserCollections } from "../hooks/useCollections";

const getDocName = (d) => d?.original_filename || d?.filename || "Untitled";
const getDocShort = (d, max = 36) => {
  const n = getDocName(d);
  return n.length > max ? n.slice(0, max) + "…" : n;
};

const STATUS_META = {
  uploaded:   { label: "Uploaded",   color: "#b45309", bg: "#fffbeb", dot: "#f59e0b" },
  processing: { label: "Processing", color: "#1d4ed8", bg: "#eff6ff", dot: "#3b82f6" },
  ready:      { label: "Ready",      color: "#15803d", bg: "#f0fdf4", dot: "#22c55e" },
  failed:     { label: "Failed",     color: "#b91c1c", bg: "#fef2f2", dot: "#ef4444" },
};

function StatusBadge({ status }) {
  const m = STATUS_META[status] || STATUS_META.processing;
  return (
    <span style={{
      background: m.bg, color: m.color, borderRadius: "20px",
      padding: "2px 9px", fontSize: "11px", fontWeight: "600",
      display: "inline-flex", alignItems: "center", gap: "5px",
    }}>
      <span style={{
        width: "5px", height: "5px", borderRadius: "50%",
        background: m.dot, flexShrink: 0,
        ...(status === "processing" ? { animation: "pulse 1.4s infinite" } : {}),
      }} />
      {m.label}
    </span>
  );
}

export default function Dashboard() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const { collections, loading, fetchCollections, startPolling, stopPolling } = useUserCollections();

  useEffect(() => {
    fetchCollections();
    startPolling();
    return () => stopPolling();
  }, []);

  const documents = collections.flatMap((c) => c.documents || []);

  const readyDocs     = documents.filter((d) => d.status === "ready");
  const processingDocs = documents.filter((d) => d.status === "processing" || d.status === "uploaded");
  const failedDocs    = documents.filter((d) => d.status === "failed");
  const recentDocs    = [...documents].slice(0, 5);

  const firstName = user?.full_name?.split(" ")[0] || "there";

  return (
    <div style={s.page}>
      <style>{`
        @keyframes pulse { 0%,100%{opacity:1} 50%{opacity:0.35} }
        @keyframes spin   { to{transform:rotate(360deg)} }
      `}</style>

      {/* Page header */}
      <div style={s.pageHeader}>
        <div>
          <h1 style={s.pageTitle}>Dashboard</h1>
          <p style={s.pageSubtitle}>Welcome back, {firstName}! Here's your workspace overview.</p>
        </div>
        {processingDocs.length > 0 && (
          <div style={s.processingPill}>
            <span style={{ animation: "spin 1s linear infinite", display: "inline-block" }}>⟳</span>
            {processingDocs.length} processing…
          </div>
        )}
      </div>

      {/* Scrollable content */}
      <div style={s.content}>

        {/* Stats cards */}
        <div style={s.statsGrid}>
          {[
            { label: "Total Documents", value: documents.length, icon: "📄", color: "#2563eb", bg: "#eff6ff" },
            { label: "Ready for Chat",  value: readyDocs.length, icon: "✓",  color: "#16a34a", bg: "#f0fdf4" },
            { label: "Processing",      value: processingDocs.length, icon: "⟳", color: "#2563eb", bg: "#eff6ff" },
            { label: "Failed",          value: failedDocs.length, icon: "⚠", color: "#dc2626", bg: "#fef2f2" },
          ].map(({ label, value, icon, color, bg }) => (
            <div key={label} style={s.statCard}>
              <div style={{ ...s.statIcon, background: bg, color }}>
                {icon}
              </div>
              <div>
                <div style={{ ...s.statValue, color }}>{value}</div>
                <div style={s.statLabel}>{label}</div>
              </div>
            </div>
          ))}
        </div>

        {/* Quick actions */}
        <div style={s.section}>
          <div style={s.sectionTitle}>Quick Actions</div>
          <div style={s.actionsRow}>
            <button style={s.actionCard} onClick={() => navigate("/documents")}>
              <div style={{ ...s.actionIcon, background: "#eff6ff" }}>
                <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
                  <path d="M10 3v10M6 7l4-4 4 4" stroke="#2563eb" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
                  <path d="M3 16v1h14v-1" stroke="#2563eb" strokeWidth="1.6" strokeLinecap="round" />
                </svg>
              </div>
              <div style={s.actionLabel}>View Collections</div>
              <div style={s.actionSub}>Browse documents assigned to you</div>
            </button>

            <button
              style={{ ...s.actionCard, ...(readyDocs.length === 0 ? s.actionCardDisabled : {}) }}
              onClick={() => readyDocs.length > 0 && navigate("/chat")}
              disabled={readyDocs.length === 0}
            >
              <div style={{ ...s.actionIcon, background: readyDocs.length > 0 ? "#f0fdf4" : "#f8fafc" }}>
                <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
                  <path d="M2 4a2 2 0 012-2h12a2 2 0 012 2v8a2 2 0 01-2 2H6l-4 4V4z"
                    stroke={readyDocs.length > 0 ? "#16a34a" : "#cbd5e1"} strokeWidth="1.8" strokeLinejoin="round" />
                </svg>
              </div>
              <div style={{ ...s.actionLabel, color: readyDocs.length > 0 ? "#0f172a" : "#94a3b8" }}>Start Chat</div>
              <div style={s.actionSub}>
                {readyDocs.length > 0 ? `${readyDocs.length} document${readyDocs.length > 1 ? "s" : ""} ready` : "No ready documents yet"}
              </div>
            </button>

            <button style={s.actionCard} onClick={() => navigate("/documents")}>
              <div style={{ ...s.actionIcon, background: "#fffbeb" }}>
                <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
                  <path d="M4 2h8l4 4v12a2 2 0 01-2 2H4a2 2 0 01-2-2V4a2 2 0 012-2z"
                    stroke="#b45309" strokeWidth="1.8" />
                  <path d="M12 2v4h4" stroke="#b45309" strokeWidth="1.5" />
                  <path d="M6 9h8M6 13h5" stroke="#b45309" strokeWidth="1.4" strokeLinecap="round" />
                </svg>
              </div>
              <div style={s.actionLabel}>View Documents</div>
              <div style={s.actionSub}>Manage all your PDFs</div>
            </button>
          </div>
        </div>

        {/* Processing pipeline info */}
        <div style={s.section}>
          <div style={s.sectionTitle}>Processing Pipeline</div>
          <div style={s.pipelineGrid}>
            {[
              { key: "OCR",        val: "pdfplumber",          desc: "Text extraction from PDFs" },
              { key: "Chunking",   val: "600 tokens",          desc: "Smart text splitting" },
              { key: "Embeddings", val: "mxbai-embed-large",   desc: "Vector representation" },
              { key: "Vector DB",  val: "ChromaDB",            desc: "Semantic search index" },
              { key: "LLM",        val: "qwen2.5:7b",          desc: "Answer generation" },
            ].map(({ key, val, desc }) => (
              <div key={key} style={s.pipeCard}>
                <div style={s.pipeCardKey}>{key}</div>
                <div style={s.pipeCardVal}>{val}</div>
                <div style={s.pipeCardDesc}>{desc}</div>
              </div>
            ))}
          </div>
        </div>

        {/* Recent documents */}
        {recentDocs.length > 0 && (
          <div style={s.section}>
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "12px" }}>
              <div style={s.sectionTitle}>Recent Documents</div>
              <button style={s.viewAllBtn} onClick={() => navigate("/documents")}>
                View all →
              </button>
            </div>
            <div style={s.recentList}>
              {recentDocs.map((doc) => (
                <div key={doc.id} style={s.recentRow}>
                  <div style={s.recentIcon}>
                    <svg width="14" height="14" viewBox="0 0 20 20" fill="none">
                      <path d="M4 2h8l4 4v12a2 2 0 01-2 2H4a2 2 0 01-2-2V4a2 2 0 012-2z"
                        stroke="#2563eb" strokeWidth="1.7" />
                      <path d="M12 2v4h4" stroke="#2563eb" strokeWidth="1.4" />
                    </svg>
                  </div>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={s.recentName}>{getDocShort(doc)}</div>
                    {doc.ocr?.total_pages && (
                      <div style={s.recentMeta}>{doc.ocr.total_pages} pages</div>
                    )}
                  </div>
                  <StatusBadge status={doc.status} />
                  {doc.status === "ready" && (
                    <button
                      style={s.chatBtn}
                      onClick={() => navigate("/chat", { state: { documentId: doc.id, documentName: getDocName(doc) } })}
                    >
                      Chat →
                    </button>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Empty state */}
        {!loading && documents.length === 0 && (
          <div style={s.emptyState}>
            <svg width="48" height="48" viewBox="0 0 60 60" fill="none">
              <rect x="10" y="5" width="40" height="50" rx="5" stroke="#cbd5e1" strokeWidth="2" />
              <path d="M38 5v10h12" stroke="#cbd5e1" strokeWidth="2" strokeLinejoin="round" />
              <path d="M18 24h24M18 32h18M18 40h12" stroke="#cbd5e1" strokeWidth="2" strokeLinecap="round" />
            </svg>
            <div style={s.emptyTitle}>No collections assigned</div>
            <div style={s.emptyText}>Your administrator will assign document collections to your account.</div>
            <button style={s.emptyBtn} onClick={() => navigate("/documents")}>
              View collections →
            </button>
          </div>
        )}

      </div>
    </div>
  );
}

const s = {
  page: {
    display: "flex",
    flexDirection: "column",
    height: "100%",
    background: "#f8fafc",
    fontFamily: "'Plus Jakarta Sans', 'DM Sans', system-ui, sans-serif",
    overflow: "hidden",
  },
  pageHeader: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    padding: "24px 28px 16px",
    background: "#fff",
    borderBottom: "1px solid #e2e8f0",
    flexShrink: 0,
    gap: "12px",
  },
  pageTitle: { color: "#0f172a", fontSize: "20px", fontWeight: "700", margin: 0, letterSpacing: "-0.4px" },
  pageSubtitle: { color: "#64748b", fontSize: "13px", margin: "3px 0 0" },
  processingPill: {
    display: "flex", alignItems: "center", gap: "6px",
    background: "#fffbeb", color: "#b45309", border: "1px solid #fde68a",
    borderRadius: "20px", padding: "6px 14px", fontSize: "12px", fontWeight: "600",
    flexShrink: 0,
  },
  content: {
    flex: 1, overflowY: "auto", padding: "24px 28px", display: "flex",
    flexDirection: "column", gap: "24px",
  },
  statsGrid: { display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: "12px" },
  statCard: {
    background: "#fff", border: "1px solid #e2e8f0", borderRadius: "12px",
    padding: "18px", display: "flex", alignItems: "center", gap: "14px",
    boxShadow: "0 1px 3px rgba(0,0,0,0.04)",
  },
  statIcon: {
    width: "44px", height: "44px", borderRadius: "10px",
    display: "flex", alignItems: "center", justifyContent: "center",
    fontSize: "18px", flexShrink: 0,
  },
  statValue: { fontSize: "24px", fontWeight: "700", lineHeight: "1" },
  statLabel: { color: "#64748b", fontSize: "12px", marginTop: "3px" },
  section: {
    background: "#fff", border: "1px solid #e2e8f0", borderRadius: "12px", padding: "20px",
  },
  sectionTitle: {
    color: "#374151", fontSize: "12px", fontWeight: "700",
    textTransform: "uppercase", letterSpacing: "0.6px", marginBottom: "14px",
  },
  actionsRow: { display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: "12px" },
  actionCard: {
    display: "flex", flexDirection: "column", alignItems: "flex-start", gap: "8px",
    background: "#f8fafc", border: "1px solid #e2e8f0", borderRadius: "10px",
    padding: "16px", cursor: "pointer", fontFamily: "inherit", textAlign: "left",
    transition: "background 0.1s, border-color 0.1s",
  },
  actionCardDisabled: { opacity: 0.5, cursor: "not-allowed" },
  actionIcon: {
    width: "40px", height: "40px", borderRadius: "10px",
    display: "flex", alignItems: "center", justifyContent: "center",
  },
  actionLabel: { color: "#0f172a", fontSize: "13px", fontWeight: "600" },
  actionSub: { color: "#64748b", fontSize: "11px" },
  pipelineGrid: { display: "grid", gridTemplateColumns: "repeat(5, 1fr)", gap: "10px" },
  pipeCard: {
    background: "#f8fafc", border: "1px solid #e2e8f0", borderRadius: "8px", padding: "12px",
  },
  pipeCardKey: { color: "#374151", fontSize: "11px", fontWeight: "700", textTransform: "uppercase", letterSpacing: "0.4px" },
  pipeCardVal: { color: "#2563eb", fontSize: "12px", fontWeight: "600", marginTop: "4px" },
  pipeCardDesc: { color: "#94a3b8", fontSize: "10px", marginTop: "3px", lineHeight: "1.4" },
  viewAllBtn: {
    background: "transparent", border: "none", color: "#2563eb",
    fontSize: "12px", fontWeight: "600", cursor: "pointer", fontFamily: "inherit",
  },
  recentList: { display: "flex", flexDirection: "column" },
  recentRow: {
    display: "flex", alignItems: "center", gap: "12px",
    padding: "10px 0", borderBottom: "1px solid #f1f5f9",
  },
  recentIcon: {
    width: "32px", height: "32px", background: "#eff6ff", borderRadius: "7px",
    display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0,
  },
  recentName: { color: "#0f172a", fontSize: "13px", fontWeight: "500", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" },
  recentMeta: { color: "#94a3b8", fontSize: "11px", marginTop: "1px" },
  chatBtn: {
    background: "transparent", border: "1px solid #bfdbfe",
    color: "#2563eb", borderRadius: "6px", padding: "4px 10px",
    fontSize: "11px", fontWeight: "600", cursor: "pointer", fontFamily: "inherit",
    flexShrink: 0,
  },
  emptyState: {
    display: "flex", flexDirection: "column", alignItems: "center",
    gap: "12px", padding: "40px 32px", textAlign: "center",
    background: "#fff", border: "1px solid #e2e8f0", borderRadius: "12px",
  },
  emptyTitle: { color: "#374151", fontSize: "16px", fontWeight: "600" },
  emptyText: { color: "#94a3b8", fontSize: "13px", maxWidth: "360px", lineHeight: "1.6" },
  emptyBtn: {
    background: "#2563eb", color: "#fff", border: "none",
    borderRadius: "8px", padding: "10px 20px", fontSize: "13px",
    fontWeight: "600", cursor: "pointer", fontFamily: "inherit", marginTop: "4px",
  },
};
