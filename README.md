# DocGen — AI Chatbot & Document Generation Platform

> **Author:** Shruti Jorvekar  
> **Submission:** *AI Chatbot & Document Generation Platform*  
> **License:** All rights reserved — review only. See [LICENSE](LICENSE).


Session-based, multi-turn AI chatbot that **analyses an uploaded Word / PowerPoint / Excel file in depth and then edits or
generates content while preserving the original layout, fonts, colours, logos, headers/footers, slide masters and
spreadsheet formatting.** Built with FastAPI, React, LangGraph/LangChain, Pinecone and PostgreSQL — on free tiers.

```
React UI ─► FastAPI ─► LangGraph workflow ─► format-preserving editors ─► .docx / .pptx / .xlsx (versioned)
                         │  document understanding → request understanding → research (web + RAG)
                         │  → generation → validation (retry loop) → build + fidelity check → response
                         ├─ LLM: Gemini (free) · Groq · OpenRouter · mock (offline)
                         ├─ Pinecone Starter (free) — per-session RAG namespace   [fallback: in-memory]
                         └─ PostgreSQL (Neon free) — sessions, messages, artifact versions   [fallback: SQLite]
```

## Deliverables checklist

| Assignment deliverable | Where |
|---|---|
| Multi-agent chatbot POC | `backend/app/graph.py` (LangGraph, 8 nodes), `frontend/` |
| Complete source code | `backend/`, `frontend/`, `scripts/` |
| Document / PPT template analysis | `backend/app/analyzers/` · examples in `samples/analysis/*.json` · "Analysis" button in the UI |
| Web research and RAG | `research.py` (DuckDuckGo), `rag.py` (fastembed + Pinecone) |
| Conversational artifact editing | every chat turn edits the latest version; versions are kept (`v1 → v2 → v3`) |
| Source / citation traceability | `[S1]` markers in generated text + *Sources* section/slide/sheet + chips in the UI |
| Sample templates and outputs | `samples/templates/`, `samples/outputs/` |
| Project documentation | this README + `docs/ARCHITECTURE.md` |
| README + requirements.txt | ✔ |

## 1. Setup

Requirements: Python 3.11+, Node 18+.

### 1.1 Free accounts (all optional except an LLM key)
1. **LLM** — Google AI Studio → create an API key (free, no card) → `GOOGLE_API_KEY`.
   (Alternatives: Groq or OpenRouter — set `LLM_PROVIDER` accordingly. Free-tier limits and model names change; set `LLM_MODEL` if the default is retired.)
2. **Pinecone** — create a free *Starter* account → API key → `PINECONE_API_KEY`. The index is created automatically (384-dim, cosine, AWS `us-east-1`).
3. **PostgreSQL** — create a free Neon project → copy the connection string →
   `DATABASE_URL=postgresql+psycopg2://USER:PASSWORD@HOST/DB?sslmode=require`.
   (Neon scales to zero, so the first query after idle can be slow; avoid Supabase free for demos — it pauses after a week idle.)

### 1.2 Install & run
**Quickest way:** run `./setup.sh` then `./run.sh` (Windows: `setup.bat` then `run.bat`). This installs everything and starts in keyless mock mode; add your keys to `.env` later.

**Locked-down Windows PC (Device Guard blocks pip.exe/venv)?** Use `setup_no_venv.bat` then `run_no_venv.bat` and open http://localhost:8000 — no venv and no Node needed (the UI is pre-built in `frontend/dist`).

Manual steps:
```bash
git clone <your-repo-url> docgen && cd docgen
python -m venv .venv && source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                                     # then fill in your keys
python scripts/make_templates.py                         # (optional) regenerate sample templates

# backend  → http://localhost:8000  (docs at /docs)
uvicorn app.main:app --app-dir backend --reload

# frontend → http://localhost:5173
cd frontend && npm install && npm run dev
```
**No keys yet?** Set `LLM_PROVIDER=mock` — a deterministic offline model understands simple commands
(`replace "A" with "B"`, `add slide about X with a, b, c`, `add row: ...`, `add paragraph: ...`, `create a presentation about X`) so you can try the whole pipeline.

### 1.3 Docker (single container)
```bash
docker build -t docgen . && docker run -p 8000:8000 --env-file .env docgen     # UI + API on :8000
```

## 2. Usage guide
1. Click **＋ New chat**, then **📎** and attach a `.docx`, `.pptx` or `.xlsx` template (PDF/TXT/MD can be attached as *reference* material for RAG).
2. The file is validated, analysed (see **Analysis** in the right panel) and indexed.
3. Chat naturally. Examples:
   - *"Replace Q3 2026 with Q4 2026 everywhere."*
   - *"Add a slide on 2027 AI regulation trends for the finance sector"* (triggers web research, cites sources)
   - *"Fill the regional table with these four rows …"*
   - *"Add a row for Hooli, Platform, Won, 9900, owner Ana."*
   - *"Create a presentation about renewable energy"* (no file attached → starts from the built-in Acme starter template)
   - *"What does the attached policy say about travel approvals?"* (RAG answer with `[S#]` citations)
4. Each change creates a **new version**; download any version or pick **Edit this** to continue from an older one.
5. The reply ends with a **format check** comparing the output to the template (page setup, margins, headers/footers, logos, master/layouts, fonts, column widths, freeze panes…).

## 3. API (summary)
| Method | Path | Purpose |
|---|---|---|
| POST | `/api/sessions` | new session |
| GET | `/api/sessions`, `/api/sessions/{id}` | list / messages + artifacts |
| POST | `/api/sessions/{id}/files` | upload + analyse + index (multipart `file`) |
| POST | `/api/sessions/{id}/chat` | `{message, artifact_id?}` → assistant message, new artifact, fidelity report |
| GET | `/api/artifacts/{id}/download` · `/analysis` | file · full analysis JSON |
| GET | `/api/health` | provider / store status |

## 4. Tests & samples
```bash
cd backend && pytest -q            # 6 offline tests (mock LLM, SQLite, in-memory vectors)
python scripts/make_samples.py     # regenerates samples/analysis + samples/outputs
```
`samples/outputs/` were produced by the mock model through the real pipeline (analysis → plan → validate → apply → fidelity check).

## 5. Security
Extension allow-list; size cap; magic-byte + zip-structure check; zip-bomb and path-traversal guard; macro files rejected;
files stored under random UUID names (client name only used for display/download); downloads only via artifact id;
no server-side page fetching during research (snippets only); optional `X-API-Key`; CORS allow-list; secrets only in `.env`.

## 6. Known limitations (POC)
- Verified offline with the mock model and generated templates; **live Gemini / Pinecone / Neon calls were not exercised in the build environment** — run the smoke test in §7 with your keys.
- Free LLM tiers rate-limit and may use prompts for training: don't upload confidential files while on a free tier.
- Editors favour fidelity over freedom: text, tables, rows, slides and sheets are edited via the existing structure. Not covered: editing chart data, SmartArt, tracked changes, and embedded-chart styling beyond what openpyxl round-trips.
- Cloned slides share chart parts with the source slide.
- No authentication/multi-tenancy beyond the optional shared API key; add OAuth/JWT before real deployment.

## 7. Smoke test with real services
```bash
curl localhost:8000/api/health        # shows llm / vector_store / database in use
# in the UI: upload samples/templates/acme_deck_template.pptx and ask:
#   "Add a slide about the 2027 outlook for renewable energy with 3 bullets" → expect [S#] citations and a Sources slide
```

## 8. Publish to GitHub & record the demo
Before the first push, double-check that no secrets are staged:
```bash
git init
git add -A
git status                # verify .env, .venv/, data/ are NOT listed
git commit -m "DocGen — AI Chatbot & Document Generation Platform"
git branch -M main
git remote add origin https://github.com/<your-handle>/docgen.git
git push -u origin main
```
On GitHub, keep the repo **Public** so reviewers can open it without an invite; the [LICENSE](LICENSE)
("all rights reserved — review only") governs what visitors may do with the code.

Suggested 3–5 min demo recording: upload a template → show the **Analysis** panel →
conversational edit → web-researched slide with `[S#]` citations → download and open the
result in Office → show the version list in the right pane.

## 9. Authorship & reuse
This repository is a personal submission by **Shruti Jorvekar**. See [LICENSE](LICENSE) for
the full terms; the short version is that the code is published for review, not for reuse
as another person's assignment. Short attributed snippets in discussion are welcome;
wholesale copies are not.
