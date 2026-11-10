"""Deep analysis of an .xlsx: sheets, widths, merged cells, styles, number formats, images, charts, print setup."""
from openpyxl import load_workbook
from openpyxl.utils import get_column_letter
from .common import clip, read_theme


def _color(c):
    try:
        if c is None:
            return None
        if c.type == "rgb":
            return c.rgb if isinstance(c.rgb, str) else None
        if c.type == "theme":
            return f"theme:{c.theme}"
    except Exception:
        pass
    return None


def _cell_style(c):
    b = c.border
    return {"font": c.font.name, "size": c.font.sz, "bold": c.font.b, "italic": c.font.i, "font_color": _color(c.font.color),
            "fill": _color(c.fill.fgColor) if c.fill and c.fill.fill_type else None,
            "number_format": c.number_format, "align": c.alignment.horizontal, "wrap": c.alignment.wrap_text,
            "border": {s: getattr(b, s).style for s in ("left", "right", "top", "bottom") if getattr(b, s) and getattr(b, s).style}}


def analyze_xlsx(path: str) -> dict:
    wb = load_workbook(path)  # keep formulas
    sheets = []
    for ws in wb.worksheets:
        counts = {r: sum(1 for c in range(1, ws.max_column + 1) if ws.cell(r, c).value not in (None, ""))
                  for r in range(1, min(ws.max_row, 15) + 1)}
        header_row = max(counts, key=lambda r: (counts[r], -r)) if counts and max(counts.values()) else 1  # densest early row
        cols = []
        for c in range(1, ws.max_column + 1):
            L = get_column_letter(c)
            cols.append({"col": L, "width": ws.column_dimensions[L].width if L in ws.column_dimensions else None,
                         "header": clip(str(ws.cell(header_row, c).value or ""), 30),
                         "header_style": _cell_style(ws.cell(header_row, c)),
                         "sample_style": _cell_style(ws.cell(min(header_row + 1, ws.max_row), c))})
        images = []
        for im in getattr(ws, "_images", []):
            a = im.anchor
            m = getattr(a, "_from", None)
            images.append({"anchor": f"{get_column_letter(m.col + 1)}{m.row + 1}" if m else None,
                           "w_px": getattr(im, "width", None), "h_px": getattr(im, "height", None)})
        sheets.append({
            "name": ws.title, "dimensions": ws.dimensions, "max_row": ws.max_row, "max_col": ws.max_column,
            "header_row": header_row, "freeze_panes": ws.freeze_panes, "merged": [str(m) for m in ws.merged_cells.ranges],
            "columns": cols,
            "row_heights": {r: d.height for r, d in list(ws.row_dimensions.items())[:20] if d.height},
            "preview_rows": [[clip(str(v), 25) if v is not None else None for v in row]
                             for row in ws.iter_rows(min_row=1, max_row=min(ws.max_row, 8), values_only=True)],
            "formulas": [c.coordinate for row in ws.iter_rows() for c in row if isinstance(c.value, str) and c.value.startswith("=")][:30],
            "conditional_formatting": len(ws.conditional_formatting),
            "data_validations": len(ws.data_validations.dataValidation) if ws.data_validations else 0,
            "tables": list(ws.tables.keys()), "images": images, "charts": len(getattr(ws, "_charts", [])),
            "auto_filter": ws.auto_filter.ref,
            "page_setup": {"orientation": ws.page_setup.orientation, "paper": ws.page_setup.paperSize,
                           "header": clip(ws.oddHeader.center.text or ws.oddHeader.left.text or "", 50),
                           "footer": clip(ws.oddFooter.center.text or ws.oddFooter.left.text or "", 50)},
            "tab_color": _color(ws.sheet_properties.tabColor),
        })
    return {"format": "xlsx", "theme": read_theme(path), "sheets": sheets,
            "stats": {"sheets": len(sheets), "images": sum(len(s["images"]) for s in sheets),
                      "charts": sum(s["charts"] for s in sheets)}}


def xlsx_text(path: str) -> str:
    wb = load_workbook(path, data_only=False)
    out = []
    for ws in wb.worksheets:
        out.append(f"Sheet {ws.title}:")
        for row in ws.iter_rows(values_only=True):
            if any(v is not None for v in row):
                out.append(" | ".join("" if v is None else str(v) for v in row))
    return "\n".join(out)
