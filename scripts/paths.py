"""Every file location in one place, so nothing is written 'here and there'."""

import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent

DATA = ROOT / "data"
RAW = DATA / "raw"            # regenerated each run, not versioned
INCOMING = DATA / "incoming"  # the pastes, kept as source of truth
HISTORY = DATA / "history"    # one snapshot per run

# --- inputs ---
BOARDS = DATA / "boards.json"
REJECTED = DATA / "rejected_slugs.json"

# --- working artefacts ---
POSTINGS = RAW / "all_postings.json"
SHORTLIST = RAW / "shortlist.json"
HEADLINES = RAW / "headlines.json"
ROUNDS_RSS = RAW / "rounds.json"
ROUNDS_CLEAN = RAW / "rounds_clean.json"

# --- durable stores ---
FUNDING = DATA / "funding.json"        # accumulates across every ingest
SEEN = DATA / "seen.json"              # recruitment history
BENCHMARKS = DATA / "benchmarks.json"  # salary benchmarks
FUNDED_BOARDS = DATA / "funded_boards.json"

# --- outputs ---
SITE_DATA = DATA / "latest.json"       # what the page loads
BUNDLE_JSON = ROOT / "pt-tracker-all.json"
BUNDLE_CSV = ROOT / "pt-tracker-all.csv"
INDEX = ROOT / "index.html"
TEMPLATE = ROOT / "page.template.html"

for d in (DATA, RAW, INCOMING, HISTORY):
    d.mkdir(parents=True, exist_ok=True)
