"""Serve the tracker on this Mac and let the page run a full refresh.

  http://127.0.0.1:8765

The page on GitHub Pages can only re-read the three board APIs from the browser.
Served from here, its Refresh button runs scripts/refresh.sh on this machine
instead: boards, LinkedIn, Indeed, descriptions, history, the lot.

  GET  /api/status    is a run in progress, its last log lines, when LinkedIn
                      and Indeed were searched and when they may be again
  POST /api/refresh   start a run (the 4h search cooldown still applies)

Listens on 127.0.0.1 only. The refresh endpoint refuses requests from any other
origin, so a web page elsewhere cannot trigger runs, and private/ (your resume)
is never served.
"""

from __future__ import annotations

import json
import os
import posixpath
import subprocess
import sys
from datetime import datetime, timezone
from functools import partial
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote, urlsplit

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import paths

PORT = int(os.environ.get("PT_PORT", "8765"))
ORIGINS = {f"http://127.0.0.1:{PORT}", f"http://localhost:{PORT}"}
HIDDEN = ("/private", "/.git", "/.venv", "/data/archive", "/data/raw")


def hidden(raw_path: str) -> bool:
    # Decode and normalise first, or /%70rivate and /data/../private walk past the check.
    path = posixpath.normpath(unquote(urlsplit(raw_path).path)).lower()
    return any(path == h or path.startswith(h + "/") for h in HIDDEN)


def running() -> bool:
    try:
        pid = int((paths.RUN_LOCK / "pid").read_text())
    except (FileNotFoundError, ValueError):
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def log_tail(n: int = 12) -> list[str]:
    try:
        lines = (paths.LOGS / "latest.log").read_text(errors="replace").splitlines()
    except FileNotFoundError:
        return []
    # JobSpy's own INFO chatter says nothing a person needs.
    return [line for line in lines if " - INFO - " not in line and line.strip()][-n:]


def status() -> dict:
    try:
        meta = json.loads(paths.SEARCH_META.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        meta = {}
    allowed = meta.get("next_after")
    return {
        "running": running(),
        "log": log_tail(),
        "searched_at": meta.get("searched_at"),
        "next_search_after": allowed,
        "search_allowed_now": not allowed or datetime.fromisoformat(allowed) <= datetime.now(timezone.utc),
        "counts": meta.get("counts", {}),
        "blocked": meta.get("blocked", []),
    }


class Handler(SimpleHTTPRequestHandler):
    def _json(self, body: dict, code: int = 200) -> None:
        data = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def end_headers(self) -> None:
        if self.path.startswith("/data/"):
            self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def do_GET(self) -> None:
        path = self.path.split("?", 1)[0]
        if path == "/api/status":
            return self._json(status())
        if hidden(self.path):
            return self.send_error(HTTPStatus.NOT_FOUND)
        return super().do_GET()

    def do_HEAD(self) -> None:
        if hidden(self.path):
            return self.send_error(HTTPStatus.NOT_FOUND)
        return super().do_HEAD()

    def do_POST(self) -> None:
        if self.path.split("?", 1)[0] != "/api/refresh":
            return self.send_error(HTTPStatus.NOT_FOUND)
        if self.headers.get("Origin") not in ORIGINS:
            return self._json({"error": "refresh can only be started from the tracker page"}, 403)
        if running():
            return self._json({"started": False, "running": True}, 409)
        subprocess.Popen(
            [str(paths.ROOT / "scripts" / "refresh.sh")], cwd=paths.ROOT,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True,
        )
        return self._json({"started": True, **status()})

    def log_message(self, fmt: str, *args) -> None:
        if not self.path.startswith("/api/status"):
            sys.stderr.write(f"{self.log_date_time_string()} {fmt % args}\n")


def main() -> None:
    server = ThreadingHTTPServer(("127.0.0.1", PORT), partial(Handler, directory=str(paths.ROOT)))
    print(f"pt-tracker on http://127.0.0.1:{PORT}", file=sys.stderr)
    server.serve_forever()


if __name__ == "__main__":
    main()
