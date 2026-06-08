import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../hooks/useAuth.jsx";

export default function AuthPage() {
  const [mode, setMode] = useState("login");
  const [form, setForm] = useState({ full_name: "", email: "", password: "" });
  const { login, signup, loading, error, setError } = useAuth();
  const navigate = useNavigate();

  const handleChange = (e) => {
    setError(null);
    setForm((f) => ({ ...f, [e.target.name]: e.target.value }));
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    const result =
      mode === "login"
        ? await login(form.email, form.password)
        : await signup(form.full_name, form.email, form.password);
    if (result.success) navigate("/dashboard");
  };

  const switchMode = () => {
    setError(null);
    setForm({ full_name: "", email: "", password: "" });
    setMode((m) => (m === "login" ? "signup" : "login"));
  };

  return (
    <div style={s.page}>
      <div style={s.card}>
        {/* Brand */}
        <div style={s.brand}>
          <div style={s.logoBox}>
            <svg width="18" height="18" viewBox="0 0 28 28" fill="none">
              <path d="M4 6h20M4 12h14M4 18h18M4 24h10" stroke="#2563eb" strokeWidth="2.5" strokeLinecap="round"/>
            </svg>
          </div>
          <span style={s.brandName}>DocAssist</span>
        </div>

        <h1 style={s.title}>{mode === "login" ? "Sign in" : "Create account"}</h1>
        <p style={s.sub}>
          {mode === "login" ? "Welcome back to your workspace" : "Start your document intelligence journey"}
        </p>

        <form onSubmit={handleSubmit} style={s.form}>
          {mode === "signup" && (
            <div style={s.field}>
              <label style={s.label}>Full name</label>
              <input style={s.input} name="full_name" type="text"
                placeholder="Ahmed Khan" value={form.full_name}
                onChange={handleChange} required />
            </div>
          )}
          <div style={s.field}>
            <label style={s.label}>Email</label>
            <input style={s.input} name="email" type="email"
              placeholder="you@example.com" value={form.email}
              onChange={handleChange} required />
          </div>
          <div style={s.field}>
            <label style={s.label}>Password</label>
            <input style={s.input} name="password" type="password"
              placeholder="••••••••" value={form.password}
              onChange={handleChange} required />
          </div>

          {error && <div style={s.errorBox}>{error}</div>}

          <button type="submit" style={s.btn} disabled={loading}>
            {loading ? "Please wait…" : mode === "login" ? "Sign in" : "Create account"}
          </button>
        </form>

        <p style={s.switchText}>
          {mode === "login" ? "Don't have an account? " : "Already have an account? "}
          <span style={s.link} onClick={switchMode}>
            {mode === "login" ? "Sign up" : "Sign in"}
          </span>
        </p>
      </div>
    </div>
  );
}

const s = {
  page: { minHeight:"100vh", background:"#f8fafc", display:"flex", alignItems:"center",
    justifyContent:"center", fontFamily:"'Geist','DM Sans',system-ui,sans-serif", padding:"24px" },
  card: { background:"#fff", border:"1px solid #e2e8f0", borderRadius:"16px",
    padding:"44px 40px", width:"100%", maxWidth:"400px",
    boxShadow:"0 4px 24px rgba(0,0,0,0.06)" },
  brand: { display:"flex", alignItems:"center", gap:"9px", marginBottom:"28px" },
  logoBox: { width:"34px", height:"34px", background:"#eff6ff", border:"1px solid #bfdbfe",
    borderRadius:"8px", display:"flex", alignItems:"center", justifyContent:"center" },
  brandName: { color:"#0f172a", fontSize:"16px", fontWeight:"700", letterSpacing:"-0.3px" },
  title: { color:"#0f172a", fontSize:"22px", fontWeight:"700", margin:"0 0 4px",
    letterSpacing:"-0.5px" },
  sub: { color:"#64748b", fontSize:"13px", margin:"0 0 24px" },
  form: { display:"flex", flexDirection:"column", gap:"16px" },
  field: { display:"flex", flexDirection:"column", gap:"5px" },
  label: { color:"#374151", fontSize:"13px", fontWeight:"500" },
  input: { background:"#fff", border:"1px solid #d1d5db", borderRadius:"8px",
    padding:"10px 13px", color:"#0f172a", fontSize:"14px", outline:"none",
    transition:"border-color 0.15s", fontFamily:"inherit" },
  errorBox: { background:"#fef2f2", border:"1px solid #fecaca", borderRadius:"8px",
    padding:"10px 13px", color:"#dc2626", fontSize:"13px" },
  btn: { background:"#2563eb", color:"#fff", border:"none", borderRadius:"8px",
    padding:"11px", fontSize:"14px", fontWeight:"600", cursor:"pointer",
    marginTop:"2px", fontFamily:"inherit" },
  switchText: { color:"#64748b", fontSize:"13px", textAlign:"center",
    marginTop:"20px", marginBottom:0 },
  link: { color:"#2563eb", cursor:"pointer", fontWeight:"500" },
};