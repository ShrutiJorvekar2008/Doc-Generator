from pathlib import Path
from .docx_analyzer import analyze_docx, docx_text
from .pptx_analyzer import analyze_pptx, pptx_text
from .xlsx_analyzer import analyze_xlsx, xlsx_text


def analyze(path: str, kind: str) -> dict:
    return {"docx": analyze_docx, "pptx": analyze_pptx, "xlsx": analyze_xlsx}[kind](path)


def extract_text(path: str, kind: str) -> str:
    if kind == "docx": return docx_text(path)
    if kind == "pptx": return pptx_text(path)
    if kind == "xlsx": return xlsx_text(path)
    if kind in ("txt", "md"): return Path(path).read_text(errors="ignore")
    if kind == "pdf":
        from pypdf import PdfReader
        return "\n".join((p.extract_text() or "") for p in PdfReader(path).pages)
    return ""
