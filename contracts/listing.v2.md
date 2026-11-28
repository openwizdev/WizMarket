# WizMarket listing, version 2 (`listing.v2`)

`listing.v2` sits beside [`listing.v1`](listing.v1.md). Version 1 never changes: a listing with no `package` block is version 1, and the check and the index read it exactly as they do today. Version 2 is a driver or harness listing that pins the release it installs, using the [`package` block][package] from the OpenWiz driver package contract, and optionally that contract's [`key_host` block][package].

The JSON Schema for one v2 listing file is [`schema/listing.v2.json`](../schema/listing.v2.json). It checks the file's shape, including the two blocks. The id rule, the no-repeated-key rule, the kind rules, the receipt, and the two bindings below are checked by `check/check.py`, as they are for version 1. Synthetic examples are in [`fixtures/v2/`](../fixtures/v2/).

A driver author starts from the template repository [openwizdev/driver-template](https://github.com/openwizdev/driver-template). The recommended repository name is `<owner>/openwiz-driver-<name>`.

## A v2 listing

A v2 listing is a version 1 listing file, `listings/<id>.json`, with the same fields and the same rules, plus:

| Field | Required | What it holds |
| --- | --- | --- |
| `package` | yes | The driver package contract's `package` block: `driver`, `version`, `repository`, `commit`, `asset_url`, `sha256`, `kit_commit`. |
| `key_host` | no | The driver package contract's `key_host` block: `origin`, `variable`, `keychain`. Names and an address, never a key. |

`package` and `key_host` are only for a listing tagged `driver` or `harness`. A `key_host` block without a `package` block is refused. Any other shape the driver package contract refuses (a missing field, an extra field, a value of the wrong shape) is refused.

**The asset URL.** `package.asset_url` must be the release asset of the package's own repository and version, exactly:

```text
https://github.com/<repository>/releases/download/v<version>/driver.tar.gz
```

`<repository>` and `<version>` are the block's own `repository` and `version`. No other host, path, query or fragment. An asset URL that is not that release asset is refused.

**A verified listing.** A `verified` driver or harness still needs its kind's proof, and the receipt's format is the version 1 receipt. The receipt is for this package only when its `# driver:` line is `<repository>@<commit>` and its `# kit:` line is `openwizdev/OpenWiz@<kit_commit>`, using the block's own `repository`, `commit` and `kit_commit`. Anything else is refused: a verified listing passes only with a receipt for that exact package commit. A `listed` listing has no receipt, so this binding does not apply to it.

`key_host` is checked for shape and nothing more. It does not authorize a credential read, and it stays inactive until the key-host rule lands in OpenWiz.

A listed driver, `listings/pinned-driver.json`:

```json
{
  "name": "Pinned driver",
  "summary": "A synthetic driver pinned to one release of its own repository.",
  "tags": ["driver"],
  "url": "https://example.com/pinned-driver",
  "plugs_into": "The OpenWiz driver interface",
  "publisher": "example-publisher",
  "stage": "available",
  "status": "listed",
  "package": {
    "driver": "pinned-driver",
    "version": "0.1.0",
    "repository": "example-owner/pinned-driver",
    "commit": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    "asset_url": "https://github.com/example-owner/pinned-driver/releases/download/v0.1.0/driver.tar.gz",
    "sha256": "abababababababababababababababababababababababababababababababab",
    "kit_commit": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
  }
}
```

## The index

`python3 -I check/check.py index` prints the same envelope as version 1: `contract` is `"listing.v1"`, `commit` is the WizMarket commit, and `listings` is every listing. Keeping that envelope means a registry of only version 1 listings is byte-identical to the version 1 index, including [`fixtures/index.json`](../fixtures/index.json).

Each listing says which contract it uses:

- A version 1 listing is the same object as today. It has no `contract` field, and that absence means `listing.v1`.
- A version 2 listing is that same object plus the `package` block and, when the file has one, the `key_host` block, plus `"contract": "listing.v2"`. Its `proof`, when it is verified, is replaced the same way as in version 1.

[package]: https://github.com/openwizdev/OpenWiz/blob/main/contracts/driver-package.v1.md
