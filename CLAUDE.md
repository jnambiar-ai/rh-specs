# RH spec database builder: handoff notes

The full brief is `RH_Spec_Crawler_Brief.md`. Follow its working rules strictly (plan first,
one tested step at a time, never invent numbers, read-only everywhere, polite crawling,
stop on any block and report, secrets only in `.env`).

## Status
- Done: venv deps list, `rh_specs/fetch.py` (cache, 1 req/s, robots, stops on blocks), offline tests,
  `scripts/preflight.py` (+ test). Plan for 1a/1b was approved by the user.
- The cloud sandbox where this started is blocked by RH's CDN (Akamai "Access Denied", even for
  robots.txt). Do not try to get around that. The user chose to run fetching from their own computer.
- Next, in order:
  1. Run `python scripts/preflight.py` on the user's machine. If it prints STOP, tell the user and
     stop. Do not retry, change the User-Agent, or use a headless browser to evade.
  2. Read the saved robots.txt, sitemap files and `Leather_Maxwell.pdf`; then build 1a discovery
     (`rh_specs/discover.py`) and test it offline against those cached files first.
  3. 1b: parse `Leather_Maxwell.pdf`, pass the 7-row fixture in `tests/test_fixture.py` exactly
     (never edit the fixture), then 3 files, then scale.
- Maxwell is an old collection. It is only the parser's test file. Real targets are current
  collections; `sheet_revision` shows how stale each sheet is.

## Setup
    python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
    pip install httpx pdfplumber pymupdf pandas pytest
    python -m pytest -q

## Still needed from the user
- Their prompt-generation engine (add under `prompt_engine/` or paste it; no secrets).
- The exact name of the image model they generate with ("chat gpt 2.5" is not a model name we recognize).
