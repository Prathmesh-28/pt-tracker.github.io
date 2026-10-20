"""Prathmesh's daily application report: what has been applied to, end to end, and what is open now.

Reads the team site's records (japan_applications joined to japan_jobs, Prathmesh's rows only) and the India list
(private/roles.json), writes private/reports/<date>.md, and with --send mails it to Prathmesh.

Mail goes out over SMTP with the settings in private/mail.env (gitignored), for example a Gmail address and an app
password made for it:

  SMTP_HOST=smtp.gmail.com
  SMTP_PORT=465
  SMTP_USER=someone@gmail.com
  SMTP_PASSWORD=<an app password, not the account password>
  MAIL_TO=23b0747@iitb.ac.in

Without that file the report is written and not sent, and the run says so.

  .venv/bin/python India/report.py           # write today's report
  .venv/bin/python India/report.py --send    # and mail it
"""

from __future__ import annotations

import json
import smtplib
import ssl
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "Japan" / "team"))
from sync_jobs import ENV_FILE, env, get_all  # noqa: E402  the team site's credentials and paged reads

MAIL_ENV = HERE / "private" / "mail.env"
REPORTS = HERE / "private" / "reports"
INDIA_ROLES = HERE / "private" / "roles.json"
MAIL_TO = "23b0747@iitb.ac.in"
IST = timezone(timedelta(hours=5, minutes=30))
APPLIED = ("applied", "interview", "offer", "rejected", "withdrawn")   # every status an application reaches
KIND = {"india": "India", "role": "Japan", "program": "Japan programmes", "manual": "Added by the team",
        "competition": "Competitions"}


def when(iso: str) -> datetime | None:
    try:
        return datetime.fromisoformat((iso or "").replace("Z", "+00:00"))
    except ValueError:
        return None


def build(now: datetime) -> tuple[str, str]:
    cfg = env(ENV_FILE)
    base, key = cfg.get("SUPABASE_URL", "").rstrip("/"), cfg.get("SUPABASE_SERVICE_ROLE_KEY", "")
    if not base or not key:
        raise SystemExit(f"Set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY in {ENV_FILE}.")
    jobs = {j["key"]: j for j in get_all(base, key, "japan_jobs?select=key,kind,company,title,url,is_open"
                                                   "&candidate=eq.prathmesh&order=key")}
    apps = [a for a in get_all(base, key, "japan_applications?select=job_key,status,applied_at,applied_with,updated_at"
                                          "&order=job_key") if a["job_key"] in jobs]
    sent = [a for a in apps if a["status"] in APPLIED]
    day_ago, week_ago = now - timedelta(days=1), now - timedelta(days=7)
    recent = sorted((a for a in sent if (when(a.get("applied_at")) or when(a["updated_at"]) or now) >= week_ago),
                    key=lambda a: a.get("applied_at") or a["updated_at"], reverse=True)
    today = [a for a in recent if (when(a.get("applied_at")) or when(a["updated_at"]) or now) >= day_ago]
    status = Counter(a["status"] for a in apps)
    by_kind = Counter(KIND.get(jobs[a["job_key"]]["kind"], jobs[a["job_key"]]["kind"]) for a in sent)
    companies = {jobs[a["job_key"]]["company"] for a in sent}

    india = json.loads(INDIA_ROLES.read_text()) if INDIA_ROLES.exists() else {}
    counts = india.get("counts") or {}
    top = [x for x in india.get("roles") or [] if x.get("ctc") and x["ctc"] >= 20
           and "across India" not in (x.get("basis") or "") and x.get("fit") != "no"][:10]

    line = lambda a: (f"- {jobs[a['job_key']]['company']}: {jobs[a['job_key']]['title']} "
                      f"({a['status']}{', with ' + a['applied_with'] if a.get('applied_with') else ''})")
    subject = (f"Job search {now:%-d %b}: {len(sent)} applications to {len(companies)} companies, "
               f"{len(today)} in the last day")
    body = [f"# {subject}", "",
            f"Applied, end to end: **{len(sent)}** applications to **{len(companies)}** companies.", "",
            "| Status | Count |", "|---|---|",
            *[f"| {s.title()} | {status[s]} |" for s in ("claimed", *APPLIED, "skipped") if status[s]], "",
            "By list: " + (", ".join(f"{k} {v}" for k, v in by_kind.most_common()) or "none yet"), "",
            f"## Last 24 hours ({len(today)})", *([line(a) for a in today] or ["- None"]), "",
            f"## Last 7 days ({len(recent)})", *([line(a) for a in recent[:40]] or ["- None"]), "",
            "## Interviews and offers", *([line(a) for a in sent if a["status"] in ("interview", "offer")] or ["- None yet"]), "",
            "## India list now",
            f"{counts.get('roles', 0)} roles open, {counts.get('from_top_employers', 0)} of them at the top-paying employers, "
            f"{counts.get('pay_20_plus', 0)} where freshers report ₹20 lakh or more.", "",
            *[f"- {x['company']}: {x['title']} (₹{x['ctc']} lakh, {x.get('fit_why') or ''}) {x.get('url') or ''}" for x in top],
            "", f"Generated {now:%-d %b %Y %H:%M} IST from the team site (japan-applications.vercel.app)."]
    return subject, "\n".join(body) + "\n"


def send(subject: str, body: str) -> str:
    cfg = env(MAIL_ENV)
    need = ("SMTP_HOST", "SMTP_USER", "SMTP_PASSWORD")
    if not MAIL_ENV.exists() or not all(cfg.get(k) for k in need):
        return f"not sent: no mail settings in {MAIL_ENV.relative_to(HERE.parent)} (see this script's docstring)"
    msg = EmailMessage()
    msg["Subject"], msg["From"], msg["To"] = subject, cfg["SMTP_USER"], cfg.get("MAIL_TO") or MAIL_TO
    msg.set_content(body)
    port = int(cfg.get("SMTP_PORT") or 465)
    if port == 465:
        with smtplib.SMTP_SSL(cfg["SMTP_HOST"], port, context=ssl.create_default_context(), timeout=60) as s:
            s.login(cfg["SMTP_USER"], cfg["SMTP_PASSWORD"])
            s.send_message(msg)
    else:
        with smtplib.SMTP(cfg["SMTP_HOST"], port, timeout=60) as s:
            s.starttls(context=ssl.create_default_context())
            s.login(cfg["SMTP_USER"], cfg["SMTP_PASSWORD"])
            s.send_message(msg)
    return f"sent to {msg['To']}"


def main() -> None:
    now = datetime.now(IST)
    subject, body = build(now)
    REPORTS.mkdir(parents=True, exist_ok=True)
    out = REPORTS / f"{now:%Y-%m-%d}.md"
    out.write_text(body)
    print(f"{subject}\nwrote {out.relative_to(HERE.parent)}", file=sys.stderr)
    if "--send" in sys.argv:
        print(send(subject, body), file=sys.stderr)


if __name__ == "__main__":
    main()
