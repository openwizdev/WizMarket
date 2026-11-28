# WizMarket public-catalog importer

Standard-library Python 3.11 tool for generating `listing.v1` entries from public, reusable catalogs. Every imported listing is labelled as listed from a public source and unverified (`"status": "listed"`, `"publisher": "openwizdev"`).

## Commands

Run from the repository root:

```sh
# Fetch a source, dedupe against listings/, queue entries without summaries in pending/,
# and write listings for entries that have a checked summary.
python3 -I tools/import/run.py <source> --out listings/

# Re-run from tools/import/pending/<source>.json without fetching the source again
# (still checks that listing and link URLs resolve at write time).
python3 -I tools/import/run.py <source> --offline --out listings/

# Run the summary copy-check and marketing-word check over all public-source listings.
python3 -I tools/import/run.py --check-summaries

# Print counts by status, kind tag, source, and pending queue.
python3 -I tools/import/run.py count

# Run the offline unit tests.
python3 -I -m unittest discover -s tools/import -p 'test_*.py'
```

Set `GITHUB_TOKEN` or `GH_TOKEN` (e.g. `GH_TOKEN=$(gh auth token)`) when fetching GitHub-backed sources to use batched GraphQL reads and stay within GitHub's rate limits.

## Conventions

Every imported listing written to `listings/<id>.json` follows `contracts/listing.v1.md` plus these shared rules:

- `publisher`: `"openwizdev"` (OpenWiz listed it; never impersonate a maintainer).
- `status`: `"listed"` (never `"verified"`). `stage`: `"available"`. No `login`, no `proof`.
- `tags`: always starts with `"public-source"`, plus at least one kind tag (`coding-agent-cli`, `sandbox-host`, `ci`, `billing`, `skill`, `skill-collection`, `mcp-server`) and at most a few topical tags (max 8 total). Never `"driver"` or `"harness"`.
- `summary`: one line, at most 140 characters, written in our own words from the source. `--check-summaries` refuses summaries equal to the source description, sharing a run of 5+ consecutive words with it (case-insensitive, punctuation stripped), or using hype/marketing words.
- `links` (in order):
  1. `{"label": "Listed from public source, unverified: <catalog name>", "url": "<source entry URL>"}`
  2. `{"label": "Licence: <SPDX id, 'other', or 'not stated'>", "url": "<licence file URL or repository URL>"}`
     GitHub `NOASSERTION` is labelled `Licence: other` and linked to the licence file; missing licences are `Licence: not stated` linked to the repository or official page.
- **Dedupe:** entries whose normalised URL (lowercase host, `www.` stripped, trailing `/` and `.git` stripped) already exists in `listings/` or another source's pending queue are skipped. On an `id` clash with a different URL, `-<owner>` is appended (truncated to 40 chars).
- **No silent overwrites:** re-running a source refreshes metadata in `listings/` and `tools/import/manifest/<source>.json` without overwriting an existing listing's `summary`.
- **Two-step summaries:** a newly fetched entry without a written summary goes to `tools/import/pending/<source>.json`, never straight to `listings/`.

## Source plug-in interface

Add a new catalog as `tools/import/sources/<source>.py` and document its terms and licence evidence in `tools/import/sources/<source>.md` (keep catalog notes per-source to avoid merge conflicts).

Each plug-in exports:

- `NAME`: default catalog display name (string).
- `fetch() -> list[dict]`: network calls happen here only. Each returned dict has:
  - `id`: lowercase slug (2–40 chars, `[a-z0-9-]`)
  - `name`: project's own name (one line)
  - `source_description`: raw description from the source (stored in `manifest/<source>.json`, not the listing)
  - `url`: public `https://` home (repository if public, else official site)
  - `licence`: SPDX id, `"other"` (for `NOASSERTION` / custom licence files), or `"not stated"`
  - `licence_url`: `https://` link to the licence file, or the repository/site when not stated
  - `source_url`: `https://` catalog page or entry URL
  - `tags`: list of 1–7 tags (must include a kind tag; `"public-source"` is added automatically)
  - `plugs_into`: one line describing where it fits an OpenWiz fleet
  - `catalog` *(optional)*: overrides `NAME` for that specific entry

Helpers for public GitHub API reads (batched GraphQL + REST fallback), HTML meta descriptions, and URL resolution live in `tools/import/fetching.py`.
