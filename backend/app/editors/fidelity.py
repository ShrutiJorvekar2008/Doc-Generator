"""Validation of the *result*: does the generated file still carry the template's layout/design?"""
from ..analyzers import analyze


def _eq(issues, label, a, b):
    if a != b:
        issues.append(f"{label} changed: {a} → {b}")


def check_fidelity(before_path, after_path, kind):
    try:
        a, b = analyze(before_path, kind), analyze(after_path, kind)
    except Exception as e:  # file must at least re-open
        return {"passed": False, "issues": [f"Generated file cannot be re-opened: {e}"]}
    issues = []
    _eq(issues, "theme", a["theme"], b["theme"])
    if kind == "docx":
        for sa, sb in zip(a["sections"], b["sections"]):
            for k in ("page_w_in", "page_h_in", "orientation", "margins_in", "header_images", "footer_images", "header_text", "footer_text"):
                _eq(issues, f"section {sa['index']} {k}", sa[k], sb[k])
        _eq(issues, "section count", len(a["sections"]), len(b["sections"]))
        _eq(issues, "header/footer image count", [i for i in a["images"] if i["where"] != "body"].__len__(),
            [i for i in b["images"] if i["where"] != "body"].__len__())
        for ta, tb in zip(a["tables"], b["tables"]):
            _eq(issues, f"table {ta['index']} style/borders", (ta["style"], ta["borders"]), (tb["style"], tb["borders"]))
        new_fonts = {p.get("font") for p in b["paragraphs"] if p.get("font")} - {p.get("font") for p in a["paragraphs"] if p.get("font")}
        if new_fonts:
            issues.append(f"new fonts introduced: {sorted(new_fonts)}")
    elif kind == "pptx":
        _eq(issues, "slide size", a["slide_size_in"], b["slide_size_in"])
        _eq(issues, "masters/layouts", a["masters"], b["masters"])
        new_fonts = {s.get("font") for sl in b["slides"] for s in sl["shapes"] if s.get("font")} - \
                    {s.get("font") for sl in a["slides"] for s in sl["shapes"] if s.get("font")}
        if new_fonts:
            issues.append(f"new fonts introduced: {sorted(new_fonts)}")
    elif kind == "xlsx":
        bmap = {s["name"]: s for s in b["sheets"]}
        for sa in a["sheets"]:
            sb = bmap.get(sa["name"])
            if not sb:
                issues.append(f"sheet '{sa['name']}' missing"); continue
            _eq(issues, f"{sa['name']} freeze panes", sa["freeze_panes"], sb["freeze_panes"])
            _eq(issues, f"{sa['name']} column widths", [c["width"] for c in sa["columns"]], [c["width"] for c in sb["columns"]][: len(sa["columns"])])
            _eq(issues, f"{sa['name']} header style", [c["header_style"] for c in sa["columns"]], [c["header_style"] for c in sb["columns"]][: len(sa["columns"])])
            _eq(issues, f"{sa['name']} images", len(sa["images"]), len(sb["images"]))
    return {"passed": not issues, "issues": issues}
