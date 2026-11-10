"""Offline tests (mock LLM, in-memory vector store, SQLite). Run:  pytest -q"""
import os
import sys
from pathlib import Path

os.environ.update(LLM_PROVIDER="mock", WEB_SEARCH="false", EMBEDDING_BACKEND="hash", PINECONE_API_KEY="",
                  DATABASE_URL="sqlite:///./test.db", STORAGE_DIR="./test_files")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.analyzers import analyze
from app.editors import apply_ops, validate_ops, check_fidelity

T = Path(__file__).resolve().parents[2] / "samples" / "templates"


def test_analyzers_capture_design():
    d = analyze(str(T / "acme_report_template.docx"), "docx")
    assert d["sections"][0]["header_images"] == 1 and d["sections"][0]["margins_in"]["left"] == 0.9
    assert d["tables"][0]["header_shading"][0] == "1F3A5F"
    p = analyze(str(T / "acme_deck_template.pptx"), "pptx")
    assert any(s["type"] == "PICTURE" for s in p["masters"][0]["shapes"])        # logo lives on the master
    x = analyze(str(T / "acme_sales_template.xlsx"), "xlsx")["sheets"][0]
    assert x["freeze_panes"] == "A5" and x["images"] and x["data_validations"] == 1


def test_docx_edit_preserves_layout(tmp_path):
    src, dst = str(T / "acme_report_template.docx"), str(tmp_path / "o.docx")
    ops = [{"op": "replace_text", "find": "Q3 2026", "replace": "Q4 2026"},
           {"op": "fill_table", "table_index": 0, "rows": [["A", "1", "+1%"], ["B", "2", "+2%"], ["C", "3", "+3%"], ["D", "4", "+4%"]]}]
    assert validate_ops("docx", ops, analyze(src, "docx")) == []
    apply_ops("docx", src, dst, ops)
    assert check_fidelity(src, dst, "docx")["passed"]
    assert analyze(dst, "docx")["tables"][0]["rows"] == 5


def test_validation_rejects_bad_plan():
    a = analyze(str(T / "acme_deck_template.pptx"), "pptx")
    errs = validate_ops("pptx", [{"op": "set_text", "slide": 99, "shape": 0, "text": "x"}, {"op": "nope"}], a)
    assert len(errs) == 2


def test_security_rejects_fake_docx():
    with TestClient(app) as c:
        sid = c.post("/api/sessions").json()["id"]
        r = c.post(f"/api/sessions/{sid}/files", files={"file": ("evil.docx", b"not a zip", "application/octet-stream")})
        assert r.status_code == 400
        r = c.post(f"/api/sessions/{sid}/files", files={"file": ("run.exe", b"MZ....", "application/octet-stream")})
        assert r.status_code == 400


def test_end_to_end_chat_edit_and_versioning():
    with TestClient(app) as c:
        sid = c.post("/api/sessions").json()["id"]
        up = c.post(f"/api/sessions/{sid}/files", files={"file": ("deck.pptx", (T / "acme_deck_template.pptx").read_bytes(), "application/octet-stream")})
        assert up.status_code == 200 and up.json()["stats"]["slides"] == 3
        r1 = c.post(f"/api/sessions/{sid}/chat", json={"message": "add slide about Risks with delays, hiring"}).json()
        assert r1["artifact"]["version"] == 2 and r1["fidelity"]["passed"]
        r2 = c.post(f"/api/sessions/{sid}/chat", json={"message": 'replace "2026" with "2027"'}).json()
        assert r2["artifact"]["version"] == 3                     # conversational editing builds on the latest version
        dl = c.get(f"/api/artifacts/{r2['artifact']['id']}/download")
        assert dl.status_code == 200 and dl.content[:2] == b"PK"
        assert len(c.get(f"/api/sessions/{sid}").json()["artifacts"]) == 3


def test_create_from_scratch_without_template():
    with TestClient(app) as c:
        sid = c.post("/api/sessions").json()["id"]
        r = c.post(f"/api/sessions/{sid}/chat", json={"message": "create a presentation about solar power"}).json()
        assert r["artifact"] and r["artifact"]["kind"] == "pptx"
