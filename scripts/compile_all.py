"""Compile everything collected in this project into one file.

Inputs are scattered by design - each stage writes its own artefact - but the
thing a person actually wants is a single table they can open and read.
"""

from __future__ import annotations

import csv
import json
import pathlib
from datetime import date

import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import paths
ROOT = paths.ROOT
WF = pathlib.Path("/Users/prathmeshwalimbe/.claude/projects/"
                  "-Users-prathmeshwalimbe-Downloads-pt-tracker/"
                  "dc0aae93-a222-471f-879b-aa8a79c94e09/subagents/workflows")


def load(path, fallback):
    try:
        return json.loads(pathlib.Path(path).read_text())
    except Exception:
        return fallback


def estimates() -> dict:
    """Per-company role and salary estimates, from every workflow that ran."""
    out = {}
    for journal in WF.glob("*/journal.jsonl"):
        for line in journal.read_text().splitlines():
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                continue
            r = d.get("result")
            if isinstance(r, dict) and "likely_roles" in r and r.get("company"):
                out[r["company"]] = r          # later run wins
    return out


def benchmarks() -> list:
    out, seen = [], set()
    for journal in WF.glob("*/journal.jsonl"):
        for line in journal.read_text().splitlines():
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                continue
            r = d.get("result")
            if isinstance(r, dict) and "family" in r and r.get("bands"):
                if r["family"] not in seen:
                    seen.add(r["family"])
                    out.append(r)
    return out


def main() -> None:
    funding = load(paths.FUNDING, {})
    roles = load(paths.SITE_DATA, {}).get("roles", [])
    boards = load(paths.BOARDS, [])
    seen = load(paths.SEEN, {})
    est = estimates()
    bench = benchmarks()

    # attach estimates to the funding rows they belong to
    def match(name):
        n = "".join(c for c in name.lower() if c.isalnum())
        for k, v in est.items():
            m = "".join(c for c in k.lower() if c.isalnum())
            if n and (n in m or m.startswith(n) or n.startswith(m[:12])):
                return v
        return None

    companies = []
    for rec in sorted(funding.values(), key=lambda r: r.get("date", ""), reverse=True):
        e = match(rec["company"])
        companies.append({
            **rec,
            "amount_cr": round(rec["amount_inr"] / 1e7, 2) if rec.get("amount_inr") else None,
            "post_money_cr": round(rec["post_money_inr"] / 1e7, 2) if rec.get("post_money_inr") else None,
            "estimated_roles": (e or {}).get("likely_roles", []),
            "band_confidence": (e or {}).get("band_confidence", ""),
            "fit_for_fresher": (e or {}).get("fit_for_fresher", ""),
            "fit_reason": (e or {}).get("fit_reason", ""),
            "careers_url": (e or {}).get("careers_url", ""),
            "caveat": (e or {}).get("caveat", ""),
        })

    bundle = {
        "compiled": date.today().isoformat(),
        "summary": {
            "funding_rounds_india": len(funding),
            "with_role_estimates": sum(1 for c in companies if c["estimated_roles"]),
            "with_valuation": sum(1 for c in companies if c.get("post_money_cr")),
            "open_roles_scraped": len(roles),
            "roles_open_to_freshers": sum(1 for r in roles if r["tier"] == "open"),
            "employers_with_readable_board": len({b["slug"] for b in boards}),
            "postings_tracked_in_history": len(seen),
            "benchmark_families": len(bench),
        },
        "companies": companies,
        "open_roles": roles,
        "salary_benchmarks": bench,
        "boards": boards,
    }
    (paths.BUNDLE_JSON).write_text(json.dumps(bundle, indent=2))

    # flat CSV: one line per estimated role, which is the usable shape
    with open(paths.BUNDLE_CSV, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["company", "parent", "round", "date", "amount_cr", "post_money_cr",
                    "investors", "founded", "fit_for_fresher", "role_title", "role_family",
                    "likelihood", "band_low_lpa", "band_high_lpa", "band_confidence",
                    "careers_url", "why"])
        for c in companies:
            base = [c["company"], c.get("parent", ""), c["round"], c["date"],
                    c.get("amount_cr") or "", c.get("post_money_cr") or "",
                    "; ".join(c.get("investors") or []), c.get("founded", ""),
                    c.get("fit_for_fresher", "")]
            if not c["estimated_roles"]:
                w.writerow(base + ["", "", "", "", "", "", c.get("careers_url", ""), ""])
                continue
            for r in c["estimated_roles"]:
                w.writerow(base + [r.get("title", ""), r.get("family", ""),
                                   r.get("likelihood", ""), r.get("band_low_lpa", ""),
                                   r.get("band_high_lpa", ""), c.get("band_confidence", ""),
                                   c.get("careers_url", ""), (r.get("why") or "")[:300]])

    s = bundle["summary"]
    for k, v in s.items():
        print(f"{k:34} {v}")


if __name__ == "__main__":
    main()
