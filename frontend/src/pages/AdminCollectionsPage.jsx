import { useEffect, useRef, useState } from "react";
import { usersApi } from "../api/users";
import { useCollections } from "../hooks/useCollections";

const formatDate = (iso) => {
  if (!iso) return "—";
  return new Date(iso).toLocaleString([], { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
};

const STATUS_COLORS = {
  ready: "#15803d",
  failed: "#b91c1c",
  uploaded: "#b45309",
  processing: "#1d4ed8",
  ocr_processing: "#1d4ed8",
  chunking: "#1d4ed8",
  embedding: "#1d4ed8",
};

export default function AdminCollectionsPage() {
  const {
    collections, selected, loading, detailLoading, uploading, error, setError,
    fetchCollections, fetchCollectionDetail, createCollection,
    uploadToCollection, assignUsers, unassignUser, removeDocument,
    startPolling, stopPolling,
  } = useCollections();

  const [users, setUsers] = useState([]);
  const [createForm, setCreateForm] = useState({ name: "", description: "" });
  const [creating, setCreating] = useState(false);
  const [selectedUserIds, setSelectedUserIds] = useState([]);
  const [assigning, setAssigning] = useState(false);
  const fileInputRef = useRef(null);

  useEffect(() => {
    fetchCollections();
    usersApi.list().then(({ data }) => setUsers(data.filter((u) => u.role === "user" && u.is_active)));
    return () => stopPolling();
  }, []);

  useEffect(() => {
    if (selected?.id) {
      const assigned = new Set((selected.assigned_users || []).map((u) => u.id));
      setSelectedUserIds(Array.from(assigned));
      const hasProcessing = (selected.documents || []).some(
        (d) => !["ready", "failed"].includes(d.status)
      );
      if (hasProcessing) startPolling(selected.id);
      else stopPolling();
    }
  }, [selected?.id, selected?.documents?.length]);

  const handleCreate = async (e) => {
    e.preventDefault();
    setCreating(true);
    const result = await createCollection(createForm);
    if (result.success) {
      setCreateForm({ name: "", description: "" });
      fetchCollectionDetail(result.collection.id);
    }
    setCreating(false);
  };

  const handleSelect = (id) => {
    stopPolling();
    fetchCollectionDetail(id);
  };

  const handleUpload = async (e) => {
    const files = Array.from(e.target.files || []);
    if (!files.length || !selected?.id) return;
    await uploadToCollection(selected.id, files);
    startPolling(selected.id);
    e.target.value = "";
  };

  const handleAssign = async () => {
    if (!selected?.id) return;
    setAssigning(true);
    const current = new Set((selected.assigned_users || []).map((u) => u.id));
    const toAdd = selectedUserIds.filter((id) => !current.has(id));
    const toRemove = [...current].filter((id) => !selectedUserIds.includes(id));

    if (toAdd.length) await assignUsers(selected.id, toAdd);
    for (const uid of toRemove) await unassignUser(selected.id, uid);

    setAssigning(false);
  };

  const toggleUser = (id) => {
    setSelectedUserIds((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]
    );
  };

  return (
    <div style={s.page}>
      <div style={s.pageHeader}>
        <div>
          <h1 style={s.pageTitle}>Collections</h1>
          <p style={s.pageSubtitle}>
            Create collections, upload documents, and assign them to users.
          </p>
        </div>
      </div>

      <div style={s.content}>
        {error && <div style={s.errorBox}>{error} <button style={s.errorClose} onClick={() => setError(null)}>✕</button></div>}

        <div style={s.grid}>
          {/* Left: collections list + create */}
          <div style={s.panel}>
            <div style={s.panelTitle}>Your Collections</div>
            {loading ? (
              <p style={s.muted}>Loading…</p>
            ) : collections.length === 0 ? (
              <p style={s.muted}>No collections yet. Create one below.</p>
            ) : (
              <div style={s.list}>
                {collections.map((c) => (
                  <button
                    key={c.id}
                    style={{ ...s.listItem, ...(selected?.id === c.id ? s.listItemActive : {}) }}
                    onClick={() => handleSelect(c.id)}
                  >
                    <div style={s.listItemName}>{c.name}</div>
                    <div style={s.listItemMeta}>
                      {c.document_count} docs · {c.assigned_user_count} users
                    </div>
                    <div style={s.listItemUpdated}>Updated {formatDate(c.updated_at)}</div>
                  </button>
                ))}
              </div>
            )}

            <form onSubmit={handleCreate} style={s.createForm}>
              <div style={s.panelTitle}>New Collection</div>
              <input
                style={s.input}
                placeholder="Collection name"
                value={createForm.name}
                onChange={(e) => setCreateForm((f) => ({ ...f, name: e.target.value }))}
                required
              />
              <textarea
                style={{ ...s.input, minHeight: "60px", resize: "vertical" }}
                placeholder="Description (optional)"
                value={createForm.description}
                onChange={(e) => setCreateForm((f) => ({ ...f, description: e.target.value }))}
              />
              <button type="submit" style={s.btn} disabled={creating}>
                {creating ? "Creating…" : "Create collection"}
              </button>
            </form>
          </div>

          {/* Right: collection detail */}
          <div style={s.panel}>
            {!selected ? (
              <div style={s.emptyDetail}>
                <p style={s.muted}>Select a collection to manage documents and user access.</p>
              </div>
            ) : detailLoading ? (
              <p style={s.muted}>Loading collection…</p>
            ) : (
              <>
                <div style={s.detailHeader}>
                  <div>
                    <h2 style={s.detailTitle}>{selected.name}</h2>
                    {selected.description && <p style={s.detailDesc}>{selected.description}</p>}
                    <p style={s.detailMeta}>Last updated {formatDate(selected.updated_at)}</p>
                  </div>
                  <button style={s.uploadBtn} onClick={() => fileInputRef.current?.click()} disabled={uploading}>
                    {uploading ? "Uploading…" : "Upload documents"}
                  </button>
                  <input
                    ref={fileInputRef}
                    type="file"
                    accept=".pdf,.png,.jpg,.jpeg,.tiff"
                    multiple
                    style={{ display: "none" }}
                    onChange={handleUpload}
                  />
                </div>

                <div style={s.section}>
                  <div style={s.sectionTitle}>Documents ({selected.documents?.length || 0})</div>
                  {(selected.documents || []).length === 0 ? (
                    <p style={s.muted}>No documents yet. Upload PDFs or images.</p>
                  ) : (
                    <div style={s.docList}>
                      {selected.documents.map((doc) => (
                        <div key={doc.id} style={s.docRow}>
                          <div style={{ flex: 1, minWidth: 0 }}>
                            <div style={s.docName}>{doc.filename}</div>
                            <div style={s.docMeta}>
                              <span style={{ color: STATUS_COLORS[doc.status] || "#64748b" }}>
                                {doc.status}
                              </span>
                              {" · "}{formatDate(doc.created_at)}
                            </div>
                          </div>
                          <button
                            style={s.removeBtn}
                            onClick={async () => {
                              if (window.confirm(`Remove "${doc.filename}"?`)) {
                                await removeDocument(selected.id, doc.id);
                              }
                            }}
                          >
                            Remove
                          </button>
                        </div>
                      ))}
                    </div>
                  )}
                </div>

                <div style={s.section}>
                  <div style={s.sectionTitle}>Assign to Users</div>
                  <p style={s.sectionSub}>
                    Selected users will see this collection and all its documents. Updates sync automatically.
                  </p>
                  {users.length === 0 ? (
                    <p style={s.muted}>Create user accounts first from the Admin Dashboard.</p>
                  ) : (
                    <>
                      <div style={s.userChecks}>
                        {users.map((u) => (
                          <label key={u.id} style={s.userCheck}>
                            <input
                              type="checkbox"
                              checked={selectedUserIds.includes(u.id)}
                              onChange={() => toggleUser(u.id)}
                            />
                            <span>{u.full_name}</span>
                            <span style={s.userEmail}>{u.email}</span>
                          </label>
                        ))}
                      </div>
                      <button style={s.btn} onClick={handleAssign} disabled={assigning}>
                        {assigning ? "Saving…" : "Save assignments"}
                      </button>
                      {(selected.assigned_users || []).length > 0 && (
                        <div style={s.assignedList}>
                          <div style={s.assignedTitle}>Currently assigned:</div>
                          {selected.assigned_users.map((u) => (
                            <span key={u.id} style={s.assignedChip}>{u.full_name}</span>
                          ))}
                        </div>
                      )}
                    </>
                  )}
                </div>
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

const s = {
  page: { display: "flex", flexDirection: "column", height: "100%", background: "#f8fafc", overflow: "hidden" },
  pageHeader: { padding: "24px 28px 16px", background: "#fff", borderBottom: "1px solid #e2e8f0" },
  pageTitle: { color: "#0f172a", fontSize: "20px", fontWeight: "700", margin: 0 },
  pageSubtitle: { color: "#64748b", fontSize: "13px", margin: "3px 0 0" },
  content: { flex: 1, overflowY: "auto", padding: "24px 28px" },
  grid: { display: "grid", gridTemplateColumns: "320px 1fr", gap: "16px", alignItems: "start" },
  panel: { background: "#fff", border: "1px solid #e2e8f0", borderRadius: "12px", padding: "20px" },
  panelTitle: { color: "#374151", fontSize: "12px", fontWeight: "700", textTransform: "uppercase", letterSpacing: "0.6px", marginBottom: "12px" },
  list: { display: "flex", flexDirection: "column", gap: "6px", marginBottom: "20px" },
  listItem: { textAlign: "left", background: "#f8fafc", border: "1px solid #e2e8f0", borderRadius: "8px", padding: "12px", cursor: "pointer", fontFamily: "inherit" },
  listItemActive: { background: "#eff6ff", borderColor: "#93c5fd" },
  listItemName: { color: "#0f172a", fontSize: "14px", fontWeight: "600" },
  listItemMeta: { color: "#64748b", fontSize: "12px", marginTop: "2px" },
  listItemUpdated: { color: "#94a3b8", fontSize: "11px", marginTop: "4px" },
  createForm: { display: "flex", flexDirection: "column", gap: "10px", borderTop: "1px solid #f1f5f9", paddingTop: "16px" },
  input: { border: "1px solid #d1d5db", borderRadius: "8px", padding: "9px 12px", fontSize: "13px", fontFamily: "inherit" },
  btn: { background: "#2563eb", color: "#fff", border: "none", borderRadius: "8px", padding: "10px", fontSize: "13px", fontWeight: "600", cursor: "pointer", fontFamily: "inherit" },
  emptyDetail: { padding: "40px 20px", textAlign: "center" },
  detailHeader: { display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: "16px", marginBottom: "20px" },
  detailTitle: { color: "#0f172a", fontSize: "18px", fontWeight: "700", margin: 0 },
  detailDesc: { color: "#64748b", fontSize: "13px", margin: "6px 0 0" },
  detailMeta: { color: "#94a3b8", fontSize: "12px", margin: "6px 0 0" },
  uploadBtn: { background: "#2563eb", color: "#fff", border: "none", borderRadius: "8px", padding: "10px 16px", fontSize: "13px", fontWeight: "600", cursor: "pointer", fontFamily: "inherit", flexShrink: 0 },
  section: { borderTop: "1px solid #f1f5f9", paddingTop: "16px", marginTop: "8px" },
  sectionTitle: { color: "#374151", fontSize: "12px", fontWeight: "700", textTransform: "uppercase", letterSpacing: "0.6px", marginBottom: "8px" },
  sectionSub: { color: "#64748b", fontSize: "13px", margin: "0 0 12px" },
  docList: { display: "flex", flexDirection: "column", gap: "8px" },
  docRow: { display: "flex", alignItems: "center", gap: "12px", padding: "10px 12px", background: "#f8fafc", borderRadius: "8px", border: "1px solid #e2e8f0" },
  docName: { color: "#0f172a", fontSize: "13px", fontWeight: "600", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" },
  docMeta: { color: "#64748b", fontSize: "11px", marginTop: "2px" },
  removeBtn: { background: "transparent", border: "1px solid #fecaca", color: "#b91c1c", borderRadius: "6px", padding: "5px 10px", fontSize: "11px", cursor: "pointer", fontFamily: "inherit" },
  userChecks: { display: "flex", flexDirection: "column", gap: "8px", marginBottom: "12px", maxHeight: "200px", overflowY: "auto" },
  userCheck: { display: "flex", alignItems: "center", gap: "8px", fontSize: "13px", color: "#0f172a", cursor: "pointer" },
  userEmail: { color: "#94a3b8", fontSize: "11px", marginLeft: "auto" },
  assignedList: { marginTop: "12px" },
  assignedTitle: { color: "#64748b", fontSize: "12px", marginBottom: "6px" },
  assignedChip: { display: "inline-block", background: "#eff6ff", color: "#1d4ed8", borderRadius: "20px", padding: "4px 10px", fontSize: "11px", marginRight: "6px", marginBottom: "6px" },
  errorBox: { background: "#fef2f2", border: "1px solid #fecaca", borderRadius: "8px", padding: "10px 12px", color: "#dc2626", fontSize: "13px", marginBottom: "16px", display: "flex", justifyContent: "space-between" },
  errorClose: { background: "none", border: "none", cursor: "pointer", color: "#dc2626" },
  muted: { color: "#94a3b8", fontSize: "13px" },
};
