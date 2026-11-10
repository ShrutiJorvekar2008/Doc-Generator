#!/usr/bin/env bash
# One-time setup (macOS/Linux). Creates a venv, installs Python + Node deps, writes a keyless demo .env.
set -e
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
[ -f .env ] || { cp .env.example .env; sed -i.bak 's/^LLM_PROVIDER=.*/LLM_PROVIDER=mock/; s/^WEB_SEARCH=.*/WEB_SEARCH=false/' .env && rm -f .env.bak; echo "Created .env in MOCK mode (no keys needed)."; }
(cd frontend && npm install)
echo "Setup done. Run ./run.sh"
