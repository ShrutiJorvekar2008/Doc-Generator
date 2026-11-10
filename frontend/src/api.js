const BASE = import.meta.env.VITE_API_URL || "";
const KEY = import.meta.env.VITE_API_KEY || "";
const headers = (extra = {}) => (KEY ? { "X-API-Key": KEY, ...extra } : extra);

async function req(path, opts = {}) {
  const res = await fetch(BASE + path, { ...opts, headers: headers(opts.headers) });
  if (!res.ok) {
    let detail = res.statusText;
    try { detail = (await res.json()).detail || detail; } catch { /* ignore */ }
    throw new Error(detail);
  }
  return res.json();
}

export const api = {
  health: () => req("/api/health"),
  sessions: () => req("/api/sessions"),
  newSession: () => req("/api/sessions", { method: "POST" }),
  session: (id) => req(`/api/sessions/${id}`),
  deleteSession: (id) => req(`/api/sessions/${id}`, { method: "DELETE" }),
  upload: (id, file) => {
    const fd = new FormData();
    fd.append("file", file);
    return req(`/api/sessions/${id}/files`, { method: "POST", body: fd });
  },
  chat: (id, message, artifact_id) =>
    req(`/api/sessions/${id}/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message, artifact_id }),
    }),
  analysis: (aid) => req(`/api/artifacts/${aid}/analysis`),
  // downloads need the API key too, so fetch as a blob
  download: async (a) => {
    const res = await fetch(`${BASE}/api/artifacts/${a.id}/download`, { headers: headers() });
    if (!res.ok) throw new Error("Download failed");
    const url = URL.createObjectURL(await res.blob());
    const el = document.createElement("a");
    el.href = url; el.download = a.name; el.click();
    URL.revokeObjectURL(url);
  },
};
