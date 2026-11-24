# WizMarket

The OpenWiz marketplace registry: one small file per listing, added by pull request.

WizMarket is the registry behind [openwiz.dev/market](https://openwiz.dev/market): drivers, harnesses, skills and anything else you built for OpenWiz. Anyone with a GitHub account can publish here. You add one file in a pull request; once it passes the check and is reviewed and merged, it is in the registry the market page is built from.

The format is [`contracts/listing.v1.md`](contracts/listing.v1.md), merged on `main`. It is the whole rulebook: where this page and the contract differ, the contract wins.

## Publish your own

1. Fork this repository.
2. Pick an id for your listing: 2 to 40 characters, each a lowercase letter, a digit or a hyphen. The id is the file's name; don't write it inside the file.
3. Add one file, `listings/<id>.json`. Start from this minimal listing, `listings/my-tool.json`:

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

   - `name`, `summary` (at most 140 characters), `plugs_into` and `publisher` (your GitHub login) are each one line.
   - `tags` are yours to choose: 1 to 8, each made of lowercase letters, digits and hyphens, none twice. They say what it is: `driver`, `harness`, `skill`, `mcp-server`, anything.
   - `url` is where to get it. Follow the [contract's URL rules](contracts/listing.v1.md#a-listing) for this field and every link.
   - `stage` is `available`, or `being-built`. A `being-built` listing needs `links`, and its first link is the public pull request or ticket where it is being built.
   - Optional fields are `login` (one line saying where the login lives) and `links`. If you include `links`, give it at least one entry. Each entry has a one-line label in `label` and its URL in `url`. Omit `links` when you have no links. Only the contract's fields are allowed.
   - Leave `status` as `listed` unless you add your kind's proof (below).
4. Keep it public: no token, key or password, no private id (a thread, session or machine id) and no path on your own machine, such as one in your home folder. Hosts, logins, commits and public GitHub links are fine.
5. Run the check locally (below), then open a pull request. The template lists what the reviewer looks for.

## What `verified` means

`listed` is a link, not proven. `verified` means the listing passed its kind's test, and your tags decide which test:

- **Tag `driver` or `harness`:** a kit receipt from the real host. Run OpenWiz's `kernel/driver-kit/kit.py` on that host. Before saving the receipt, replace the status-note comment ID at the end of both `pass start:` and `pass wake:` with the literal `<note>`. Keep the raw output and the throwaway repository and ticket out of the public pull request. Save the redacted output in the contract's [receipt format](contracts/listing.v1.md#the-receipt) at `receipts/<id>/<date>-<commit>.txt` (`<date>` is the run's date, `<commit>` the first 12 characters of its driver commit), and set `"proof": {"receipt": "receipts/<id>/<date>-<commit>.txt"}`. Keep merged receipts intact.
- **Tag `skill`:** the skill's own check, passing at a pinned commit. Set `"proof": {"source": "<owner>/<repo>@<40-hex commit>", "check": "<command>"}`. WizMarket's CI clones that public GitHub repository, checks out that exact commit and runs the command from its root, with no secrets, read-only permissions and a time limit. Exit 0 is a pass.
- **Both** (`driver` or `harness`, and `skill`): `proof` holds all three keys, and both proofs must pass.
- **Any other tags:** `verified` is refused. Keep `listed` until your kind gets its own test.

A `verified` listing without its kind's proof is refused: drop it to `listed`, or add the proof. A `listed` listing has no `proof`.

## Check it locally

Use Python 3.11 in a Unix environment. On Windows, run these commands inside Windows Subsystem for Linux (WSL). From the root of your checkout, run

```sh
python3 -I check/check.py check
```

The command checks the contents of `listings/` and `receipts/` in your working tree. It prints `check: ok, ...` and exits 0 when the contents pass. It reports any problems and exits 1.

To check receipt history too, fetch WizMarket's `main` (the pull request's base branch) and pass the fetched commit to `--base`:

```sh
git fetch https://github.com/openwizdev/WizMarket.git main &&
  python3 -I check/check.py check --base FETCH_HEAD
```

This also catches edits to or deletions of merged receipts. On each pull request, CI validates the candidate commit and compares its receipts against the pull request's base commit.

For a `verified` skill, `python3 -I check/check.py skill <id>` clones your source at its pinned commit and runs its check on your machine. CI runs the same check, isolated, on every pull request that adds or changes a `verified` skill listing.

## Licence

Apache License 2.0: see [LICENSE](LICENSE).
