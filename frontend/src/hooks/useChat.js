import { useState, useCallback } from "react";
import { chatApi } from "../api/chat";

export function useChat() {
  const [sessions, setSessions]         = useState([]);
  const [activeSession, setActiveSession] = useState(null);
  const [messages, setMessages]         = useState([]);
  const [sending, setSending]           = useState(false);
  const [loading, setLoading]           = useState(false);
  const [error, setError]               = useState(null);

  const fetchSessions = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await chatApi.listSessions();
      setSessions(data.sessions || []);
    } catch (e) {
      setError("Failed to load sessions");
    } finally {
      setLoading(false);
    }
  }, []);

  const openSession = useCallback(async (sessionId) => {
    setLoading(true);
    try {
      const { data } = await chatApi.getSession(sessionId);
      setActiveSession(data.session);
      setMessages(data.messages || []);
    } catch (e) {
      setError("Failed to load session");
    } finally {
      setLoading(false);
    }
  }, []);

  const createSession = useCallback(async (documentId = null) => {
    try {
      const { data } = await chatApi.createSession({
        title:       "New Chat",
        document_id: documentId,
      });
      setSessions((prev) => [data, ...prev]);
      setActiveSession(data);
      setMessages([]);
      return data;
    } catch (e) {
      setError("Failed to create session");
    }
  }, []);

  const updateTitle = useCallback(async (sessionId, title) => {
    try {
      const { data } = await chatApi.updateTitle(sessionId, title);
      setSessions((prev) => prev.map((s) => s.id === sessionId ? data : s));
      if (activeSession?.id === sessionId) setActiveSession(data);
    } catch (e) {
      setError("Failed to update title");
    }
  }, [activeSession]);

  const deleteSession = useCallback(async (sessionId) => {
    try {
      await chatApi.deleteSession(sessionId);
      setSessions((prev) => prev.filter((s) => s.id !== sessionId));
      if (activeSession?.id === sessionId) {
        setActiveSession(null);
        setMessages([]);
      }
    } catch (e) {
      setError("Failed to delete session");
    }
  }, [activeSession]);

  // explicitSessionId bypasses the stale-closure problem when sendMessage is called
  // immediately after createSession (before React has re-rendered with the new activeSession).
  const sendMessage = useCallback(async (content, documentId = null, explicitSessionId = null) => {
    const sessionId = explicitSessionId ?? activeSession?.id;
    if (!sessionId || !content.trim()) return;
    setSending(true);

    // Optimistic user message
    const tempMsg = { id: Date.now(), role: "user", content, created_at: new Date().toISOString() };
    setMessages((prev) => [...prev, tempMsg]);

    try {
      const payload = { message: content };
      // Only include document_id when explicitly provided — omitting it lets the
      // backend fall back to the session's stored document_id.
      // Sending null explicitly means "no document / general chat".
      if (documentId !== undefined) payload.document_id = documentId;

      const { data } = await chatApi.sendMessage(sessionId, payload);

      // Replace optimistic message with confirmed one, then append assistant reply
      setMessages((prev) => [
        ...prev.filter((m) => m.id !== tempMsg.id),
        { ...tempMsg },
        data.message,
      ]);

      // Update session preview in sidebar
      setSessions((prev) =>
        prev.map((s) =>
          s.id === sessionId
            ? {
                ...s,
                message_count: (s.message_count || 0) + 2,
                last_message: data.message?.content?.slice(0, 100) ?? "",
              }
            : s
        )
      );

      return data;
    } catch (e) {
      setMessages((prev) => prev.filter((m) => m.id !== tempMsg.id));
      setError("Failed to send message");
    } finally {
      setSending(false);
    }
  }, [activeSession]);

  return {
    sessions, activeSession, messages, sending, loading, error, setError,
    fetchSessions, openSession, createSession, updateTitle, deleteSession, sendMessage,
  };
}