# Partner listing drafts

Draft listings for products made by other teams. They stay on this branch until the maker says yes. Each maker either opens the pull request from their own account (copy the listing file into `listings/` on a fork) or agrees that OpenWiz opens it on their behalf, credited to them. Nothing here goes to `main` without that yes.

All three pass `python3 -I check/check.py check` on this branch. Each is `listed`. Notes below say what was tried on 2026-11-24 and what a `verified` listing would still need.

| Draft | Maker | Kind | Status |
| --- | --- | --- | --- |
| [`listings/joggernaut.json`](../../listings/joggernaut.json) | Jog (`usejog`) | skill | `listed`. A `verified` proof is ready and passes WizMarket's skill check; it needs the maker's OK on the check command |
| [`listings/jog.json`](../../listings/jog.json) | Jog (`usejog`) | CI runner | `listed`. Not a `driver`, `harness` or `skill`, so there is no `verified` test yet |
| [`listings/limitr.json`](../../listings/limitr.json) | Formata (`dev-formata-io`) | skill + library | `listed` |

`publisher` is set to each maker's GitHub organisation. A maker who opens the pull request from a personal account can put their own login there.

## Joggernaut and Jog

**What it is.** [Joggernaut](https://github.com/usejog/joggernaut) (MIT) is seven agent skills for GitHub Actions CI: `ci-diagnose` (read-only, through your own `gh`), `ci-cache`, `ci-workflow`, `ci-slow-tests`, `ci-flaky-tests`, `ci-measure` and `ci-guard`. Its rules: measure CI's own runs before and after, keep every test running, one fix per pull request. It works on any GitHub Actions repository and does not need a Jog account. Jog itself is drop-in runners for private repositories (`runs-on: jog`), with a separate [right-size skill](https://usejog.com/skills/jog/SKILL.md) that reads Jog's own measurements (a Jog account and a browser-approved token are needed).

**What we tried.** Joggernaut at `010072c49018bfb5e9dbe01e4fdf4530c8ef7ff4`, copied into a scratch repository. We ran `ci-diagnose`'s read-only `fetch` and `split`, then `ci-flaky-tests`, against the last 150 `pull_request` runs of OpenWiz's `ci.yml`. We changed nothing in OpenWiz and opened nothing there. The fetch took 5m 09s and 232 GET requests. We checked three runs by hand against `gh run view`, and all 21 job timings matched.

**What it found.**
- The median PR wait was 20m 10s. On every passing run the slowest path was the same: one long release test leg, then the two gate jobs. Waiting for a runner was 6s. Nearly all the time was tests running.
- Its top lead is one serial test block of about 11 minutes inside that leg. Moving it to its own parallel job models about 8 minutes off the median. That is a ceiling, not a measured result; `ci-measure` would measure it after a change.
- 31% of runner-minutes (967 of 3,102) went to failed or cancelled runs. Most cancellations were older runs replaced by a newer push, so the cancelling already works as intended.
- No rerun-based flakes, because every sampled run was a first attempt. One test failed on two different commits, which is a lead to look at, not a proven flake.

**Rough edges (for the maker).**
- The default setup matcher counted two test steps named "installer" as setup (2m 30s, against 36s after a reviewed pattern). An agent that doesn't read the workflow could rank the wrong cause.
- `cachelog` could not read job logs with GitHub CLI 2.100.0, which refuses output with terminal escapes unless `--allow-escape-sequences` is passed.
- `python3 -I tools/selftest.py` stops with `No module named 'selftest_hook'`, because isolated mode leaves the script's folder off the import path. Without `-I` it passes.
- The fetch used 232 requests against the README's estimate of about 155 (extra pull-request base lookups).

**Verdict: helps partly.** It found the real bottleneck fast and suggested a sensible next experiment. Accurate numbers still needed a person to read the workflow.

**Verified, if the maker agrees.** With this proof, WizMarket's own `python3 -I check/check.py skill joggernaut` cloned the pinned commit and passed (exit 0):

```json
"status": "verified",
"proof": {
  "source": "usejog/joggernaut@010072c49018bfb5e9dbe01e4fdf4530c8ef7ff4",
  "check": "python3 tools/check.py && python3 tools/selftest.py"
}
```

## Limitr

**What it is.** [Limitr](https://github.com/dev-formata-io/limitr) (Apache-2.0; npm `@formata/limitr`, PyPI `limitr`) is a policy engine for usage limits, metering and pricing. It runs inside your process. Limitr Cloud is the hosted side. The repository also ships agent skills and a Claude Code plugin for writing and debugging policies.

**What it can plug into in OpenWiz.**

| OpenWiz need | Limitr API | Where it plugs in |
| --- | --- | --- |
| Cap builder starts per fleet | `reserve()`, then `settle()` or `release()`; refusals say `limit` or `held` | A driver v1 wrapper on `start`. Tried: see below |
| Gate before a start | `check()` (preview) and `held()`; `reserve()` at the real start | A fleet or loop check that defers a wake, plus the wrapper at dispatch |
| Meter merged pull requests | `allow(id, entitlement, 1, event, undefined, true)` for a merge that already happened; `addHandler()` for `meter-overage` | An outside reader of confirmed merges, with its own dedupe record |
| Per-repository deals | `ensureCustomer()`, `createCustomerOverride()`, `setCustomerRules()` | One Limitr customer per repository |
| Live policy change | Limitr Cloud publish; local `setPlan()` | Policy, not code |

**What we tried.** A wrapper driver from a community build night caps builder starts through `reserve`/`settle`/`release` around OpenWiz's template driver. It is not public yet. We ran OpenWiz's five-check driver kit on it locally (OpenWiz at `f45763747a8cd9fddd9e3067690bdb1b3a8f4f89`, `@formata/limitr` 0.8.9), with a local tracker and the kit's synthetic harness, so nothing was written to GitHub.
- As shipped: 2 of 5. `version` and `token` pass. `start` fails because the wrapper forwards the template's `effort` capability but its README has no `Effort:` line. `wake` and `stop` don't run.
- A copy with only that README fix: 5 of 5.
- With the budget used up, `start` refuses in driver v1's error shape: `{"error":"Limitr refused: reason \"limit\", ...","next":"raise the start_builder limit ..."}`.
- The build-night demo still runs: 3 of 4 sequential starts and exactly 3 of 10 parallel starts are allowed at a limit of 3.

**Before a `driver` listing could be `verified`.** The wrapper needs a public repository at a pinned commit, the README fix, input checks before it reserves, durable budget state, and a real-host kit receipt on a throwaway ticket. Until then, the draft lists Limitr's own skills and engine, not the wrapper.
