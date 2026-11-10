"""Generate sample analysis reports + sample outputs using the offline mock model (no API keys needed).
Run from the repo root:  python scripts/make_samples.py"""
import json
import os
import shutil
import sys
from pathlib import Path

os.environ.update(LLM_PROVIDER="mock", WEB_SEARCH="false", EMBEDDING_BACKEND="hash", PINECONE_API_KEY="",
                  STORAGE_DIR=str(Path(__file__).resolve().parents[1] / "data" / "sample_run"))
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.analyzers import analyze          # noqa: E402
from app.graph import run_turn             # noqa: E402

T, OUT, AN = ROOT / "samples" / "templates", ROOT / "samples" / "outputs", ROOT / "samples" / "analysis"
OUT.mkdir(exist_ok=True); AN.mkdir(exist_ok=True)


def turn(path, kind, msg, name):
    art = {"id": "x", "name": path.name, "kind": kind, "path": str(path), "analysis": None} if path else None
    r = run_turn({"session_id": "samples", "message": msg, "history": [], "artifact": art})
    nf = r["new_file"]
    dst = OUT / name
    shutil.copy(nf["path"], dst)
    print(f"{name}: {r['reply'].splitlines()[-1]}")
    return dst


for f, k in [("acme_report_template.docx", "docx"), ("acme_deck_template.pptx", "pptx"), ("acme_sales_template.xlsx", "xlsx")]:
    (AN / f"{f}.analysis.json").write_text(json.dumps(analyze(str(T / f), k), indent=2, default=str))

d = turn(T / "acme_report_template.docx", "docx", 'replace "Q3 2026" with "Q4 2026"', "report_q4_step1.docx")
turn(d, "docx", "add paragraph titled 4. Risks: Supply-chain delays may affect Q1 deliveries.", "report_q4_step2.docx")
p = turn(T / "acme_deck_template.pptx", "pptx", "add slide about Risks with supply delays, hiring, currency", "deck_step1.pptx")
turn(p, "pptx", 'replace "2026" with "2027"', "deck_step2.pptx")
turn(T / "acme_sales_template.xlsx", "xlsx", "add row: 2026-09-01, Hooli, Platform, Won, 9900, Ana", "sales_with_new_row.xlsx")
turn(None, "pptx", "create a presentation about renewable energy", "generated_from_scratch_renewable_energy.pptx")
shutil.rmtree(ROOT / "data", ignore_errors=True)
