import { useState, useRef } from "react";

export default function DocumentUpload({ onUpload, uploading, uploadProgress }) {
  const [dragOver, setDragOver] = useState(false);
  const [selectedFile, setSelectedFile] = useState(null);
  const inputRef = useRef();

  const handleFile = (file) => {
    if (!file) return;
    if (file.type !== "application/pdf") { alert("Only PDF files are supported."); return; }
    if (file.size > 200 * 1024 * 1024) { alert("File too large. Max 200MB."); return; }
    setSelectedFile(file);
  };

  const handleDrop = (e) => {
    e.preventDefault();
    setDragOver(false);
    handleFile(e.dataTransfer.files[0]);
  };

  const handleSubmit = async () => {
    if (!selectedFile || uploading) return;
    const result = await onUpload(selectedFile);
    if (result?.success) setSelectedFile(null);
  };

  return (
    <div style={s.wrapper}>
      <div
        style={{ ...s.dropZone, ...(dragOver ? s.dropActive : {}), ...(selectedFile ? s.dropSelected : {}) }}
        onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
        onDragLeave={() => setDragOver(false)}
        onDrop={handleDrop}
        onClick={() => !selectedFile && inputRef.current?.click()}
      >
        <input ref={inputRef} type="file" accept=".pdf" style={{ display:"none" }}
          onChange={(e) => handleFile(e.target.files[0])} />

        {selectedFile ? (
          <div style={s.fileInfo}>
            <div style={s.fileIconBox}>
              <svg width="16" height="16" viewBox="0 0 20 20" fill="none">
                <path d="M4 2h8l4 4v12a2 2 0 01-2 2H4a2 2 0 01-2-2V4a2 2 0 012-2z"
                  stroke="#2563eb" strokeWidth="1.7"/>
                <path d="M12 2v4h4" stroke="#2563eb" strokeWidth="1.4" strokeLinejoin="round"/>
              </svg>
            </div>
            <div>
              <div style={s.fileName}>{selectedFile.name}</div>
              <div style={s.fileSize}>{(selectedFile.size / 1024 / 1024).toFixed(2)} MB</div>
            </div>
            <button style={s.removeBtn}
              onClick={(e) => { e.stopPropagation(); setSelectedFile(null); }}>
              ✕
            </button>
          </div>
        ) : (
          <div style={s.hint}>
            <div style={s.uploadIconBox}>
              <svg width="18" height="18" viewBox="0 0 20 20" fill="none">
                <path d="M10 14V4M6 8l4-4 4 4" stroke="#2563eb" strokeWidth="1.8"
                  strokeLinecap="round" strokeLinejoin="round"/>
                <path d="M3 16h14" stroke="#2563eb" strokeWidth="1.6" strokeLinecap="round"/>
              </svg>
            </div>
            <div style={s.hintTitle}>Drop PDF here or click to browse</div>
            <div style={s.hintSub}>Max 200MB · PDF only</div>
          </div>
        )}
      </div>

      {uploading && (
        <div style={s.progressWrap}>
          <div style={s.track}>
            <div style={{ ...s.bar, width:`${uploadProgress}%` }} />
          </div>
          <span style={s.pct}>{uploadProgress}%</span>
        </div>
      )}

      <button
        style={{ ...s.btn, ...(!selectedFile || uploading ? s.btnDisabled : {}) }}
        onClick={handleSubmit}
        disabled={!selectedFile || uploading}>
        {uploading ? "Uploading…" : "Upload & Process"}
      </button>
    </div>
  );
}

const s = {
  wrapper: { display:"flex", flexDirection:"column", gap:"12px" },
  dropZone: { border:"2px dashed #e2e8f0", borderRadius:"10px", padding:"28px 16px",
    textAlign:"center", cursor:"pointer", background:"#f8fafc",
    transition:"border-color 0.15s, background 0.15s" },
  dropActive: { borderColor:"#2563eb", background:"#eff6ff" },
  dropSelected: { borderColor:"#bfdbfe", background:"#eff6ff", cursor:"default" },
  hint: { display:"flex", flexDirection:"column", alignItems:"center", gap:"7px" },
  uploadIconBox: { width:"36px", height:"36px", background:"#eff6ff", border:"1px solid #bfdbfe",
    borderRadius:"8px", display:"flex", alignItems:"center",
    justifyContent:"center", margin:"0 auto" },
  hintTitle: { color:"#374151", fontSize:"13px", fontWeight:"500" },
  hintSub: { color:"#94a3b8", fontSize:"12px" },
  fileInfo: { display:"flex", alignItems:"center", gap:"10px", textAlign:"left" },
  fileIconBox: { width:"32px", height:"32px", background:"#eff6ff", border:"1px solid #bfdbfe",
    borderRadius:"7px", display:"flex", alignItems:"center",
    justifyContent:"center", flexShrink:0 },
  fileName: { color:"#0f172a", fontSize:"13px", fontWeight:"500",
    wordBreak:"break-all", lineHeight:"1.3" },
  fileSize: { color:"#94a3b8", fontSize:"11px", marginTop:"2px" },
  removeBtn: { marginLeft:"auto", background:"transparent", border:"none",
    color:"#94a3b8", cursor:"pointer", fontSize:"13px", padding:"4px",
    flexShrink:0 },
  progressWrap: { display:"flex", alignItems:"center", gap:"9px" },
  track: { flex:1, height:"5px", background:"#e2e8f0", borderRadius:"99px", overflow:"hidden" },
  bar: { height:"100%", background:"#2563eb", borderRadius:"99px",
    transition:"width 0.3s ease" },
  pct: { color:"#64748b", fontSize:"12px", minWidth:"30px" },
  btn: { background:"#2563eb", color:"#fff", border:"none", borderRadius:"8px",
    padding:"10px", fontSize:"13px", fontWeight:"600", cursor:"pointer",
    fontFamily:"inherit" },
  btnDisabled: { background:"#e2e8f0", color:"#94a3b8", cursor:"not-allowed" },
};