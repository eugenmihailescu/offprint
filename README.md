# Offprint

Extract the article from a URL or a whole site. Emits structured JSON (title, body HTML, metadata) — not CMS rows, not a scraper toolkit.

Offprint is a CLI and library. It fetches a public page (or discovers a site via sitemap and RSS/Atom), strips chrome, and writes a versioned `offprint-article` JSON document or a JSONL corpus. It does not import into a CMS.

```text
offprint https://old.blog/2020/foo/
offprint extract https://old.blog/2020/foo/ --out article.json --pretty
offprint --origin https://old.blog --out corpus.jsonl
```

Single-URL extract writes `offprint-article` JSON to stdout (or `--out`). `--save-html DIR` stores the raw fetch as `{sha256}.html` and records the path on `provenance`.

Site mode discovers posts from sitemaps and RSS/Atom, then writes JSONL plus `{out-dir}/manifest.json` and `{out-dir}/state.json` (canonical keys). If `--out` already exists, pass `--overwrite` or `--resume` (append JSONL, skip keys already in `state.json`). `--retry-failed` is not v1; failed URLs are not in `state.json`, so `--resume` will try them again. Default delay is 0.5s per host (polite); robots.txt crawl-delay is respected and clamped at 10s.

`--probe-media` fills `media[].mimeType` / `byteSize` via HEAD (GET `Range` fallback, 5s, SSRF). `--download-media DIR` writes `{sha256}.{ext}` after a successful extract (20 MiB cap, same SSRF policy). Default **off**. Probe/download failures are warnings, not article failures.

```bash
offprint schema              # offprint-article JSON Schema
offprint schema --run        # offprint-run manifest schema
python -m offprint URL
offprint --origin https://old.blog --out corpus.jsonl --overwrite --delay 0.5
offprint --origin https://old.blog --out corpus.jsonl --resume
offprint extract URL --probe-media --download-media ./media
```

## Install

Git-only until a consumer exists. **Not on PyPI.**

```bash
pip install "git+https://github.com/eugenmihailescu/offprint"
```

For development:

```bash
python -m pip install -e ".[dev]"
offprint --version
offprint --help
```

Python 3.12 or newer.

Optional SPA fallback (`offprint[browser]`). Chromium is **not** bundled:

```bash
pip install "offprint[browser] @ git+https://github.com/eugenmihailescu/offprint"
playwright install chromium
```

For a local checkout: `pip install -e ".[browser]" && playwright install chromium`.

`--browser` always tries Playwright (exit 2 if the extra is missing). `--no-browser` never does. Omitting both falls back only when the extra is installed and the HTML overlay is empty. With `--browser`, site `--concurrency` defaults to 2 (cap 4). Ordinary blogs do not need this extra.

## Non-goals (v1)

- Writing another CMS’s tables or editor documents (TipTap, Puck, WordPress WXR)
- Comments, drafts, private, member, or paywall content
- Reconstructing page-builder blocks as objects
- A hosted HTTP API
- Screenshots or PDFs as the article body
- AI as the primary extractor

## Operator notes

You are responsible for the terms of service and copyright of anything you fetch. `--save-html` stores **raw** page bytes and may include personal data that was already public on the source page. Default fetch policy respects `robots.txt`; `--ignore-robots` is for sites you own.

## License

[MIT](LICENSE) © 2026 Eugen Mihailescu
