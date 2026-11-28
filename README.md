# WizMarket

The registry behind [openwiz.dev/market](https://openwiz.dev/market): drivers, harnesses and skills for [OpenWiz](https://github.com/openwizdev/OpenWiz), the open source kernel for agent factories that runs fleets of coding agents on your own machines. One JSON file per listing, added by pull request. `main` holds 54 listings today, 18 of them verified.

## Publish your own

1. **Fork** this repository.
2. **Add `listings/<id>.json`**, where `<id>` is 2 to 40 lowercase letters, digits or hyphens. Start from the minimal example:

   ```json
   {
     "name": "My tool",
     "summary": "A small tool that does one thing for OpenWiz fleets.",
     "tags": ["mcp-server"],
     "url": "https://example.com/my-tool",
     "plugs_into": "The agent's MCP servers",
     "publisher": "example-publisher",
     "stage": "available",
     "status": "listed"
   }
   ```

3. **Run the check and open a pull request:**

   ```sh
   python3 -I check/check.py check   # prints "check: ok, ..." and exits 0
   ```

Field rules, URL rules, what stays private and what makes a listing `verified` (a kit receipt for a driver or harness, a pinned-commit check for a skill) are in the contract, [`contracts/listing.v1.md`](contracts/listing.v1.md). Where this page and the contract differ, the contract wins.

## Check it locally

Needs Python 3.11 on Unix (on Windows, use WSL). To also catch edits to merged receipts, compare against `main`:

```sh
git fetch https://github.com/openwizdev/WizMarket.git main &&
  python3 -I check/check.py check --base FETCH_HEAD
```

For a `verified` skill, `python3 -I check/check.py skill <id>` runs its pinned check on your machine. CI runs the same checks on every pull request.

## Review a listing with Jev

`python3 -I check/check.py review` reads the same tree as `check` and does not change what `check` accepts. Proof kind stays the tag rule in the contract: `driver` or `harness` is a receipt, `skill` is a pinned check, both tags need both, and any other tag needs neither.

With `TYPESAFE_API_KEY` set, Jev (`POST https://api.typesafe.ai/v1/systemone`, model `jev-1.14.0`) answers three Nouls in that one request: is it a driver, a harness, and a skill. Code combines the confident yeses with `KIND_WEIGHT_DRIVER`, `KIND_WEIGHT_HARNESS`, and `KIND_WEIGHT_SKILL`. Pass `--public-work-links` to confirm `being-built` first links are public; when set, the same request also asks whether `first_link` (scheme, host, and path only, skipping private hosts and credential-bearing URLs) is a work item and whether it is about this listing, then combines those with `WORK_WEIGHT_ITEM` and `WORK_WEIGHT_ABOUT`. The check still accepts that link as a URL only. The same request scores how specifically `summary` says what the listing does and what it plugs into, combined with `SUMMARY_WEIGHT_DOES` and `SUMMARY_WEIGHT_PLUG`. The length rule still accepts the line. A receipt stays done only when its pass lines match exactly. Eight Nouls on that receipt, in their own request, are combined with `RECEIPT_WEIGHTS` and printed only as a note when they confidently disagree. Each Noul is compared directly against the inclusive `0.7` (yes) and `0.3` (no) thresholds (`abs(2p - 1) >= 0.4` in exact arithmetic). Strictly between `0.3` and `0.7` on any Noul, or a Score confidence below `0.7`, or no key or a failed call, that reading stays the deterministic fallback. The key is read only from the environment.

**Data scope and timeouts:** when `TYPESAFE_API_KEY` is set, listing requests send only `name`, `summary`, and `plugs_into` (plus `first_link` scheme, host, and path for public URLs when `--public-work-links` is passed; never `tags` or `url`), and receipt text is sent in its own separate request; prose or receipts caught by the privacy scan are never sent. By default, `review` sends only listings and receipts whose content matches `refs/remotes/origin/main`; untracked drafts, local edits, unmerged branch commits, and checkouts without `origin/main` stay local and fall back to the deterministic rules. Select specific listings (`python3 -I check/check.py review <id> ...`), pass `--rev <rev>` to read a commit's tree, or pass `--include-unpublished` to opt in to sending unpublished working-tree listings and receipts. `review` enforces an overall `--deadline` (default 60 seconds) and stops calling TypeSafe after a service-wide failure, falling back to the deterministic rules for the remaining listings and receipts.

```sh
python3 -I check/jev_bench.py
python3 -I check/jev_bench.py --live   # asks Jev; needs TYPESAFE_API_KEY
```

The first command compares the tag rule and a keyword baseline with hand-labeled prose in `check/jev_fixtures.json`. `--live` adds Jev's agreement on that same set.

## Licence

Apache License 2.0: see [LICENSE](LICENSE).
