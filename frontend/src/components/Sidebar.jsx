import { useNavigate, useLocation } from "react-router-dom";
import { useAuth } from "../hooks/useAuth.jsx";
import { isAdmin } from "../utils/auth";

const USER_NAV = [
  {
    path: "/dashboard",
    label: "Dashboard",
    icon: (c) => (
      <svg width="16" height="16" viewBox="0 0 20 20" fill="none">
        <rect x="2" y="2" width="7" height="7" rx="1.5" stroke={c} strokeWidth="1.6" />
        <rect x="11" y="2" width="7" height="7" rx="1.5" stroke={c} strokeWidth="1.6" />
        <rect x="2" y="11" width="7" height="7" rx="1.5" stroke={c} strokeWidth="1.6" />
        <rect x="11" y="11" width="7" height="7" rx="1.5" stroke={c} strokeWidth="1.6" />
      </svg>
    ),
  },
  {
    path: "/documents",
    label: "My Collections",
    icon: (c) => (
      <svg width="16" height="16" viewBox="0 0 20 20" fill="none">
        <path d="M4 2h8l4 4v12a2 2 0 01-2 2H4a2 2 0 01-2-2V4a2 2 0 012-2z" stroke={c} strokeWidth="1.7" />
        <path d="M12 2v4h4" stroke={c} strokeWidth="1.4" />
        <path d="M6 9h8M6 13h5" stroke={c} strokeWidth="1.4" strokeLinecap="round" />
      </svg>
    ),
  },
  {
    path: "/chat",
    label: "Chat",
    icon: (c) => (
      <svg width="16" height="16" viewBox="0 0 20 20" fill="none">
        <path
          d="M2 4a2 2 0 012-2h12a2 2 0 012 2v8a2 2 0 01-2 2H6l-4 4V4z"
          stroke={c}
          strokeWidth="1.7"
          strokeLinejoin="round"
        />
      </svg>
    ),
  },
];

const ADMIN_NAV = [
  {
    path: "/admin/dashboard",
    label: "Admin Dashboard",
    icon: (c) => (
      <svg width="16" height="16" viewBox="0 0 20 20" fill="none">
        <path d="M3 10h14M10 3v14" stroke={c} strokeWidth="1.6" strokeLinecap="round" />
        <rect x="2" y="2" width="16" height="16" rx="3" stroke={c} strokeWidth="1.6" />
      </svg>
    ),
  },
  {
    path: "/admin/collections",
    label: "Collections",
    icon: (c) => (
      <svg width="16" height="16" viewBox="0 0 20 20" fill="none">
        <path d="M3 6a2 2 0 012-2h3l1 2h8a2 2 0 012 2v8a2 2 0 01-2 2H5a2 2 0 01-2-2V6z" stroke={c} strokeWidth="1.7" />
        <path d="M3 8h14" stroke={c} strokeWidth="1.4" />
      </svg>
    ),
  },
  ...USER_NAV.filter((item) => item.path !== "/dashboard" && item.path !== "/documents"),
];

export default function Sidebar() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const { pathname } = useLocation();
  const navItems = isAdmin(user) ? ADMIN_NAV : USER_NAV;
  const roleLabel = user?.role === "admin" ? "Administrator" : "User";

  const handleLogout = () => {
    logout();
    navigate("/login");
  };

  return (
    <aside style={s.sidebar}>
      <div style={s.brand}>
        <div style={s.logo}>
          <svg width="16" height="16" viewBox="0 0 28 28" fill="none">
            <path
              d="M4 6h20M4 12h14M4 18h18M4 24h10"
              stroke="#fff"
              strokeWidth="2.5"
              strokeLinecap="round"
            />
          </svg>
        </div>
        <span style={s.brandName}>DocAssist</span>
      </div>

      <nav style={s.nav}>
        <div style={s.navSection}>
          <div style={s.navSectionLabel}>Main Menu</div>
          {navItems.map((item) => {
            const active = pathname === item.path;
            const iconColor = active ? "#60a5fa" : "#64748b";
            return (
              <button
                key={item.path}
                style={{ ...s.navItem, ...(active ? s.navItemActive : {}) }}
                onClick={() => navigate(item.path)}
              >
                {item.icon(iconColor)}
                <span style={{ color: active ? "#e2e8f0" : "#94a3b8" }}>{item.label}</span>
                {active && <div style={s.activeDot} />}
              </button>
            );
          })}
        </div>
      </nav>

      <div style={{ flex: 1 }} />

      <div style={s.bottom}>
        <div style={s.userRow}>
          <div style={s.avatar}>{(user?.full_name || "U")[0].toUpperCase()}</div>
          <div style={s.userInfo}>
            <div style={s.userName}>{user?.full_name || "User"}</div>
            <div style={s.userRole}>{roleLabel}</div>
          </div>
        </div>
        <button style={s.logoutBtn} onClick={handleLogout}>
          <svg width="13" height="13" viewBox="0 0 20 20" fill="none">
            <path
              d="M13 3h4v14h-4M9 14l4-4-4-4M13 10H3"
              stroke="currentColor"
              strokeWidth="1.8"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
          Sign out
        </button>
      </div>
    </aside>
  );
}

const s = {
  sidebar: {
    width: "220px",
    minWidth: "220px",
    height: "100vh",
    background: "#0f172a",
    display: "flex",
    flexDirection: "column",
    borderRight: "1px solid #1e293b",
    flexShrink: 0,
  },
  brand: {
    display: "flex",
    alignItems: "center",
    gap: "10px",
    padding: "18px 16px 16px",
    borderBottom: "1px solid #1e293b",
  },
  logo: {
    width: "32px",
    height: "32px",
    background: "#2563eb",
    borderRadius: "8px",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    flexShrink: 0,
  },
  brandName: {
    color: "#f8fafc",
    fontWeight: "700",
    fontSize: "15px",
    letterSpacing: "-0.3px",
  },
  nav: { padding: "12px 8px", display: "flex", flexDirection: "column", gap: "16px" },
  navSection: { display: "flex", flexDirection: "column", gap: "2px" },
  navSectionLabel: {
    color: "#475569",
    fontSize: "10px",
    fontWeight: "600",
    textTransform: "uppercase",
    letterSpacing: "0.8px",
    padding: "4px 10px 6px",
  },
  navItem: {
    display: "flex",
    alignItems: "center",
    gap: "10px",
    padding: "9px 10px",
    borderRadius: "8px",
    border: "none",
    background: "transparent",
    cursor: "pointer",
    width: "100%",
    textAlign: "left",
    fontSize: "13px",
    fontWeight: "500",
    fontFamily: "inherit",
    color: "#94a3b8",
    position: "relative",
    transition: "background 0.1s",
  },
  navItemActive: { background: "#1e293b" },
  activeDot: {
    position: "absolute",
    right: "10px",
    width: "5px",
    height: "5px",
    background: "#3b82f6",
    borderRadius: "50%",
  },
  bottom: {
    borderTop: "1px solid #1e293b",
    padding: "10px 8px 16px",
    display: "flex",
    flexDirection: "column",
    gap: "6px",
  },
  userRow: {
    display: "flex",
    alignItems: "center",
    gap: "9px",
    padding: "8px 10px",
    borderRadius: "8px",
  },
  avatar: {
    width: "30px",
    height: "30px",
    background: "#2563eb",
    borderRadius: "50%",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    color: "#fff",
    fontSize: "12px",
    fontWeight: "700",
    flexShrink: 0,
  },
  userInfo: { flex: 1, minWidth: 0 },
  userName: {
    color: "#cbd5e1",
    fontSize: "12px",
    fontWeight: "500",
    overflow: "hidden",
    textOverflow: "ellipsis",
    whiteSpace: "nowrap",
  },
  userRole: { color: "#475569", fontSize: "10px", marginTop: "1px" },
  logoutBtn: {
    display: "flex",
    alignItems: "center",
    gap: "7px",
    background: "transparent",
    border: "1px solid #1e293b",
    color: "#64748b",
    borderRadius: "7px",
    padding: "8px 10px",
    fontSize: "12px",
    cursor: "pointer",
    fontFamily: "inherit",
    width: "100%",
    transition: "border-color 0.1s, color 0.1s",
  },
};
