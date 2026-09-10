#!/usr/bin/env bash
# The whole pipeline, in the only order that works.
set -euo pipefail
cd "$(dirname "$0")/.."
python3 scripts/fetch_jobs.py       # pull postings from every board
python3 scripts/enrich.py           # read descriptions, extract experience
python3 scripts/funding.py 60       # funding RSS
python3 scripts/track_history.py    # first seen / last seen / closed
python3 scripts/build_data.py       # assemble data/latest.json
python3 scripts/render.py           # write index.html
python3 scripts/compile_all.py      # write pt-tracker-all.{json,csv}
