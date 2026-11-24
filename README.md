# WizMarket

The open registry behind [openwiz.dev/market](https://openwiz.dev/market): drivers, harnesses, skills and loops for [OpenWiz](https://github.com/openwizdev/OpenWiz), the agent factory for the coding agents you already have.

**On `main` today: 54 listings, 18 verified.** That's 20 skills, 15 harnesses, 13 drivers, 5 loops and 1 plugin. The market page shows what's merged here after its next registry refresh.

**Why publish here:** you add one JSON file by pull request, and you need nothing but a GitHub account. A `verified` badge is earned by a real test: a kit receipt from the real host for a driver or harness, or the skill's own check at a pinned commit. The registry is Apache-2.0 and owned by no one.

## Publish your own

Fork the repository and add `listings/<id>.json`. The `<id>` is 2 to 40 lowercase letters, digits or hyphens, and is not written inside the file:

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

Keep `status` as `listed` unless you add your kind's [proof](contracts/listing.v1.md#verified-by-kind). Keep it public: no secrets, no private ids, no local paths ([rules](contracts/listing.v1.md#nothing-private)). The contract, [`contracts/listing.v1.md`](contracts/listing.v1.md), is the whole rulebook, covering fields, URLs, proofs and the [receipt format](contracts/listing.v1.md#the-receipt). Where this page and the contract differ, the contract wins.

## Check it locally

Use Python 3.11 on Unix (WSL on Windows). From the repository root:

```sh
python3 -I check/check.py check
```

It prints `check: ok, ...` and exits 0, or lists the problems and exits 1. Then open a pull request; the template lists what review looks for.

To check receipt history too, run `git fetch https://github.com/openwizdev/WizMarket.git main` and add `--base FETCH_HEAD`. To run a `verified` skill's check yourself, use `python3 -I check/check.py skill <id>`. CI checks receipt history on every pull request, and runs the skill check on each one that adds or changes a `verified` skill.

## Licence

[Apache License 2.0](LICENSE).
