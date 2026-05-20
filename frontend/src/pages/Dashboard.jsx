import { useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../hooks/useAuth";
import { useDocuments } from "../hooks/useDocuments";
import DocumentUpload from "../components/DocumentUpload";
import DocumentCard from "../components/DocumentCard";

export default function Dashboard() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const {
    documents, uploading, uploadProgress,
    loading, error, setError,
    fetchDocuments, uploadDocument, deleteDocument,
  } = useDocuments();

  useEffect(() => { fetchDocuments(); }, []);

  const handleLogout = () => { logout(); navigate("/login"); };

  return (
    <div style={s.page}>
      <nav style={s.nav}>
        <div style={s.brand}>
          <div style={s.logoBox}>
            <svg width="20" height="20" viewBox="0 0 28 28" fill="none">
              <path d="M4 6h20M4 12h14M4 18h18M4 24h10" stroke="#60a5fa" strokeWidth="2.2" strokeLinecap="round"/>
            </svg>
          </div>
          <span style={s.brandName}>DocAssist</span>
        </div>
        <div style={s.navRight}>
          <span style={s.userChip}>{user?.full_name}</span>
          <button style={s.logoutBtn} onClick={handleLogout}>Sign out</button>
        </div>
      </nav>

      <div style={s.layout}>
        <div style={s.sidebar}>
          <div style={s.panel}>
            <h2 style={s.panelTitle}>Upload Document</h2>
            <p style={s.panelSub}>Upload a PDF contract to extract and index its content.</p>
            <DocumentUpload onUpload={uploadDocument} uploading={uploading} uploadProgress={uploadProgress} />
            {error && (
              <div style={s.errorBox}>
                {error}
                <span style={s.errorClose} onClick={() => setError(null)}>✕</span>
              </div>
            )}
            <div style={s.modelCard}>
              <div style={s.modelTitle}>🔧 Pipeline</div>
              {[
                ["1. OCR",       "pdfplumber + Tesseract"],
                ["2. Chunking",  "Section-aware · 600 tokens"],
                ["3. Embeddings","mxbai-embed-large (Ollama)"],
                ["4. Vector DB", "ChromaDB (local)"],
                ["5. LLM (Q&A)", "mistral (Ollama)"],
              ].map(([step, val]) => (
                <div key={step} style={s.modelRow}>
                  <span style={s.modelStep}>{step}</span>
                  <span style={s.modelVal}>{val}</span>
                </div>
              ))}
            </div>
          </div>
        </div>

        <div style={s.main}>
          <div style={s.mainHeader}>
            <h2 style={s.mainTitle}>
              My Documents
              {documents.length > 0 && <span style={s.docCount}>{documents.length}</span>}
            </h2>
            <button style={s.refreshBtn} onClick={fetchDocuments} disabled={loading}>
              {loading ? "Loading…" : "↺ Refresh"}
            </button>
          </div>

          {loading && documents.length === 0 ? (
            <div style={s.emptyState}><div style={s.emptyIcon}>⏳</div><p style={s.emptyText}>Loading...</p></div>
          ) : documents.length === 0 ? (
            <div style={s.emptyState}>
              <div style={s.emptyIcon}>📂</div>
              <p style={s.emptyText}>No documents yet</p>
              <p style={s.emptySub}>Upload a PDF contract to get started</p>
            </div>
          ) : (
            <div style={s.docList}>
              {documents.map((doc) => (
                <DocumentCard key={doc.id} doc={doc} onDelete={deleteDocument} />
              ))}
            </div>
          )}
        </div>
      </div>

      <style>{`
        @keyframes pulse { 0%,100%{opacity:1} 50%{opacity:0.5} }
        @keyframes spin  { from{transform:rotate(0deg)} to{transform:rotate(360deg)} }
      `}</style>
    </div>
  );
}

const s = {
  page: { minHeight:"100vh", background:"#0f1117", fontFamily:"'Inter',sans-serif" },
  nav: { display:"flex", alignItems:"center", justifyContent:"space-between", padding:"14px 32px", borderBottom:"1px solid #1e2130", position:"sticky", top:0, background:"#0f1117", zIndex:10 },
  brand: { display:"flex", alignItems:"center", gap:"10px" },
  logoBox: { width:"36px", height:"36px", background:"rgba(96,165,250,0.1)", border:"1px solid rgba(96,165,250,0.2)", borderRadius:"8px", display:"flex", alignItems:"center", justifyContent:"center" },
  brandName: { color:"#f1f5f9", fontWeight:"700", fontSize:"16px" },
  navRight: { display:"flex", alignItems:"center", gap:"12px" },
  userChip: { background:"#1a1d27", border:"1px solid #2a2d3d", color:"#94a3b8", borderRadius:"20px", padding:"5px 14px", fontSize:"13px" },
  logoutBtn: { background:"transparent", border:"1px solid #2a2d3d", color:"#64748b", borderRadius:"6px", padding:"6px 14px", fontSize:"13px", cursor:"pointer" },
  layout: { maxWidth:"1200px", margin:"0 auto", padding:"32px 24px", display:"grid", gridTemplateColumns:"340px 1fr", gap:"24px" },
  sidebar: {},
  panel: { background:"#1a1d27", border:"1px solid #2a2d3d", borderRadius:"14px", padding:"24px", display:"flex", flexDirection:"column", gap:"20px", position:"sticky", top:"72px" },
  panelTitle: { color:"#f1f5f9", fontSize:"16px", fontWeight:"700", margin:0 },
  panelSub: { color:"#64748b", fontSize:"13px", margin:0, lineHeight:"1.5" },
  errorBox: { background:"rgba(239,68,68,0.1)", border:"1px solid rgba(239,68,68,0.25)", borderRadius:"8px", padding:"10px 14px", color:"#f87171", fontSize:"13px", display:"flex", justifyContent:"space-between" },
  errorClose: { cursor:"pointer" },
  modelCard: { background:"#0f1117", border:"1px solid #1e2130", borderRadius:"10px", padding:"16px", display:"flex", flexDirection:"column", gap:"10px" },
  modelTitle: { color:"#94a3b8", fontSize:"11px", fontWeight:"600", textTransform:"uppercase", letterSpacing:"0.5px" },
  modelRow: { display:"flex", justifyContent:"space-between", alignItems:"center" },
  modelStep: { color:"#64748b", fontSize:"12px" },
  modelVal: { color:"#60a5fa", fontSize:"12px", fontWeight:"500", background:"rgba(59,130,246,0.08)", padding:"2px 8px", borderRadius:"4px" },
  main: { display:"flex", flexDirection:"column", gap:"16px" },
  mainHeader: { display:"flex", alignItems:"center", justifyContent:"space-between" },
  mainTitle: { color:"#f1f5f9", fontSize:"18px", fontWeight:"700", margin:0, display:"flex", alignItems:"center", gap:"10px" },
  docCount: { background:"#1a1d27", border:"1px solid #2a2d3d", color:"#64748b", borderRadius:"20px", padding:"2px 10px", fontSize:"12px" },
  refreshBtn: { background:"transparent", border:"1px solid #2a2d3d", color:"#64748b", borderRadius:"6px", padding:"6px 14px", fontSize:"13px", cursor:"pointer" },
  docList: { display:"flex", flexDirection:"column", gap:"12px" },
  emptyState: { background:"#1a1d27", border:"1px dashed #2a2d3d", borderRadius:"14px", padding:"64px 32px", display:"flex", flexDirection:"column", alignItems:"center", gap:"10px" },
  emptyIcon: { fontSize:"40px" },
  emptyText: { color:"#64748b", fontSize:"16px", fontWeight:"500", margin:0 },
  emptySub: { color:"#475569", fontSize:"13px", margin:0 },
};