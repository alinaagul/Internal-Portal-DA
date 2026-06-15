import { useEffect, useState } from "react";
import { useAuth } from "../hooks/useAuth.jsx";
import { usersApi } from "../api/users";

export default function AdminDashboard() {
  const { user } = useAuth();
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [form, setForm] = useState({ full_name: "", email: "", password: "" });
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState(null);
  const [createSuccess, setCreateSuccess] = useState(null);

  const fetchUsers = async () => {
    setLoading(true);
    setError(null);
    try {
      const { data } = await usersApi.list();
      setUsers(data);
    } catch (err) {
      setError(err.response?.data?.detail || "Failed to load users");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetchUsers(); }, []);

  const handleChange = (e) => {
    setCreateError(null);
    setCreateSuccess(null);
    setForm((f) => ({ ...f, [e.target.name]: e.target.value }));
  };

  const handleCreateUser = async (e) => {
    e.preventDefault();
    setCreating(true);
    setCreateError(null);
    setCreateSuccess(null);
    try {
      await usersApi.create({ ...form, role: "user" });
      setForm({ full_name: "", email: "", password: "" });
      setCreateSuccess("User account created successfully.");
      fetchUsers();
    } catch (err) {
      setCreateError(err.response?.data?.detail || "Failed to create user");
    } finally {
      setCreating(false);
    }
  };

  const toggleActive = async (u) => {
    try {
      await usersApi.updateStatus(u.id, !u.is_active);
      fetchUsers();
    } catch (err) {
      setError(err.response?.data?.detail || "Failed to update user");
    }
  };

  const regularUsers = users.filter((u) => u.role === "user");
  const adminUsers = users.filter((u) => u.role === "admin");
  const activeUsers = users.filter((u) => u.is_active);
  const firstName = user?.full_name?.split(" ")[0] || "Admin";

  return (
    <div style={s.page}>
      <div style={s.pageHeader}>
        <div>
          <h1 style={s.pageTitle}>Admin Dashboard</h1>
          <p style={s.pageSubtitle}>Welcome, {firstName}. Manage user accounts and monitor access.</p>
        </div>
      </div>

      <div style={s.content}>
        <div style={s.statsGrid}>
          {[
            { label: "Total Users", value: users.length, color: "#2563eb", bg: "#eff6ff" },
            { label: "Regular Users", value: regularUsers.length, color: "#7c3aed", bg: "#f5f3ff" },
            { label: "Administrators", value: adminUsers.length, color: "#0f766e", bg: "#f0fdfa" },
            { label: "Active Accounts", value: activeUsers.length, color: "#16a34a", bg: "#f0fdf4" },
          ].map(({ label, value, color, bg }) => (
            <div key={label} style={s.statCard}>
              <div style={{ ...s.statValue, color }}>{value}</div>
              <div style={s.statLabel}>{label}</div>
              <div style={{ ...s.statAccent, background: bg }} />
            </div>
          ))}
        </div>

        <div style={s.grid}>
          <div style={s.section}>
            <div style={s.sectionTitle}>Create User Account</div>
            <p style={s.sectionSub}>
              Users cannot sign up themselves. Create accounts here so they can log in.
            </p>
            <form onSubmit={handleCreateUser} style={s.form}>
              <div style={s.field}>
                <label style={s.label}>Full name</label>
                <input style={s.input} name="full_name" value={form.full_name}
                  onChange={handleChange} required placeholder="Jane Doe" />
              </div>
              <div style={s.field}>
                <label style={s.label}>Email</label>
                <input style={s.input} name="email" type="email" value={form.email}
                  onChange={handleChange} required placeholder="user@example.com" />
              </div>
              <div style={s.field}>
                <label style={s.label}>Temporary password</label>
                <input style={s.input} name="password" type="password" value={form.password}
                  onChange={handleChange} required placeholder="Min. 8 characters" />
              </div>
              {createError && <div style={s.errorBox}>{createError}</div>}
              {createSuccess && <div style={s.successBox}>{createSuccess}</div>}
              <button type="submit" style={s.btn} disabled={creating}>
                {creating ? "Creating…" : "Create user"}
              </button>
            </form>
          </div>

          <div style={s.section}>
            <div style={s.sectionTitle}>All Accounts</div>
            {error && <div style={s.errorBox}>{error}</div>}
            {loading ? (
              <p style={s.muted}>Loading users…</p>
            ) : users.length === 0 ? (
              <p style={s.muted}>No users yet. Create the first user account.</p>
            ) : (
              <div style={s.table}>
                {users.map((u) => (
                  <div key={u.id} style={s.row}>
                    <div style={s.avatar}>{u.full_name[0].toUpperCase()}</div>
                    <div style={s.userInfo}>
                      <div style={s.userName}>{u.full_name}</div>
                      <div style={s.userEmail}>{u.email}</div>
                    </div>
                    <span style={{
                      ...s.roleBadge,
                      ...(u.role === "admin" ? s.roleAdmin : s.roleUser),
                    }}>
                      {u.role}
                    </span>
                    <span style={{
                      ...s.statusBadge,
                      ...(u.is_active ? s.statusActive : s.statusInactive),
                    }}>
                      {u.is_active ? "Active" : "Disabled"}
                    </span>
                    {u.id !== user?.id && (
                      <button style={s.toggleBtn} onClick={() => toggleActive(u)}>
                        {u.is_active ? "Disable" : "Enable"}
                      </button>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

const s = {
  page: {
    display: "flex", flexDirection: "column", height: "100%",
    background: "#f8fafc", fontFamily: "'Plus Jakarta Sans', 'DM Sans', system-ui, sans-serif",
    overflow: "hidden",
  },
  pageHeader: {
    padding: "24px 28px 16px", background: "#fff",
    borderBottom: "1px solid #e2e8f0", flexShrink: 0,
  },
  pageTitle: { color: "#0f172a", fontSize: "20px", fontWeight: "700", margin: 0 },
  pageSubtitle: { color: "#64748b", fontSize: "13px", margin: "3px 0 0" },
  content: { flex: 1, overflowY: "auto", padding: "24px 28px", display: "flex", flexDirection: "column", gap: "20px" },
  statsGrid: { display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: "12px" },
  statCard: {
    background: "#fff", border: "1px solid #e2e8f0", borderRadius: "12px",
    padding: "18px", position: "relative", overflow: "hidden",
  },
  statValue: { fontSize: "28px", fontWeight: "700", lineHeight: 1 },
  statLabel: { color: "#64748b", fontSize: "12px", marginTop: "6px" },
  statAccent: { position: "absolute", top: 0, right: 0, width: "60px", height: "60px", borderRadius: "0 12px 0 60px", opacity: 0.5 },
  grid: { display: "grid", gridTemplateColumns: "1fr 1.4fr", gap: "16px" },
  section: { background: "#fff", border: "1px solid #e2e8f0", borderRadius: "12px", padding: "20px" },
  sectionTitle: { color: "#374151", fontSize: "12px", fontWeight: "700", textTransform: "uppercase", letterSpacing: "0.6px", marginBottom: "8px" },
  sectionSub: { color: "#64748b", fontSize: "13px", margin: "0 0 16px", lineHeight: 1.5 },
  form: { display: "flex", flexDirection: "column", gap: "12px" },
  field: { display: "flex", flexDirection: "column", gap: "5px" },
  label: { color: "#374151", fontSize: "12px", fontWeight: "500" },
  input: { border: "1px solid #d1d5db", borderRadius: "8px", padding: "9px 12px", fontSize: "13px", fontFamily: "inherit" },
  btn: { background: "#2563eb", color: "#fff", border: "none", borderRadius: "8px", padding: "10px", fontSize: "13px", fontWeight: "600", cursor: "pointer", fontFamily: "inherit" },
  errorBox: { background: "#fef2f2", border: "1px solid #fecaca", borderRadius: "8px", padding: "10px", color: "#dc2626", fontSize: "12px" },
  successBox: { background: "#f0fdf4", border: "1px solid #bbf7d0", borderRadius: "8px", padding: "10px", color: "#15803d", fontSize: "12px" },
  muted: { color: "#94a3b8", fontSize: "13px" },
  table: { display: "flex", flexDirection: "column", gap: "8px" },
  row: { display: "flex", alignItems: "center", gap: "10px", padding: "10px 0", borderBottom: "1px solid #f1f5f9" },
  avatar: { width: "32px", height: "32px", background: "#2563eb", color: "#fff", borderRadius: "50%", display: "flex", alignItems: "center", justifyContent: "center", fontSize: "12px", fontWeight: "700", flexShrink: 0 },
  userInfo: { flex: 1, minWidth: 0 },
  userName: { color: "#0f172a", fontSize: "13px", fontWeight: "600" },
  userEmail: { color: "#94a3b8", fontSize: "11px", marginTop: "1px" },
  roleBadge: { fontSize: "10px", fontWeight: "700", textTransform: "uppercase", padding: "3px 8px", borderRadius: "20px" },
  roleAdmin: { background: "#eff6ff", color: "#1d4ed8" },
  roleUser: { background: "#f5f3ff", color: "#6d28d9" },
  statusBadge: { fontSize: "10px", fontWeight: "600", padding: "3px 8px", borderRadius: "20px" },
  statusActive: { background: "#f0fdf4", color: "#15803d" },
  statusInactive: { background: "#fef2f2", color: "#b91c1c" },
  toggleBtn: { background: "transparent", border: "1px solid #e2e8f0", borderRadius: "6px", padding: "4px 10px", fontSize: "11px", cursor: "pointer", fontFamily: "inherit", color: "#64748b" },
};
