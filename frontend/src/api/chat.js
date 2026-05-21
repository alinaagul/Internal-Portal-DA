import api from "./client";

export const chatApi = {
  // Sessions
  createSession:  (data)              => api.post("/chat/sessions", data),
  listSessions:   ()                  => api.get("/chat/sessions"),
  getSession:     (id)                => api.get(`/chat/sessions/${id}`),
  updateTitle:    (id, title)         => api.patch(`/chat/sessions/${id}/title`, { title }),
  deleteSession:  (id)                => api.delete(`/chat/sessions/${id}`),

  // Messages
  sendMessage:    (sessionId, data)   => api.post(`/chat/sessions/${sessionId}/message`, data),
};