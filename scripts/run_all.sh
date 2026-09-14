#!/usr/bin/env bash
# The whole pipeline, in the only order that works. Use refresh.sh to run it
# with a lock and a log; arguments (--force) pass through to fetch_search.py.
set -euo pipefail
cd "$(dirname "$0")/.."
step() { echo; echo "== $*"; }
step "Company boards";        python3 scripts/fetch_jobs.py
# A job board being down or blocked must not stop the rest of the run.
step "LinkedIn and Indeed";   python3 scripts/fetch_search.py "$@" || echo "search step failed; continuing with the last results"
step "Reading descriptions";  python3 scripts/enrich.py
step "Funding news";          python3 scripts/funding.py 60 || echo "funding feeds failed; continuing"
step "History";               python3 scripts/track_history.py
step "Building the page";     python3 scripts/build_data.py
                              python3 scripts/render.py
                              python3 scripts/compile_all.py
