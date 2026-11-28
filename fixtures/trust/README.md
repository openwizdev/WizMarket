# Trust v1 fixtures

These synthetic examples exercise [the trust contract](../../contracts/trust.v1.md).

| Rule | Valid | Broken |
| --- | --- | --- |
| Trust schema identifier | [full](valid/trust/full.json) | [wrong-schema](broken/trust/wrong-schema.json) |
| Trust listing ID | [full](valid/trust/full.json) | [bad-listing-id](broken/trust/bad-listing-id.json) |
| Publisher is a GitHub login | [full](valid/trust/full.json) | [bad-publisher](broken/trust/bad-publisher.json) |
| Source uses a GitHub owner/repository | [full](valid/trust/full.json) | [bad-repository](broken/trust/bad-repository.json) |
| Source uses a full lowercase Git commit | [full](valid/trust/full.json) | [short-source-commit](broken/trust/short-source-commit.json) |
| Checksum is 64 lowercase hexadecimal digits | [full](valid/trust/full.json) | [bad-digest](broken/trust/bad-digest.json) |
| Signature uses the trust namespace | [full](valid/trust/full.json) | [wrong-namespace](broken/trust/wrong-namespace.json) |
| Signature is an armored SSHSIG | [full](valid/trust/full.json) | [missing-armor](broken/trust/missing-armor.json) |
| Scan report contains the six baseline scans | [full](valid/trust/full.json) | [missing-scan](broken/trust/missing-scan.json) |
| Additional scan names are lowercase identifiers | [full](valid/trust/full.json) | [bad-scan-name](broken/trust/bad-scan-name.json) |
| Scan result is pass or fail | [full](valid/trust/full.json) | [bad-scan-result](broken/trust/bad-scan-result.json) |
| A failed scan has a finding | [failed-review](valid/trust/failed-review.json) | [failed-scan-without-findings](broken/trust/failed-scan-without-findings.json) |
| Findings use one line each | [failed-review](valid/trust/failed-review.json) | [multiline-finding](broken/trust/multiline-finding.json) |
| Review names its model family | [full](valid/trust/full.json) | [missing-model-family](broken/trust/missing-model-family.json) |
| Review verdict is pass or fail | [full](valid/trust/full.json) | [bad-verdict](broken/trust/bad-verdict.json) |
| Review records the full commit it read | [full](valid/trust/full.json) | [short-review-commit](broken/trust/short-review-commit.json) |
| A passing review has no failure reasons | [full](valid/trust/full.json) | [passed-with-reasons](broken/trust/passed-with-reasons.json) |
| A failed review has reasons | [failed-review](valid/trust/failed-review.json) | [failed-review-without-reasons](broken/trust/failed-review-without-reasons.json) |
| Review reasons use one line each | [failed-review](valid/trust/failed-review.json) | [multiline-review-reason](broken/trust/multiline-review-reason.json) |
| Empty permission maps are explicit | [empty-declaration](valid/trust/empty-declaration.json) | [missing-permission-map](broken/trust/missing-permission-map.json) |
| Network grants name exact hosts | [full](valid/trust/full.json) | [wildcard-host](broken/trust/wildcard-host.json) |
| Every network grant includes a one-line reason | [full](valid/trust/full.json) | [blank-host-reason](broken/trust/blank-host-reason.json) |
| File grants use explicit absolute paths | [full](valid/trust/full.json) | [path-traversal](broken/trust/path-traversal.json) |
| File grants use read or write | [full](valid/trust/full.json) | [bad-file-access](broken/trust/bad-file-access.json) |
| Every file grant includes a one-line reason | [full](valid/trust/full.json) | [no-file-reason](broken/trust/no-file-reason.json) |
| Key grants use names | [full](valid/trust/full.json) | [bad-key-name](broken/trust/bad-key-name.json) |
| Every key grant includes a one-line reason | [full](valid/trust/full.json) | [multiline-key-reason](broken/trust/multiline-key-reason.json) |
| Objects are closed to extra fields | [full](valid/trust/full.json) | [unknown-field](broken/trust/unknown-field.json) |
| Approval identifies the listing | [exact-declaration](valid/approval/exact-declaration.json) | [no-listing](broken/approval/no-listing.json) |
| Approval stores the complete declaration | [exact-declaration](valid/approval/exact-declaration.json) | [partial-declaration](broken/approval/partial-declaration.json) |
| Approval time is in UTC with seconds | [exact-declaration](valid/approval/exact-declaration.json) | [non-utc-time](broken/approval/non-utc-time.json) |
| Approval time is a real calendar date | [exact-declaration](valid/approval/exact-declaration.json) | [invalid-date](broken/approval/invalid-date.json) |
| A profile denies by default | [enforced](valid/profile/enforced.json) | [allow-by-default](broken/profile/allow-by-default.json) |
| A profile lists exact hosts | [enforced](valid/profile/enforced.json) | [wildcard-host](broken/profile/wildcard-host.json) |
| A profile names paths and access modes | [enforced](valid/profile/enforced.json) | [bad-file-access](broken/profile/bad-file-access.json) |
| A profile names only keys to pass | [enforced](valid/profile/enforced.json) | [wildcard-key](broken/profile/wildcard-key.json) |
| The profile reports sandbox availability | [enforced](valid/profile/enforced.json) | [unknown-sandbox](broken/profile/unknown-sandbox.json) |
| An unavailable sandbox has the plain notice | [unavailable](valid/profile/unavailable.json) | [missing-notice](broken/profile/missing-notice.json) |
| The unsandboxed notice has exact wording | [unavailable](valid/profile/unavailable.json) | [wrong-notice](broken/profile/wrong-notice.json) |
| An enforced sandbox omits the notice | [enforced](valid/profile/enforced.json) | [notice-while-enforced](broken/profile/notice-while-enforced.json) |

## Run the proof

From the repository root, run the tests with Python's `jsonschema` and OpenSSH available.

```sh
python3 -I fixtures/trust/test_trust.py -v
```

The test selects the schema root for trust files and the appropriate `$defs`
entry for approvals and profiles. “Valid” means structurally valid, including
examples that report failing scans or reviews. The checksum and detached
signature check uses only the bytes in [package.txt](canary/package.txt)
and the synthetic public key in [allowed_signers](canary/allowed_signers).
The canary publisher is invented and the canary private key was discarded
after signing. The test makes no network calls.
