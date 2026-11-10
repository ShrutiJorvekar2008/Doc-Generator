"""LangGraph workflow:  document understanding → request understanding → target preparation →
research (web + RAG) → content generation → validation (retry loop) → file build + fidelity check → response."""
import json
import re
import shutil
import uuid
from pathlib import Path
from typing import TypedDict, Optional
from langgraph.graph import StateGraph, START, END

from .analyzers import analyze
from .config import settings, ROOT
from .editors import apply_ops, validate_ops, check_fidelity, OPS
from .llm import get_llm, extract_json
from .research import web_search
from . import rag

STARTERS = {"docx": "acme_report_template.docx", "pptx": "acme_deck_template.pptx", "xlsx": "acme_sales_template.xlsx"}
MAX_ATTEMPTS = 3

OPS_DOC = {
    "docx": """Allowed ops (indices refer to the ORIGINAL paragraph/table numbering shown in the analysis):
- {"op":"replace_text","find":"old","replace":"new"}                      (body, tables, headers, footers)
- {"op":"set_paragraph","index":3,"text":"new text"}
- {"op":"append_paragraph","after_index":7,"like_index":5,"text":"...","style":"Heading 1"(optional)}   like_index = existing paragraph whose formatting is cloned
- {"op":"delete_paragraph","index":4}
- {"op":"set_cell","table_index":0,"row":1,"col":2,"text":"..."}
- {"op":"fill_table","table_index":0,"rows":[["a","b","c"],...],"start_row":1}   rows after the header; extra rows clone the last row's formatting""",
    "pptx": """Allowed ops (slide/shape indices are 0-based and refer to the ORIGINAL deck in the analysis):
- {"op":"replace_text","find":"old","replace":"new","slide":2(optional)}
- {"op":"set_text","slide":1,"shape":0,"paragraphs":["line 1","line 2"]}
- {"op":"add_slide","layout":"Title and Content","title":"...","bullets":["...","..."],"notes":"(optional)","after_slide":1(optional)}   uses the deck's own layouts/master
- {"op":"duplicate_slide","source":1,"texts":{"0":"new title","1":["bullet","bullet"]},"after_slide":1(optional)}   copies an existing slide incl. pictures
- {"op":"delete_slide","slide":3}
- {"op":"set_notes","slide":1,"text":"..."}
- {"op":"set_table_cell","slide":2,"shape":1,"row":1,"col":1,"text":"..."} / {"op":"fill_table","slide":2,"shape":1,"rows":[[...]]}""",
    "xlsx": """Allowed ops:
- {"op":"set_cell","sheet":"Sales","cell":"E6","value":123}            (strings starting with "=" are formulas)
- {"op":"append_row","sheet":"Sales","values":["2026-09-01","Hooli","Platform","Won",9900,"Ana"]}   copies the previous data row's styles; use {row} inside formulas
- {"op":"set_range","sheet":"Sales","start":"A10","rows":[[...],[...]]}
- {"op":"add_sheet","name":"Q4","copy_from":"Sales","rows":[[...]]}   clones formatting of an existing sheet""",
}

SYSTEM_GENERATE = """You are the content engine of an enterprise document-editing assistant.
You never rewrite files directly. You return ONLY a JSON object: {"reply": "<short message to the user>", "ops": [ ... ]}.
Rules:
1. Preserve the template: reuse existing paragraphs/slides/rows as formatting models; never invent fonts, colours or layouts.
2. Use only indices, sheet names and table numbers that appear in the analysis.
3. When facts come from the SOURCES block, cite them inline as [S1], [S2] in the text you write, and in the reply. Never invent facts or sources.
4. If the user only asks a question, return "ops": [] and answer in "reply" (cite sources with [S#]).
5. Keep text concise and professional; match the template's tone and length.
6. Output valid JSON only, no markdown fences."""


class State(TypedDict, total=False):
    session_id: str
    message: str
    history: list
    artifact: Optional[dict]     # {id, name, kind, path, analysis}
    intent: str
    target_kind: Optional[str]
    queries: list
    use_rag: bool
    sources: list
    ops: list
    reply: str
    errors: list
    attempts: int
    new_file: Optional[dict]
    started_from_starter: bool
    cited: list


# ---------- helpers ----------
def compact(a: dict, limit: int = 9000) -> str:
    f = a["format"]
    if f == "docx":
        d = {"sections": [{k: s[k] for k in ("page_w_in", "page_h_in", "margins_in", "header_text", "footer_text", "header_images")} for s in a["sections"]],
             "theme_fonts": [a["theme"]["major_font"], a["theme"]["minor_font"]], "styles": a["styles_used"],
             "paragraphs": [f'{p["index"]}|{p["style"]}|{p["text"][:70]}' for p in a["paragraphs"]],
             "tables": a["tables"], "images": [{k: i.get(k) for k in ("where", "width_in", "height_in")} for i in a["images"]]}
    elif f == "pptx":
        d = {"slide_size_in": a["slide_size_in"], "layouts": [l["name"] for l in a["masters"][0]["layouts"]],
             "master_title_style": a["masters"][0].get("title_style"), "master_body_style": a["masters"][0].get("body_style"),
             "master_shapes": [s["name"] for s in a["masters"][0]["shapes"] if "placeholder" not in s],
             "slides": [{"index": s["index"], "layout": s["layout"],
                         "shapes": [f'{sh["index"]}|{sh["name"]}|{sh.get("placeholder") or sh["type"]}|{sh.get("text", "")[:60]}' for sh in s["shapes"]]} for s in a["slides"]]}
    else:
        d = {"sheets": [{"name": s["name"], "dimensions": s["dimensions"], "header_row": s["header_row"], "freeze_panes": s["freeze_panes"],
                         "columns": [c["header"] for c in s["columns"]], "preview_rows": s["preview_rows"], "formulas": s["formulas"],
                         "merged": s["merged"]} for s in a["sheets"]]}
    out = json.dumps(d, ensure_ascii=False, default=str)
    return out if len(out) <= limit else out[:limit] + " …(truncated)"


def _history_text(h, n=6):
    return "\n".join(f'{m["role"]}: {m["content"][:300]}' for m in (h or [])[-n:])


# ---------- nodes ----------
def document_understanding(s: State):
    a = s.get("artifact")
    if a and not a.get("analysis"):
        a["analysis"] = analyze(a["path"], a["kind"])
    return {"artifact": a}


def understand(s: State):
    a = s.get("artifact")
    kind = a["kind"] if a else None
    ctx = {"message": s["message"], "kind": kind, "has_rag": True}
    system = ('Classify the user request for a document assistant. Return ONLY JSON: '
              '{"intent":"chat"|"edit","target_kind":"docx"|"pptx"|"xlsx"|null,"research_queries":[up to 3 short web queries if '
              'fresh external facts are needed, else []],"use_rag":true|false}. '
              '"edit" = the user wants a document created or changed. "chat" = questions/discussion.')
    user = f'Active file: {kind or "none"}\nRecent chat:\n{_history_text(s.get("history"))}\n\nUser request: {s["message"]}'
    try:
        r = extract_json(get_llm().complete(system, user, "understand", ctx))
    except Exception:
        r = {"intent": "chat"}
    return {"intent": r.get("intent", "chat") if r.get("intent") in ("chat", "edit") else "chat",
            "target_kind": r.get("target_kind") if r.get("target_kind") in ("docx", "pptx", "xlsx") else kind,
            "queries": [q for q in (r.get("research_queries") or []) if isinstance(q, str)][:3],
            "use_rag": bool(r.get("use_rag", True)), "attempts": 0, "errors": []}


def prepare_target(s: State):
    """Create-from-scratch: when no file is attached, start from the built-in branded starter template."""
    if s["intent"] != "edit" or s.get("artifact"):
        return {}
    kind = s.get("target_kind")
    if kind not in STARTERS:
        return {"intent": "chat", "reply": "Which format should I create — Word (.docx), PowerPoint (.pptx) or Excel (.xlsx)? You can also upload a template."}
    src = ROOT / "samples" / "templates" / STARTERS[kind]
    dst_dir = settings.STORAGE_DIR / s["session_id"]
    dst_dir.mkdir(parents=True, exist_ok=True)
    dst = dst_dir / f"{uuid.uuid4().hex}.{kind}"
    shutil.copy(src, dst)
    art = {"id": None, "name": STARTERS[kind], "kind": kind, "path": str(dst), "analysis": analyze(str(dst), kind), "starter": True}
    return {"artifact": art, "started_from_starter": True}


def research(s: State):
    sources, n = [], 1
    for q in s.get("queries", []):
        for r in web_search(q):
            sources.append({"id": f"S{n}", "type": "web", "title": r["title"][:120], "ref": r["url"], "snippet": r["snippet"][:400]}); n += 1
    if s.get("use_rag"):
        for h in rag.retrieve(s["session_id"], s["message"], 4):
            sources.append({"id": f"S{n}", "type": "document", "title": h["file"], "ref": f'{h["file"]} · chunk {h["chunk"]}', "snippet": h["text"][:400]}); n += 1
    return {"sources": sources}


def generate(s: State):
    a = s.get("artifact")
    llm = get_llm()
    src_txt = "\n".join(f'[{x["id"]}] ({x["type"]}) {x["title"]} — {x["snippet"]}' for x in s.get("sources", [])) or "(none)"
    parts = [f"USER REQUEST: {s['message']}", f"RECENT CHAT:\n{_history_text(s.get('history'))}", f"SOURCES:\n{src_txt}"]
    if a:
        parts += [f'TEMPLATE FORMAT: {a["kind"]}', OPS_DOC[a["kind"]], f"TEMPLATE ANALYSIS (compact):\n{compact(a['analysis'])}"]
    if s.get("errors"):
        parts.append("YOUR PREVIOUS PLAN WAS REJECTED. Fix these problems:\n" + "\n".join(s["errors"]))
    ctx = {"message": s["message"], "kind": a["kind"] if a else None, "analysis": a["analysis"] if a else None,
           "sources": s.get("sources", []), "intent": s["intent"]}
    raw = llm.complete(SYSTEM_GENERATE, "\n\n".join(parts), "generate", ctx)
    try:
        r = extract_json(raw)
        return {"reply": str(r.get("reply", "")), "ops": r.get("ops") or [], "errors": [], "attempts": s.get("attempts", 0) + 1}
    except Exception as e:
        return {"errors": [f"Output was not valid JSON ({e}). Return only the JSON object."], "ops": [], "attempts": s.get("attempts", 0) + 1}


def validate(s: State):
    if s.get("errors"):
        return {}
    errs = validate_ops(s["artifact"]["kind"], s.get("ops", []), s["artifact"]["analysis"]) if s["intent"] == "edit" else []
    if s["intent"] == "edit" and not s.get("ops") and not errs:
        return {}  # nothing to change; reply explains why
    return {"errors": errs}


def build(s: State):
    ops = s.get("ops") or []
    if not ops:
        return {}
    a = s["artifact"]
    blob = json.dumps(ops) + s.get("reply", "")
    cited = sorted({int(n) for n in re.findall(r"\[S(\d+)\]", blob)})
    used = [x for x in s.get("sources", []) if int(x["id"][1:]) in cited]
    out_dir = settings.STORAGE_DIR / s["session_id"]
    out_dir.mkdir(parents=True, exist_ok=True)
    dst = out_dir / f'{uuid.uuid4().hex}.{a["kind"]}'
    try:
        log = apply_ops(a["kind"], a["path"], str(dst), ops, used or None)
    except Exception as e:
        return {"errors": [f"Could not apply changes: {type(e).__name__}: {e}"], "ops": []}
    fid = check_fidelity(a["path"], str(dst), a["kind"])
    return {"new_file": {"path": str(dst), "kind": a["kind"], "log": log, "fidelity": fid, "analysis": analyze(str(dst), a["kind"])},
            "cited": used}


def respond(s: State):
    if s.get("errors") and not s.get("new_file"):
        return {"reply": "I couldn't produce a valid change for that request after several attempts:\n- " + "\n- ".join(s["errors"][:5])
                         + "\nTry rephrasing or being more specific (e.g. mention the slide/paragraph/sheet)."}
    reply = s.get("reply") or "Done."
    nf = s.get("new_file")
    if nf:
        reply += "\n\nChanges applied: " + "; ".join(nf["log"]) + "."
        reply += "\nFormat check: " + ("original layout, fonts and design preserved ✔" if nf["fidelity"]["passed"] else
                                         "⚠ " + "; ".join(nf["fidelity"]["issues"][:3]))
    if s.get("started_from_starter"):
        reply = "(No template was attached, so I started from the built-in Acme starter template.)\n" + reply
    if not nf and s.get("sources") and not s.get("cited"):
        cited = sorted({int(n) for n in re.findall(r"\[S(\d+)\]", reply)})
        return {"reply": reply, "cited": [x for x in s["sources"] if int(x["id"][1:]) in cited]}
    return {"reply": reply}


# ---------- wiring ----------
def _after_prepare(s):  # research only when asked for / documents exist
    return "research" if (s.get("queries") or s.get("use_rag")) else "generate"


def _after_generate(s):
    return "validate" if s["intent"] == "edit" or s.get("errors") else "respond"


def _after_validate(s):
    if s.get("errors") and s.get("attempts", 0) < MAX_ATTEMPTS:
        return "generate"
    return "respond" if s.get("errors") or not s.get("ops") else "build"


def build_graph():
    g = StateGraph(State)
    for name, fn in [("document_understanding", document_understanding), ("understand", understand), ("prepare_target", prepare_target),
                     ("research", research), ("generate", generate), ("validate", validate), ("build", build), ("respond", respond)]:
        g.add_node(name, fn)
    g.add_edge(START, "document_understanding")
    g.add_edge("document_understanding", "understand")
    g.add_edge("understand", "prepare_target")
    g.add_conditional_edges("prepare_target", lambda s: "respond" if s.get("reply") and s["intent"] == "chat" and not s.get("artifact") and "Which format" in s["reply"] else _after_prepare(s),
                            {"research": "research", "generate": "generate", "respond": "respond"})
    g.add_edge("research", "generate")
    g.add_conditional_edges("generate", _after_generate, {"validate": "validate", "respond": "respond"})
    g.add_conditional_edges("validate", _after_validate, {"generate": "generate", "respond": "respond", "build": "build"})
    g.add_conditional_edges("build", lambda s: "respond", {"respond": "respond"})
    g.add_edge("respond", END)
    return g.compile()


_graph = None


def run_turn(state: dict) -> dict:
    global _graph
    if _graph is None:
        _graph = build_graph()
    return _graph.invoke(state)
