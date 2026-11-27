# WizMarket

The registry behind [openwiz.dev/market](https://openwiz.dev/market): drivers, harnesses and skills for [OpenWiz](https://github.com/openwizdev/OpenWiz), the open source kernel for agent factories that runs fleets of coding agents on your own machines. One JSON file per listing in [`listings/`](listings/), added by pull request.

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

Use Python 3.11 to match CI. On Windows, use WSL. To also catch edits or deletions of merged receipts, compare against `main` with Git:

```sh
git fetch https://github.com/openwizdev/WizMarket.git main &&
  python3 -I check/check.py check --base FETCH_HEAD
```

For a `verified` skill, `python3 -I check/check.py skill -- <id>` runs its pinned check on your machine. CI checks the registry on every pull request and runs the pinned checks in isolation only for verified skill listings the pull request adds or changes.

## Licence

Apache License 2.0: see [LICENSE](LICENSE).
