export function getDashboardPath(role) {
  return role === "admin" ? "/admin/dashboard" : "/dashboard";
}

export function isAdmin(user) {
  return user?.role === "admin";
}
