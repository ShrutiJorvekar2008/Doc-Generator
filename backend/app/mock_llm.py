"""Deterministic offline 'LLM' used for tests, CI and demos without API keys (LLM_PROVIDER=mock).
It understands a handful of plain-English commands and emits the same JSON the real model would."""
import json
import re

Q = r"""["'“”‘’]?"""


def _kind_from_text(t: str):
    t = t.lower()
    if any(w in t for w in ("ppt", "slide", "deck", "presentation")): return "pptx"
    if any(w in t for w in ("excel", "xlsx", "spreadsheet", "sheet")): return "xlsx"
    if any(w in t for w in ("docx", "word", "report", "document", "memo")): return "docx"
    return None


def mock_complete(stage: str, ctx: dict) -> str:
    msg, kind = ctx.get("message", ""), ctx.get("kind")
    low = msg.lower()
    if stage == "understand":
        verbs = ("replace", "add", "append", "set ", "change", "update", "create", "generate", "make", "delete", "remove", "write")
        edit = any(low.startswith(v) or f" {v}" in low[:40] for v in verbs)
        q = re.findall(r"research (?:on |about )?(.+?)(?:[.;]|$)", msg, flags=re.I)
        return json.dumps({"intent": "edit" if edit else "chat", "target_kind": kind or _kind_from_text(msg),
                           "research_queries": q[:1], "use_rag": bool(ctx.get("has_rag"))})
    # stage == generate
    kind = kind or _kind_from_text(msg)
    srcs = ctx.get("sources") or []
    cite = f" [{srcs[0]['id']}]" if srcs else ""
    ops, reply = [], ""
    m = re.search(rf"replace {Q}(.+?){Q} with {Q}(.+?){Q}\s*$", msg.strip(), flags=re.I)
    if m:
        ops.append({"op": "replace_text", "find": m.group(1), "replace": m.group(2)})
    m = re.search(r"(?:create|generate|make|write) (?:a |an )?(?:new )?(?:presentation|deck|report|document|memo)(?: \w+)? (?:about|on) (.+?)[.]?$", msg.strip(), flags=re.I)
    if m and kind in ("pptx", "docx"):
        topic = m.group(1).strip().rstrip(".").title()
        if kind == "pptx":
            ops += [{"op": "replace_text", "find": "Acme Corp Product Roadmap", "replace": topic},
                    {"op": "replace_text", "find": "Strategy briefing · 2026", "replace": "Generated overview"},
                    {"op": "set_text", "slide": 1, "shape": 0, "text": "Overview"},
                    {"op": "set_text", "slide": 1, "shape": 1, "paragraphs": [f"Why {topic} matters{cite}", "Key opportunities", "Main risks"]}]
        else:
            ops += [{"op": "replace_text", "find": "Quarterly Business Report", "replace": topic},
                    {"op": "replace_text", "find": "Acme Corp delivered steady growth in Q3 2026. Revenue increased 12% year over year, driven by strong demand in the enterprise segment.",
                     "replace": f"This document gives an overview of {topic}.{cite}"}]
    if kind == "pptx":
        m = re.search(r"add (?:a )?slide (?:titled|called|about|on) (.+?)(?: with (.+))?$", msg.strip().rstrip("."), flags=re.I)
        if m:
            bullets = [b.strip() for b in re.split(r",| and ", m.group(2) or "") if b.strip()] or ["Key point one", "Key point two"]
            ops.append({"op": "add_slide", "title": m.group(1).strip(), "bullets": [b + cite if i == 0 else b for i, b in enumerate(bullets)]})
    elif kind == "docx":
        m = re.search(r"(?:add|append) (?:a )?(heading|paragraph)(?: titled (.+?))?: (.+)$", msg.strip(), flags=re.I)
        if m:
            a = ctx.get("analysis") or {}
            hs = [h["index"] for h in a.get("headings", []) if h["level"].lower().startswith("heading")]
            body = [p["index"] for p in a.get("paragraphs", []) if p["style"] in ("Normal", "Body Text") and p["text"]]
            last = max(i for i in range(a["stats"]["paragraphs"]) if a["paragraphs"][i]["text"])
            if m.group(1).lower() == "heading" and hs:
                ops.append({"op": "append_paragraph", "after_index": last, "like_index": hs[0], "text": m.group(3)})
            else:
                if m.group(2) and hs:
                    ops.append({"op": "append_paragraph", "after_index": last, "like_index": hs[0], "text": m.group(2)})
                ops.append({"op": "append_paragraph", "after_index": last, "like_index": body[-1] if body else last, "text": m.group(3) + cite})
    elif kind == "xlsx":
        a = ctx.get("analysis") or {}
        sheet = a["sheets"][0]["name"] if a.get("sheets") else "Sheet1"
        m = re.search(r"add (?:a )?row:? (.+)$", msg.strip(), flags=re.I)
        if m:
            vals = [int(v) if v.strip().isdigit() else (float(v) if re.fullmatch(r"-?\d+\.\d+", v.strip()) else v.strip()) for v in m.group(1).split(",")]
            ops.append({"op": "append_row", "sheet": sheet, "values": vals})
        m = re.search(r"set ([A-Z]+\d+) to (.+)$", msg.strip(), flags=re.I)
        if m:
            ops.append({"op": "set_cell", "sheet": sheet, "cell": m.group(1).upper(), "value": m.group(2).strip()})
    if ops:
        reply = f"Done — applied {len(ops)} change(s) while keeping the template's formatting."
    else:
        reply = ("(mock model) I can't edit anything for that request yet. Try: replace \"A\" with \"B\", "
                 "add slide about X with a, b, c, add row: ..., or add paragraph: ...") if ctx.get("intent") == "edit" else \
                f"(mock model) You said: {msg}" + (f" — related context: {srcs[0]['snippet'][:120]} [{srcs[0]['id']}]" if srcs else "")
    return json.dumps({"reply": reply, "ops": ops})
