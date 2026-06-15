import api from "./client";

export const usersApi = {
  list: () => api.get("/users"),
  create: (data) => api.post("/users", data),
  updateStatus: (userId, isActive) => api.patch(`/users/${userId}`, { is_active: isActive }),
};
