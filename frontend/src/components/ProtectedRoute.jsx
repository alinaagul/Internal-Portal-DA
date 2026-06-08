import { Navigate } from "react-router-dom";

export default function ProtectedRoute({ user, children }) {
  return user ? children : <Navigate to="/login" replace />;
}
