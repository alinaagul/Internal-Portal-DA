import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { AuthProvider, useAuth } from "./hooks/useAuth.jsx";
import AuthPage from "./pages/AuthPage";
import AdminSignupPage from "./pages/AdminSignupPage";
import Dashboard from "./pages/Dashboard";
import AdminDashboard from "./pages/AdminDashboard";
import AdminCollectionsPage from "./pages/AdminCollectionsPage";
import DocumentsPage from "./pages/DocumentsPage";
import ChatPage from "./pages/ChatPage";
import ProtectedRoute from "./components/ProtectedRoute";
import AdminRoute from "./components/AdminRoute";
import UserRoute from "./components/UserRoute";
import Layout from "./components/Layout";
import { getDashboardPath } from "./utils/auth";

function AppRoutes() {
  const { user } = useAuth();
  const home = user ? getDashboardPath(user.role) : "/login";

  return (
    <Routes>
      <Route path="/login" element={user ? <Navigate to={home} replace /> : <AuthPage />} />
      <Route path="/signup" element={<Navigate to="/admin/signup" replace />} />
      <Route path="/admin/signup" element={user ? <Navigate to={home} replace /> : <AdminSignupPage />} />

      <Route
        path="/admin/dashboard"
        element={
          <AdminRoute user={user}>
            <Layout><AdminDashboard /></Layout>
          </AdminRoute>
        }
      />
      <Route
        path="/admin/collections"
        element={
          <AdminRoute user={user}>
            <Layout><AdminCollectionsPage /></Layout>
          </AdminRoute>
        }
      />

      <Route
        path="/dashboard"
        element={
          <UserRoute user={user}>
            <Layout><Dashboard /></Layout>
          </UserRoute>
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

      <Route path="*" element={<Navigate to={home} replace />} />
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
