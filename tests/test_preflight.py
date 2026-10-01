import importlib.util
import json
from pathlib import Path

import httpx

from rh_specs.fetch import Fetcher

spec = importlib.util.spec_from_file_location(
    "preflight", Path(__file__).resolve().parents[1] / "scripts" / "preflight.py")
preflight = importlib.util.module_from_spec(spec)
spec.loader.exec_module(preflight)


def make(handler):
    client = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True)
    return Fetcher(client=client, min_interval=0, sleep=lambda s: None)


def test_happy_path_saves_files(tmp_path):
    def handler(req):
        if req.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nDisallow: /cart\nSitemap: https://www.rh.com/sm1.xml")
        if req.url.path.endswith(".pdf"):
            return httpx.Response(200, content=b"%PDF-1.4", headers={"content-type": "application/pdf"})
        return httpx.Response(200, text="<urlset/>", headers={"content-type": "application/xml"})

    assert preflight.run(make(handler), root=tmp_path, out=lambda *_: None) == 0
    assert (tmp_path / "data/raw/tearsheets/Leather_Maxwell.pdf").read_bytes() == b"%PDF-1.4"
    saved = json.loads((tmp_path / "data/discovery/preflight_summary.json").read_text())["saved"]
    assert any("sitemap_" in s for s in saved)


def test_block_stops_and_reports(tmp_path):
    calls = []

    def handler(req):
        calls.append(req.url.path)
        return httpx.Response(403, text="Access Denied")

    assert preflight.run(make(handler), root=tmp_path, out=lambda *_: None) == 2
    assert calls == ["/robots.txt"]  # stopped on the first block, no retries, no PDF attempt
    assert json.loads((tmp_path / "data/discovery/preflight_summary.json").read_text())["blocked"]
