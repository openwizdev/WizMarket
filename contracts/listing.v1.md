# WizMarket listing, version 1 (`listing.v1`)

WizMarket is the registry behind [openwiz.dev/market](https://openwiz.dev/market). Anyone can list something they built for OpenWiz by adding one file here in a pull request. This page is the whole format: the listing file, how a listing is verified, the receipt, what stays out, and the index the market page reads.

`listing.v1` is a public format. It never changes: a later change adds `listing.v2` beside it.

The JSON Schema for one listing file is [`schema/listing.v1.json`](../schema/listing.v1.json). The id rule, the no-repeated-key rule, the kind rules and the receipt are checked by `check/check.py`, not by the schema. Synthetic examples, valid and broken, are in [`fixtures/`](../fixtures/).

## A listing

One listing is one file, `listings/<id>.json`.

- **The id** is the file's name without `.json`: 2 to 40 characters, each a lowercase letter, a digit or a hyphen. The id is not written inside the file.
- **The file** is standard JSON in UTF-8: one object, no key twice, and only the fields below.

| Field | Required | What it holds |
| --- | --- | --- |
| `name` | yes | The listing's name. One line. |
| `summary` | yes | What it is, in one line of at most 140 characters. |
| `tags` | yes | 1 to 8 tags you choose, each made of lowercase letters, digits and hyphens, none twice. Tags say what the listing is: `driver`, `harness`, `skill`, `mcp-server`, anything. |
| `url` | yes | Where to get it: an `https://` URL. |
| `plugs_into` | yes | What in OpenWiz it plugs into. One line. |
| `publisher` | yes | Your GitHub login. |
| `stage` | yes | `available`, or `being-built`. A `being-built` listing needs a `links` entry to its public pull request or ticket on GitHub (`https://github.com/<owner>/<repo>/pull/<n>` or `.../issues/<n>`). |
| `login` | no | Where the login lives, as the Drivers page says it, for example "your own `claude` login on your computer". One line. |
| `links` | no | A list of at least one `{"label": "<one line>", "url": "https://..."}`. |
| `status` | yes | `listed` or `verified`. `listed` is a link, not proven. `verified` means it passed its kind's test (below). |
| `proof` | when verified | What proves it. Required when `status` is `verified`, and absent when it is `listed`. |

"One line" means at least one character and no line break or other control character.

A minimal listing, `listings/my-tool.json`:

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

## Verified, by kind

Your tags decide what proves a `verified` listing.

- **Tag `driver` or `harness`:** a kit receipt from the real host. `proof` is `{"receipt": "receipts/<id>/<date>-<commit>.txt"}`, where `<id>` is this listing's id, `<date>` is the receipt's `# date:` and `<commit>` is the first 12 characters of its `# driver:` commit. The receipt's format is below.
- **Tag `skill`:** the skill's own check, passing at a pinned commit. `proof` is `{"source": "<owner>/<repo>@<commit>", "check": "<command>"}`: a public GitHub repository, a full 40-character lowercase hex commit, and one command line. WizMarket's CI clones that repository, checks out that exact commit and runs the command from its root, in a job with no secrets, read-only permissions and a time limit. Exit 0 is a pass.
- **Tagged both** (`driver` or `harness`, and `skill`): `proof` holds all three keys, and both proofs must pass.
- **Any other tags:** `verified` is refused. The listing is `listed` until its kind gets its own test, in a later version of this contract.

`proof` holds only the keys its kind needs. A `verified` listing without its kind's proof is refused: drop it to `listed`, or add the proof.

## The receipt

A receipt is a plain text file at the path `proof.receipt` names. It is exactly 14 lines, in this order, each ending in a newline (`\n`), with nothing before, between or after them:

```text
# listing: <id>
# host: <the real host the kit ran on>
# driver: <owner>/<repo>@<40-hex commit>
# kit: openwizdev/OpenWiz@<40-hex commit>
# harness: <harness>
# model: <model>
# date: <YYYY-MM-DD>
# run by: <GitHub login>
pass version: <what kit.py printed>
pass start: <what kit.py printed>
pass wake: <what kit.py printed>
pass stop: <what kit.py printed>
pass token: <what kit.py printed>
Result: 5 of 5 pass
```

- `# listing:` is this listing's id.
- `# host:` is the real host the run used, for example `local`, `boat.dev` or `Cloudroom`.
- `# driver:` is the driver's repository and the exact commit the kit ran against. A harness listing names the driver its harness ran on.
- `# kit:` is the OpenWiz commit whose `kernel/driver-kit/kit.py` ran.
- `# harness:` and `# model:` are the harness and model the run used.
- `# date:` is the run's date, in UTC.
- The `# driver:` and `# kit:` commits are full 40-character lowercase hex.
- `# run by:` is the GitHub login whose `gh` the kit read with.
- Each header value is one line, after exactly one space.
- Lines 9 to 13 are kit.py's standard output, copied verbatim: its five `pass` lines, in that order. A `fail` line, a missing line or another order is refused.
- Line 14, `Result: 5 of 5 pass`, is written by whoever writes the receipt, after kit.py exits 0. kit.py does not print it.

The pull request that adds the receipt is its public record. The throwaway repository and ticket the kit used never appear in it.

## Nothing private

Listings and receipts are public. They never hold:

- anything shaped like a token, key, password or other credential;
- a private id (a thread, session or machine id, or a private repository's records);
- a machine path (for example `/home/…`, `/Users/…`, `C:\…`).

Hosts, logins, commits and public GitHub links are fine. The receipt's `pass token:` line is part of the format, not a credential: a privacy scan must not refuse it for the word `token:` alone.

## The index

`python3 -I check/check.py index` prints the registry index: the one shape consumers read, such as openwiz.dev's market page, from a saved copy. It prints only when the whole registry passes `check`; otherwise it exits 1 like `check`.

The index is one JSON object, in UTF-8, keys sorted, indented by two spaces, ending in a newline:

- `contract`: `"listing.v1"`.
- `commit`: the 40-hex WizMarket commit the index was made at.
- `listings`: every listing, sorted by id. Each is the listing file's fields as written (optional ones only when present), plus `id`. For a `verified` listing, `proof` is replaced by what was checked, one key per proof kind:
  - `receipt`: `{"path": "<the receipt's path>", "date": "<its # date:>", "url": "https://github.com/openwizdev/WizMarket/blob/<the index's commit>/<path>"}`;
  - `skill`: `{"source": "<owner>/<repo>@<commit>", "check": "<command>", "url": "https://github.com/<owner>/<repo>/tree/<commit>"}`, with the source's own commit.

A `listed` listing has no `proof`.

[`fixtures/index.json`](../fixtures/index.json) is the synthetic index of the five valid fixtures' listings and receipts, made at the synthetic commit `dddddddddddddddddddddddddddddddddddddddd`.
