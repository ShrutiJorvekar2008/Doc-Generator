"""Format-preserving DOCX edits. The original file is opened and modified in place, so page
setup, headers/footers, logos, styles and theme are untouched; new content is cloned from
existing paragraphs/rows so it inherits their formatting."""
import copy
from docx import Document
from docx.text.paragraph import Paragraph
from .textutil import replace_in_paragraph, set_paragraph_text

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def _all_paragraphs(doc):
    for p in doc.paragraphs:
        yield p
    tables = list(doc.tables)
    for s in doc.sections:
        for part in (s.header, s.footer):
            yield from part.paragraphs
            tables += list(part.tables)
    for t in tables:
        for row in t.rows:
            for c in row.cells:
                yield from c.paragraphs


def _clone_par(ref: Paragraph):
    new = copy.deepcopy(ref._p)
    for r in new.findall(f"{W}r"):  # drop images / page breaks from the clone
        if r.find(f".//{W}drawing") is not None or r.find(f"{W}br") is not None:
            new.remove(r)
    for el in new.findall(f"{W}bookmarkStart") + new.findall(f"{W}bookmarkEnd"):
        new.remove(el)
    return new


def _set_cell(cell, text):
    pars = cell.paragraphs
    set_paragraph_text(pars[0], str(text))
    for extra in pars[1:]:
        extra._p.getparent().remove(extra._p)


def apply_docx(src, dst, ops, sources=None):
    doc = Document(src)
    pars = list(doc.paragraphs)       # snapshot: indices always refer to the analysed original
    tables = list(doc.tables)
    last_after = {}
    log = []
    for op in ops:
        name = op["op"]
        if name == "replace_text":
            n = sum(replace_in_paragraph(p, op["find"], op["replace"]) for p in _all_paragraphs(doc))
            log.append(f"replace_text '{op['find']}' → '{op['replace']}' ({n} place(s))")
        elif name == "set_paragraph":
            set_paragraph_text(pars[op["index"]], op["text"])
            log.append(f"set paragraph {op['index']}")
        elif name == "append_paragraph":
            nonempty = [i for i, p in enumerate(pars) if p.text.strip()]
            after = op.get("after_index", nonempty[-1] if nonempty else len(pars) - 1)
            like = op.get("like_index", after)
            new = _clone_par(pars[like])
            anchor = last_after.get(after, pars[after]._p)
            anchor.addnext(new)
            last_after[after] = new
            p = Paragraph(new, pars[like]._parent)
            set_paragraph_text(p, op["text"])
            if op.get("style") and op["style"] in [s.name for s in doc.styles]:
                p.style = doc.styles[op["style"]]
            log.append(f"append paragraph after {after} (formatted like {like})")
        elif name == "delete_paragraph":
            el = pars[op["index"]]._p
            el.getparent().remove(el)
            log.append(f"delete paragraph {op['index']}")
        elif name == "set_cell":
            _set_cell(tables[op["table_index"]].cell(op["row"], op["col"]), op["text"])
            log.append(f"set table {op['table_index']} cell ({op['row']},{op['col']})")
        elif name == "fill_table":
            t = tables[op["table_index"]]
            start = op.get("start_row", 1)
            rows = op["rows"]
            while len(t.rows) < start + len(rows):
                t._tbl.append(copy.deepcopy(t.rows[-1]._tr))
            for ri, data in enumerate(rows):
                for ci, val in enumerate(data[: len(t.columns)]):
                    _set_cell(t.rows[start + ri].cells[ci], val)
            if op.get("clear_extra", True):
                for extra in list(t.rows)[start + len(rows):]:
                    t._tbl.remove(extra._tr)
            log.append(f"fill table {op['table_index']} with {len(rows)} row(s)")
        else:
            raise ValueError(f"unknown docx op {name}")

    if sources:
        _append_sources(doc, sources)
        log.append(f"appended Sources section ({len(sources)} item(s))")
    doc.save(dst)
    return log


def _append_sources(doc, sources):
    pars = [p for p in doc.paragraphs]
    heading = next((p for p in pars if p.style is not None and p.style.name.lower().startswith("heading")), None)
    body = next((p for p in reversed(pars) if p.text.strip() and not (p.style.name.lower().startswith(("heading", "title")))), None)
    anchor = next((p for p in reversed(pars) if p.text.strip()), pars[-1])
    last = anchor._p
    if heading is not None:
        h = _clone_par(heading)
        last.addnext(h)
        set_paragraph_text(Paragraph(h, heading._parent), "Sources")
        last = h
    for s in sources:
        ref = body if body is not None else anchor
        n = _clone_par(ref)
        last.addnext(n)
        set_paragraph_text(Paragraph(n, ref._parent), f"[{s['id']}] {s['title']} — {s['ref']}")
        last = n
