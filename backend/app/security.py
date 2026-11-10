"""Secure file handling: allow-list, size caps, magic bytes, zip-bomb guard, safe names."""
import re
import zipfile
from pathlib import Path
from fastapi import HTTPException
from .config import settings

OFFICE = {"docx", "pptx", "xlsx"}
REFERENCE = {"txt", "md", "pdf"}
ALLOWED = OFFICE | REFERENCE
OFFICE_ROOT_PART = {"docx": "word/document.xml", "pptx": "ppt/presentation.xml", "xlsx": "xl/workbook.xml"}


def safe_name(name: str) -> str:
    name = Path(name or "file").name
    name = re.sub(r"[^A-Za-z0-9._ -]", "_", name).strip(" .")
    return name[:120] or "file"


def validate_upload(filename: str, data: bytes) -> str:
    """Return the validated extension or raise HTTP 400/413."""
    ext = Path(filename or "").suffix.lower().lstrip(".")
    if ext not in ALLOWED:
        raise HTTPException(400, f"Unsupported file type '.{ext}'. Allowed: {sorted(ALLOWED)}")
    if len(data) > settings.MAX_UPLOAD_MB * 1024 * 1024:
        raise HTTPException(413, f"File larger than {settings.MAX_UPLOAD_MB} MB")
    if not data:
        raise HTTPException(400, "Empty file")
    if ext in OFFICE:
        if data[:4] != b"PK\x03\x04":
            raise HTTPException(400, "File content does not match its extension")
        import io
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as z:
                total = sum(i.file_size for i in z.infolist())
                if total > settings.MAX_UNZIPPED_MB * 1024 * 1024:
                    raise HTTPException(400, "Archive expands too large (possible zip bomb)")
                names = z.namelist()
                if any(n.startswith("/") or ".." in Path(n).parts for n in names):
                    raise HTTPException(400, "Unsafe path inside archive")
                if OFFICE_ROOT_PART[ext] not in names:
                    raise HTTPException(400, f"Not a valid .{ext} file")
                if any(n.lower().endswith(("vbaproject.bin",)) for n in names):
                    raise HTTPException(400, "Macros are not allowed")
        except zipfile.BadZipFile:
            raise HTTPException(400, "Corrupted Office file")
    if ext == "pdf" and data[:5] != b"%PDF-":
        raise HTTPException(400, "File content does not match its extension")
    return ext
