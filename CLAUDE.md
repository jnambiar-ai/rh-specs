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

## Box Drive rules (hard)
- Never delete, move, rename, edit, copy, share or create anything inside the Box Drive folder.
- Never run shell commands, editors or file tools with a path inside it. Never open or read file
  contents there (Box Drive downloads on open) and never touch 3D model files.
- The ONLY allowed interaction is `python scripts/box_drive_index.py "<box folder>"`, which lists
  metadata and writes its csv outside Box. Start with one subfolder, then widen.
- Work from the resulting csv. Deny write/edit permissions for the Box path in local settings.

## Setup
    python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
    pip install httpx pdfplumber pymupdf pandas pytest
    python -m pytest -q

## Downstream use
- The user generates images with ChatGPT Images 2.5 (OpenAI, announced 2026-09-08; API models
  GPT-Image-2.5 Flare and Sunburst). They dropped the request to review their prompt-generation
  engine, so do not ask for it again unless they bring it up.
- The specs exist to pick reference images and keep scale accurate in prompts. Proposed, pending the
  user's OK: an extra `prompt_dims` text column per row (e.g. `96" W x 40" D x 34" H; seat 18"; arm 26"`).
