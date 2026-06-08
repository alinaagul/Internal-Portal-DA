import { useState } from "react";
import { documentsApi } from "../api/documents";

const STATUS_STEPS = ["uploaded", "ocr_processing", "chunking", "embedding", "ready"];
const STEP_LABELS  = ["Uploaded", "OCR", "Chunking", "Embedding", "Ready"];

function StatusPipeline({ status }) {
  const idx = STATUS_STEPS.indexOf(status);
  const failed = status === "failed";
  return (
    <div style={s.pipeline}>
      {STATUS_STEPS.map((key, i) => {
        const done   = !failed && i < idx;
        const active = !failed && i === idx;
        const isFail = failed && i === idx;
        return (
          <div key={key} style={s.pipeStep}>
            <div style={{ ...s.dot,
              ...(done ? s.dotDone : active ? s.dotActive : isFail ? s.dotFail : {}) }}>
              {done
                ? <svg width="10" height="10" viewBox="0 0 12 12" fill="none">
                    <path d="M2 6l3 3 5-5" stroke="#16a34a" strokeWidth="1.8"
                      strokeLinecap="round" strokeLinejoin="round"/>
                  </svg>
                : <span style={{ fontSize:"9px",
                    color: active ? "#2563eb" : isFail ? "#dc2626" : "#94a3b8" }}>
                    {i + 1}
                  </span>}
            </div>
            <span style={{ ...s.stepLabel,
              color: done ? "#16a34a" : active ? "#2563eb" : isFail ? "#dc2626" : "#94a3b8" }}>
              {STEP_LABELS[i]}
            </span>
            {i < STATUS_STEPS.length - 1 && (
              <div style={{ ...s.line, background: done ? "#86efac" : "#e2e8f0" }} />
            )}
          </div>
        );
      })}
    </div>
  );
}

export default function DocumentCard({ doc, onDelete }) {
  const [deleting, setDeleting]     = useState(false);
  const [expanded, setExpanded]     = useState(false);
  const [detail, setDetail]         = useState(null);   // full status from API
  const [loadingDetail, setLoadingDetail] = useState(false);
  const isProcessing = !["ready", "failed"].includes(doc.status);

  const handleDelete = async () => {
    const name = doc.filename || doc.original_filename;
    if (!confirm(`Delete "${name}"?`)) return;
    setDeleting(true);
    await onDelete(doc.id ?? doc.document_id);
  };

  const toggleDetails = async () => {
    if (expanded) { setExpanded(false); return; }
    // Fetch full status with chunks if not already loaded
    if (!detail) {
      setLoadingDetail(true);
      try {
        const { data } = await documentsApi.getStatus(
          doc.id ?? doc.document_id, true   // include_chunks=true if your API supports it
        );
        setDetail(data);
      } catch {
        setDetail(doc); // fallback to whatever we already have
      } finally {
        setLoadingDetail(false);
      }
    }
    setExpanded(true);
  };

  // Use enriched detail if available, else fall back to doc
  const d = detail || doc;
  const ocr       = d.ocr       || {};
  const chunking  = d.chunking  || {};
  const embedding = d.embedding || {};

  const infoRows = [
    ["Language",        d.language?.toUpperCase()],
    ["Pages",           ocr.total_pages],
    ["OCR method",      ocr.method],
    ["OCR confidence",  ocr.avg_confidence_pct != null ? `${ocr.avg_confidence_pct}%` : null],
    ["Tables (pages)",  ocr.pages_with_tables],
    ["Total chunks",    chunking.total_chunks],
    ["Text chunks",     chunking.text_chunks],
    ["Table chunks",    chunking.table_chunks],
    ["Embedding model", embedding.embedding_model],
    ["Embedded",        embedding.embedded_chunks != null
      ? `${embedding.embedded_chunks} chunks` : null],
    ["Failed chunks",   embedding.failed_chunks || null],
    ["Vector index",    embedding.vector_index],
    ["BM25 index",      embedding.bm25_index],
    ["Uploaded",        doc.created_at
      ? new Date(doc.created_at).toLocaleDateString(undefined,
          { day:"numeric", month:"short", year:"numeric" })
      : null],
  ].filter(([, v]) => v != null && v !== "");

  return (
    <div style={s.card}>
      {/* ── Header ── */}
      <div style={s.header}>
        <div style={s.fileInfo}>
          <div style={s.fileIconBox}>
            <svg width="14" height="14" viewBox="0 0 20 20" fill="none">
              <path d="M4 2h8l4 4v12a2 2 0 01-2 2H4a2 2 0 01-2-2V4a2 2 0 012-2z"
                stroke="#2563eb" strokeWidth="1.6"/>
              <path d="M12 2v4h4" stroke="#2563eb" strokeWidth="1.4" strokeLinejoin="round"/>
            </svg>
          </div>
          <div>
            <div style={s.fileName}>{doc.filename || doc.original_filename}</div>
            <div style={s.fileMeta}>
              {[
                ocr.total_pages        && `${ocr.total_pages} pages`,
                chunking.total_chunks  && `${chunking.total_chunks} chunks`,
                ocr.avg_confidence_pct != null && `${ocr.avg_confidence_pct}% OCR`,
                d.language             && d.language.toUpperCase(),
              ].filter(Boolean).join(" · ") || doc.status}
            </div>
          </div>
        </div>
        <div style={s.actions}>
          {doc.status === "ready" && (
            <button style={s.detailBtn} onClick={toggleDetails} disabled={loadingDetail}>
              {loadingDetail ? "…" : expanded ? "Hide" : "Details"}
            </button>
          )}
          <button style={{ ...s.deleteBtn, opacity: deleting ? 0.5 : 1 }}
            onClick={handleDelete} disabled={deleting || isProcessing}>
            Delete
          </button>
        </div>
      </div>

      {/* ── Pipeline ── */}
      <StatusPipeline status={doc.status} />

      {isProcessing && (
        <div style={s.processingMsg}>
          <span style={s.spin}>⏳</span> Processing — this may take a minute…
        </div>
      )}
      {doc.status === "failed" && (
        <div style={s.errorMsg}>❌ {doc.error_message || "Processing failed"}</div>
      )}

      {/* ── Expanded Details ── */}
      {expanded && (
        <div style={s.detailBox}>
          {/* Info grid */}
          <div style={s.sectionLabel}>Document Info</div>
          <div style={s.infoGrid}>
            {infoRows.map(([k, v]) => (
              <div key={k} style={s.infoRow}>
                <span style={s.infoKey}>{k}</span>
                <span style={s.infoVal}>{String(v)}</span>
              </div>
            ))}
          </div>

          {/* Chunk previews */}
          {d.chunks?.length > 0 && (
            <>
              <div style={{ ...s.sectionLabel, marginTop:"14px" }}>
                Chunks ({d.chunks.length})
              </div>
              <div style={s.chunkList}>
                {d.chunks.map((chunk) => (
                  <div key={chunk.chunk_index} style={s.chunkItem}>
                    <div style={s.chunkMeta}>
                      <span style={s.chunkPage}>p.{chunk.page_number}</span>
                      <span style={s.chunkSection}>{chunk.section_title}</span>
                      <span style={s.chunkTokens}>{chunk.token_count} tokens</span>
                    </div>
                    <div style={s.chunkPreview}>
                      {chunk.text_preview?.slice(0, 140)}{chunk.text_preview?.length > 140 ? "…" : ""}
                    </div>
                  </div>
                ))}
              </div>
            </>
          )}
        </div>
      )}

      <style>{`
        @keyframes pulse3 { 0%,100%{opacity:1} 50%{opacity:0.5} }
        @keyframes spin3   { from{transform:rotate(0deg)} to{transform:rotate(360deg)} }
      `}</style>
    </div>
  );
}

const s = {
  card: { background:"#fff", border:"1px solid #e2e8f0", borderRadius:"12px",
    padding:"18px 20px", display:"flex", flexDirection:"column", gap:"14px",
    fontFamily:"'Geist','DM Sans',system-ui,sans-serif" },

  header: { display:"flex", alignItems:"flex-start", justifyContent:"space-between", gap:"10px" },
  fileInfo: { display:"flex", alignItems:"flex-start", gap:"11px" },
  fileIconBox: { width:"30px", height:"30px", background:"#eff6ff", border:"1px solid #bfdbfe",
    borderRadius:"7px", display:"flex", alignItems:"center", justifyContent:"center",
    flexShrink:0, marginTop:"1px" },
  fileName: { color:"#0f172a", fontSize:"14px", fontWeight:"600", wordBreak:"break-all" },
  fileMeta: { color:"#94a3b8", fontSize:"12px", marginTop:"2px" },
  actions: { display:"flex", gap:"7px", flexShrink:0 },
  detailBtn: { background:"#f8fafc", border:"1px solid #e2e8f0", color:"#475569",
    borderRadius:"6px", padding:"5px 11px", fontSize:"12px", cursor:"pointer",
    fontFamily:"inherit" },
  deleteBtn: { background:"#fef2f2", border:"1px solid #fecaca", color:"#dc2626",
    borderRadius:"6px", padding:"5px 11px", fontSize:"12px", cursor:"pointer",
    fontFamily:"inherit" },

  pipeline: { display:"flex", alignItems:"center" },
  pipeStep: { display:"flex", alignItems:"center", flex:1 },
  dot: { width:"24px", height:"24px", borderRadius:"50%", background:"#f1f5f9",
    border:"1px solid #e2e8f0", display:"flex", alignItems:"center",
    justifyContent:"center", flexShrink:0 },
  dotDone:   { background:"#f0fdf4", border:"1px solid #86efac" },
  dotActive: { background:"#eff6ff", border:"1px solid #93c5fd",
    animation:"pulse3 1.5s infinite" },
  dotFail:   { background:"#fef2f2", border:"1px solid #fca5a5" },
  stepLabel: { fontSize:"10px", margin:"0 3px", whiteSpace:"nowrap" },
  line: { flex:1, height:"1px", margin:"0 3px" },

  processingMsg: { background:"#eff6ff", border:"1px solid #bfdbfe", borderRadius:"8px",
    padding:"9px 13px", color:"#1d4ed8", fontSize:"13px",
    display:"flex", alignItems:"center", gap:"7px" },
  spin: { animation:"spin3 2s linear infinite", display:"inline-block" },
  errorMsg: { background:"#fef2f2", border:"1px solid #fecaca", borderRadius:"8px",
    padding:"9px 13px", color:"#dc2626", fontSize:"13px" },

  detailBox: { background:"#f8fafc", border:"1px solid #e2e8f0", borderRadius:"10px",
    padding:"14px" },
  sectionLabel: { color:"#374151", fontSize:"11px", fontWeight:"600",
    textTransform:"uppercase", letterSpacing:"0.6px", marginBottom:"8px" },
  infoGrid: { display:"grid", gridTemplateColumns:"1fr 1fr", gap:"1px",
    background:"#e2e8f0", borderRadius:"7px", overflow:"hidden", border:"1px solid #e2e8f0" },
  infoRow: { display:"flex", justifyContent:"space-between", alignItems:"center",
    padding:"6px 10px", background:"#fff", gap:"8px" },
  infoKey: { color:"#64748b", fontSize:"12px", whiteSpace:"nowrap" },
  infoVal: { color:"#1d4ed8", fontSize:"12px", fontWeight:"500",
    background:"#eff6ff", padding:"1px 7px", borderRadius:"4px",
    maxWidth:"140px", overflow:"hidden", textOverflow:"ellipsis",
    whiteSpace:"nowrap" },

  chunkList: { display:"flex", flexDirection:"column", gap:"6px",
    maxHeight:"240px", overflowY:"auto" },
  chunkItem: { background:"#fff", border:"1px solid #e2e8f0",
    borderRadius:"7px", padding:"9px 11px" },
  chunkMeta: { display:"flex", alignItems:"center", gap:"7px", marginBottom:"4px" },
  chunkPage: { background:"#eff6ff", color:"#2563eb", borderRadius:"4px",
    padding:"1px 7px", fontSize:"10px", fontWeight:"600", whiteSpace:"nowrap" },
  chunkSection: { color:"#374151", fontSize:"11px", fontWeight:"500",
    overflow:"hidden", textOverflow:"ellipsis", whiteSpace:"nowrap", flex:1 },
  chunkTokens: { color:"#94a3b8", fontSize:"10px", whiteSpace:"nowrap" },
  chunkPreview: { color:"#64748b", fontSize:"11px", lineHeight:"1.5" },
};