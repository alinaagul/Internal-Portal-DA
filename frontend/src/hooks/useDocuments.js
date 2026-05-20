import { useState, useCallback, useRef } from "react";
import { documentsApi } from "../api/documents";

export function useDocuments() {
  const [documents, setDocuments]   = useState([]);
  const [uploading, setUploading]   = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [loading, setLoading]       = useState(false);
  const [error, setError]           = useState(null);
  const pollingRefs = useRef({});   // track active polling intervals

  // Fetch all documents
  const fetchDocuments = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await documentsApi.list();
      setDocuments(data.documents || []);
    } catch (err) {
      setError(err.response?.data?.detail || "Failed to load documents");
    } finally {
      setLoading(false);
    }
  }, []);

  // Upload a file
  const uploadDocument = useCallback(async (file) => {
    setUploading(true);
    setUploadProgress(0);
    setError(null);
    try {
      const { data } = await documentsApi.upload(file, (evt) => {
        const pct = Math.round((evt.loaded / evt.total) * 100);
        setUploadProgress(pct);
      });

      // Add to list immediately with "uploaded" status
      setDocuments((prev) => [data, ...prev]);

      // Start polling for status updates
      _startPolling(data.id);

      return { success: true, document: data };
    } catch (err) {
      const msg = err.response?.data?.detail || "Upload failed";
      setError(msg);
      return { success: false, error: msg };
    } finally {
      setUploading(false);
      setUploadProgress(0);
    }
  }, []);

  // Delete a document
  const deleteDocument = useCallback(async (id) => {
    try {
      await documentsApi.delete(id);
      _stopPolling(id);
      setDocuments((prev) => prev.filter((d) => d.id !== id));
      return { success: true };
    } catch (err) {
      return { success: false, error: err.response?.data?.detail };
    }
  }, []);

  // Poll status until document is "ready" or "failed"
  const _startPolling = (documentId) => {
    if (pollingRefs.current[documentId]) return;

    const interval = setInterval(async () => {
      try {
        const { data } = await documentsApi.getStatus(documentId);
        setDocuments((prev) =>
          prev.map((d) => (d.id === documentId ? { ...d, ...data } : d))
        );
        if (data.status === "ready" || data.status === "failed") {
          _stopPolling(documentId);
        }
      } catch {
        _stopPolling(documentId);
      }
    }, 3000); // poll every 3 seconds

    pollingRefs.current[documentId] = interval;
  };

  const _stopPolling = (documentId) => {
    if (pollingRefs.current[documentId]) {
      clearInterval(pollingRefs.current[documentId]);
      delete pollingRefs.current[documentId];
    }
  };

  return {
    documents,
    uploading,
    uploadProgress,
    loading,
    error,
    setError,
    fetchDocuments,
    uploadDocument,
    deleteDocument,
  };
}