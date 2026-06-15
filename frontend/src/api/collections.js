import api from "./client";

export const collectionsApi = {
  list: () => api.get("/collections"),
  get: (id) => api.get(`/collections/${id}`),
  create: (data) => api.post("/collections", data),
  update: (id, data) => api.patch(`/collections/${id}`, data),
  remove: (id) => api.delete(`/collections/${id}`),
  uploadDocuments: (id, files, onUploadProgress) => {
    const formData = new FormData();
    files.forEach((file) => formData.append("files", file));
    return api.post(`/collections/${id}/documents`, formData, {
      headers: { "Content-Type": "multipart/form-data" },
      onUploadProgress,
    });
  },
  removeDocument: (collectionId, documentId) =>
    api.delete(`/collections/${collectionId}/documents/${documentId}`),
  assignUsers: (id, userIds) => api.post(`/collections/${id}/assign`, { user_ids: userIds }),
  unassignUser: (id, userId) => api.delete(`/collections/${id}/assign/${userId}`),
};
