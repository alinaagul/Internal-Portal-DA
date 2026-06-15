import { useState, useCallback, useContext, createContext } from "react";
import { authApi } from "../api/auth";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(() => {
    try {
      const stored = localStorage.getItem("user");
      return stored ? JSON.parse(stored) : null;
    } catch {
      return null;
    }
  });
  const [loading, setLoading] = useState(false);
  const [error, setError]     = useState(null);

  const saveSession = (data) => {
    localStorage.setItem("access_token", data.access_token);
    localStorage.setItem("user", JSON.stringify(data.user));
    setUser(data.user);
    return data.user;
  };

  const login = useCallback(async (email, password) => {
    setLoading(true);
    setError(null);
    try {
      const { data } = await authApi.login({ email, password });
      const loggedInUser = saveSession(data);
      return { success: true, user: loggedInUser };
    } catch (err) {
      const msg = err.response?.data?.detail || "Login failed";
      setError(msg);
      return { success: false, error: msg };
    } finally {
      setLoading(false);
    }
  }, []);

  const adminSignup = useCallback(async ({ full_name, email, password, signup_secret }) => {
    setLoading(true);
    setError(null);
    try {
      const payload = { full_name, email, password };
      if (signup_secret) payload.signup_secret = signup_secret;
      const { data } = await authApi.adminSignup(payload);
      const newUser = saveSession(data);
      return { success: true, user: newUser };
    } catch (err) {
      const msg = err.response?.data?.detail || "Admin signup failed";
      setError(msg);
      return { success: false, error: msg };
    } finally {
      setLoading(false);
    }
  }, []);

  const logout = useCallback(() => {
    localStorage.removeItem("access_token");
    localStorage.removeItem("user");
    setUser(null);
  }, []);

  return (
    <AuthContext.Provider value={{ user, loading, error, login, adminSignup, logout, setError }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside <AuthProvider>");
  return ctx;
}
