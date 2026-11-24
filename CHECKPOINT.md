# Checkpoint: B2 importer (market/import-tool)

Done:
- `tools/import/run.py` (untested draft): run_source (dedupe by normalised URL/id, `-<owner>` on id clash, pending/ for entries without a summary, never overwrites an existing summary, at-write-time URL check, manifest), `--offline`, `--check-summaries` (one line, <=140, no 5-word run/equality with source, marketing-word list), `count`.
- `tools/import/fetching.py`: GitHub repo facts (licence: SPDX id, `other` for NOASSERTION, `not stated` -> repo URL; drops archived/private), site meta description, `resolves()`.
- check.py timing: 5,054 listings in 1.0 s. No fix needed.
- `tools/import/CANDIDATES.tsv`: gh api facts for candidate repos (name, archived, fork, private, stars, licence, homepage, description). Delete before the PR.

Next:
1. Unit tests `tools/import/test_run.py` (offline, fake entries; call run_source with resolves=lambda u: True). Then README (conventions, plug-in interface incl. optional per-entry `catalog`, licence `other` rule, terms relied on).
2. Sources `sources/agent_clis.py`, `sandbox_hosts.py`, `ci_tools.py`: seed lists -> fetch() via fetching.repo / site_description. Write summaries in pending/, rerun `--offline`.
3. PR per brief; body: counts, copy-check, timing.

Gotchas:
- `python3 -I` drops the script dir from sys.path: run.py inserts HERE itself; plug-ins are loaded by file path.
- Skip (already OpenWiz harness/driver rows or listings): Claude Code, Codex, Antigravity (agy), Amp, Warp Oz, Fly Sprites, OpenHands, plus all 54 listings/ entries.
- Many repos were renamed (gh api returns canonical full_name: e.g. Codebuff->CodebuffAI/freebuff, forge->tailcallhq/forgecode, Kode->Kode-CLI, microsandbox->superradcompany). Archived (skip or use site): daytona (use daytona.io), refact, gpt-engineer, Roo-Code, coder/agentapi.
- Jog: https://usejog.com (GitHub Actions runners) -> `ci`. Limitr (https://limitr.dev, dev-formata-io/limitr) is usage billing/limits, NOT CI: needs the lead's decision on a kind tag; don't tag it `ci`. usejog/joggernaut is skills (B6/B7 own skills).
