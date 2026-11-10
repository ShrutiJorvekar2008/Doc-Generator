"""Helpers shared by the three analyzers."""
import re
import zipfile
from lxml import etree

EMU_PER_INCH = 914400
NS = {
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main",
    "wp": "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "p": "http://schemas.openxmlformats.org/presentationml/2006/main",
}


def inches(emu):
    return None if emu is None else round(int(emu) / EMU_PER_INCH, 2)


def rgb(color_obj):
    """Best-effort hex colour from a python-docx/pptx colour object."""
    try:
        if color_obj is None or color_obj.type is None:
            return None
        if color_obj.rgb is not None:
            return str(color_obj.rgb)
        if color_obj.theme_color is not None:
            return f"theme:{color_obj.theme_color}"
    except Exception:
        pass
    return None


def read_theme(path: str) -> dict:
    """Theme colours and fonts from any OOXML package (docx/pptx/xlsx)."""
    out = {"colors": {}, "major_font": None, "minor_font": None}
    try:
        with zipfile.ZipFile(path) as z:
            theme = next((n for n in z.namelist() if re.search(r"theme/theme\d*\.xml$", n)), None)
            if not theme:
                return out
            root = etree.fromstring(z.read(theme))
        for el in root.iterfind(".//a:clrScheme/*", NS):
            name = etree.QName(el).localname
            child = el[0] if len(el) else None
            if child is not None:
                out["colors"][name] = child.get("val") or child.get("lastClr")
        major = root.find(".//a:majorFont/a:latin", NS)
        minor = root.find(".//a:minorFont/a:latin", NS)
        out["major_font"] = major.get("typeface") if major is not None else None
        out["minor_font"] = minor.get("typeface") if minor is not None else None
    except Exception:
        pass
    return out


def clip(text, n=90):
    text = (text or "").replace("\n", " ").strip()
    return text if len(text) <= n else text[: n - 1] + "…"
