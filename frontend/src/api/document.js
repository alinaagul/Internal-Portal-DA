import api from "./client";

export const documentsApi = {
  // Upload a PDF file
  upload: (file, onUploadProgress) => {
    const formData = new FormData();
    formData.append("file", file);
    return api.post("/documents/upload", formData, {
      headers: { "Content-Type": "multipart/form-data" },
      onUploadProgress,
    });
  },

  // List all documents for current user
  list: () => api.get("/documents/"),

  // Get processing status of a document
  getStatus: (id) => api.get(`/documents/${id}/status`),

  // Get all chunks of a document
  getChunks: (id) => api.get(`/documents/${id}/chunks`),

  // Delete a document
  delete: (id) => api.delete(`/documents/${id}`),
};