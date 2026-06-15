import api from "./client";

export const authApi = {
  adminSignup: (data) => api.post("/auth/admin/signup", data),
  login: (data) => api.post("/auth/login", data),
  me: () => api.get("/auth/me"),
};