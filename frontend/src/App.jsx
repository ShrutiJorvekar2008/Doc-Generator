import React, { useEffect, useRef, useState } from "react";
import { api } from "./api.js";

const ICON = { docx: "📄", pptx: "📊", xlsx: "📈", pdf: "📕", txt: "📝", md: "📝" };

function Sources({ items }) {
  if (!items?.length) return null;
  return (
    <div className="sources">
      {items.map((s) => (
        <span key={s.id} className="chip" title={s.snippet}>
          [{s.id}] {s.type === "web" ? <a href={s.ref} target="_blank" rel="noreferrer">{s.title || s.ref}</a> : s.ref}
        </span>
      ))}
    </div>
  );
}

function AnalysisModal({ data, onClose }) {
  if (!data) return null;
  return (
    <div className="modal" onClick={onClose}>
      <div className="modal-box" onClick={(e) => e.stopPropagation()}>
        <div className="modal-head"><b>Template analysis — {data.name}</b><button onClick={onClose}>✕</button></div>
        <pre>{JSON.stringify(data.analysis, null, 2)}</pre>
      </div>
    </div>
  );
}

export default function App() {
  const [sessions, setSessions] = useState([]);
  const [sid, setSid] = useState(null);
  const [messages, setMessages] = useState([]);
  const [artifacts, setArtifacts] = useState([]);
  const [active, setActive] = useState(null);   // artifact id used as the edit target
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [modal, setModal] = useState(null);
  const [health, setHealth] = useState(null);
  const endRef = useRef(null);
  const fileRef = useRef(null);

  const refreshSessions = () => api.sessions().then(setSessions).catch((e) => setErr(e.message));
  const load = async (id) => {
    const d = await api.session(id);
    setSid(id); setMessages(d.messages); setArtifacts(d.artifacts);
    const office = d.artifacts.filter((a) => ["docx", "pptx", "xlsx"].includes(a.kind));
    setActive(office.length ? office[office.length - 1].id : null);
  };
  useEffect(() => { refreshSessions(); api.health().then(setHealth).catch(() => {}); }, []);
  useEffect(() => { endRef.current?.scrollIntoView({ behavior: "smooth" }); }, [messages, busy]);

  const newChat = async () => {
    const s = await api.newSession();
    await refreshSessions(); await load(s.id);
  };
  const ensureSession = async () => sid || (await api.newSession()).id;

  const send = async () => {
    const text = input.trim();
    if (!text || busy) return;
    setErr(""); setBusy(true); setInput("");
    try {
      const id = await ensureSession();
      if (!sid) setSid(id);
      setMessages((m) => [...m, { role: "user", content: text }]);
      const r = await api.chat(id, text, active);
      setMessages((m) => [...m, r.message]);
      if (r.artifact) { setArtifacts((a) => [...a, r.artifact]); setActive(r.artifact.id); }
      refreshSessions();
    } catch (e) { setErr(e.message); } finally { setBusy(false); }
  };

  const onFile = async (e) => {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;
    setErr(""); setBusy(true);
    try {
      const id = await ensureSession();
      if (!sid) setSid(id);
      const a = await api.upload(id, file);
      setArtifacts((x) => [...x, a]);
      if (["docx", "pptx", "xlsx"].includes(a.kind)) setActive(a.id);
      setMessages((m) => [...m, { role: "assistant", content: `Uploaded ${a.name} and analysed its structure (${JSON.stringify(a.stats || {})}). Tell me what to change or generate — I'll keep the original design.`, sources: [] }]);
      refreshSessions();
    } catch (e2) { setErr(e2.message); } finally { setBusy(false); }
  };

  const del = async (id) => {
    await api.deleteSession(id);
    if (id === sid) { setSid(null); setMessages([]); setArtifacts([]); setActive(null); }
    refreshSessions();
  };

  return (
    <div className="app">
      <aside className="side">
        <h1>DocGen</h1>
        <button className="primary" onClick={newChat}>＋ New chat</button>
        <div className="list">
          {sessions.map((s) => (
            <div key={s.id} className={"item" + (s.id === sid ? " on" : "")} onClick={() => load(s.id)}>
              <span>{s.title}</span><i onClick={(e) => { e.stopPropagation(); del(s.id); }}>🗑</i>
            </div>
          ))}
        </div>
        {health && <small className="muted">LLM: {health.llm} · vectors: {health.vector_store} · db: {health.database}</small>}
      </aside>

      <main className="chat">
        <div className="msgs">
          {!messages.length && (
            <div className="empty">
              <h2>Chat with your documents</h2>
              <p>Attach a Word, PowerPoint or Excel template, then ask for edits or new content. Or just ask: <i>“create a presentation about renewable energy”</i>.</p>
            </div>
          )}
          {messages.map((m, i) => (
            <div key={i} className={"msg " + m.role}>
              <div className="bubble">{m.content.split("\n").map((l, j) => <div key={j}>{l}</div>)}<Sources items={m.sources} />
                {m.artifact_id && artifacts.find((a) => a.id === m.artifact_id) &&
                  <button className="dl" onClick={() => api.download(artifacts.find((a) => a.id === m.artifact_id))}>⬇ {artifacts.find((a) => a.id === m.artifact_id).name}</button>}
              </div>
            </div>
          ))}
          {busy && <div className="msg assistant"><div className="bubble typing">Working… (analysing → researching → generating → validating)</div></div>}
          <div ref={endRef} />
        </div>
        {err && <div className="err">⚠ {err}</div>}
        <div className="composer">
          <input ref={fileRef} type="file" hidden accept=".docx,.pptx,.xlsx,.pdf,.txt,.md" onChange={onFile} />
          <button title="Attach file" onClick={() => fileRef.current.click()}>📎</button>
          <textarea value={input} placeholder="e.g. Add a slide about risks with supply delays, hiring…" rows={2}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); } }} />
          <button className="primary" disabled={busy} onClick={send}>Send</button>
        </div>
      </main>

      <aside className="files">
        <h3>Files &amp; versions</h3>
        {!artifacts.length && <p className="muted">No files yet.</p>}
        {artifacts.map((a) => {
          const editable = ["docx", "pptx", "xlsx"].includes(a.kind);
          return (
            <div key={a.id} className={"file" + (a.id === active ? " on" : "")}>
              <div>{ICON[a.kind]} <b>{a.name}</b></div>
              <small className="muted">{a.role} · v{a.version}</small>
              {a.change_log?.length > 0 && <details><summary>changes</summary><ul>{a.change_log.map((c, i) => <li key={i}>{c}</li>)}</ul></details>}
              <div className="row">
                <button onClick={() => api.download(a)}>Download</button>
                {editable && <button onClick={() => api.analysis(a.id).then(setModal)}>Analysis</button>}
                {editable && <button onClick={() => setActive(a.id)} disabled={a.id === active}>{a.id === active ? "Editing" : "Edit this"}</button>}
              </div>
            </div>
          );
        })}
      </aside>
      <AnalysisModal data={modal} onClose={() => setModal(null)} />
    </div>
  );
}
