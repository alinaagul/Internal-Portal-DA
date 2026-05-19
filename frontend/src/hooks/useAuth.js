import { useState, useCallback } from "react";
import { authApi } from "../api/auth";

export function useAuth() {
  const [user, setUser] = useState(() => {
    try {
      const stored = localStorage.getItem("user");
      return stored ? JSON.parse(stored) : null;
    } catch {
      return null;
    }
  });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const saveSession = (data) => {
    localStorage.setItem("access_token", data.access_token);
    localStorage.setItem("user", JSON.stringify(data.user));
    setUser(data.user);
  };

  const login = useCallback(async (email, password) => {
    setLoading(true);
    setError(null);
    try {
      const { data } = await authApi.login({ email, password });
      saveSession(data);
      return { success: true };
    } catch (err) {
      const msg = err.response?.data?.detail || "Login failed";
      setError(msg);
      return { success: false, error: msg };
    } finally {
      setLoading(false);
    }
  }, []);

  const signup = useCallback(async (full_name, email, password) => {
    setLoading(true);
    setError(null);
    try {
      const { data } = await authApi.signup({ full_name, email, password });
      saveSession(data);
      return { success: true };
    } catch (err) {
      const msg = err.response?.data?.detail || "Signup failed";
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

  return { user, loading, error, login, signup, logout, setError };
}