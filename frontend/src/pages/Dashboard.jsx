import { useNavigate } from "react-router-dom";
import { useAuth } from "../hooks/useAuth";

export default function Dashboard() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  const handleLogout = () => {
    logout();
    navigate("/login");
  };

  return (
    <div style={styles.page}>
      <div style={styles.header}>
        <div style={styles.brand}>
          <svg width="22" height="22" viewBox="0 0 28 28" fill="none">
            <path d="M4 6h20M4 12h14M4 18h18M4 24h10" stroke="#60a5fa" strokeWidth="2.2" strokeLinecap="round"/>
          </svg>
          <span style={styles.brandName}>DocAssist</span>
        </div>
        <div style={styles.userInfo}>
          <span style={styles.userEmail}>{user?.full_name}</span>
          <button style={styles.logoutBtn} onClick={handleLogout}>
            Sign out
          </button>
        </div>
      </div>

      <div style={styles.body}>
        <h1 style={styles.welcome}>Welcome, {user?.full_name?.split(" ")[0]} 👋</h1>
        <p style={styles.hint}>
          Your document assistant workspace is ready.<br />
          RAG pipeline coming next.
        </p>
        <div style={styles.cards}>
          {["Upload Document", "Ask a Question", "View History"].map((label) => (
            <div key={label} style={styles.card}>{label}</div>
          ))}
        </div>
      </div>
    </div>
  );
}

const styles = {
  page: { minHeight: "100vh", background: "#0f1117", fontFamily: "'Inter', sans-serif" },
  header: {
    display: "flex", alignItems: "center", justifyContent: "space-between",
    padding: "18px 32px", borderBottom: "1px solid #1e2130",
  },
  brand: { display: "flex", alignItems: "center", gap: "10px" },
  brandName: { color: "#f1f5f9", fontWeight: "600", fontSize: "16px" },
  userInfo: { display: "flex", alignItems: "center", gap: "16px" },
  userEmail: { color: "#94a3b8", fontSize: "14px" },
  logoutBtn: {
    background: "transparent", border: "1px solid #2a2d3d",
    color: "#94a3b8", borderRadius: "6px", padding: "6px 14px",
    fontSize: "13px", cursor: "pointer",
  },
  body: { maxWidth: "900px", margin: "0 auto", padding: "64px 32px" },
  welcome: { color: "#f1f5f9", fontSize: "32px", fontWeight: "700", margin: "0 0 8px" },
  hint: { color: "#64748b", fontSize: "15px", lineHeight: "1.6", margin: "0 0 48px" },
  cards: { display: "grid", gridTemplateColumns: "repeat(3,1fr)", gap: "16px" },
  card: {
    background: "#1a1d27", border: "1px solid #2a2d3d", borderRadius: "12px",
    padding: "32px 24px", color: "#94a3b8", fontSize: "14px",
    fontWeight: "500", cursor: "pointer",
  },
};