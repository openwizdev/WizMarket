# Listing v3 fixtures

These synthetic registries illustrate [listing v3](../../contracts/listing.v3.md).
Run the proof from the repository root with `python3 -I fixtures/v3/test_schema.py`
using a local Python with `jsonschema` 4.x. The proof uses Draft 2020-12 with
date format assertions enabled.

Each subdirectory of `valid/` or `broken/` is an independent registry.
The schema proof validates each JSON document at the listing root or the
corresponding definition in `schema/listing.v3.json`. A broken registry has one
schema-invalid document. The valid comparison can cover several independent
rules.

| Rule | Valid registry | Broken registry |
| --- | --- | --- |
| Category is required, scalar, and on the allowlist | `listed-driver` | `missing-category`, `multiple-categories`, `unknown-category` |
| Status is one of the four allowed values | `listed-driver`, `verified-driver`, `unverified-driver`, `experimental-skill` | `unknown-status` |
| Unverified has a one-line reason and a real since date | `unverified-driver` | `unverified-no-reason`, `unverified-multiline-reason`, `unverified-no-since`, `unverified-bad-date` |
| A listed row carries neither proof nor unverified metadata | `listed-driver` | `listed-with-proof`, `listed-with-reason` |
| Only a skill may be experimental, with the gate result | `experimental-skill` | `experimental-driver`, `experimental-no-result` |
| Verified driver or harness requires a kit receipt path | `verified-driver`, `verified-harness`, `verified-unpinned-driver` | `verified-no-receipt`, `verified-shared-as-kit` |
| Verified skill has a pinned source and check, and only the supported categories verify | `verified-skill` | `verified-wrong-proof-kind`, `verified-unsupported-kind` |
| The v2 pin and key host keep their exact shapes, with category and package restrictions | `listed-driver`, `verified-harness` | `package-malformed`, `key-host-malformed`, `package-wrong-category`, `key-host-without-package` |
| Counts are separate and non-negative | `listed-driver` | `inline-counts`, `counts-negative` |
| Referral has the literal label, an HTTPS URL and a one-line vendor | `listed-driver` | `referral-mislabelled`, `referral-insecure-url`, `referral-multiline-vendor` |
| Only a factory has a preset with a repository-relative path and allowed fields | `factory-preset` | `factory-missing-preset`, `preset-wrong-category`, `preset-path-traversal`, `preset-account-field` |
| A shared receipt has exactly six fields with check results and a UUIDv4 | `shared-receipt` | `shared-extra-field`, `shared-missing-os`, `shared-bad-check`, `shared-bad-id`, `shared-repo-as-version` |

The [policy scenarios](policy.json) pair an acceptable input with a refusal for
each rule that needs context beyond a single JSON document. Use `fixture` as
the starting registry or index where supplied. The scenario inputs give the
observed writer, output, path or other fact relevant to that comparison.
They serve the repository checker, intake and ranking work.

| Rule | Paired scenario |
| --- | --- |
| The package release belongs to the pinned repository and version | `asset_binding` |
| The kit receipt matches the pin, passes 5-of-5 and covers the latest scheduled run or newer | `receipt_binding`, `kit_receipt_result`, `receipt_freshness` |
| Only the release bar sets unverified, and the listing stays visible with its reason and date | `unverified_writer`, `unverified_visibility` |
| An experimental listing gives the gate's actual output | `experimental_gate` |
| Only intake writes counts | `counts_writer` |
| Only a market maintainer adds a referral, which is shown with its label | `referral_writer`, `referral_display` |
| The shared path agrees with the listing id, the factory id is random, and results stay public | `shared_receipt_location`, `factory_id_origin`, `shared_receipt_privacy` |
| A preset belongs to its listing and names public pieces and settings only | `preset_binding`, `preset_public_pieces`, `preset_public_settings` |
| Status, Wilson score, installs and id determine rank, independent of the referral | `rank`, `referral_rank_invariance` |

[index.json](index.json) is the synthetic ranked index for the combined valid
registries at the fixture commit of 40 `d`s. It includes the unverified reason,
an experimental skill, examples with and without counts, and the referral used
in the ranking comparison. The pre-ranking index has the same entries and
omits `rank` and `success_rate`.
