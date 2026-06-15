import { useState, useCallback, useRef } from "react";
import { collectionsApi } from "../api/collections";

const normalizeDoc = (d) => ({ ...d, id: d.id ?? d.document_id });

export function useCollections() {
  const [collections, setCollections] = useState([]);
  const [selected, setSelected] = useState(null);
  const [loading, setLoading] = useState(false);
  const [detailLoading, setDetailLoading] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState(null);
  const pollingRef = useRef(null);

  const fetchCollections = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const { data } = await collectionsApi.list();
      setCollections(data.collections || []);
    } catch (err) {
      setError(err.response?.data?.detail || "Failed to load collections");
    } finally {
      setLoading(false);
    }
  }, []);

  const fetchCollectionDetail = useCallback(async (id) => {
    if (!id) return;
    setDetailLoading(true);
    setError(null);
    try {
      const { data } = await collectionsApi.get(id);
      setSelected({
        ...data,
        documents: (data.documents || []).map(normalizeDoc),
      });
    } catch (err) {
      setError(err.response?.data?.detail || "Failed to load collection");
    } finally {
      setDetailLoading(false);
    }
  }, []);

  const createCollection = useCallback(async (payload) => {
    setError(null);
    try {
      const { data } = await collectionsApi.create(payload);
      await fetchCollections();
      return { success: true, collection: data };
    } catch (err) {
      const msg = err.response?.data?.detail || "Failed to create collection";
      setError(msg);
      return { success: false, error: msg };
    }
  }, [fetchCollections]);

  const uploadToCollection = useCallback(async (collectionId, files) => {
    setUploading(true);
    setError(null);
    try {
      const { data } = await collectionsApi.uploadDocuments(collectionId, files);
      await fetchCollectionDetail(collectionId);
      await fetchCollections();
      return { success: true, ...data };
    } catch (err) {
      const msg = err.response?.data?.detail || "Upload failed";
      setError(msg);
      return { success: false, error: msg };
    } finally {
      setUploading(false);
    }
  }, [fetchCollectionDetail, fetchCollections]);

  const assignUsers = useCallback(async (collectionId, userIds) => {
    setError(null);
    try {
      const { data } = await collectionsApi.assignUsers(collectionId, userIds);
      setSelected({
        ...data,
        documents: (data.documents || []).map(normalizeDoc),
      });
      await fetchCollections();
      return { success: true };
    } catch (err) {
      const msg = err.response?.data?.detail || "Failed to assign users";
      setError(msg);
      return { success: false, error: msg };
    }
  }, [fetchCollections]);

  const unassignUser = useCallback(async (collectionId, userId) => {
    setError(null);
    try {
      const { data } = await collectionsApi.unassignUser(collectionId, userId);
      setSelected({
        ...data,
        documents: (data.documents || []).map(normalizeDoc),
      });
      await fetchCollections();
      return { success: true };
    } catch (err) {
      const msg = err.response?.data?.detail || "Failed to remove user";
      setError(msg);
      return { success: false, error: msg };
    }
  }, [fetchCollections]);

  const removeDocument = useCallback(async (collectionId, documentId) => {
    try {
      await collectionsApi.removeDocument(collectionId, documentId);
      await fetchCollectionDetail(collectionId);
      await fetchCollections();
      return { success: true };
    } catch (err) {
      return { success: false, error: err.response?.data?.detail };
    }
  }, [fetchCollectionDetail, fetchCollections]);

  const startPolling = useCallback((collectionId) => {
    if (pollingRef.current) clearInterval(pollingRef.current);
    pollingRef.current = setInterval(async () => {
      try {
        const { data } = await collectionsApi.get(collectionId);
        const docs = (data.documents || []).map(normalizeDoc);
        const hasProcessing = docs.some(
          (d) => d.status === "uploaded" || d.status === "processing" ||
            ["ocr_processing", "chunking", "embedding"].includes(d.status)
        );
        setSelected((prev) =>
          prev?.id === collectionId ? { ...data, documents: docs } : prev
        );
        if (!hasProcessing && pollingRef.current) {
          clearInterval(pollingRef.current);
          pollingRef.current = null;
        }
      } catch {
        if (pollingRef.current) {
          clearInterval(pollingRef.current);
          pollingRef.current = null;
        }
      }
    }, 3000);
  }, []);

  const stopPolling = useCallback(() => {
    if (pollingRef.current) {
      clearInterval(pollingRef.current);
      pollingRef.current = null;
    }
  }, []);

  return {
    collections,
    selected,
    loading,
    detailLoading,
    uploading,
    error,
    setError,
    setSelected,
    fetchCollections,
    fetchCollectionDetail,
    createCollection,
    uploadToCollection,
    assignUsers,
    unassignUser,
    removeDocument,
    startPolling,
    stopPolling,
  };
}

export function useUserCollections() {
  const [collections, setCollections] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const pollingRef = useRef(null);

  const fetchCollections = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const { data } = await collectionsApi.list();
      const items = data.collections || [];
      const detailed = await Promise.all(
        items.map(async (c) => {
          const res = await collectionsApi.get(c.id);
          return {
            ...res.data,
            documents: (res.data.documents || []).map(normalizeDoc),
          };
        })
      );
      setCollections(detailed);
    } catch (err) {
      setError(err.response?.data?.detail || "Failed to load collections");
    } finally {
      setLoading(false);
    }
  }, []);

  const startPolling = useCallback(() => {
    if (pollingRef.current) clearInterval(pollingRef.current);
    pollingRef.current = setInterval(() => fetchCollections(), 5000);
  }, [fetchCollections]);

  const stopPolling = useCallback(() => {
    if (pollingRef.current) {
      clearInterval(pollingRef.current);
      pollingRef.current = null;
    }
  }, []);

  return {
    collections,
    loading,
    error,
    fetchCollections,
    startPolling,
    stopPolling,
  };
}
