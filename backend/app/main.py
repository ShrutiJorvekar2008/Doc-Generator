"""FastAPI application: sessions, uploads, chat (LangGraph), artifact download/analysis."""
import re
import shutil
import uuid
from pathlib import Path
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Depends, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

from .config import settings, ROOT
from .db import init_db, SessionLocal, ChatSession, Message, Artifact
from .security import validate_upload, safe_name, OFFICE
from .analyzers import analyze, extract_text
from .graph import run_turn
from . import rag

MIME = {"docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "pdf": "application/pdf", "txt": "text/plain", "md": "text/markdown"}

from contextlib import asynccontextmanager


@asynccontextmanager
async def lifespan(_):
    init_db()
    yield


app = FastAPI(title="AI Chatbot & Document Generation Platform", version="1.0.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=settings.CORS_ORIGINS, allow_methods=["*"], allow_headers=["*"])


def auth(x_api_key: str = Header(default="")):
    if settings.API_KEY and x_api_key != settings.API_KEY:
        raise HTTPException(401, "Invalid API key")


def db():
    s = SessionLocal()
    try:
        yield s
    finally:
        s.close()


# ---------- serializers ----------
def art_json(a: Artifact, with_analysis=False):
    d = {"id": a.id, "name": a.name, "kind": a.kind, "role": a.role, "version": a.version, "parent_id": a.parent_id,
         "change_log": a.change_log or [], "created_at": a.created_at.isoformat(),
         "stats": (a.analysis or {}).get("stats")}
    if with_analysis:
        d["analysis"] = a.analysis
    return d


def msg_json(m: Message):
    return {"id": m.id, "role": m.role, "content": m.content, "sources": m.sources or [], "artifact_id": m.artifact_id,
            "created_at": m.created_at.isoformat()}


def get_session(s, sid) -> ChatSession:
    cs = s.get(ChatSession, sid)
    if not cs:
        raise HTTPException(404, "Session not found")
    return cs


_FILLER_LEAD = re.compile(r"^(please\s+|can\s+you\s+|could\s+you\s+|i\s+want\s+|i\s+need\s+|let'?s\s+)+", re.I)
_LEADING_VERB = re.compile(
    r"^(create|make|generate|build|write|produce|draft|prepare|give\s+me|put\s+together)\s+(me\s+)?(a\s+|an\s+|the\s+)?",
    re.I,
)
_LEADING_ARTICLE = re.compile(r"^(a\s+|an\s+|the\s+|new\s+)+", re.I)
_SLUG_STOP = {
    "a", "an", "the", "my", "our", "your", "their",
    "presentation", "deck", "slide", "slides", "document", "doc", "docs", "report",
    "spreadsheet", "workbook", "sheet", "file", "about", "on", "regarding", "for",
    "with", "of", "to", "in", "and", "or", "that", "this", "please", "new", "some",
    "titled", "called",
}


def slug_from_prompt(text: str, max_words: int = 4) -> str:
    """Turn a user instruction into a filename-friendly base, e.g.
    'create a presentation about renewable energy' -> 'renewable_energy'."""
    t = _FILLER_LEAD.sub("", (text or "").strip())
    t = _LEADING_VERB.sub("", t)
    t = _LEADING_ARTICLE.sub("", t)
    tokens = re.findall(r"[A-Za-z0-9]+", t.lower())
    meaningful = [w for w in tokens if w not in _SLUG_STOP and not w.isdigit()]
    chosen = (meaningful or tokens)[:max_words]
    return "_".join(chosen) or "generated"


# ---------- routes ----------
@app.get("/api/health")
def health():
    return {"status": "ok", "llm": settings.LLM_PROVIDER, "vector_store": "pinecone" if settings.PINECONE_API_KEY else "memory",
            "database": settings.DATABASE_URL.split(":")[0]}


@app.post("/api/sessions", dependencies=[Depends(auth)])
def create_session(s=Depends(db)):
    cs = ChatSession()
    s.add(cs); s.commit()
    return {"id": cs.id, "title": cs.title}


@app.get("/api/sessions", dependencies=[Depends(auth)])
def list_sessions(s=Depends(db)):
    rows = s.query(ChatSession).order_by(ChatSession.created_at.desc()).limit(100).all()
    return [{"id": r.id, "title": r.title, "created_at": r.created_at.isoformat()} for r in rows]


@app.get("/api/sessions/{sid}", dependencies=[Depends(auth)])
def get_session_detail(sid: str, s=Depends(db)):
    cs = get_session(s, sid)
    return {"id": cs.id, "title": cs.title, "messages": [msg_json(m) for m in cs.messages],
            "artifacts": [art_json(a) for a in cs.artifacts]}


@app.delete("/api/sessions/{sid}", dependencies=[Depends(auth)])
def delete_session(sid: str, s=Depends(db)):
    cs = get_session(s, sid)
    s.delete(cs); s.commit()
    shutil.rmtree(settings.STORAGE_DIR / sid, ignore_errors=True)
    rag.get_store().delete_ns(sid)
    return {"deleted": sid}


@app.post("/api/sessions/{sid}/files", dependencies=[Depends(auth)])
async def upload(sid: str, file: UploadFile = File(...), role: str = Form("auto"), s=Depends(db)):
    cs = get_session(s, sid)
    data = await file.read(settings.MAX_UPLOAD_MB * 1024 * 1024 + 1)
    ext = validate_upload(file.filename, data)
    name = safe_name(file.filename)
    folder = settings.STORAGE_DIR / sid
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{uuid.uuid4().hex}.{ext}"          # never trust the client's file name on disk
    path.write_bytes(data)
    role = role if role in ("template", "reference") else ("template" if ext in OFFICE else "reference")
    try:
        analysis = await run_in_threadpool(analyze, str(path), ext) if ext in OFFICE else None
        text = await run_in_threadpool(extract_text, str(path), ext)
    except Exception as e:
        path.unlink(missing_ok=True)
        raise HTTPException(422, f"Could not read this file: {type(e).__name__}: {e}")
    a = Artifact(session_id=sid, name=name, kind=ext, role=role, path=str(path), analysis=analysis)
    s.add(a); s.commit()
    chunks = await run_in_threadpool(rag.ingest, sid, a.id, name, text)   # file attachments feed RAG
    if cs.title == "New chat":
        cs.title = name[:60]; s.commit()
    return {**art_json(a, with_analysis=True), "rag_chunks": chunks}


class ChatIn(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    artifact_id: str | None = None


@app.post("/api/sessions/{sid}/chat", dependencies=[Depends(auth)])
async def chat(sid: str, body: ChatIn, s=Depends(db)):
    cs = get_session(s, sid)
    active = s.get(Artifact, body.artifact_id) if body.artifact_id else None
    if body.artifact_id and (not active or active.session_id != sid):
        raise HTTPException(404, "Artifact not found in this session")
    if not active:
        office = [a for a in cs.artifacts if a.kind in OFFICE]
        active = office[-1] if office else None
    history = [{"role": m.role, "content": m.content} for m in cs.messages[-8:]]
    s.add(Message(session_id=sid, role="user", content=body.message)); s.commit()

    state = {"session_id": sid, "message": body.message, "history": history,
             "artifact": {"id": active.id, "name": active.name, "kind": active.kind, "path": active.path, "analysis": active.analysis} if active else None}
    try:
        out = await run_in_threadpool(run_turn, state)
    except Exception as e:
        err = f"Sorry, something went wrong while processing that: {type(e).__name__}: {str(e)[:300]}"
        m = Message(session_id=sid, role="assistant", content=err); s.add(m); s.commit()
        return {"message": msg_json(m), "artifact": None, "error": True}

    new_art = None
    nf = out.get("new_file")
    if nf:
        parent = active
        if out.get("started_from_starter") and parent is None:
            # No template was attached: the first output is v1, named from the user's prompt.
            base = slug_from_prompt(body.message)
            version = 1
            parent_id = None
        else:
            base = Path(parent.name).stem.split(" (v")[0]
            version = parent.version + 1
            parent_id = parent.id
        name = f"{base}.{nf['kind']}" if version == 1 else f"{base} (v{version}).{nf['kind']}"
        new_art = Artifact(session_id=sid, name=name, kind=nf["kind"], role="output",
                           version=version, parent_id=parent_id, path=nf["path"],
                           analysis=nf["analysis"], change_log=nf["log"])
        s.add(new_art); s.commit()
        await run_in_threadpool(rag.ingest, sid, new_art.id, new_art.name, extract_text(nf["path"], nf["kind"]))
    m = Message(session_id=sid, role="assistant", content=out.get("reply", ""), sources=out.get("cited") or [],
                artifact_id=new_art.id if new_art else None)
    s.add(m)
    if cs.title == "New chat":
        cs.title = body.message[:60]
    s.commit()
    return {"message": msg_json(m), "artifact": art_json(new_art) if new_art else None, "fidelity": (nf or {}).get("fidelity")}


@app.get("/api/artifacts/{aid}/download", dependencies=[Depends(auth)])
def download(aid: str, s=Depends(db)):
    a = s.get(Artifact, aid)
    if not a or not Path(a.path).is_file():
        raise HTTPException(404, "File not found")
    return FileResponse(a.path, media_type=MIME.get(a.kind, "application/octet-stream"), filename=safe_name(a.name))


@app.get("/api/artifacts/{aid}/analysis", dependencies=[Depends(auth)])
def get_analysis(aid: str, s=Depends(db)):
    a = s.get(Artifact, aid)
    if not a:
        raise HTTPException(404, "Artifact not found")
    return art_json(a, with_analysis=True)


# optional: serve the built React app from the same container
_dist = ROOT / "frontend" / "dist"
if _dist.is_dir():
    app.mount("/", StaticFiles(directory=_dist, html=True), name="ui")
