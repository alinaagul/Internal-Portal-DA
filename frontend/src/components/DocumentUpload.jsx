import { useState, useRef } from "react";

export default function DocumentUpload({ onUpload, uploading, uploadProgress }) {
  const [dragOver, setDragOver] = useState(false);
  const [selectedFile, setSelectedFile] = useState(null);
  const inputRef = useRef();

  const handleFile = (file) => {
    if (!file) return;
    if (file.type !== "application/pdf") {
      alert("Only PDF files are supported.");
      return;
    }
    if (file.size > 50 * 1024 * 1024) {
      alert("File too large. Max 50MB.");
      return;
    }
    setSelectedFile(file);
  };

  const handleDrop = (e) => {
    e.preventDefault();
    setDragOver(false);
    const file = e.dataTransfer.files[0];
    handleFile(file);
  };

  const handleSubmit = async () => {
    if (!selectedFile || uploading) return;
    const result = await onUpload(selectedFile);
    if (result.success) setSelectedFile(null);
  };

  return (
    <div style={s.wrapper}>
      {/* Drop zone */}
      <div
        style={{ ...s.dropZone, ...(dragOver ? s.dropZoneActive : {}) }}
        onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
        onDragLeave={() => setDragOver(false)}
        onDrop={handleDrop}
        onClick={() => !selectedFile && inputRef.current?.click()}
      >
        <input
          ref={inputRef}
          type="file"
          accept=".pdf"
          style={{ display: "none" }}
          onChange={(e) => handleFile(e.target.files[0])}
        />

        {selectedFile ? (
          <div style={s.fileSelected}>
            <div style={s.fileIcon}>📄</div>
            <div style={s.fileName}>{selectedFile.name}</div>
            <div style={s.fileSize}>{(selectedFile.size / 1024 / 1024).toFixed(2)} MB</div>
            <button
              style={s.clearBtn}
              onClick={(e) => { e.stopPropagation(); setSelectedFile(null); }}
            >
              ✕ Remove
            </button>
          </div>
        ) : (
          <div style={s.dropHint}>
            <div style={s.uploadIcon}>⬆</div>
            <div style={s.dropTitle}>Drop PDF here or click to browse</div>
            <div style={s.dropSub}>Max 50MB · PDF only</div>
          </div>
        )}
      </div>

      {/* Upload progress bar */}
      {uploading && (
        <div style={s.progressWrap}>
          <div style={s.progressTrack}>
            <div style={{ ...s.progressBar, width: `${uploadProgress}%` }} />
          </div>
          <span style={s.progressLabel}>{uploadProgress}%</span>
        </div>
      )}

      {/* Upload button */}
      <button
        style={{
          ...s.uploadBtn,
          ...((!selectedFile || uploading) ? s.uploadBtnDisabled : {}),
        }}
        onClick={handleSubmit}
        disabled={!selectedFile || uploading}
      >
        {uploading ? "Uploading…" : "Upload & Process"}
      </button>
    </div>
  );
}

const s = {
  wrapper: { display: "flex", flexDirection: "column", gap: "14px" },
  dropZone: {
    border: "2px dashed #2a2d3d",
    borderRadius: "12px",
    padding: "40px 24px",
    textAlign: "center",
    cursor: "pointer",
    background: "#0f1117",
    transition: "border-color 0.2s, background 0.2s",
  },
  dropZoneActive: {
    borderColor: "#3b82f6",
    background: "rgba(59,130,246,0.05)",
  },
  dropHint: { display: "flex", flexDirection: "column", alignItems: "center", gap: "8px" },
  uploadIcon: { fontSize: "32px", color: "#3b82f6" },
  dropTitle: { color: "#94a3b8", fontSize: "15px", fontWeight: "500" },
  dropSub: { color: "#475569", fontSize: "13px" },
  fileSelected: { display: "flex", flexDirection: "column", alignItems: "center", gap: "8px" },
  fileIcon: { fontSize: "36px" },
  fileName: { color: "#f1f5f9", fontSize: "14px", fontWeight: "500", wordBreak: "break-all" },
  fileSize: { color: "#64748b", fontSize: "12px" },
  clearBtn: {
    background: "transparent", border: "1px solid #2a2d3d",
    color: "#94a3b8", borderRadius: "6px", padding: "4px 12px",
    fontSize: "12px", cursor: "pointer", marginTop: "4px",
  },
  progressWrap: { display: "flex", alignItems: "center", gap: "10px" },
  progressTrack: {
    flex: 1, height: "6px", background: "#1e2130", borderRadius: "99px", overflow: "hidden",
  },
  progressBar: {
    height: "100%", background: "#3b82f6", borderRadius: "99px",
    transition: "width 0.3s ease",
  },
  progressLabel: { color: "#64748b", fontSize: "12px", minWidth: "32px" },
  uploadBtn: {
    background: "#3b82f6", color: "#fff", border: "none",
    borderRadius: "8px", padding: "12px", fontSize: "14px",
    fontWeight: "600", cursor: "pointer", transition: "opacity 0.2s",
  },
  uploadBtnDisabled: { opacity: 0.4, cursor: "not-allowed" },
};