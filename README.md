# WizMarket

The registry behind [openwiz.dev/market](https://openwiz.dev/market): drivers, harnesses and skills for [OpenWiz](https://github.com/openwizdev/OpenWiz), the open source kernel for agent factories that runs fleets of coding agents on your own machines. One JSON file per listing, added by pull request. `main` holds 115 listings today, 18 of them verified.

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

### Drivers and harnesses

Publish a driver or a harness as listing v2, [`contracts/listing.v2.md`](contracts/listing.v2.md). Listing v1 does not change, and every other kind of listing stays on it. Start from the template repository [openwizdev/driver-template](https://github.com/openwizdev/driver-template); the recommended repository name is `<owner>/openwiz-driver-<name>`. The listing's `package` block pins that repository's release, and a `verified` receipt's `# driver:` line is that package's repository and commit.

Field rules, URL rules, what stays private and what makes a listing `verified` (a kit receipt for a driver or harness, a pinned-commit check for a skill) are in the contract, [`contracts/listing.v1.md`](contracts/listing.v1.md). Where this page and the contract differ, the contract wins.

## Check it locally

Needs Python 3.11 on Unix (on Windows, use WSL). To also catch edits to merged receipts, compare against `main`:

```sh
git fetch https://github.com/openwizdev/WizMarket.git main &&
  python3 -I check/check.py check --base FETCH_HEAD
```

For a `verified` skill, `python3 -I check/check.py skill <id>` runs its pinned check on your machine. CI runs the same checks on every pull request.

## Licence

Apache License 2.0: see [LICENSE](LICENSE).
