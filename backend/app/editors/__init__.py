"""Op registry: validation of an edit plan against the template analysis + dispatch to editors."""
from .docx_editor import apply_docx
from .pptx_editor import apply_pptx
from .xlsx_editor import apply_xlsx
from .fidelity import check_fidelity

APPLY = {"docx": apply_docx, "pptx": apply_pptx, "xlsx": apply_xlsx}

OPS = {  # op name -> required keys
    "docx": {"replace_text": ["find", "replace"], "set_paragraph": ["index", "text"],
             "append_paragraph": ["text"], "delete_paragraph": ["index"],
             "set_cell": ["table_index", "row", "col", "text"], "fill_table": ["table_index", "rows"]},
    "pptx": {"replace_text": ["find", "replace"], "set_text": ["slide", "shape"], "add_slide": ["title"],
             "duplicate_slide": ["source"], "delete_slide": ["slide"], "set_notes": ["slide", "text"],
             "set_table_cell": ["slide", "shape", "row", "col", "text"], "fill_table": ["slide", "shape", "rows"]},
    "xlsx": {"set_cell": ["sheet", "cell", "value"], "append_row": ["sheet", "values"],
             "set_range": ["sheet", "start", "rows"], "add_sheet": ["name"]},
}


def validate_ops(kind: str, ops: list, analysis: dict) -> list[str]:
    """Return a list of human-readable problems (empty = plan is applicable)."""
    errs = []
    if not isinstance(ops, list):
        return ["'ops' must be a list"]
    spec = OPS[kind]
    for i, op in enumerate(ops):
        if not isinstance(op, dict) or op.get("op") not in spec:
            errs.append(f"op #{i}: unknown op {op.get('op') if isinstance(op, dict) else op!r}; allowed: {sorted(spec)}")
            continue
        for k in spec[op["op"]]:
            if k not in op:
                errs.append(f"op #{i} ({op['op']}): missing '{k}'")
        if kind == "docx":
            n = analysis["stats"]["paragraphs"]
            for k in ("index", "after_index", "like_index"):
                if k in op and not (isinstance(op[k], int) and 0 <= op[k] < n):
                    errs.append(f"op #{i}: {k}={op[k]} out of range 0..{n-1}")
            if "table_index" in op and not (isinstance(op["table_index"], int) and 0 <= op["table_index"] < len(analysis["tables"])):
                errs.append(f"op #{i}: table_index {op['table_index']} does not exist")
        elif kind == "pptx":
            n = analysis["stats"]["slides"]
            for k in ("slide", "source", "after_slide"):
                if k in op and not (isinstance(op[k], int) and 0 <= op[k] < n):
                    errs.append(f"op #{i}: {k}={op[k]} out of range 0..{n-1}")
            if isinstance(op.get("slide"), int) and op.get("shape") is not None and op["slide"] < n:
                if not (isinstance(op["shape"], int) and 0 <= op["shape"] < len(analysis["slides"][op["slide"]]["shapes"])):
                    errs.append(f"op #{i}: shape {op['shape']} does not exist on slide {op['slide']}")
        elif kind == "xlsx":
            names = [s["name"] for s in analysis["sheets"]]
            if "sheet" in op and op["sheet"] not in names:
                errs.append(f"op #{i}: sheet '{op['sheet']}' not found; sheets: {names}")
    return errs


def apply_ops(kind, src, dst, ops, sources=None):
    return APPLY[kind](src, dst, ops, sources)
