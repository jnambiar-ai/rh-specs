"""Polite, caching, read-only HTTP fetcher.

Rules enforced here: descriptive User-Agent, max 1 request/second, robots.txt
respected, every download cached on disk and never re-fetched, and a hard stop
(BlockedError) on login walls, CAPTCHAs, bot blocks or network-policy denials.
Nothing here ever bypasses a block.
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

import httpx

USER_AGENT = "rh-specs-research/0.1 (personal product-reference workflow; contact jnambiar@rh.com)"
BLOCK_STATUSES = {401, 403, 407, 429}
BLOCK_MARKERS = ("captcha", "access denied", "are you a human", "unusual traffic", "sign in to continue")


class BlockedError(RuntimeError):
    """A login wall, CAPTCHA, bot block, or network-policy denial. Stop and report."""


class RobotsDisallowed(RuntimeError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Fetcher:
    def __init__(self, min_interval: float = 1.0, client: httpx.Client | None = None,
                 clock=time.monotonic, sleep=time.sleep):
        self.min_interval = max(min_interval, 1.0)  # brief: never faster than 1 req/s
        self.client = client or httpx.Client(headers={"User-Agent": USER_AGENT},
                                             follow_redirects=True, timeout=30)
        self._clock, self._sleep = clock, sleep
        self._last = None
        self._robots: dict[str, RobotFileParser] = {}

    def _throttle(self) -> None:
        if self._last is not None:
            wait = self.min_interval - (self._clock() - self._last)
            if wait > 0:
                self._sleep(wait)
        self._last = self._clock()

    def _request(self, method: str, url: str) -> httpx.Response:
        self._throttle()
        try:
            resp = self.client.request(method, url)
        except httpx.ProxyError as e:
            raise BlockedError(f"network policy denied {urlsplit(url).netloc}: {e}") from e
        self._check_block(url, resp)
        return resp

    @staticmethod
    def _check_block(url: str, resp: httpx.Response) -> None:
        if resp.status_code in BLOCK_STATUSES:
            raise BlockedError(f"HTTP {resp.status_code} from {url}")
        ctype = resp.headers.get("content-type", "")
        if "html" in ctype and resp.request.method == "GET" and len(resp.content) < 20000:
            low = resp.text.lower()
            if any(m in low for m in BLOCK_MARKERS):
                raise BlockedError(f"block/CAPTCHA page detected at {url}")

    def robots(self, url: str, cache_dir: Path) -> RobotFileParser:
        host = urlsplit(url)
        origin = f"{host.scheme}://{host.netloc}"
        if origin not in self._robots:
            dest = cache_dir / f"robots_{host.netloc}.txt"
            if dest.exists():
                text = dest.read_text()
            else:
                resp = self._request("GET", f"{origin}/robots.txt")
                text = resp.text if resp.status_code == 200 else ""
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_text(text)
            rp = RobotFileParser()
            rp.parse(text.splitlines())
            self._robots[origin] = rp
        return self._robots[origin]

    def allowed(self, url: str, cache_dir: Path) -> bool:
        return self.robots(url, cache_dir).can_fetch(USER_AGENT, url)

    def get(self, url: str, dest: Path, robots_dir: Path | None = None) -> Path:
        """GET url into dest (plus dest.meta.json). Cached files are never re-fetched."""
        meta = dest.with_name(dest.name + ".meta.json")
        if dest.exists() and meta.exists():
            return dest
        if robots_dir is not None and not self.allowed(url, robots_dir):
            raise RobotsDisallowed(url)
        resp = self._request("GET", url)
        dest.parent.mkdir(parents=True, exist_ok=True)
        if resp.status_code == 200:
            dest.write_bytes(resp.content)
        meta.write_text(json.dumps({
            "url": url, "final_url": str(resp.url), "status": resp.status_code,
            "retrieved_at": _now(),
            "headers": {k: resp.headers[k] for k in
                        ("content-type", "content-length", "last-modified", "etag") if k in resp.headers},
        }, indent=2))
        if resp.status_code != 200:
            raise FileNotFoundError(f"HTTP {resp.status_code} for {url}")
        return dest

    def head(self, url: str, log: Path, robots_dir: Path | None = None) -> dict:
        """Polite HEAD probe; results cached by URL in a JSONL log and never repeated."""
        seen = {}
        if log.exists():
            for line in log.read_text().splitlines():
                rec = json.loads(line)
                seen[rec["url"]] = rec
        if url in seen:
            return seen[url]
        if robots_dir is not None and not self.allowed(url, robots_dir):
            raise RobotsDisallowed(url)
        resp = self._request("HEAD", url)
        rec = {"url": url, "status": resp.status_code, "checked_at": _now(),
               "content_length": resp.headers.get("content-length"),
               "last_modified": resp.headers.get("last-modified"),
               "content_type": resp.headers.get("content-type")}
        log.parent.mkdir(parents=True, exist_ok=True)
        with log.open("a") as f:
            f.write(json.dumps(rec) + "\n")
        return rec
