const docName = (d) => d?.original_filename || d?.filename || "Untitled";

export default function StatusModal({ doc, onClose }) {
  if (!doc) return null;

  const name = docName(doc);

  const steps = [
    {
      label: "Uploaded",
      detail: "File received and stored successfully",
      done: true,
    },
    {
      label: "OCR Extraction",
      detail: doc.ocr
        ? `${doc.ocr.total_pages} pages · ${doc.ocr.avg_confidence_pct ?? "?"}% confidence · ${doc.ocr.method}`
        : doc.status === "failed" ? "Failed" : "Pending…",
      done: !!doc.ocr,
      failed: doc.status === "failed" && !doc.ocr,
      active: !doc.ocr && doc.status === "processing",
    },
    {
      label: "Text Chunking",
      detail: doc.chunking
        ? `${doc.chunking.total_chunks} chunks created`
        : doc.status === "failed" && doc.ocr ? "Failed" : "Pending…",
      done: !!doc.chunking,
      failed: doc.status === "failed" && !!doc.ocr && !doc.chunking,
      active: !!doc.ocr && !doc.chunking && doc.status === "processing",
    },
    {
      label: "Embeddings Generated",
      detail: doc.embedding
        ? `${doc.embedding.embedded_chunks} vectors · ${doc.embedding.embedding_model}`
        : doc.status === "failed" && doc.chunking ? "Failed" : "Pending…",
      done: !!doc.embedding,
      failed: doc.status === "failed" && !!doc.chunking && !doc.embedding,
      active: !!doc.chunking && !doc.embedding && doc.status === "processing",
    },
    {
      label: "Indexed & Ready",
      detail: doc.status === "ready" ? "Ready for AI-powered chat" : doc.status === "failed" ? "Failed" : "Pending…",
      done: doc.status === "ready",
      failed: doc.status === "failed" && !!doc.embedding,
      active: !!doc.embedding && doc.status !== "ready" && doc.status !== "failed",
    },
  ];

  const completedCount = steps.filter((s) => s.done).length;
  const pct = Math.round((completedCount / steps.length) * 100);
  const isReady = doc.status === "ready";
  const isFailed = doc.status === "failed";
  const barColor = isFailed ? "#ef4444" : isReady ? "#22c55e" : "#3b82f6";

  return (
    <div style={s.overlay} onClick={onClose}>
      <div style={s.modal} onClick={(e) => e.stopPropagation()}>

        {/* Header */}
        <div style={s.header}>
          <div style={s.headerLeft}>
            <div style={s.headerIconWrap}>
              <svg width="18" height="18" viewBox="0 0 20 20" fill="none">
                <circle cx="10" cy="10" r="8" stroke="#2563eb" strokeWidth="1.7" />
                <path d="M10 6v4l3 3" stroke="#2563eb" strokeWidth="1.7" strokeLinecap="round" />
              </svg>
            </div>
            <div>
              <div style={s.modalTitle}>Document Status</div>
              <div style={s.docLabel} title={name}>{name.length > 44 ? name.slice(0, 44) + "…" : name}</div>
            </div>
          </div>
          <button style={s.closeBtn} onClick={onClose}>✕</button>
        </div>

        {/* Progress bar */}
        <div style={s.progressSection}>
          <div style={s.progressTrack}>
            <div style={{ ...s.progressFill, width: `${pct}%`, background: barColor }} />
          </div>
          <div style={{ ...s.progressLabel, color: barColor }}>
            {isReady ? "✓ 100% — Ready for Chat" : isFailed ? "⚠ Processing Failed" : `${pct}% Complete`}
          </div>
        </div>

        {/* Steps */}
        <div style={s.steps}>
          {steps.map((step, i) => {
            const stepColor = step.done
              ? "#16a34a"
              : step.failed
              ? "#dc2626"
              : step.active
              ? "#3b82f6"
              : "#94a3b8";
            const iconBg = step.done
              ? "#f0fdf4"
              : step.failed
              ? "#fef2f2"
              : step.active
              ? "#eff6ff"
              : "#f8fafc";
            const iconBorder = step.done
              ? "#86efac"
              : step.failed
              ? "#fecaca"
              : step.active
              ? "#bfdbfe"
              : "#e2e8f0";

            return (
              <div key={i} style={s.stepRow}>
                {/* Connector line */}
                {i > 0 && <div style={s.connector} />}
                <div style={{ display: "flex", alignItems: "flex-start", gap: "12px" }}>
                  <div style={{ ...s.stepDot, background: iconBg, border: `1.5px solid ${iconBorder}` }}>
                    {step.done ? (
                      <svg width="12" height="12" viewBox="0 0 16 16" fill="none">
                        <path d="M3 8l3.5 3.5L13 5" stroke="#16a34a" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
                      </svg>
                    ) : step.failed ? (
                      <svg width="12" height="12" viewBox="0 0 16 16" fill="none">
                        <path d="M4 4l8 8M12 4l-8 8" stroke="#dc2626" strokeWidth="2" strokeLinecap="round" />
                      </svg>
                    ) : step.active ? (
                      <div style={{ width: "8px", height: "8px", background: "#3b82f6", borderRadius: "50%", animation: "pulse 1.4s infinite" }} />
                    ) : (
                      <div style={{ width: "8px", height: "8px", background: "#cbd5e1", borderRadius: "50%" }} />
                    )}
                  </div>
                  <div style={s.stepContent}>
                    <div style={{ ...s.stepLabel, color: stepColor }}>
                      {step.label}
                    </div>
                    <div style={s.stepDetail}>{step.detail}</div>
                  </div>
                </div>
              </div>
            );
          })}
        </div>

        {/* Error */}
        {doc.error_message && (
          <div style={s.errorBox}>
            <div style={s.errorTitle}>⚠ Error Details</div>
            <div style={s.errorText}>{doc.error_message}</div>
          </div>
        )}

        <button style={s.doneBtn} onClick={onClose}>Close</button>
      </div>
      <style>{`@keyframes pulse{0%,100%{opacity:1}50%{opacity:0.4}}`}</style>
    </div>
  );
}

const s = {
  overlay: {
    position: "fixed",
    inset: 0,
    background: "rgba(15,23,42,0.5)",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    zIndex: 1000,
    backdropFilter: "blur(4px)",
  },
  modal: {
    background: "#fff",
    borderRadius: "16px",
    padding: "24px",
    width: "440px",
    maxWidth: "calc(100vw - 40px)",
    maxHeight: "calc(100vh - 80px)",
    overflowY: "auto",
    boxShadow: "0 25px 60px rgba(0,0,0,0.2)",
    display: "flex",
    flexDirection: "column",
    gap: "18px",
  },
  header: {
    display: "flex",
    alignItems: "flex-start",
    justifyContent: "space-between",
    gap: "12px",
  },
  headerLeft: { display: "flex", alignItems: "flex-start", gap: "12px" },
  headerIconWrap: {
    width: "40px",
    height: "40px",
    background: "#eff6ff",
    border: "1px solid #bfdbfe",
    borderRadius: "10px",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    flexShrink: 0,
  },
  modalTitle: { color: "#0f172a", fontSize: "16px", fontWeight: "700", marginBottom: "2px" },
  docLabel: { color: "#64748b", fontSize: "12px", lineHeight: "1.4" },
  closeBtn: {
    background: "transparent",
    border: "none",
    cursor: "pointer",
    color: "#94a3b8",
    fontSize: "16px",
    padding: "2px",
    lineHeight: 1,
    flexShrink: 0,
    marginTop: "2px",
  },
  progressSection: { display: "flex", flexDirection: "column", gap: "6px" },
  progressTrack: {
    height: "8px",
    background: "#f1f5f9",
    borderRadius: "4px",
    overflow: "hidden",
  },
  progressFill: {
    height: "100%",
    borderRadius: "4px",
    transition: "width 0.4s ease",
  },
  progressLabel: {
    fontSize: "12px",
    fontWeight: "600",
    textAlign: "center",
  },
  steps: { display: "flex", flexDirection: "column", gap: "0px" },
  stepRow: { display: "flex", flexDirection: "column" },
  connector: {
    width: "1.5px",
    height: "10px",
    background: "#e2e8f0",
    marginLeft: "16px",
    marginBottom: "2px",
  },
  stepDot: {
    width: "34px",
    height: "34px",
    borderRadius: "50%",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    flexShrink: 0,
  },
  stepContent: { flex: 1, paddingTop: "6px" },
  stepLabel: { fontSize: "13px", fontWeight: "600", marginBottom: "2px" },
  stepDetail: { color: "#64748b", fontSize: "11px", lineHeight: "1.4" },
  errorBox: {
    background: "#fef2f2",
    border: "1px solid #fecaca",
    borderRadius: "10px",
    padding: "14px",
  },
  errorTitle: { color: "#dc2626", fontSize: "12px", fontWeight: "700", marginBottom: "6px" },
  errorText: { color: "#991b1b", fontSize: "12px", lineHeight: "1.55", fontFamily: "monospace" },
  doneBtn: {
    background: "#0f172a",
    color: "#fff",
    border: "none",
    borderRadius: "8px",
    padding: "11px",
    fontSize: "13px",
    fontWeight: "600",
    cursor: "pointer",
    fontFamily: "inherit",
    width: "100%",
  },
};
