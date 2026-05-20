import { useState } from "react";

const STATUS_STEPS = [
  { key: "uploaded",       label: "Uploaded",    icon: "📁" },
  { key: "ocr_processing", label: "OCR",         icon: "🔍" },
  { key: "chunking",       label: "Chunking",    icon: "✂️" },
  { key: "embedding",      label: "Embedding",   icon: "🧠" },
  { key: "ready",          label: "Ready",       icon: "✅" },
];

const STATUS_ORDER = STATUS_STEPS.map((s) => s.key);

function StatusPipeline({ status }) {
  const currentIdx = STATUS_ORDER.indexOf(status);
  const isFailed = status === "failed";

  return (
    <div style={s.pipeline}>
      {STATUS_STEPS.map((step, i) => {
        const done    = !isFailed && i < currentIdx;
        const active  = !isFailed && i === currentIdx;
        const pending = isFailed || i > currentIdx;

        return (
          <div key={step.key} style={s.pipelineStep}>
            <div style={{
              ...s.stepDot,
              ...(done   ? s.stepDone   : {}),
              ...(active ? s.stepActive : {}),
              ...(isFailed && i === currentIdx ? s.stepFailed : {}),
            }}>
              {done ? "✓" : step.icon}
            </div>
            <span style={{
              ...s.stepLabel,
              color: done ? "#22c55e" : active ? "#60a5fa" : "#475569",
            }}>
              {step.label}
            </span>
            {i < STATUS_STEPS.length - 1 && (
              <div style={{ ...s.stepLine, background: done ? "#22c55e" : "#1e2130" }} />
            )}
          </div>
        );
      })}
    </div>
  );
}

export default function DocumentCard({ doc, onDelete }) {
  const [deleting, setDeleting] = useState(false);
  const [expanded, setExpanded] = useState(false);

  const handleDelete = async () => {
    if (!confirm(`Delete "${doc.original_filename}"?`)) return;
    setDeleting(true);
    await onDelete(doc.id);
  };

  const isProcessing = !["ready", "failed"].includes(doc.status);

  return (
    <div style={s.card}>
      {/* Header row */}
      <div style={s.header}>
        <div style={s.fileInfo}>
          <span style={s.fileIcon}>📄</span>
          <div>
            <div style={s.fileName}>{doc.original_filename}</div>
            <div style={s.fileMeta}>
              {doc.total_pages && `${doc.total_pages} pages · `}
              {doc.total_chunks && `${doc.total_chunks} chunks · `}
              {doc.ocr_confidence && `${doc.ocr_confidence.toFixed(0)}% OCR confidence · `}
              {doc.language_detected && `Lang: ${doc.language_detected.toUpperCase()}`}
            </div>
          </div>
        </div>

        <div style={s.actions}>
          {doc.status === "ready" && (
            <button style={s.expandBtn} onClick={() => setExpanded(!expanded)}>
              {expanded ? "Hide details" : "Details"}
            </button>
          )}
          <button
            style={{ ...s.deleteBtn, opacity: deleting ? 0.5 : 1 }}
            onClick={handleDelete}
            disabled={deleting || isProcessing}
          >
            {deleting ? "…" : "🗑"}
          </button>
        </div>
      </div>

      {/* Processing pipeline */}
      <StatusPipeline status={doc.status} />

      {/* Animated processing message */}
      {isProcessing && (
        <div style={s.processingMsg}>
          <span style={s.spinner}>⏳</span>
          Processing document — this may take a minute...
        </div>
      )}

      {/* Failed message */}
      {doc.status === "failed" && (
        <div style={s.errorMsg}>
          ❌ {doc.error_message || "Processing failed"}
        </div>
      )}

      {/* Expanded stats */}
      {expanded && doc.status === "ready" && (
        <div style={s.stats}>
          <div style={s.statRow}>
            <span style={s.statLabel}>Model for embeddings</span>
            <span style={s.statVal}>mxbai-embed-large (Ollama)</span>
          </div>
          <div style={s.statRow}>
            <span style={s.statLabel}>Vector store</span>
            <span style={s.statVal}>ChromaDB (local)</span>
          </div>
          <div style={s.statRow}>
            <span style={s.statLabel}>OCR engine</span>
            <span style={s.statVal}>pdfplumber / Tesseract</span>
          </div>
          <div style={s.statRow}>
            <span style={s.statLabel}>Chunk size</span>
            <span style={s.statVal}>~600 tokens · 15% overlap</span>
          </div>
          {doc.total_chunks && (
            <div style={s.statRow}>
              <span style={s.statLabel}>Total chunks</span>
              <span style={s.statVal}>{doc.total_chunks}</span>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

const s = {
  card: {
    background: "#1a1d27", border: "1px solid #2a2d3d",
    borderRadius: "12px", padding: "20px", display: "flex",
    flexDirection: "column", gap: "16px",
  },
  header: { display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: "12px" },
  fileInfo: { display: "flex", alignItems: "flex-start", gap: "12px" },
  fileIcon: { fontSize: "24px", marginTop: "2px" },
  fileName: { color: "#f1f5f9", fontSize: "14px", fontWeight: "600", wordBreak: "break-all" },
  fileMeta: { color: "#64748b", fontSize: "12px", marginTop: "3px" },
  actions: { display: "flex", gap: "8px", flexShrink: 0 },
  expandBtn: {
    background: "transparent", border: "1px solid #2a2d3d",
    color: "#94a3b8", borderRadius: "6px", padding: "5px 12px",
    fontSize: "12px", cursor: "pointer",
  },
  deleteBtn: {
    background: "rgba(239,68,68,0.1)", border: "1px solid rgba(239,68,68,0.2)",
    color: "#f87171", borderRadius: "6px", padding: "5px 10px",
    fontSize: "14px", cursor: "pointer",
  },
  pipeline: { display: "flex", alignItems: "center" },
  pipelineStep: { display: "flex", alignItems: "center", flex: 1 },
  stepDot: {
    width: "28px", height: "28px", borderRadius: "50%",
    background: "#1e2130", border: "1px solid #2a2d3d",
    display: "flex", alignItems: "center", justifyContent: "center",
    fontSize: "12px", flexShrink: 0,
  },
  stepDone:   { background: "rgba(34,197,94,0.15)", border: "1px solid #22c55e", color: "#22c55e", fontSize: "11px" },
  stepActive: { background: "rgba(59,130,246,0.15)", border: "1px solid #3b82f6", animation: "pulse 1.5s infinite" },
  stepFailed: { background: "rgba(239,68,68,0.15)", border: "1px solid #ef4444" },
  stepLabel:  { fontSize: "11px", margin: "0 4px", whiteSpace: "nowrap" },
  stepLine:   { flex: 1, height: "1px", margin: "0 4px" },
  processingMsg: {
    background: "rgba(59,130,246,0.08)", border: "1px solid rgba(59,130,246,0.2)",
    borderRadius: "8px", padding: "10px 14px", color: "#93c5fd",
    fontSize: "13px", display: "flex", alignItems: "center", gap: "8px",
  },
  spinner: { animation: "spin 2s linear infinite", display: "inline-block" },
  errorMsg: {
    background: "rgba(239,68,68,0.08)", border: "1px solid rgba(239,68,68,0.2)",
    borderRadius: "8px", padding: "10px 14px", color: "#f87171", fontSize: "13px",
  },
  stats: {
    background: "#0f1117", borderRadius: "8px", padding: "14px",
    display: "flex", flexDirection: "column", gap: "8px",
  },
  statRow: { display: "flex", justifyContent: "space-between", alignItems: "center" },
  statLabel: { color: "#64748b", fontSize: "12px" },
  statVal: { color: "#94a3b8", fontSize: "12px", fontWeight: "500" },
};