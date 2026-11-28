# OpenWiz market trust v1

`openwiz.trust.v1` defines one UTF-8 JSON file at `trust/<listing id>.json`
for each listing. The file lives alongside the listing and its receipts.
Listing fields, status and the existing receipt rules stay in the listing
contracts. The trust file gives the install gate the evidence and permissions
for a specific package. The installer writes approval locally and derives
the runtime profile from it.

[The JSON Schema](../schema/trust.v1.json) validates the trust file at its
root, the local record at `#/$defs/installApproval`, and the runtime profile
at `#/$defs/sandboxProfile`. Fields are required unless stated otherwise.
Objects have only the named fields except where a map defines its keys.
Readers reject duplicate JSON object members before applying the schema.
A one-line string has at least one non-whitespace character and contains no
control characters or Unicode line or paragraph separators. Structure,
cryptographic verification and authorization are separate checks.

## Trust file

| Field | Exact value | Synthetic example |
| --- | --- | --- |
| `schema` | The literal `openwiz.trust.v1`. | `openwiz.trust.v1` |
| `listing_id` | 2–40 lowercase ASCII letters, digits or hyphens. It matches the listing ID and the basename of the trust file exactly. | `canary-tool` |
| `publisher` | The listing publisher's GitHub login, 1–39 ASCII letters or digits with optional single interior hyphens. Match the listing publisher case-insensitively. | `wiz-canary-n0nreal` |
| `source.repository` | GitHub `owner/repository`. The owner has the login syntax. The repository name is 1–100 ASCII letters, digits, periods, underscores or hyphens. The names `.` and `..` are excluded. | `wiz-canary-n0nreal/example-package` |
| `source.commit` | A full Git commit ID of 40 lowercase hexadecimal digits. | `0123456789abcdef0123456789abcdef01234567` |
| `sha256` | A SHA-256 digest of the exact package bytes the installer consumes, as 64 lowercase hexadecimal digits. | The `sha256` in the [full canary trust file](../fixtures/trust/valid/trust/full.json). |
| `signature` | The detached OpenSSH signature described below. | [Full canary trust file](../fixtures/trust/valid/trust/full.json). |
| `scan_report` | A map from scan name to its result and findings. | [Canary report with findings](../fixtures/trust/valid/trust/failed-review.json). |
| `review` | The model family, verdict, reasons and reviewed commit. | [Canary review with reasons](../fixtures/trust/valid/trust/failed-review.json). |
| `declaration` | The three permission maps defined below. | [Full canary trust file](../fixtures/trust/valid/trust/full.json). |

Resolve the package using the pinned repository and commit and the listing's
package selection. Any repository or commit recorded for that package in the
listing must agree with the trust file. Hash the actual bytes used for
installation before unpacking or transformation, whether those bytes are a
release artifact or a pinned source snapshot. Refuse a source that cannot be
bound to that commit and a package whose digest does not match. The installer
uses the same bytes it verified.

### Detached signature

`signature.namespace` is the literal `openwiz.trust.v1`.
`signature.sshsig` is the complete ASCII armor produced by OpenSSH signing,
including the opening and closing SSH signature markers and LF after each
line. JSON stores each LF as `\n`. Sign exactly the 64 lowercase ASCII bytes
of `sha256`, with zero trailing bytes.

Use the public signing keys from GitHub's
[`GET /users/{username}/ssh_signing_keys` endpoint](https://docs.github.com/en/rest/users/ssh-signing-keys#list-ssh-signing-keys-for-a-user)
for the publisher matched to the listing. Read all pages. Use those public
keys as allowed signers under that login, with `namespaces="openwiz.trust.v1"`.
The verifier takes the login from the matched listing and the public keys from
GitHub. A missing signing key or failed lookup means verification fails.
The detached signature attests to the package digest. The listing, source and
review bindings also require their own checks.

With shell variables set to the digest, SSH signing key selector, publisher
login and decoded signature file, the
[OpenSSH signing and verification commands](https://man.openbsd.org/ssh-keygen.1)
are:

```sh
printf '%s' "$sha256" | ssh-keygen -Y sign -n openwiz.trust.v1 -f "$signing_key" > checksum.sig
printf '%s' "$sha256" | ssh-keygen -Y verify -n openwiz.trust.v1 -I "$publisher" -f allowed_signers -s "$signature_file"
```

See [the fixture proof](../fixtures/trust/README.md) for an offline example
using the synthetic artifact, public key and detached signature.

### Scan report and review

Each scan has a name expressed as its map key. The six baseline names are
`secrets`, `obfuscated-code`, `install-scripts`, `bundled-binaries`,
`undeclared-network` and `agent-directed-instructions`. Additional names
use lowercase ASCII letters and digits separated by single hyphens.
Each value has `result` (`pass` or `fail`) and `findings` (an array of
one-line strings). A failure has at least one finding. A pass may have
advisory findings or an empty array.

`review.model_family` is the reviewing model's family as a one-line name,
such as `Example Reviewer`. `review.verdict` is `pass` or `fail`.
`review.reasons` is an empty array on `pass` and contains one or more
one-line reasons on `fail`. `review.commit` is the 40-digit lowercase
hexadecimal commit the reviewer read and must equal `source.commit`.
Scan and review results must refer to the exact package being considered.
A recorded `fail` is valid report data and fails the corresponding trust gate.

### Permission declaration

Include each map even if it is empty. Any host, file action or key absent
from the declaration is outside the grant.

| Map | Key and value | Synthetic entry |
| --- | --- | --- |
| `network` | An exact lowercase ASCII DNS host with at least two labels and at most 253 characters. Each label is 1–63 ASCII letters, digits or interior hyphens, and the final label starts with a letter. Use DNS ASCII form for internationalized names. Grants name a host only and exclude wildcards, IP literals, schemes, ports, paths and trailing dots. The value is a one-line reason. | `"api.canary.example": "Fetch synthetic metadata."` |
| `files` | An exact absolute POSIX file path with nonempty, slash-separated components. Components may contain spaces. Exclude `.` and `..` components, trailing slashes, backslashes, glob characters (`*?[]{}`), tilde and control or Unicode line and paragraph separators. The value has `access`, an array with one or both of `read` and `write` with no repetitions, and a one-line `reason`. | `"/opt/canary/input.txt": {"access":["read"],"reason":"Read the synthetic input."}` |
| `keys` | An exact key name, 1–64 characters, beginning with an uppercase ASCII letter and followed by uppercase ASCII letters, digits or underscores. The value is a one-line reason. | `"CANARY_TOKEN": "Authenticate to the synthetic API."` |

A read grant permits reading that file. A write grant permits creating or
modifying that file. Grant both to allow both operations. A path grant
covers a single file and grants zero access to other files under its parent
directory. A key entry carries the name and reason. Secret values stay in
the local key store until passed to the specific run.

## Local install approval

The installer shows the listing, publisher, trust results and full declaration
with reasons and records approval only after an explicit yes. The
[canary approval](../fixtures/trust/valid/approval/exact-declaration.json)
has these required fields:

| Field | Exact value | Synthetic example |
| --- | --- | --- |
| `listing_id` | The ID of the listing approved, with the same syntax as in its trust file. | `canary-tool` |
| `declaration` | A full copy of the declaration the user approved. | The declaration in the linked canary approval. |
| `approved_at` | A valid UTC calendar timestamp with integral seconds in `YYYY-MM-DDTHH:MM:SSZ` form. Validate the schema's `date-time` format as an assertion. | `2026-11-28T08:00:00Z` |

Bind approval to the same listing and compare complete decoded declarations.
JSON object member order and whitespace outside strings are immaterial.
Strings and arrays, including file access lists, compare exactly. Any
difference, including a changed reason, requires a new yes before install or
execution under that declaration. Run the package trust checks for the
current package even when the declaration matches an existing approval.

## Runtime sandbox profile

Build the profile from the exact locally approved declaration for the
listing. Copy network host names and key names to unique arrays, and copy
each file path and its access array to the files map. The profile has these
fields:

| Field | Exact value | Synthetic example |
| --- | --- | --- |
| `default` | The literal `deny`. | `deny` |
| `network` | An array of unique host names from the approved `network` map. | `["api.canary.example"]` |
| `files` | A map from each approved file path to its access array. | `{"/opt/canary/input.txt":["read"],"/opt/canary/output.txt":["write"]}` |
| `keys` | An array of unique names from the approved `keys` map. | `["CANARY_TOKEN"]` |
| `sandbox` | `enforced` when the system sandbox applies the profile, or `unavailable` when the system offers no sandbox. | `enforced` |
| `notice` | Required for `unavailable` and omitted for `enforced`. It uses the exact text below. | [Canary profile with the notice](../fixtures/trust/valid/profile/unavailable.json). |

In `enforced` mode, the sandbox denies every undeclared host and file
operation. Apply host restrictions to redirects and file restrictions to
the actual target of filesystem operations. Deny aliases or other accesses
when the backend cannot prove they resolve within the approved grant.
If a system sandbox exists but cannot enforce the whole profile, fail
closed. Only the declared key values reach the item's run. Start with an
environment that contains no ambient secrets.

With no system sandbox, display the following notice before install approval
and when launching the unsandboxed item. The local key broker still passes
only declared keys. Sandbox installation requires a separate owner action.

> No system sandbox is available. This item will run unsandboxed.

The fixtures pair the structural rules with valid and broken examples.
The loader, verifier, install gate and sandbox check rules that depend on
external state, including the listing binding, the package and signature,
the matching reviewed commit, freshness of consent and actual enforcement.
[Fixture index and proof](../fixtures/trust/README.md).
