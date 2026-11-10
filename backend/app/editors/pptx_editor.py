"""Format-preserving PPTX edits: text keeps run formatting, new slides come from the deck's own
layouts (so master logos/backgrounds/fonts carry over), duplicated slides keep pictures."""
import copy
from pptx import Presentation
from pptx.enum.shapes import PP_PLACEHOLDER
from .textutil import replace_in_paragraph

R = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
TITLES = (PP_PLACEHOLDER.TITLE, PP_PLACEHOLDER.CENTER_TITLE)
SKIP = (PP_PLACEHOLDER.DATE, PP_PLACEHOLDER.FOOTER, PP_PLACEHOLDER.SLIDE_NUMBER)


def _set_tf(tf, lines):
    lines = [lines] if isinstance(lines, str) else list(lines)
    paras = tf.paragraphs
    first = paras[0]
    runs = first.runs
    if runs:
        runs[0].text = lines[0]
        for r in runs[1:]:
            r._r.getparent().remove(r._r)
    else:
        first.add_run().text = lines[0]
    template = copy.deepcopy(first._p)
    for p in paras[1:]:
        p._p.getparent().remove(p._p)
    for line in lines[1:]:
        n = copy.deepcopy(template)
        tf._txBody.append(n)
        from pptx.text.text import _Paragraph
        para = _Paragraph(n, tf)
        para.runs[0].text = line


def _fill_slide(slide, title=None, bullets=None):
    body_done = False
    for ph in list(slide.placeholders):
        t = ph.placeholder_format.type
        if t in SKIP:
            continue
        if t in TITLES and title is not None:
            _set_tf(ph.text_frame, title)
        elif t not in TITLES and bullets and not body_done and ph.has_text_frame:
            _set_tf(ph.text_frame, bullets)
            body_done = True
        elif not ph.text_frame.text.strip() if ph.has_text_frame else False:
            ph._element.getparent().remove(ph._element)  # no empty "Click to add text" boxes


def _layout(prs, key):
    layouts = list(prs.slide_layouts)
    if isinstance(key, int) and 0 <= key < len(layouts):
        return layouts[key]
    for l in layouts:
        if isinstance(key, str) and l.name.lower() == key.lower():
            return l
    for l in layouts:
        if l.name.lower() in ("title and content", "title and body"):
            return l
    return layouts[1] if len(layouts) > 1 else layouts[0]


def _move_last(prs, pos):
    lst = prs.slides._sldIdLst
    el = list(lst)[-1]
    lst.remove(el)
    lst.insert(pos, el)


def _duplicate(prs, src):
    new = prs.slides.add_slide(src.slide_layout)
    for sh in list(new.shapes):
        sh._element.getparent().remove(sh._element)
    for sh in src.shapes:
        new.shapes._spTree.append(copy.deepcopy(sh._element))
    rmap = {}
    for rid, rel in src.part.rels.items():
        if rel.reltype.endswith(("/slideLayout", "/notesSlide")):
            continue
        rmap[rid] = (new.part.relate_to(rel.target_ref, rel.reltype, is_external=True) if rel.is_external
                     else new.part.relate_to(rel.target_part, rel.reltype))
    for el in new.shapes._spTree.iter():
        for k, v in list(el.attrib.items()):
            if k.startswith(R) and v in rmap:
                el.set(k, rmap[v])
    return new


def _tables(slide):
    return [s for s in slide.shapes if getattr(s, "has_table", False) and s.has_table]


def apply_pptx(src, dst, ops, sources=None):
    prs = Presentation(src)
    slides = list(prs.slides)          # snapshot of original numbering
    sld_ids = list(prs.slides._sldIdLst)
    log, deletions = [], []
    for op in ops:
        name = op["op"]
        if name == "replace_text":
            n = 0
            targets = [slides[op["slide"]]] if "slide" in op else slides
            for s in targets:
                for sh in s.shapes:
                    frames = [sh.text_frame] if getattr(sh, "has_text_frame", False) and sh.has_text_frame else []
                    if getattr(sh, "has_table", False) and sh.has_table:
                        frames += [c.text_frame for r in sh.table.rows for c in r.cells]
                    for tf in frames:
                        n += sum(replace_in_paragraph(p, op["find"], op["replace"]) for p in tf.paragraphs)
            log.append(f"replace_text '{op['find']}' → '{op['replace']}' ({n} place(s))")
        elif name == "set_text":
            sh = slides[op["slide"]].shapes[op["shape"]]
            _set_tf(sh.text_frame, op.get("paragraphs") or op["text"])
            log.append(f"set text on slide {op['slide']} shape {op['shape']}")
        elif name == "add_slide":
            s = prs.slides.add_slide(_layout(prs, op.get("layout")))
            _fill_slide(s, op.get("title"), op.get("bullets") or ([op["body"]] if op.get("body") else None))
            if op.get("notes"):
                s.notes_slide.notes_text_frame.text = op["notes"]
            if "after_slide" in op:
                _move_last(prs, op["after_slide"] + 1)
            log.append(f"add slide '{op.get('title','')}' (layout '{s.slide_layout.name}')")
        elif name == "duplicate_slide":
            new = _duplicate(prs, slides[op["source"]])
            for idx, val in (op.get("texts") or {}).items():
                _set_tf(new.shapes[int(idx)].text_frame, val)
            if "after_slide" in op:
                _move_last(prs, op["after_slide"] + 1)
            log.append(f"duplicate slide {op['source']}")
        elif name == "delete_slide":
            deletions.append(op["slide"])  # applied last: dropping a part early makes new slide part names collide
            log.append(f"delete slide {op['slide']}")
        elif name == "set_notes":
            slides[op["slide"]].notes_slide.notes_text_frame.text = op["text"]
            log.append(f"set notes on slide {op['slide']}")
        elif name in ("set_table_cell", "fill_table"):
            tbl = slides[op["slide"]].shapes[op["shape"]].table
            if name == "set_table_cell":
                _set_tf(tbl.cell(op["row"], op["col"]).text_frame, str(op["text"]))
            else:
                start = op.get("start_row", 1)
                while len(tbl.rows) < start + len(op["rows"]):
                    tbl._tbl.append(copy.deepcopy(tbl._tbl.tr_lst[-1]))
                for ri, data in enumerate(op["rows"]):
                    for ci, val in enumerate(data[: len(tbl.columns)]):
                        _set_tf(tbl.cell(start + ri, ci).text_frame, str(val))
            log.append(f"{name} on slide {op['slide']}")
        else:
            raise ValueError(f"unknown pptx op {name}")

    if sources:
        s = prs.slides.add_slide(_layout(prs, None))
        _fill_slide(s, "Sources", [f"[{x['id']}] {x['title']} — {x['ref']}" for x in sources][:8])
        log.append(f"added Sources slide ({len(sources)} item(s))")
    for i in sorted(set(deletions), reverse=True):
        sid = sld_ids[i]
        prs.part.drop_rel(sid.rId)
        prs.slides._sldIdLst.remove(sid)
    prs.save(dst)
    return log
