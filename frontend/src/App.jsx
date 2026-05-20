import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { AuthProvider, useAuth } from "./hooks/useAuth.jsx";
import AuthPage from "./pages/AuthPage";
import Dashboard from "./pages/Dashboard";
import ProtectedRoute from "./components/ProtectedRoute";

// Inner component — can safely call useAuth() because it's inside AuthProvider
function AppRoutes() {
  const { user } = useAuth();
  return (
    <Routes>
      <Route path="/login"  element={user ? <Navigate to="/dashboard" replace /> : <AuthPage />} />
      <Route path="/signup" element={user ? <Navigate to="/dashboard" replace /> : <AuthPage />} />
      <Route
        path="/dashboard"
        element={
          <ProtectedRoute user={user}>
            <Dashboard />
          </ProtectedRoute>
        }
      />
      <Route path="*" element={<Navigate to={user ? "/dashboard" : "/login"} replace />} />
    </Routes>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <AppRoutes />
      </AuthProvider>
    </BrowserRouter>
  );
}