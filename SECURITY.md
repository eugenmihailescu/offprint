# Security policy

**Offprint** is a local CLI that fetches **operator-supplied** URLs. Those URLs are not trusted. A malicious page, redirect, or URL list must not reach private/link-local/metadata networks, `file:`, or unbounded memory.

## Supported versions

| Branch / release      | Supported                                      |
| --------------------- | ---------------------------------------------- |
| `main` (latest)       | Yes — security fixes land here first           |
| Older commits / tags  | Best-effort; please rebase onto current `main` |

There is no LTS train. Pin a commit if you need reproducibility; pull security fixes promptly.

## Reporting a vulnerability

**Do not** open a public GitHub issue for vulnerabilities that could enable:

- SSRF (localhost, link-local, cloud metadata, `file:`, DNS rebinding)
- Arbitrary file read/write on the operator machine
- Unbounded memory / decompression bombs that escape documented caps
- Execution of fetched script or unexpected cookie/session replay

### Preferred channel

1. **GitHub Security Advisories** (private):
   [Report a vulnerability](https://github.com/eugenmihailescu/offprint/security/advisories/new)

2. If Advisories are unavailable, email the address in `pyproject.toml` with subject **`[Offprint security]`**.

### What to include

- Description and impact
- Reproduction steps or a minimal proof-of-concept
- Offprint commit SHA or tag
- Whether you plan a coordinated fix

### What not to include in public channels

- Live cookies, `Authorization` headers, or credentials found on a fetched page
- Exploit chains ready to copy-paste against random hosts

## Scope

In scope:

- SSRF via the operator URL, redirects, sitemaps, feeds, media URLs, or Playwright routes
- XXE / entity expansion in sitemap or HTML parse
- Gzip / XML bombs that bypass the decompressed byte cap
- Cookie jars that replay `Set-Cookie` across a site run
- Path traversal in `--out`, `--save-html`, or `--download-media`

Out of scope unless chained:

- The operator pointing Offprint at a host they are not allowed to fetch (ToS/copyright)
- Denial of service purely by asking the tool to crawl a huge origin (use `--limit` / `--max-urls`)
- Vulnerabilities in sites being extracted, not in Offprint itself
- Downstream CMS apply steps (e.g. MyNix) — report those in the consumer repo

## Safe harbor

If you research in good faith, avoid privacy violations and service disruption, and report privately without exploiting beyond PoC, we will not pursue legal action related to that research.

## Hardening tips for operators

- Do not run Offprint as root
- Do not pass URL lists from untrusted users into a machine with sensitive `localhost` services
- Keep `--ignore-robots` for origins you own
- Treat `--save-html` dumps as copies of public (possibly personal) source data
- Keep Python and dependencies updated
