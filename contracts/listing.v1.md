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
| `url` | yes | Where to get it: an `https://` URL (see URLs, below). |
| `plugs_into` | yes | What in OpenWiz it plugs into. One line. |
| `publisher` | yes | Your GitHub login. |
| `stage` | yes | `available`, or `being-built`. A `being-built` listing needs `links`, and its **first** entry is the work link: the public pull request or ticket where it is being built, on any tracker. |
| `login` | no | Where the login lives, as the Drivers page says it, for example "your own `claude` login on your computer". One line. |
| `links` | no | A list of at least one `{"label": "<one line>", "url": "https://..."}`. |
| `status` | yes | `listed` or `verified`. `listed` is a link, not proven. `verified` means it passed its kind's test (below). |
| `proof` | when verified | What proves it. Required when `status` is `verified`, and absent when it is `listed`. |

"One line" means at least one character and no line break or other control character. Every rule here is about the whole value: a value with a newline anywhere, a final one included, is refused.

The work link of a `being-built` listing is checked only as a URL. The reviewer of the pull request that adds or changes it confirms that it is public and points to the work; the market page shows it as the "being built" link.

**URLs.** Every `url` (the listing's and each link's) is `https://`, then a host, then an optional port, then an optional path, query or fragment:

- The host is a DNS name of two or more labels joined by dots, at most 253 characters. Each label is 1 to 63 ASCII letters, digits or hyphens, and doesn't start or end with a hyphen; the last label has a letter. No IP address, no user name (`user@`), no trailing dot. Write a non-ASCII name in its `xn--` form.
- The port, if any, is `:` and a number from 1 to 65535, without leading zeros.
- The rest starts with `/`, `?` or `#` and holds only printable ASCII, no space. Percent-encode anything else (`%C3%BC` for `ü`).

WizMarket doesn't rewrite URLs: the check and the market page use them exactly as written.

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

- **Tag `driver` or `harness`:** a kit receipt from the real host. `proof` is `{"receipt": "receipts/<id>/<date>-<commit>.txt"}`, where `<id>` is this listing's id, `<date>` is the receipt's `# date:` and `<commit>` is the first 12 characters of its `# driver:` commit. The receipt's format is below. There is at most one receipt per listing, date and driver commit, and the first one written is kept: a writer that finds a file already at its path refuses, writes nothing and replaces nothing, even for a run with another harness or model. A merged receipt never changes: a pull request that edits or deletes one is refused.
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
- Lines 9 to 13 are kit.py's standard output: its five `pass` lines, in that order, verbatim but for one change. A `fail` line, a missing line or another order is refused.
- **The one change:** kit.py's `pass start:` and `pass wake:` lines end with the status note's comment id. In the receipt, that number is replaced by the fixed text `<note>`, and every other character stays as kit.py printed it. Line 10 is exactly `pass start: the run posted builder status note <note>` and line 11 is exactly `pass wake: the run edited builder status note <note>`. A digit run in place of `<note>` is refused. The raw output, with the number, stays in the run's own local record.
- Line 13 is exactly `pass token: no login or token passed through the driver`, the kit's only passing token line. Any other text there is refused.
- Line 14, `Result: 5 of 5 pass`, is written by whoever writes the receipt, after kit.py exits 0. kit.py does not print it.

The pull request that adds the receipt is its public record. The throwaway repository and ticket the kit used never appear in it.

## Nothing private

Listings and receipts are public. They never hold:

- anything shaped like a token, key, password or other credential;
- a private id (a thread, session or machine id, or a private repository's records);
- a machine path (for example `/home/…`, `/Users/…`, `C:\…`).

Hosts, logins, commits and public GitHub links are fine. The privacy scan reads every line of a listing and a receipt, with one exception: it lets through line 13 of a receipt only when it is exactly `pass token: no login or token passed through the driver`. That line is format, not a credential.

## The index

`python3 -I check/check.py index` prints the registry index: the one shape consumers read, such as openwiz.dev's market page, from a saved copy.

- It reads the registry as committed at the checkout's `HEAD`, never the working tree, and exits 1 if the checkout has any uncommitted or untracked change.
- It exits 1 unless `HEAD` is the checkout's `origin/main` or an ancestor of it. A listing reaches `main` only through a pull request whose checks passed, including each skill check it added or changed, so a `verified` skill in the index is one whose check passed at its pinned commit in WizMarket's CI.
- It prints only when that tree passes `check`; otherwise it exits 1 like `check`.

Take a saved copy only from a WizMarket `main` commit.

The index is one JSON object, in UTF-8, keys sorted, indented by two spaces, ending in a newline:

- `contract`: `"listing.v1"`.
- `commit`: the 40-hex WizMarket commit the index was made at.
- `listings`: every listing, sorted by id. Each is the listing file's fields as written (optional ones only when present), plus `id`. For a `verified` listing, `proof` is replaced by what was checked, one key per proof kind:
  - `receipt`: `{"path": "<the receipt's path>", "date": "<its # date:>", "url": "https://github.com/openwizdev/WizMarket/blob/<the index's commit>/<path>"}`;
  - `skill`: `{"source": "<owner>/<repo>@<commit>", "check": "<command>", "url": "https://github.com/<owner>/<repo>/tree/<commit>"}`, with the source's own commit.

A `listed` listing has no `proof`.

[`fixtures/index.json`](../fixtures/index.json) is the synthetic index of the six valid fixtures' listings and receipts, made at the synthetic commit `dddddddddddddddddddddddddddddddddddddddd`.
