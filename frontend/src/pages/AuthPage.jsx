import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../hooks/useAuth";

export default function AuthPage() {
  const [mode, setMode] = useState("login"); // "login" | "signup"
  const [form, setForm] = useState({ full_name: "", email: "", password: "" });
  const { login, signup, loading, error, setError } = useAuth();
  const navigate = useNavigate();

  const handleChange = (e) => {
    setError(null);
    setForm((f) => ({ ...f, [e.target.name]: e.target.value }));
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    let result;
    if (mode === "login") {
      result = await login(form.email, form.password);
    } else {
      result = await signup(form.full_name, form.email, form.password);
    }
    if (result.success) navigate("/dashboard");
  };

  const switchMode = () => {
    setError(null);
    setForm({ full_name: "", email: "", password: "" });
    setMode((m) => (m === "login" ? "signup" : "login"));
  };

  return (
    <div style={styles.page}>
      <div style={styles.card}>
        {/* Logo / brand */}
        <div style={styles.brand}>
          <div style={styles.logoRing}>
            <svg width="28" height="28" viewBox="0 0 28 28" fill="none">
              <path d="M4 6h20M4 12h14M4 18h18M4 24h10" stroke="#60a5fa" strokeWidth="2.2" strokeLinecap="round"/>
            </svg>
          </div>
          <span style={styles.brandName}>DocAssist</span>
        </div>

        <h1 style={styles.title}>
          {mode === "login" ? "Welcome back" : "Create account"}
        </h1>
        <p style={styles.sub}>
          {mode === "login"
            ? "Sign in to your workspace"
            : "Start your document intelligence journey"}
        </p>

        <form onSubmit={handleSubmit} style={styles.form}>
          {mode === "signup" && (
            <div style={styles.field}>
              <label style={styles.label}>Full name</label>
              <input
                style={styles.input}
                name="full_name"
                type="text"
                placeholder="Ahmed Khan"
                value={form.full_name}
                onChange={handleChange}
                required
              />
            </div>
          )}

          <div style={styles.field}>
            <label style={styles.label}>Email</label>
            <input
              style={styles.input}
              name="email"
              type="email"
              placeholder="you@example.com"
              value={form.email}
              onChange={handleChange}
              required
            />
          </div>

          <div style={styles.field}>
            <label style={styles.label}>Password</label>
            <input
              style={styles.input}
              name="password"
              type="password"
              placeholder={mode === "signup" ? "Min. 8 characters" : "••••••••"}
              value={form.password}
              onChange={handleChange}
              required
            />
          </div>

          {error && <div style={styles.errorBox}>{error}</div>}

          <button type="submit" style={styles.btn} disabled={loading}>
            {loading ? "Please wait…" : mode === "login" ? "Sign in" : "Create account"}
          </button>
        </form>

        <p style={styles.switchText}>
          {mode === "login" ? "Don't have an account? " : "Already have an account? "}
          <span style={styles.switchLink} onClick={switchMode}>
            {mode === "login" ? "Sign up" : "Sign in"}
          </span>
        </p>
      </div>
    </div>
  );
}

const styles = {
  page: {
    minHeight: "100vh",
    background: "#0f1117",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    fontFamily: "'Inter', sans-serif",
    padding: "24px",
  },
  card: {
    background: "#1a1d27",
    border: "1px solid #2a2d3d",
    borderRadius: "16px",
    padding: "48px 44px",
    width: "100%",
    maxWidth: "420px",
    boxShadow: "0 24px 64px rgba(0,0,0,0.5)",
  },
  brand: {
    display: "flex",
    alignItems: "center",
    gap: "10px",
    marginBottom: "32px",
  },
  logoRing: {
    width: "44px",
    height: "44px",
    background: "rgba(96,165,250,0.12)",
    border: "1px solid rgba(96,165,250,0.25)",
    borderRadius: "10px",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
  },
  brandName: {
    color: "#f1f5f9",
    fontSize: "18px",
    fontWeight: "600",
    letterSpacing: "-0.3px",
  },
  title: {
    color: "#f1f5f9",
    fontSize: "24px",
    fontWeight: "700",
    margin: "0 0 6px",
    letterSpacing: "-0.5px",
  },
  sub: {
    color: "#64748b",
    fontSize: "14px",
    margin: "0 0 28px",
  },
  form: { display: "flex", flexDirection: "column", gap: "18px" },
  field: { display: "flex", flexDirection: "column", gap: "6px" },
  label: { color: "#94a3b8", fontSize: "13px", fontWeight: "500" },
  input: {
    background: "#0f1117",
    border: "1px solid #2a2d3d",
    borderRadius: "8px",
    padding: "12px 14px",
    color: "#f1f5f9",
    fontSize: "14px",
    outline: "none",
    transition: "border-color 0.2s",
  },
  errorBox: {
    background: "rgba(239,68,68,0.1)",
    border: "1px solid rgba(239,68,68,0.3)",
    borderRadius: "8px",
    padding: "10px 14px",
    color: "#f87171",
    fontSize: "13px",
  },
  btn: {
    background: "#3b82f6",
    color: "#fff",
    border: "none",
    borderRadius: "8px",
    padding: "13px",
    fontSize: "14px",
    fontWeight: "600",
    cursor: "pointer",
    transition: "background 0.2s",
    marginTop: "4px",
  },
  switchText: {
    color: "#64748b",
    fontSize: "13px",
    textAlign: "center",
    marginTop: "24px",
    marginBottom: 0,
  },
  switchLink: {
    color: "#60a5fa",
    cursor: "pointer",
    fontWeight: "500",
  },
};