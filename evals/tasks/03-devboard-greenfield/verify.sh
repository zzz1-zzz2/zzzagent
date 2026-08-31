#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../.." && pwd)"
workspace="${repo_root}/evals/workspaces/03-devboard-greenfield"

if [[ ! -d "${workspace}" ]]; then
  printf 'FAIL: workspace is missing; run setup.sh first\n' >&2
  exit 2
fi
cd -- "${workspace}"

for file in index.html styles.css script.js; do
  if [[ ! -s "${file}" ]]; then
    printf 'FAIL: required static file is missing or empty: %s\n' "${file}" >&2
    exit 1
  fi
done

python3 - <<'PY'
from html.parser import HTMLParser
from pathlib import Path
import re
import sys


class PageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.tags: set[str] = set()
        self.links: list[str] = []
        self.scripts: list[str] = []
        self.has_viewport = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.tags.add(tag)
        values = dict(attrs)
        if tag == "meta" and values.get("name", "").lower() == "viewport":
            self.has_viewport = True
        if tag == "link" and values.get("href"):
            self.links.append(values["href"] or "")
        if tag == "script" and values.get("src"):
            self.scripts.append(values["src"] or "")


html = Path("index.html").read_text(encoding="utf-8")
css = Path("styles.css").read_text(encoding="utf-8")
js = Path("script.js").read_text(encoding="utf-8")
parser = PageParser()
parser.feed(html)

errors: list[str] = []
for tag in ("header", "main"):
    if tag not in parser.tags:
        errors.append(f"index.html should contain a semantic <{tag}> element")
if not parser.has_viewport:
    errors.append("index.html is missing a viewport meta tag")
if "styles.css" not in parser.links:
    errors.append("index.html must reference styles.css")
if "script.js" not in parser.scripts:
    errors.append("index.html must reference script.js")
if re.search(r"(?:https?:)?//", html, re.IGNORECASE):
    errors.append("index.html must not reference remote resources")
if "@media" not in css:
    errors.append("styles.css must include a responsive media query")
if not re.search(r"addEventListener|onclick\s*=", js):
    errors.append("script.js must implement a user interaction")
if len(js.strip()) < 120:
    errors.append("script.js is too small to demonstrate meaningful interaction")

if errors:
    for error in errors:
        print(f"FAIL: {error}", file=sys.stderr)
    raise SystemExit(1)

print("PASS: static DevBoard structure, responsive styling, and interaction verified")
PY
