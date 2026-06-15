import { Navigate } from "react-router-dom";
import { getDashboardPath } from "../utils/auth";

export default function UserRoute({ user, children }) {
  if (!user) return <Navigate to="/login" replace />;
  if (user.role === "admin") return <Navigate to={getDashboardPath(user.role)} replace />;
  return children;
}
