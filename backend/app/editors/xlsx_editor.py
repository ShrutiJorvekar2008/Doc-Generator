"""Format-preserving XLSX edits: new rows copy the style (fonts, fills, borders, number formats)
of an existing data row; column widths, freeze panes, merges, validations stay as they were."""
import re
from copy import copy
from datetime import date
from openpyxl import load_workbook


def _coerce(v):
    """ISO date strings become real dates so the template's date number-format applies."""
    if isinstance(v, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", v):
        return date.fromisoformat(v)
    return v


def _last_data_row(ws):
    for r in range(ws.max_row, 0, -1):
        if any(ws.cell(r, c).value not in (None, "") for c in range(1, ws.max_column + 1)):
            return r
    return 1


def _write_row(ws, r, values, style_row):
    for ci, v in enumerate(values, 1):
        cell = ws.cell(r, ci)
        if style_row and style_row != r:
            cell._style = copy(ws.cell(style_row, ci)._style)
        cell.value = v.replace("{row}", str(r)) if isinstance(v, str) and v.startswith("=") else _coerce(v)
    if style_row and style_row != r and ws.row_dimensions[style_row].height:
        ws.row_dimensions[r].height = ws.row_dimensions[style_row].height


def apply_xlsx(src, dst, ops, sources=None):
    wb = load_workbook(src)
    log = []
    for op in ops:
        name = op["op"]
        ws = wb[op["sheet"]] if "sheet" in op else None
        if name == "set_cell":
            v = op["value"]
            ws[op["cell"]].value = _coerce(v)
            log.append(f"set {op['sheet']}!{op['cell']}")
        elif name == "append_row":
            last = _last_data_row(ws)
            r = op.get("row", last + 1)
            _write_row(ws, r, op["values"], op.get("template_row", last if last > 1 else None))
            log.append(f"append row {r} on '{op['sheet']}'")
        elif name == "set_range":
            from openpyxl.utils.cell import coordinate_from_string, column_index_from_string
            col_letter, row0 = coordinate_from_string(op["start"])
            c0 = column_index_from_string(col_letter)
            tmpl = op.get("template_row", row0 if ws.cell(row0, c0).has_style else None)
            for i, vals in enumerate(op["rows"]):
                r = row0 + i
                for j, v in enumerate(vals):
                    cell = ws.cell(r, c0 + j)
                    if tmpl and tmpl != r:
                        cell._style = copy(ws.cell(tmpl, c0 + j)._style)
                    cell.value = v.replace("{row}", str(r)) if isinstance(v, str) and v.startswith("=") else _coerce(v)
            log.append(f"set range from {op['start']} ({len(op['rows'])} row(s))")
        elif name == "add_sheet":
            base = wb[op["copy_from"]] if op.get("copy_from") in wb.sheetnames else wb.worksheets[0]
            new = wb.copy_worksheet(base)
            new.title = op["name"][:31]
            hdr = op.get("header_row", 1)
            for row in new.iter_rows(min_row=hdr + 1):
                for c in row:
                    c.value = None
            for i, vals in enumerate(op.get("rows", [])):
                _write_row(new, hdr + 1 + i, vals, hdr + 1)
            log.append(f"add sheet '{new.title}' cloned from '{base.title}'")
        else:
            raise ValueError(f"unknown xlsx op {name}")

    if sources:
        base = wb.worksheets[0]
        ws = wb.create_sheet("Sources")
        hdr = base.cell(1, 1)
        for ci, h in enumerate(["ID", "Title", "Reference"], 1):
            c = ws.cell(1, ci, h)
            c._style = copy(hdr._style)
        for i, s in enumerate(sources, 2):
            for ci, v in enumerate([s["id"], s["title"], s["ref"]], 1):
                ws.cell(i, ci, v)
        for L, w in zip("ABC", (8, 50, 70)):
            ws.column_dimensions[L].width = w
        log.append(f"added Sources sheet ({len(sources)} item(s))")
    wb.save(dst)
    return log
