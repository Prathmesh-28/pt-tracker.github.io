"""Parse funding-database rows pasted as flat text.

The export is one field per line with no delimiters, so the parser anchors on
the two things that are unambiguous: a record-number line, and a date line.
Everything else is positional from the date.

It also copes with the paste artefacts: a stray one-character line after some
company names, and "Logo (failed to load)" in place of "Logo".
"""

from __future__ import annotations

import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import paths

import json
import re
import sys
import pathlib
from datetime import date, datetime

NUM = re.compile(r"^\d+\.$")
DATE = re.compile(r"^[A-Z][a-z]{2} \d{1,2}, \d{4}$")
LOGO = re.compile(r"^Logo(\s*\(failed to load\))?$", re.I)
STRAY = re.compile(r"^[A-Za-z0-9]$")          # the lone "m" / "s" / "u" / "4" lines
INV_KIND = re.compile(r"^(Institutional|Angel|Corporate|Government|Family Office):$", re.I)
PARENT = re.compile(r"^Part of \((.+)\)$", re.I)   # subsidiary marker between name and date

# Round types that are not a startup raising venture money.
NOT_VENTURE = re.compile(r"^(post ipo|conventional debt|grant|pe|buyout|secondary|icos?)", re.I)


def to_rupees(text: str) -> int | None:
    """'143Cr' -> 1430000000, '95.6L' -> 9560000, '18,300Cr' -> ..."""
    if not text or text == "-":
        return None
    t = text.strip()
    m = re.match(r"^([\d,]+(?:\.\d+)?)\s*(Cr|L)$", t, re.I)
    if m:
        value = float(m.group(1).replace(",", ""))
        return int(value * (10_000_000 if m.group(2).lower() == "cr" else 100_000))
    # a few rows come through in dollars; 88 INR/USD is close enough to rank by
    d = re.match(r"^\$\s?([\d,]+(?:\.\d+)?)\s*([KMB])?$", t, re.I)
    if d:
        mult = {"k": 1_000, "m": 1_000_000, "b": 1_000_000_000}.get((d.group(2) or "").lower(), 1)
        return int(float(d.group(1).replace(",", "")) * mult * 88)
    return None


def parse(text: str) -> list[dict]:
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    starts = [i for i, l in enumerate(lines) if NUM.match(l)]
    records = []

    for n, start in enumerate(starts):
        end = starts[n + 1] if n + 1 < len(starts) else len(lines)
        block = lines[start:end]

        date_at = next((i for i, l in enumerate(block) if DATE.match(l)), None)
        if date_at is None:
            continue

        # company: everything between the logo line and the date, minus stray chars
        parent = ""
        name_parts = []
        for l in block[1:date_at]:
            if LOGO.match(l) or STRAY.match(l):
                continue
            m = PARENT.match(l)
            if m:
                parent = m.group(1).strip()
                continue
            name_parts.append(l)
        company = " ".join(name_parts).strip()
        if not company:
            continue

        def field(offset: int) -> str:
            i = date_at + offset
            return block[i] if i < len(block) else "-"

        investors, kind = [], ""
        tail = block[date_at + 9:]
        for line in tail:
            if INV_KIND.match(line):
                kind = line.rstrip(":")
            elif line != "-":
                investors.append(line)

        round_name = field(3)
        records.append({
            "rank": int(block[0].rstrip(".")),
            "company": company,
            "parent": parent,
            "date": datetime.strptime(block[date_at], "%b %d, %Y").date().isoformat(),
            "founded": field(1) if field(1) != "-" else "",
            "location": field(2) if field(2) != "-" else "",
            "round": round_name,
            "amount_raw": field(4) if field(4) != "-" else "",
            "amount_inr": to_rupees(field(4)),
            "pre_money_inr": to_rupees(field(5)),
            "post_money_inr": to_rupees(field(6)),
            "revenue_multiple": field(7) if field(7) != "-" else "",
            "ev_ebitda": field(8) if field(8) != "-" else "",
            "investor_kind": kind,
            "investors": investors,
            "is_venture_round": not bool(NOT_VENTURE.match(round_name)),
        })
    return records


STORE = paths.FUNDING


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def merge(rows: list[dict]) -> tuple[int, int]:
    """Fold new rows into the cumulative store. Same company, date and round is
    the same event however many times it is pasted."""
    try:
        store = json.loads(STORE.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        store = {}

    added = updated = 0
    for r in rows:
        key = f"{slug(r['company'])}|{r['date']}|{slug(r['round'])}"
        if key in store:
            # a later paste may carry investors an earlier one truncated
            before = store[key]
            if len(r.get("investors") or []) > len(before.get("investors") or []):
                before.update(r)
                updated += 1
        else:
            store[key] = {**r, "first_ingested": date.today().isoformat()}
            added += 1

    STORE.parent.mkdir(parents=True, exist_ok=True)
    STORE.write_text(json.dumps(store, indent=1, sort_keys=True))
    return added, updated


def main() -> None:
    text = sys.stdin.read() if len(sys.argv) < 2 else open(sys.argv[1]).read()
    rows = parse(text)
    india = [r for r in rows if r["location"] == "India"]
    venture = [r for r in india if r["is_venture_round"]]

    print(f"parsed {len(rows)} records", file=sys.stderr)
    print(f"  India: {len(india)}  ({len(rows) and 100*len(india)//len(rows)}% of the paste)",
          file=sys.stderr)
    print(f"  India and a venture round: {len(venture)}", file=sys.stderr)
    dropped = [r for r in india if not r["is_venture_round"]]
    for r in dropped:
        print(f"  dropped {r['company']}: {r['round']}", file=sys.stderr)

    added, updated = merge(india)
    total = len(json.loads(STORE.read_text()))
    print(f"  store: +{added} new, {updated} enriched, {total} India rounds held",
          file=sys.stderr)
    for r in venture:
        cr = f"{r['amount_inr']/10_000_000:,.1f}Cr" if r["amount_inr"] else "undisclosed"
        print(f"{r['date']} | {r['company'][:26]:26} | {r['round'][:14]:14} | {cr:>12} | "
              f"{', '.join(r['investors'])[:40]}")


if __name__ == "__main__":
    main()
