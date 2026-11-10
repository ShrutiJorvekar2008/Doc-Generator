"""Run-level text helpers that keep the original formatting (works for python-docx and python-pptx)."""


def replace_in_paragraph(p, find: str, repl: str) -> int:
    """Replace `find` inside a paragraph. If the text is split across runs, the replacement
    takes the formatting of the first run it touches."""
    if not find or find not in p.text:
        return 0
    for r in p.runs:
        if find in r.text:
            r.text = r.text.replace(find, repl)
            return 1
    runs = list(p.runs)
    full = "".join(r.text for r in runs)
    if find not in full:
        return 0
    start = full.index(find)
    end = start + len(find)
    pos, first = 0, True
    for r in runs:
        rs, re_ = pos, pos + len(r.text)
        pos = re_
        if re_ <= start or rs >= end:
            continue
        a, b = max(start, rs) - rs, min(end, re_) - rs
        if first:
            r.text = r.text[:a] + repl + r.text[b:]
            first = False
        else:
            r.text = r.text[:a] + r.text[b:]
    return 1


def set_paragraph_text(p, text: str):
    """Replace all text of a paragraph, keeping the formatting of its first text run."""
    runs = list(p.runs)
    keep = next((r for r in runs if r.text), runs[0] if runs else None)
    if keep is None:
        p.add_run(text)
        return
    keep.text = text
    for r in runs:
        if r is not keep:
            r._r.getparent().remove(r._r)
