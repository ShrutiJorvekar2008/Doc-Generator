"""Deep structural analysis of a .docx: layout, styles, fonts, tables, images, headers/footers."""
import zipfile
from docx import Document
from docx.shared import Emu
from lxml import etree
from .common import NS, inches, rgb, read_theme, clip


def _run_fmt(run, par_style):
    f = run.font
    return {
        "font": f.name or (par_style.font.name if par_style is not None else None),
        "size_pt": f.size.pt if f.size else (par_style.font.size.pt if par_style is not None and par_style.font.size else None),
        "bold": f.bold, "italic": f.italic, "color": rgb(f.color),
    }


def _borders(tbl_el):
    b = tbl_el.find(".//w:tblPr/w:tblBorders", NS)
    if b is None:
        return None
    res = {}
    for side in b:
        res[etree.QName(side).localname] = {"val": side.get(f"{{{NS['w']}}}val"), "sz": side.get(f"{{{NS['w']}}}sz"),
                                            "color": side.get(f"{{{NS['w']}}}color")}
    return res


def _cell_shading(cell):
    shd = cell._tc.find(".//w:tcPr/w:shd", NS)
    return shd.get(f"{{{NS['w']}}}fill") if shd is not None else None


def _images_in(element, part, where):
    """Inline + anchored pictures with size and (for anchored) position."""
    imgs = []
    for kind in ("inline", "anchor"):
        for node in element.iterfind(f".//wp:{kind}", NS):
            ext = node.find("wp:extent", NS)
            blip = node.find(".//a:blip", NS)
            doc_pr = node.find("wp:docPr", NS)
            item = {"where": where, "placement": kind, "name": doc_pr.get("name") if doc_pr is not None else None,
                    "width_in": inches(ext.get("cx")) if ext is not None else None,
                    "height_in": inches(ext.get("cy")) if ext is not None else None}
            if blip is not None:
                rid = blip.get(f"{{{NS['r']}}}embed")
                try:
                    item["file"] = part.related_parts[rid].partname
                except Exception:
                    pass
            if kind == "anchor":
                ph, pv = node.find("wp:positionH", NS), node.find("wp:positionV", NS)
                for tag, el in (("x", ph), ("y", pv)):
                    if el is not None:
                        off = el.find("wp:posOffset", NS)
                        item[f"{tag}_in"] = inches(off.text) if off is not None else None
                        item[f"{tag}_relative_to"] = el.get("relativeFrom")
            imgs.append(item)
    return imgs


def analyze_docx(path: str) -> dict:
    doc = Document(path)
    styles_used = {}
    paragraphs, headings = [], []
    for i, p in enumerate(doc.paragraphs):
        st = p.style
        first = p.runs[0] if p.runs else None
        fmt = _run_fmt(first, st) if first is not None else {}
        paragraphs.append({"index": i, "style": st.name if st is not None else None, "text": clip(p.text, 100),
                           "align": str(p.alignment) if p.alignment is not None else None, **fmt})
        if st is not None and st.name.lower().startswith(("heading", "title")):
            headings.append({"index": i, "level": st.name, "text": clip(p.text, 80)})
        if st is not None and st.name not in styles_used:
            styles_used[st.name] = {"font": st.font.name, "size_pt": st.font.size.pt if st.font.size else None,
                                    "bold": st.font.bold, "color": rgb(st.font.color)}

    tables = []
    for ti, t in enumerate(doc.tables):
        header = t.rows[0].cells if t.rows else []
        tables.append({
            "index": ti, "rows": len(t.rows), "cols": len(t.columns),
            "style": t.style.name if t.style is not None else None,
            "borders": _borders(t._tbl) or (f"inherited from style '{t.style.name}'" if t.style is not None else None),
            "header_text": [clip(c.text, 30) for c in header],
            "header_shading": [_cell_shading(c) for c in header],
            "sample_row": [clip(c.text, 30) for c in t.rows[1].cells] if len(t.rows) > 1 else [],
        })

    sections, images = [], []
    for si, s in enumerate(doc.sections):
        hdr_imgs = _images_in(s.header._element, s.header.part, f"section{si}.header")
        ftr_imgs = _images_in(s.footer._element, s.footer.part, f"section{si}.footer")
        images += hdr_imgs + ftr_imgs
        sections.append({
            "index": si,
            "page_w_in": inches(s.page_width), "page_h_in": inches(s.page_height),
            "orientation": str(s.orientation),
            "margins_in": {"top": inches(s.top_margin), "bottom": inches(s.bottom_margin),
                           "left": inches(s.left_margin), "right": inches(s.right_margin)},
            "header_distance_in": inches(s.header_distance), "footer_distance_in": inches(s.footer_distance),
            "different_first_page": s.different_first_page_header_footer,
            "header_text": [clip(p.text) for p in s.header.paragraphs if p.text.strip()],
            "footer_text": [clip(p.text) for p in s.footer.paragraphs if p.text.strip()],
            "header_has_table": bool(s.header.tables), "header_images": len(hdr_imgs), "footer_images": len(ftr_imgs),
            "footer_has_page_number_field": "PAGE" in etree.tostring(s.footer._element).decode(),
        })
    images += _images_in(doc.element.body, doc.part, "body")

    return {
        "format": "docx",
        "theme": read_theme(path),
        "sections": sections,
        "styles_used": styles_used,
        "headings": headings,
        "paragraphs": paragraphs,
        "tables": tables,
        "images": images,
        "stats": {"paragraphs": len(paragraphs), "tables": len(tables), "images": len(images), "sections": len(sections)},
    }


def docx_text(path: str) -> str:
    d = Document(path)
    parts = [p.text for p in d.paragraphs if p.text.strip()]
    for t in d.tables:
        for r in t.rows:
            parts.append(" | ".join(c.text for c in r.cells))
    return "\n".join(parts)
