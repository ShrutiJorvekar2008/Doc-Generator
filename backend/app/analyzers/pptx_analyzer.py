"""Deep analysis of a .pptx: slide size, masters, layouts, shapes, fonts, colours, pictures, tables."""
from pptx import Presentation
from pptx.util import Emu
from pptx.enum.shapes import MSO_SHAPE_TYPE
from .common import inches, rgb, read_theme, clip


def _fill(shape):
    try:
        if shape.fill.type == 1:  # solid
            return rgb(shape.fill.fore_color)
    except Exception:
        pass
    return None


def _font(shape):
    if not getattr(shape, "has_text_frame", False) or not shape.has_text_frame:
        return {}
    for p in shape.text_frame.paragraphs:
        for r in p.runs:
            f = r.font
            return {"font": f.name, "size_pt": f.size.pt if f.size else None, "bold": f.bold, "color": rgb(f.color)}
    return {}


def _shape(shape, idx):
    d = {"index": idx, "name": shape.name, "type": str(shape.shape_type).split(".")[-1].split(" ")[0] if shape.shape_type else "UNKNOWN",
         "x_in": inches(shape.left), "y_in": inches(shape.top), "w_in": inches(shape.width), "h_in": inches(shape.height)}
    if shape.is_placeholder:
        d["placeholder"] = str(shape.placeholder_format.type).split(".")[-1].split(" ")[0]
    if getattr(shape, "has_text_frame", False) and shape.has_text_frame:
        d["text"] = clip(shape.text_frame.text, 100)
        d.update(_font(shape))
    if shape.shape_type == MSO_SHAPE_TYPE.PICTURE:
        d["image"] = {"content_type": shape.image.content_type, "px": shape.image.size}
    if getattr(shape, "has_table", False) and shape.has_table:
        t = shape.table
        d["table"] = {"rows": len(t.rows), "cols": len(t.columns),
                      "header": [clip(c.text, 25) for c in t.rows[0].cells]}
    if getattr(shape, "has_chart", False) and shape.has_chart:
        d["chart"] = str(shape.chart.chart_type)
    f = _fill(shape)
    if f:
        d["fill"] = f
    return d


def analyze_pptx(path: str) -> dict:
    prs = Presentation(path)
    masters = []
    for mi, m in enumerate(prs.slide_masters):
        def _style(tag):
            d = m._element.find(f".//{{*}}{tag}/{{*}}lvl1pPr/{{*}}defRPr")
            if d is None:
                return None
            lat = d.find("{*}latin")
            clr = d.find("{*}solidFill/{*}*")
            return {"font": lat.get("typeface") if lat is not None else None, "size_pt": int(d.get("sz")) / 100 if d.get("sz") else None,
                    "color": clr.get("val") if clr is not None else None}
        masters.append({
            "index": mi, "title_style": _style("titleStyle"), "body_style": _style("bodyStyle"),
            "shapes": [_shape(s, i) for i, s in enumerate(m.shapes)],   # logos/footers living on the master
            "layouts": [{"index": li, "name": l.name,
                         "placeholders": [{"idx": p.placeholder_format.idx,
                                           "type": str(p.placeholder_format.type).split(".")[-1].split(" ")[0],
                                           "name": p.name} for p in l.placeholders],
                         "non_placeholder_shapes": [_shape(s, i) for i, s in enumerate(l.shapes) if not s.is_placeholder]}
                        for li, l in enumerate(m.slide_layouts)],
        })
    slides = []
    for si, s in enumerate(prs.slides):
        slides.append({
            "index": si, "layout": s.slide_layout.name,
            "shapes": [_shape(sh, i) for i, sh in enumerate(s.shapes)],
            "notes": clip(s.notes_slide.notes_text_frame.text, 120) if s.has_notes_slide else None,
        })
    return {
        "format": "pptx", "theme": read_theme(path),
        "slide_size_in": {"w": inches(prs.slide_width), "h": inches(prs.slide_height)},
        "masters": masters, "slides": slides,
        "stats": {"slides": len(slides), "masters": len(masters),
                  "layouts": sum(len(m["layouts"]) for m in masters),
                  "pictures": sum(1 for s in slides for sh in s["shapes"] if "image" in sh)},
    }


def pptx_text(path: str) -> str:
    prs = Presentation(path)
    out = []
    for i, s in enumerate(prs.slides, 1):
        out.append(f"Slide {i}:")
        for sh in s.shapes:
            if getattr(sh, "has_text_frame", False) and sh.has_text_frame and sh.text_frame.text.strip():
                out.append(sh.text_frame.text)
            if getattr(sh, "has_table", False) and sh.has_table:
                for r in sh.table.rows:
                    out.append(" | ".join(c.text for c in r.cells))
    return "\n".join(out)
