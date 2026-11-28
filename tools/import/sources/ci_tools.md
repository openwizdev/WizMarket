# Source notes: `ci_tools`

- **Catalogs:** Public GitHub repositories (`https://api.github.com/graphql`, REST fallback) and the official Jog site (`https://usejog.com`).
- **Terms & reuse:** Only public repository metadata via GitHub's official API and public HTML meta descriptions from unauthenticated HTTPS GETs are read. Descriptions are stored in `tools/import/manifest/ci_tools.json` for copy-checking; every listing summary is written in our own words.
- **Licence evidence:** GitHub repositories link to their detected licence file (SPDX id, `"other"` for `NOASSERTION`, or `"not stated"` linked to the repository). `jog` (`https://usejog.com`) is a hosted GitHub Actions runner service with no public licence stated on its site, so it is marked `Licence: not stated` linked to `https://usejog.com`.
- **Tagging notes:** `limitr` (`dev-formata-io/limitr`) is tagged `public-source`, `billing`, `usage-limits` (not `ci`), matching what the project actually does. `usejog/joggernaut` is a skills repository and is intentionally excluded here (skills are handled by dedicated skill sources).
