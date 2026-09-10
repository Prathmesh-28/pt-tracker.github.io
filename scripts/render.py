"""Inject the data bundle and the live puller into the page template."""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import paths

import re

tpl = paths.TEMPLATE.read_text()
data = json.loads(paths.SITE_DATA.read_text())
live = (paths.ROOT / "scripts" / "live.js").read_text()

# Replace the whole placeholder statement, not just the marker, or the inert
# fallback literal after it survives and you get two object literals in a row.
html, n = re.subn(
    r"^let DATA = /\*__DATA__\*/.*?;$",
    lambda _: "let DATA = " + json.dumps(data, separators=(",", ":")) + ";",
    tpl, count=1, flags=re.M,
)
assert n == 1, "data placeholder not found in template"

html = html.replace("<script>", f"<script>\n{live}\n</script>\n<script>", 1)
paths.INDEX.write_text(html)
print(f"index.html written, {len(html)//1024} KB")
