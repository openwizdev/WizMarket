# Checkpoint: B7 GitHub long-tail skills (stopped early, owner's order)

Done:
- `tools/import/sources/github_skills_wip/discover.py`: repo search by topic, split by star range to stay under the 1000-result cap; stars>=10, pushed>=2025-11-24, archived:false (forks excluded by default).
- `repos.json` (same folder, sorted by stars): 2351 candidate repos from topics claude-code-skills, codex-skills, skill-md, skillsmp, claude-skill, agent-skill. Has stars, licence spdx_id, pushed_at, default_branch, topics.

Next:
1. Run discover.py for the big topics too: agent-skills (~4.7k), claude-skills (~2k), skills (~2.6k, needs SKILL.md check).
2. Filter: licence not null/NOASSERTION/"other"; skip owners anthropics, openai, mattpocock, garrytan, and B6's PR repos (check `gh pr list -R openwizdev/WizMarket`; likely vercel(-labs), cloudflare, huggingface, supabase, stripe, getsentry, trailofbits, obra).
3. Per repo (by stars), `git/trees/<branch>?recursive=1` to confirm a real SKILL.md and list skill folders (1 core call/repo; core quota is shared, ~4k/hr left when I stopped).
4. Write `tools/import/sources/github_skills.py` (NAME, fetch()) per B2's plug-in interface; no run.py on main yet and no B2 PR open, so use a temp script outside the repo.
5. Write summaries in own words (no 5-word run shared with source description), listings + manifest, batches of ~400; per-skill listings only for 50+ star repos.
Gotchas: search API 30/min; nothing committed under listings/ yet; delete github_skills_wip/ and this file before the PR.
