import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { AuthProvider, useAuth } from "./hooks/useAuth.jsx";
import AuthPage from "./pages/AuthPage";
import Dashboard from "./pages/Dashboard";
import DocumentsPage from "./pages/DocumentsPage";
import ChatPage from "./pages/ChatPage";
import ProtectedRoute from "./components/ProtectedRoute";
import Layout from "./components/Layout";

function AppRoutes() {
  const { user } = useAuth();

  return (
    <Routes>
      <Route path="/login"  element={user ? <Navigate to="/documents" replace /> : <AuthPage />} />
      <Route path="/signup" element={user ? <Navigate to="/documents" replace /> : <AuthPage />} />

      <Route
        path="/dashboard"
        element={
          <ProtectedRoute user={user}>
            <Layout><Dashboard /></Layout>
          </ProtectedRoute>
        }
      />
      <Route
        path="/documents"
        element={
          <ProtectedRoute user={user}>
            <Layout><DocumentsPage /></Layout>
          </ProtectedRoute>
        }
      />
      <Route
        path="/chat"
        element={
          <ProtectedRoute user={user}>
            <Layout><ChatPage /></Layout>
          </ProtectedRoute>
        }
      />

      <Route path="*" element={<Navigate to={user ? "/documents" : "/login"} replace />} />
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
