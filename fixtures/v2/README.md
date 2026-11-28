# Listing v2 fixtures

Synthetic examples of [`listing.v2`](../../contracts/listing.v2.md). Each folder is one small registry. Nothing here is real.

## Valid

| Folder | Shows |
| --- | --- |
| `valid/listed-driver/` | A `listed` driver and its `package` block |
| `valid/verified-driver/` | A `verified` driver whose receipt names the package's repository, commit and kit commit |
| `valid/verified-harness/` | A `verified` harness with `package` and `key_host` |

`index.json` is what `check/check.py index` prints for one registry holding these three listings, at the synthetic commit `dddddddddddddddddddddddddddddddddddddddd`.

## Broken

Each is refused for exactly one reason.

| Folder | Refused because |
| --- | --- |
| `broken/malformed-package/` | `package` is missing `sha256` |
| `broken/malformed-key-host/` | `key_host.origin` has a path, which the driver package contract refuses |
| `broken/key-host-without-package/` | `key_host` with no `package` block |
| `broken/package-other-kind/` | `package` on a listing that is not a driver or a harness |
| `broken/asset-not-release/` | `asset_url` is a release asset of a different repository |
| `broken/verified-other-commit/` | The receipt's `# driver:` line is not the package's repository and commit |
| `broken/verified-other-kit/` | The receipt's `# kit:` line is not the package's kit commit |
