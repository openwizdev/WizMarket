# Source notes: `sandbox_hosts`

- **Catalogs:** Public GitHub repositories (`https://api.github.com/graphql`, REST fallback) and official public product/documentation pages (`https://www.daytona.io`, `https://docs.fly.io/machines`).
- **Terms & reuse:** Only public repository metadata via GitHub's official API and public HTML `<meta name="description">` / `og:description` tags from unauthenticated HTTPS GETs are read. No login-gated pages are accessed. Descriptions are kept in `tools/import/manifest/sandbox_hosts.json` for copy-checking; listing summaries are written in our own words.
- **Licence evidence:** GitHub repositories link to their detected licence file (SPDX id, `"other"` for `NOASSERTION`, or `"not stated"` linked to the repository). Hosted commercial platforms without an active public repo (`daytona`, whose earlier `daytonaio/daytona` repo is archived, and `fly-machines`) are marked `Licence: not stated` linked to their official page.
- **Exclusions:** Hosts already listed in WizMarket (`boat-dev`, `cloudroom`, `codespaces`, `fly-sprites`, `local`, `openhands-cloud`, `pane`, `warp-oz`) are excluded.
