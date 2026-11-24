# Checkpoint: skills from vendor and creator skills repos (not for merge as-is)

Done: research only. No source module, listings or manifest written yet. No PR opened.
B2's `tools/import/run.py` was not on main or in an open PR on 2026-11-24, so a temporary runner outside the repo is needed.

Repos that exist and are public (SKILL.md count on main; repo licence per GitHub):
anthropics/skills 20 (none at root; every folder but doc-coauthoring has LICENSE.txt, docx/pdf/etc. now Apache-2.0 text: read each),
openai/skills 44 (skills/.curated + skills/.system; folder LICENSE.txt, figma-* LICENSE.TXT = Figma Developer Terms, not open source),
mattpocock/skills 39 MIT, garrytan/gstack 71 MIT, obra/superpowers 15 MIT, vercel-labs/agent-skills 9 (none), vercel-labs/skills 5 MIT,
cloudflare/skills 24 Apache-2.0, huggingface/skills 26 Apache-2.0, supabase/agent-skills 2 MIT, stripe/ai 77 MIT (likely duplicates across plugin dirs),
getsentry/skills 31 Apache-2.0, trailofbits/skills 99 CC-BY-SA-4.0, expo/skills 25 MIT, remotion-dev/skills 14 (none), neondatabase/agent-skills 15 Apache-2.0,
callstackincubator/agent-skills 13 MIT, microsoft/skills 215 MIT (check duplicates), google-labs-code/stitch-skills 16 Apache-2.0, hashicorp/agent-skills 20 MPL-2.0,
firebase/agent-skills 14 Apache-2.0, pulumi/agent-skills 19 Apache-2.0, planetscale/database-skills 4 MIT, browserbase/skills 19 (folder MIT LICENSE.txt), better-auth/skills 6 (none).
Not found (404): cloudflare/agent-skills, stripe/agent-skills.

Gotchas:
- Exclude non-skills: anthropics `template/`, gstack `test/fixtures/...`, nested copies (gstack `capy/`, `openclaw/`, `qm/sandbox/`, hf `hf-mcp/skills/` may duplicate; check).
- Licence order: folder LICENSE*/LICENSE.TXT text > frontmatter `license:` (often just "Complete terms in LICENSE.txt") > repo licence > "not stated". Classify text (Apache/MIT); custom terms (Figma) get a plain label, never a guessed SPDX id.
- Same skill names across repos (pdf, skill-creator, playwright...): first repo in list keeps `skill-<name>`, later ones get `-<owner>`, max 40 chars.
- Tree API: `gh api repos/<r>/git/trees/main?recursive=1` (none truncated); raw SKILL.md via raw.githubusercontent.com.

Next: write `tools/import/sources/skills_repos.py` (NAME, fetch(), REPOS list), notes in `tools/import/sources/skills_repos.md`,
run first ~250 (anthropics, openai, mattpocock, gstack, superpowers, vercel-labs, cloudflare, huggingface, supabase), write own-words summaries, PR 1; rest in PR 2-3. Delete this file before the PR.
