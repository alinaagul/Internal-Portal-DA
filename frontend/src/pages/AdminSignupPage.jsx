import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "../hooks/useAuth.jsx";
import { getDashboardPath } from "../utils/auth";

export default function AdminSignupPage() {
  const [form, setForm] = useState({
    full_name: "",
    email: "",
    password: "",
    signup_secret: "",
  });
  const { adminSignup, loading, error, setError } = useAuth();
  const navigate = useNavigate();

  const handleChange = (e) => {
    setError(null);
    setForm((f) => ({ ...f, [e.target.name]: e.target.value }));
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    const result = await adminSignup(form);
    if (result.success) navigate(getDashboardPath("admin"));
  };

  return (
    <div style={s.page}>
      <div style={s.card}>
        <div style={s.brand}>
          <div style={s.logoBox}>
            <svg width="18" height="18" viewBox="0 0 28 28" fill="none">
              <path d="M4 6h20M4 12h14M4 18h18M4 24h10" stroke="#2563eb" strokeWidth="2.5" strokeLinecap="round"/>
            </svg>
          </div>
          <span style={s.brandName}>DocAssist</span>
        </div>

        <div style={s.badge}>Administrator</div>
        <h1 style={s.title}>Admin Signup</h1>
        <p style={s.sub}>
          Create an administrator account. Regular users cannot sign up — admins create their accounts.
        </p>

        <form onSubmit={handleSubmit} style={s.form}>
          <div style={s.field}>
            <label style={s.label}>Full name</label>
            <input style={s.input} name="full_name" type="text"
              placeholder="Admin name" value={form.full_name}
              onChange={handleChange} required />
          </div>
          <div style={s.field}>
            <label style={s.label}>Email</label>
            <input style={s.input} name="email" type="email"
              placeholder="admin@example.com" value={form.email}
              onChange={handleChange} required />
          </div>
          <div style={s.field}>
            <label style={s.label}>Password</label>
            <input style={s.input} name="password" type="password"
              placeholder="••••••••" value={form.password}
              onChange={handleChange} required />
          </div>
          <div style={s.field}>
            <label style={s.label}>Admin signup secret (if required)</label>
            <input style={s.input} name="signup_secret" type="password"
              placeholder="Only needed after the first admin exists"
              value={form.signup_secret}
              onChange={handleChange} />
          </div>

          {error && <div style={s.errorBox}>{error}</div>}

          <button type="submit" style={s.btn} disabled={loading}>
            {loading ? "Please wait…" : "Create admin account"}
          </button>
        </form>

        <p style={s.switchText}>
          Already have an account?{" "}
          <Link to="/login" style={s.link}>Sign in</Link>
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
  brand: { display:"flex", alignItems:"center", gap:"9px", marginBottom:"20px" },
  logoBox: { width:"34px", height:"34px", background:"#eff6ff", border:"1px solid #bfdbfe",
    borderRadius:"8px", display:"flex", alignItems:"center", justifyContent:"center" },
  brandName: { color:"#0f172a", fontSize:"16px", fontWeight:"700", letterSpacing:"-0.3px" },
  badge: { display:"inline-block", background:"#eff6ff", color:"#1d4ed8",
    fontSize:"11px", fontWeight:"700", textTransform:"uppercase", letterSpacing:"0.6px",
    padding:"4px 10px", borderRadius:"20px", marginBottom:"12px" },
  title: { color:"#0f172a", fontSize:"22px", fontWeight:"700", margin:"0 0 4px",
    letterSpacing:"-0.5px" },
  sub: { color:"#64748b", fontSize:"13px", margin:"0 0 24px", lineHeight:"1.5" },
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
  link: { color:"#2563eb", fontWeight:"500", textDecoration:"none" },
};
