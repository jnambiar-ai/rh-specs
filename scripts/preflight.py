"""Step 1 preflight, meant to be run LOCALLY (your own computer and network).

Makes about 10 polite requests (1/second, robots.txt respected, cached on disk):
  1. robots.txt for www.rh.com and images.restorationhardware.com
  2. the known tear sheet, Leather_Maxwell.pdf
  3. up to 5 sitemap files listed in robots.txt
It stops immediately if the site shows a block, CAPTCHA or login wall. It never
retries or tries to get around one.

Usage:  python scripts/preflight.py
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from rh_specs.fetch import BlockedError, Fetcher, RobotsDisallowed  # noqa: E402

HOSTS = ["https://www.rh.com", "https://images.restorationhardware.com"]
KNOWN_PDF = "https://images.restorationhardware.com/content/catalog/tearsheets/Leather_Maxwell.pdf"
MAX_SITEMAPS = 5


def _sitemap_urls(robots_text: str) -> list[str]:
    return re.findall(r"(?im)^\s*sitemap:\s*(\S+)", robots_text)


def _safe_name(url: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", url.split("://", 1)[-1])[:120]


def run(f: Fetcher, root: Path = ROOT, out=print) -> int:
    pages = root / "data" / "raw" / "pages"
    summary = {"saved": [], "skipped": [], "blocked": None}
    sitemaps: list[str] = []
    try:
        for origin in HOSTS:
            f.robots(origin + "/", pages)
            text = (pages / f"robots_{origin.split('//')[1]}.txt").read_text()
            out(f"ok   robots.txt  {origin}  ({len(text)} bytes)")
            summary["saved"].append(f"robots_{origin.split('//')[1]}.txt")
            sitemaps += _sitemap_urls(text)

        dest = root / "data" / "raw" / "tearsheets" / "Leather_Maxwell.pdf"
        f.get(KNOWN_PDF, dest, robots_dir=pages)
        out(f"ok   tear sheet  {dest.name}  ({dest.stat().st_size} bytes)")
        summary["saved"].append(str(dest.relative_to(root)))

        for url in list(dict.fromkeys(sitemaps))[:MAX_SITEMAPS]:
            try:
                sm = f.get(url, pages / f"sitemap_{_safe_name(url)}", robots_dir=pages)
            except FileNotFoundError as e:
                out(f"skip sitemap     {e}")
                summary["skipped"].append(url)
                continue
            out(f"ok   sitemap     {url}  ({sm.stat().st_size} bytes)")
            summary["saved"].append(str(sm.relative_to(root)))
    except RobotsDisallowed as e:
        out(f"STOP robots.txt disallows {e}. Nothing further was requested.")
        summary["blocked"] = f"robots: {e}"
        code = 3
    except BlockedError as e:
        out(f"STOP blocked: {e}. Nothing further was requested. Tell Claude; do not retry.")
        summary["blocked"] = str(e)
        code = 2
    else:
        out("\nAll good. Now upload or commit the `data/` folder so Claude can read it.")
        code = 0
    (root / "data" / "discovery").mkdir(parents=True, exist_ok=True)
    (root / "data" / "discovery" / "preflight_summary.json").write_text(json.dumps(summary, indent=2))
    return code


if __name__ == "__main__":
    sys.exit(run(Fetcher()))
