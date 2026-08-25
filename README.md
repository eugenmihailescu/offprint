# Offprint

Extract the article from a URL or a whole site. Emits structured JSON (title, body HTML, metadata) — not CMS rows, not a scraper toolkit.

Offprint is a CLI and library. It fetches a public page (or discovers a site via sitemap and RSS/Atom), strips chrome, and writes a versioned `offprint-article` JSON document or a JSONL corpus. It does not import into a CMS.

```text
offprint https://old.blog/2020/foo/
offprint extract https://old.blog/2020/foo/ --out article.json --pretty
offprint --origin https://old.blog --out corpus.jsonl
```

Single-URL extract writes `offprint-article` JSON to stdout (or `--out`). `--save-html DIR` stores the raw fetch as `{sha256}.html` and records the path on `provenance`. Site-wide JSONL (`--origin`) is not in this release yet.

```bash
offprint schema              # offprint-article JSON Schema
offprint schema --run        # offprint-run manifest schema
python -m offprint URL
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

Python 3.12 or newer. Optional SPA fallback: `pip install -e ".[browser]"` (Playwright / Chromium; not required for ordinary blogs).

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
