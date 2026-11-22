# Fixtures

Synthetic examples of [`listing.v1`](../contracts/listing.v1.md). Each folder is one small registry: `listings/<id>.json`, plus `receipts/<id>/` when a receipt is part of the example. Nothing here is real: `example-*` names, `example.com` URLs and repeated-letter commits.

## Valid

Each passes the schema and every rule of the contract.

| Folder | Shows |
| --- | --- |
| `valid/listed-available/` | The smallest listing: `listed`, `available`, no optional fields |
| `valid/listed-being-built/` | `being-built` with its pull request link, and a `login` line |
| `valid/listed-being-built-any-tracker/` | `being-built` whose first link, the work link, is on another tracker, with a query and a fragment |
| `valid/verified-driver/` | A `verified` driver and its 5 of 5 receipt |
| `valid/verified-skill/` | A `verified` skill with its source at a commit and its check |
| `valid/verified-driver-and-skill/` | Tagged `driver` and `skill`, so it carries both proofs |

[`index.json`](index.json) is what `check/check.py index` prints for one registry holding these six listings and their receipts, at the synthetic commit `dddddddddddddddddddddddddddddddddddddddd`.

## Broken

Each is refused for exactly one reason.

| Folder | Refused because | Caught by |
| --- | --- | --- |
| `broken/unknown-field/` | A field v1 does not have (`price`) | schema |
| `broken/being-built-without-link/` | `being-built` with no link to its pull request or ticket | schema |
| `broken/name-final-newline/` | `name` ends in a newline | schema |
| `broken/tag-final-newline/` | A tag ends in a newline | schema |
| `broken/publisher-final-newline/` | `publisher` ends in a newline | schema |
| `broken/source-final-newline/` | A skill's `source` ends in a newline | schema |
| `broken/url-port-out-of-range/` | The `url` port is 99999 | schema |
| `broken/url-bad-host/` | The `url` host has an underscore | schema |
| `broken/verified-without-proof/` | `verified` with no `proof` | schema |
| `broken/listed-with-proof/` | `listed` with a `proof` | schema |
| `broken/bad-id/` | The file name `Example_Tool` is not a valid id | id rule |
| `broken/repeated-key/` | The key `status` appears twice | JSON rule |
| `broken/false-verified-driver-skill-proof/` | A `verified` driver whose proof is a skill check, not a receipt | kind rule |
| `broken/false-verified-harness-missing-receipt/` | A `verified` harness whose receipt file is not there | kind rule |
| `broken/false-verified-skill-receipt-proof/` | A `verified` skill whose proof is a receipt, not a source and check | kind rule |
| `broken/false-verified-other-kind/` | `verified` with tags no test covers (`mcp-server`) | kind rule |
| `broken/false-verified-driver-and-skill-one-proof/` | Tagged `driver` and `skill`, with only the receipt | kind rule |
| `broken/receipt-4-of-5/` | The receipt has a `fail wake:` line and `Result: 4 of 5 pass` | receipt rule |
| `broken/receipt-names-another-listing/` | The receipt's `# listing:` is `another-driver` | receipt rule |
| `broken/receipt-lines-out-of-order/` | The receipt's `pass stop:` comes before `pass wake:` | receipt rule |
| `broken/receipt-token-line-other-text/` | The receipt's line 13 is `pass token: example-opaque-value`, not the kit's passing sentence | receipt rule |

Every broken folder's other content is valid, so the reason above is the only one.
