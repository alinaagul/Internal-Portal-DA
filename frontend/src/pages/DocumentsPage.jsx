import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { useDocuments } from "../hooks/useDocuments";
import DocumentUpload from "../components/DocumentUpload";
import StatusModal from "../components/StatusModal";

const getDocName = (d) => d?.original_filename || d?.filename || "Untitled";
const getDocShort = (d, max = 46) => {
  const n = getDocName(d);
  return n.length > max ? n.slice(0, max) + "…" : n;
};

const formatDate = (iso) => {
  if (!iso) return "—";
  return new Date(iso).toLocaleDateString([], { month: "short", day: "numeric", year: "numeric" });
};

const STATUS_META = {
  uploaded:   { label: "Uploaded",   color: "#b45309", bg: "#fffbeb", border: "#fde68a" },
  processing: { label: "Processing", color: "#1d4ed8", bg: "#eff6ff", border: "#bfdbfe" },
  ready:      { label: "Ready",      color: "#15803d", bg: "#f0fdf4", border: "#86efac" },
  failed:     { label: "Failed",     color: "#b91c1c", bg: "#fef2f2", border: "#fecaca" },
};

function StatusBadge({ status }) {
  const m = STATUS_META[status] || STATUS_META.processing;
  return (
    <span style={{
      background: m.bg, color: m.color,
      border: `1px solid ${m.border}`,
      borderRadius: "20px", padding: "3px 10px",
      fontSize: "11px", fontWeight: "600",
      display: "inline-flex", alignItems: "center", gap: "5px",
    }}>
      <span style={{
        width: "5px", height: "5px", borderRadius: "50%",
        background: m.color, flexShrink: 0,
        ...(status === "processing" ? { animation: "pulse 1.4s infinite" } : {}),
      }} />
      {m.label}
    </span>
  );
}

function DocRow({ doc, active, onView, onChat, onStatus, onDelete }) {
  const [hovering, setHovering] = useState(false);
  const name = getDocName(doc);

  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        padding: "12px 20px",
        borderBottom: "1px solid #f1f5f9",
        background: active ? "#eff6ff" : hovering ? "#f8fafc" : "#fff",
        borderLeft: `3px solid ${active ? "#2563eb" : "transparent"}`,
        cursor: "pointer",
        transition: "background 0.1s",
        gap: "0",
      }}
      onMouseEnter={() => setHovering(true)}
      onMouseLeave={() => setHovering(false)}
      onClick={onView}
    >
      {/* File icon + name */}
      <div style={{ display: "flex", alignItems: "center", gap: "12px", flex: "1 1 0", minWidth: 0 }}>
        <div style={{
          width: "36px", height: "36px", background: active ? "#dbeafe" : "#f1f5f9",
          borderRadius: "8px", display: "flex", alignItems: "center",
          justifyContent: "center", flexShrink: 0,
        }}>
          <svg width="16" height="16" viewBox="0 0 20 20" fill="none">
            <path d="M4 2h8l4 4v12a2 2 0 01-2 2H4a2 2 0 01-2-2V4a2 2 0 012-2z"
              stroke={active ? "#2563eb" : "#64748b"} strokeWidth="1.7" />
            <path d="M12 2v4h4" stroke={active ? "#2563eb" : "#64748b"} strokeWidth="1.4" />
          </svg>
        </div>
        <div style={{ minWidth: 0 }}>
          <div style={{
            color: active ? "#1d4ed8" : "#0f172a", fontSize: "13px", fontWeight: "600",
            overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
          }} title={name}>
            {name}
          </div>
          <div style={{ color: "#94a3b8", fontSize: "11px", marginTop: "1px" }}>PDF Document</div>
        </div>
      </div>

      {/* Date */}
      <div style={{ width: "110px", color: "#64748b", fontSize: "12px", flexShrink: 0 }}>
        {formatDate(doc.created_at)}
      </div>

      {/* Pages */}
      <div style={{ width: "70px", color: "#64748b", fontSize: "12px", flexShrink: 0 }}>
        {doc.ocr?.total_pages ? `${doc.ocr.total_pages} pg` : "—"}
      </div>

      {/* Status */}
      <div style={{ width: "120px", flexShrink: 0 }}>
        <StatusBadge status={doc.status} />
      </div>

      {/* Actions */}
      <div
        style={{ display: "flex", gap: "6px", flexShrink: 0 }}
        onClick={(e) => e.stopPropagation()}
      >
        <button style={s.actionBtn} onClick={onView} title="View details">
          <svg width="11" height="11" viewBox="0 0 20 20" fill="none">
            <circle cx="10" cy="10" r="3" stroke="currentColor" strokeWidth="1.8" />
            <path d="M2 10s3-6 8-6 8 6 8 6-3 6-8 6-8-6-8-6z" stroke="currentColor" strokeWidth="1.8" />
          </svg>
          View
        </button>

        <button
          style={{ ...s.actionBtn, ...s.actionBtnStatus }}
          onClick={onStatus}
          title="Processing status"
        >
          <svg width="11" height="11" viewBox="0 0 20 20" fill="none">
            <circle cx="10" cy="10" r="8" stroke="currentColor" strokeWidth="1.8" />
            <path d="M10 6v4l3 3" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
          </svg>
          Status
        </button>

        {doc.status === "ready" && (
          <button style={{ ...s.actionBtn, ...s.actionBtnPrimary }} onClick={onChat} title="Chat">
            <svg width="11" height="11" viewBox="0 0 20 20" fill="none">
              <path d="M2 4a2 2 0 012-2h12a2 2 0 012 2v8a2 2 0 01-2 2H6l-4 4V4z"
                stroke="currentColor" strokeWidth="1.8" strokeLinejoin="round" />
            </svg>
            Chat
          </button>
        )}

        <button style={{ ...s.actionBtn, ...s.actionBtnDanger }} onClick={onDelete} title="Delete">
          <svg width="11" height="11" viewBox="0 0 20 20" fill="none">
            <path d="M6 2h8M3 5h14M8 9v6M12 9v6M4 5l1 13h10L16 5"
              stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </button>
      </div>
    </div>
  );
}

function DetailPanel({ doc, onClose, onChat, onDelete, onRefresh, onStatus }) {
  const name = getDocName(doc);

  return (
    <div style={s.detailPanel}>
      {/* Panel header */}
      <div style={s.detailHeader}>
        <div style={s.detailTitle}>Document Details</div>
        <button style={s.closePanelBtn} onClick={onClose}>
          <svg width="14" height="14" viewBox="0 0 20 20" fill="none">
            <path d="M4 4l12 12M16 4L4 16" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
          </svg>
        </button>
      </div>

      <div style={s.detailBody}>
        {/* File card */}
        <div style={s.fileCard}>
          <div style={s.fileCardIcon}>
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none">
              <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"
                stroke="#2563eb" strokeWidth="1.7" />
              <polyline points="14,2 14,8 20,8" stroke="#2563eb" strokeWidth="1.7" />
              <path d="M8 13h8M8 17h5" stroke="#2563eb" strokeWidth="1.4" strokeLinecap="round" />
            </svg>
          </div>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={s.fileCardName} title={name}>{getDocShort(doc, 36)}</div>
            <div style={s.fileCardMeta}>PDF · {doc.ocr?.total_pages || "?"} pages</div>
          </div>
        </div>

        {/* Status row */}
        <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
          <StatusBadge status={doc.status} />
          {doc.language && (
            <span style={s.langBadge}>{doc.language.toUpperCase()}</span>
          )}
        </div>

        {/* Stats grid */}
        <div style={s.statsGrid}>
          {[
            { label: "Pages",      value: doc.ocr?.total_pages ?? "—" },
            { label: "Chunks",     value: doc.chunking?.total_chunks ?? "—" },
            { label: "Vectors",    value: doc.embedding?.embedded_chunks ?? "—" },
            { label: "Confidence", value: doc.ocr?.avg_confidence_pct != null ? `${doc.ocr.avg_confidence_pct}%` : "—" },
          ].map(({ label, value }) => (
            <div key={label} style={s.statCard}>
              <div style={s.statValue}>{value}</div>
              <div style={s.statLabel}>{label}</div>
            </div>
          ))}
        </div>

        {/* Metadata */}
        <div style={s.metaSection}>
          {doc.created_at && (
            <div style={s.metaRow}>
              <span style={s.metaKey}>Uploaded</span>
              <span style={s.metaVal}>{new Date(doc.created_at).toLocaleString()}</span>
            </div>
          )}
          {doc.ocr?.method && (
            <div style={s.metaRow}>
              <span style={s.metaKey}>OCR Method</span>
              <span style={s.metaVal}>{doc.ocr.method}</span>
            </div>
          )}
          {doc.embedding?.embedding_model && (
            <div style={s.metaRow}>
              <span style={s.metaKey}>Embed Model</span>
              <span style={s.metaVal}>{doc.embedding.embedding_model}</span>
            </div>
          )}
          {doc.ocr?.requires_review != null && (
            <div style={s.metaRow}>
              <span style={s.metaKey}>Needs Review</span>
              <span style={{ ...s.metaVal, color: doc.ocr.requires_review ? "#b91c1c" : "#15803d" }}>
                {doc.ocr.requires_review ? "Yes" : "No"}
              </span>
            </div>
          )}
        </div>

        {/* Processing status */}
        {doc.status !== "ready" && (
          <div style={s.processingSection}>
            <div style={s.processingSectionTitle}>Processing Pipeline</div>
            {[
              { label: "OCR Extraction",   done: !!doc.ocr },
              { label: "Text Chunking",    done: !!doc.chunking },
              { label: "Embeddings",       done: !!doc.embedding },
              { label: "Indexed & Ready",  done: doc.status === "ready" },
            ].map(({ label, done }) => (
              <div key={label} style={s.pipeStep}>
                <span style={{
                  ...s.pipeStepDot,
                  background: done ? "#22c55e" : doc.status === "processing" ? "#3b82f6" : "#e2e8f0",
                }}>
                  {done && (
                    <svg width="8" height="8" viewBox="0 0 12 12" fill="none">
                      <path d="M2 6l2.5 2.5L10 3" stroke="#fff" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
                    </svg>
                  )}
                </span>
                <span style={{ color: done ? "#0f172a" : "#94a3b8", fontSize: "12px" }}>{label}</span>
              </div>
            ))}
          </div>
        )}

        {/* Actions */}
        <div style={s.detailActions}>
          {doc.status === "ready" && (
            <button style={s.primaryAction} onClick={onChat}>
              <svg width="13" height="13" viewBox="0 0 20 20" fill="none">
                <path d="M2 4a2 2 0 012-2h12a2 2 0 012 2v8a2 2 0 01-2 2H6l-4 4V4z"
                  stroke="currentColor" strokeWidth="1.7" strokeLinejoin="round" />
              </svg>
              Open Chat
            </button>
          )}
          <div style={{ display: "flex", gap: "8px" }}>
            <button style={s.secondaryAction} onClick={onRefresh}>
              <svg width="12" height="12" viewBox="0 0 20 20" fill="none">
                <path d="M4 4a8 8 0 1112 1M16 2v4h-4"
                  stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
              </svg>
              Refresh
            </button>
            <button style={s.secondaryAction} onClick={onStatus}>
              <svg width="12" height="12" viewBox="0 0 20 20" fill="none">
                <circle cx="10" cy="10" r="8" stroke="currentColor" strokeWidth="1.8" />
                <path d="M10 6v4l3 3" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
              </svg>
              Full Status
            </button>
          </div>
          <button style={s.deleteAction} onClick={onDelete}>
            <svg width="12" height="12" viewBox="0 0 20 20" fill="none">
              <path d="M6 2h8M3 5h14M8 9v6M12 9v6M4 5l1 13h10L16 5"
                stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
            Delete Document
          </button>
        </div>
      </div>
    </div>
  );
}

export default function DocumentsPage() {
  const navigate = useNavigate();
  const {
    documents, uploading, uploadProgress,
    loading, error, setError,
    fetchDocuments, uploadDocument, deleteDocument,
  } = useDocuments();

  const [showUpload, setShowUpload] = useState(false);
  const [viewDoc, setViewDoc] = useState(null);
  const [statusDoc, setStatusDoc] = useState(null);

  useEffect(() => { fetchDocuments(); }, []);

  // Keep viewDoc in sync with latest document data (for live status updates)
  useEffect(() => {
    if (viewDoc) {
      const updated = documents.find((d) => d.id === viewDoc.id);
      if (updated) setViewDoc(updated);
    }
  }, [documents]);

  const handleChatWithDoc = (doc) => {
    navigate("/chat", { state: { documentId: doc.id, documentName: getDocName(doc) } });
  };

  const handleDelete = async (id) => {
    if (!window.confirm("Delete this document? This cannot be undone.")) return;
    await deleteDocument(id);
    if (viewDoc?.id === id) setViewDoc(null);
  };

  const readyCount = documents.filter((d) => d.status === "ready").length;
  const processingCount = documents.filter(
    (d) => d.status === "processing" || d.status === "uploaded"
  ).length;

  return (
    <div style={s.page}>
      <style>{`
        @keyframes pulse { 0%,100%{opacity:1} 50%{opacity:0.35} }
        @keyframes spin   { to{transform:rotate(360deg)} }
      `}</style>

      {/* Page header */}
      <div style={s.pageHeader}>
        <div>
          <h1 style={s.pageTitle}>Documents</h1>
          <p style={s.pageSubtitle}>
            {loading && documents.length === 0
              ? "Loading…"
              : documents.length === 0
              ? "No documents yet — upload a PDF to get started"
              : `${documents.length} document${documents.length !== 1 ? "s" : ""} · ${readyCount} ready${processingCount > 0 ? ` · ${processingCount} processing` : ""}`}
          </p>
        </div>
        <button
          style={{ ...s.uploadToggleBtn, ...(showUpload ? s.uploadToggleBtnActive : {}) }}
          onClick={() => setShowUpload(!showUpload)}
        >
          <svg width="14" height="14" viewBox="0 0 20 20" fill="none">
            {showUpload ? (
              <path d="M4 4l12 12M16 4L4 16" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
            ) : (
              <>
                <path d="M10 3v10M6 7l4-4 4 4" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" />
                <path d="M3 16v1h14v-1" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
              </>
            )}
          </svg>
          {showUpload ? "Cancel" : "Upload PDF"}
        </button>
      </div>

      {/* Upload drawer */}
      {showUpload && (
        <div style={s.uploadDrawer}>
          <div style={s.uploadDrawerInner}>
            <DocumentUpload
              onUpload={async (file) => {
                const result = await uploadDocument(file);
                if (result?.success) setShowUpload(false);
              }}
              uploading={uploading}
              uploadProgress={uploadProgress}
            />
            {error && (
              <div style={s.errorBanner}>
                <span>{error}</span>
                <button style={s.errorClose} onClick={() => setError(null)}>✕</button>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Main area */}
      <div style={{ display: "flex", flex: 1, overflow: "hidden" }}>

        {/* Document list */}
        <div style={{ flex: 1, display: "flex", flexDirection: "column", overflow: "hidden" }}>

          {/* Table header */}
          {documents.length > 0 && (
            <div style={s.tableHeader}>
              <div style={{ flex: "1 1 0", color: "#64748b", fontSize: "11px", fontWeight: "600", textTransform: "uppercase", letterSpacing: "0.5px" }}>Document</div>
              <div style={{ width: "110px", color: "#64748b", fontSize: "11px", fontWeight: "600", textTransform: "uppercase", letterSpacing: "0.5px" }}>Date</div>
              <div style={{ width: "70px",  color: "#64748b", fontSize: "11px", fontWeight: "600", textTransform: "uppercase", letterSpacing: "0.5px" }}>Pages</div>
              <div style={{ width: "120px", color: "#64748b", fontSize: "11px", fontWeight: "600", textTransform: "uppercase", letterSpacing: "0.5px" }}>Status</div>
              <div style={{ width: "186px", color: "#64748b", fontSize: "11px", fontWeight: "600", textTransform: "uppercase", letterSpacing: "0.5px", textAlign: "right" }}>Actions</div>
            </div>
          )}

          {/* Rows */}
          <div style={{ flex: 1, overflowY: "auto" }}>
            {loading && documents.length === 0 ? (
              <div style={s.emptyState}>
                <div style={{ fontSize: "28px", animation: "spin 1s linear infinite", color: "#94a3b8" }}>⟳</div>
                <span style={s.emptyText}>Loading your documents…</span>
              </div>
            ) : documents.length === 0 ? (
              <div style={s.emptyState}>
                <div style={s.emptyIllustration}>
                  <svg width="48" height="48" viewBox="0 0 60 60" fill="none">
                    <rect x="10" y="5" width="40" height="50" rx="5" stroke="#cbd5e1" strokeWidth="2" />
                    <path d="M38 5v10h12" stroke="#cbd5e1" strokeWidth="2" strokeLinejoin="round" />
                    <path d="M18 24h24M18 32h18M18 40h12" stroke="#cbd5e1" strokeWidth="2" strokeLinecap="round" />
                  </svg>
                </div>
                <div style={s.emptyTitle}>No documents yet</div>
                <div style={s.emptyText}>Upload a PDF to start using AI-powered document chat</div>
                <button style={s.emptyCta} onClick={() => setShowUpload(true)}>
                  <svg width="13" height="13" viewBox="0 0 20 20" fill="none">
                    <path d="M10 3v10M6 7l4-4 4 4M3 16v1h14v-1" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" />
                  </svg>
                  Upload your first PDF
                </button>
              </div>
            ) : (
              documents.map((doc) => (
                <DocRow
                  key={doc.id}
                  doc={doc}
                  active={viewDoc?.id === doc.id}
                  onView={() => setViewDoc(viewDoc?.id === doc.id ? null : doc)}
                  onChat={() => handleChatWithDoc(doc)}
                  onStatus={() => setStatusDoc(doc)}
                  onDelete={() => handleDelete(doc.id)}
                />
              ))
            )}
          </div>
        </div>

        {/* Detail panel */}
        {viewDoc && (
          <DetailPanel
            doc={viewDoc}
            onClose={() => setViewDoc(null)}
            onChat={() => handleChatWithDoc(viewDoc)}
            onDelete={() => handleDelete(viewDoc.id)}
            onRefresh={fetchDocuments}
            onStatus={() => setStatusDoc(viewDoc)}
          />
        )}
      </div>

      {/* Status modal */}
      {statusDoc && (
        <StatusModal
          doc={statusDoc}
          onClose={() => setStatusDoc(null)}
        />
      )}
    </div>
  );
}

/* ─── styles ── */
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
    gap: "16px",
  },
  pageTitle: {
    color: "#0f172a",
    fontSize: "20px",
    fontWeight: "700",
    margin: 0,
    letterSpacing: "-0.4px",
  },
  pageSubtitle: {
    color: "#64748b",
    fontSize: "13px",
    margin: "3px 0 0",
  },
  uploadToggleBtn: {
    display: "flex",
    alignItems: "center",
    gap: "7px",
    background: "#2563eb",
    color: "#fff",
    border: "none",
    borderRadius: "8px",
    padding: "9px 16px",
    fontSize: "13px",
    fontWeight: "600",
    cursor: "pointer",
    fontFamily: "inherit",
    flexShrink: 0,
  },
  uploadToggleBtnActive: {
    background: "#f1f5f9",
    color: "#64748b",
    border: "1px solid #e2e8f0",
  },
  uploadDrawer: {
    background: "#fff",
    borderBottom: "1px solid #e2e8f0",
    flexShrink: 0,
  },
  uploadDrawerInner: {
    maxWidth: "520px",
    margin: "0 auto",
    padding: "20px 28px",
  },
  errorBanner: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    background: "#fef2f2",
    border: "1px solid #fecaca",
    borderRadius: "8px",
    padding: "8px 12px",
    color: "#dc2626",
    fontSize: "12px",
    marginTop: "10px",
  },
  errorClose: {
    background: "none",
    border: "none",
    cursor: "pointer",
    color: "#dc2626",
    fontSize: "13px",
  },

  tableHeader: {
    display: "flex",
    alignItems: "center",
    padding: "8px 20px",
    background: "#f8fafc",
    borderBottom: "1px solid #e2e8f0",
    flexShrink: 0,
    gap: "0",
  },

  actionBtn: {
    display: "flex",
    alignItems: "center",
    gap: "4px",
    background: "#f8fafc",
    border: "1px solid #e2e8f0",
    color: "#64748b",
    borderRadius: "6px",
    padding: "5px 10px",
    fontSize: "11px",
    fontWeight: "500",
    cursor: "pointer",
    fontFamily: "inherit",
    whiteSpace: "nowrap",
  },
  actionBtnPrimary: {
    background: "#eff6ff",
    border: "1px solid #bfdbfe",
    color: "#2563eb",
  },
  actionBtnStatus: {
    background: "#fffbeb",
    border: "1px solid #fde68a",
    color: "#b45309",
  },
  actionBtnDanger: {
    background: "#fef2f2",
    border: "1px solid #fecaca",
    color: "#dc2626",
    padding: "5px 8px",
  },

  emptyState: {
    display: "flex",
    flexDirection: "column",
    alignItems: "center",
    gap: "12px",
    padding: "60px 32px",
    textAlign: "center",
  },
  emptyIllustration: {
    width: "80px",
    height: "80px",
    background: "#f1f5f9",
    borderRadius: "16px",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    marginBottom: "4px",
  },
  emptyTitle: { color: "#374151", fontSize: "16px", fontWeight: "600" },
  emptyText: { color: "#94a3b8", fontSize: "13px", maxWidth: "340px", lineHeight: "1.6" },
  emptyCta: {
    display: "flex",
    alignItems: "center",
    gap: "7px",
    background: "#2563eb",
    color: "#fff",
    border: "none",
    borderRadius: "8px",
    padding: "10px 20px",
    fontSize: "13px",
    fontWeight: "600",
    cursor: "pointer",
    fontFamily: "inherit",
    marginTop: "4px",
  },

  /* Detail panel */
  detailPanel: {
    width: "320px",
    minWidth: "320px",
    background: "#fff",
    borderLeft: "1px solid #e2e8f0",
    display: "flex",
    flexDirection: "column",
    overflow: "hidden",
    flexShrink: 0,
  },
  detailHeader: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    padding: "16px 18px",
    borderBottom: "1px solid #e2e8f0",
    flexShrink: 0,
  },
  detailTitle: { color: "#374151", fontSize: "12px", fontWeight: "700", textTransform: "uppercase", letterSpacing: "0.6px" },
  closePanelBtn: {
    background: "#f8fafc",
    border: "1px solid #e2e8f0",
    borderRadius: "6px",
    width: "28px",
    height: "28px",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    cursor: "pointer",
    color: "#64748b",
  },
  detailBody: {
    flex: 1,
    overflowY: "auto",
    padding: "16px 18px",
    display: "flex",
    flexDirection: "column",
    gap: "14px",
  },
  fileCard: {
    display: "flex",
    alignItems: "center",
    gap: "12px",
    background: "#f8fafc",
    border: "1px solid #e2e8f0",
    borderRadius: "10px",
    padding: "12px",
  },
  fileCardIcon: {
    width: "44px",
    height: "44px",
    background: "#eff6ff",
    border: "1px solid #bfdbfe",
    borderRadius: "10px",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    flexShrink: 0,
  },
  fileCardName: { color: "#0f172a", fontSize: "13px", fontWeight: "600", lineHeight: "1.3", wordBreak: "break-word" },
  fileCardMeta: { color: "#94a3b8", fontSize: "11px", marginTop: "3px" },
  langBadge: { background: "#f1f5f9", color: "#475569", borderRadius: "4px", padding: "2px 7px", fontSize: "10px", fontWeight: "700" },
  statsGrid: { display: "grid", gridTemplateColumns: "1fr 1fr", gap: "8px" },
  statCard: { background: "#f8fafc", border: "1px solid #e2e8f0", borderRadius: "8px", padding: "10px 12px", textAlign: "center" },
  statValue: { color: "#0f172a", fontSize: "18px", fontWeight: "700" },
  statLabel: { color: "#94a3b8", fontSize: "10px", marginTop: "2px" },
  metaSection: { display: "flex", flexDirection: "column", gap: "6px" },
  metaRow: { display: "flex", justifyContent: "space-between", alignItems: "center", padding: "6px 0", borderBottom: "1px solid #f8fafc" },
  metaKey: { color: "#94a3b8", fontSize: "11px" },
  metaVal: { color: "#374151", fontSize: "11px", fontWeight: "600", textAlign: "right", maxWidth: "180px", wordBreak: "break-word" },
  processingSection: { background: "#f8fafc", border: "1px solid #e2e8f0", borderRadius: "8px", padding: "12px" },
  processingSectionTitle: { color: "#374151", fontSize: "10px", fontWeight: "700", textTransform: "uppercase", letterSpacing: "0.5px", marginBottom: "10px" },
  pipeStep: { display: "flex", alignItems: "center", gap: "8px", marginBottom: "8px" },
  pipeStepDot: { width: "18px", height: "18px", borderRadius: "50%", display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 },
  detailActions: { display: "flex", flexDirection: "column", gap: "8px", paddingTop: "4px" },
  primaryAction: {
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    gap: "7px",
    background: "#2563eb",
    color: "#fff",
    border: "none",
    borderRadius: "8px",
    padding: "10px",
    fontSize: "13px",
    fontWeight: "600",
    cursor: "pointer",
    fontFamily: "inherit",
  },
  secondaryAction: {
    flex: 1,
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    gap: "6px",
    background: "#f8fafc",
    color: "#374151",
    border: "1px solid #e2e8f0",
    borderRadius: "7px",
    padding: "8px 10px",
    fontSize: "12px",
    cursor: "pointer",
    fontFamily: "inherit",
  },
  deleteAction: {
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    gap: "7px",
    background: "transparent",
    color: "#dc2626",
    border: "1px solid #fecaca",
    borderRadius: "8px",
    padding: "8px 10px",
    fontSize: "12px",
    cursor: "pointer",
    fontFamily: "inherit",
  },
};
