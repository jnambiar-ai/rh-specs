import json

import httpx
import pytest

from rh_specs.fetch import BlockedError, Fetcher, RobotsDisallowed


def make(handler, **kw):
    client = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True)
    return Fetcher(client=client, **kw)


def test_cache_hit_never_refetches(tmp_path):
    calls = []

    def handler(req):
        calls.append(str(req.url))
        return httpx.Response(200, content=b"%PDF-1.4", headers={"content-type": "application/pdf"})

    f = make(handler)
    dest = tmp_path / "a.pdf"
    f.get("https://x.test/a.pdf", dest)
    f.get("https://x.test/a.pdf", dest)
    assert len(calls) == 1
    assert json.loads((tmp_path / "a.pdf.meta.json").read_text())["status"] == 200


def test_rate_limit_is_at_least_one_second(tmp_path):
    t = [0.0]
    slept = []

    def sleep(s):
        slept.append(s)
        t[0] += s

    f = make(lambda r: httpx.Response(200, content=b"x"), clock=lambda: t[0], sleep=sleep, min_interval=0.1)
    f.get("https://x.test/1", tmp_path / "1")
    f.get("https://x.test/2", tmp_path / "2")
    assert slept and slept[0] == pytest.approx(1.0)


@pytest.mark.parametrize("status", [401, 403, 429])
def test_block_statuses_stop(tmp_path, status):
    f = make(lambda r: httpx.Response(status))
    with pytest.raises(BlockedError):
        f.get("https://x.test/a", tmp_path / "a")


def test_captcha_page_stops(tmp_path):
    f = make(lambda r: httpx.Response(200, text="<html>Please solve this CAPTCHA</html>",
                                      headers={"content-type": "text/html"}))
    with pytest.raises(BlockedError):
        f.get("https://x.test/a", tmp_path / "a")


def test_robots_disallow(tmp_path):
    def handler(req):
        if req.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nDisallow: /private/")
        return httpx.Response(200, content=b"x")

    f = make(handler)
    with pytest.raises(RobotsDisallowed):
        f.get("https://x.test/private/a", tmp_path / "a", robots_dir=tmp_path / "r")
    f.get("https://x.test/public/a", tmp_path / "b", robots_dir=tmp_path / "r")


def test_head_cached_in_log(tmp_path):
    calls = []

    def handler(req):
        calls.append(req.method)
        return httpx.Response(200, headers={"content-length": "10"})

    f = make(handler)
    log = tmp_path / "head.jsonl"
    assert f.head("https://x.test/a.pdf", log)["status"] == 200
    assert f.head("https://x.test/a.pdf", log)["status"] == 200
    assert calls == ["HEAD"]
