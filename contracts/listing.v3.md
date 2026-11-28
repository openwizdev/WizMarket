# WizMarket listing, version 3 (`listing.v3`)

A file at `listings/<id>.json` that declares a `category` uses listing v3. The filename supplies the id, which has 2 to 40 lowercase letters, digits or hyphens. Use one UTF-8 JSON object with unique keys. Listings without `category` retain the [v1](listing.v1.md) and [v2](listing.v2.md) version rules. Each version is a fixed public format.

The [JSON Schema](../schema/listing.v3.json) describes the listing at its root and the related documents in `$defs`. The [synthetic fixtures](../fixtures/v3/README.md) show both shape and repository-level rules.

## Listing fields

The author writes `name`, `summary`, `tags`, `url`, `plugs_into`, `publisher`, `stage`, and optional `login` and `links` as in [v1](listing.v1.md#a-listing), including the public work link for `being-built`. The original HTTPS URL rules apply to the listing, links and referral URLs. One-line strings follow v1's rule, including its ban on control characters. Dates are real calendar dates in UTC, written `YYYY-MM-DD`.

| Field | When present | Value and writer |
| --- | --- | --- |
| `category` | Always | The author chooses exactly one of `driver`, `harness`, `agent-cloud`, `compute`, `ci`, `model-provider`, `skill`, `loop`, `plugin`, `tool`, `factory`. `tags` stay free-form within the v1 tag syntax. |
| `status` | Always | The author may submit `listed` or `verified` with the required evidence, or `experimental` for a skill with its gate result. Only the release bar may set `unverified`. The status rules below apply to every write. |
| `proof` | Verified only | The author supplies exactly the proof for the listing's category. |
| `reason` | Unverified only | The release bar supplies the failing check on one line, or the literal `no current receipt`. |
| `since` | Unverified only | The release bar supplies the date when the listing entered `unverified`. |
| `gate_result` | Experimental only | The skill's author copies the eval and regression gate's result line verbatim. |
| `package` | Optional, for a driver or harness | The author may pin the installed release using v2's [package block](listing.v2.md#a-v2-listing), with the same seven fields and release asset rule. |
| `key_host` | Optional, with `package` | The author may include v2's `key_host` block, with the same three fields. It describes where a key would be used and carries no credential. |
| `referral` | Optional | Only a WizMarket maintainer may add or change it. It holds exactly `label` with the literal `referral`, an HTTPS `url`, and a one-line `vendor`. Display the slot with the label `referral` wherever the link is shown. |
| `preset` | Factory only, required for a factory | The author writes the string `presets/<id>.json`, using this listing's id. |

A v3 author publishes the listing and its evidence by pull request. Intake owns the separate counts and shared receipt files. The index joins these records at a WizMarket commit.

## Status and evidence

- **`listed`** means the listing is present with a public link and no accepted proof.
- **`verified`** means its category's proof passed. A driver or harness needs `proof.receipt` pointing to a current 5-of-5 [v1 kit receipt](listing.v1.md#the-receipt). Current means from the rig's latest scheduled run or newer. A receipt from an earlier run is stale, even if it passed. Use the v1 path, its 14 lines and its immutability rule. When a package pin is present, the receipt's `# driver:` and `# kit:` lines must match its repository, commit and kit commit exactly as in [v2](listing.v2.md#a-v2-listing). The pin's release asset must likewise match its repository and version. A skill needs `proof.source` (its public repository and full commit) and `proof.check` (the command that passes at that commit) as in [v1](listing.v1.md#verified-by-kind), with its eval and regression gate passed. The other categories have no verification proof in this version.
- **`unverified`** means the live check failed or the receipt is no longer current. The release bar changes the status, records `reason` and `since`, and removes the listing's current proof field. Previously committed kit receipts stay in the registry. A failed listing stays visible with its status, reason and date, including in the index. An author cannot set this status.
- **`experimental`** means a skill has yet to pass its eval and regression gate. Its gate result is required and visible. Only the `skill` category can use this status.

The category selects the proof kind. A tag supplies no extra proof requirement. Keep previously committed receipts when a listing's status or proof pointer changes.

## Shared receipts and install reports

Sharing is opt-in and off by default. Wiz previews the exact report and tells the user that GitHub shows which login files it. Once a report passes intake, intake may save it as UTF-8 JSON at `receipts/<id>/shared/<report>.json`. The directory id and the first field identify the same listing. `<report>` distinguishes reports so intake can keep one record per accepted report. A shared report carries exactly these six fields, in this order in the issue form.

| Field | Value |
| --- | --- |
| `listing_id` | The public WizMarket listing id. |
| `version_or_commit` | The piece's release version or full 40-character lowercase hexadecimal commit, alone. A version is a single label of at most 64 ASCII letters, digits, dots, underscores, plus signs or hyphens, starting with a letter or digit. |
| `checks` | An array of public, one-line results in check order, in the form `pass <check>: <result>` or `fail <check>: <result>`. Check names use lowercase letters, digits and hyphens. An install report may use an empty array when it ran no checks. A live-check report has at least one result. |
| `date` | The UTC date of the check or install. |
| `os_family` | The operating system family, such as `linux`, `macos` or `windows`. Use a lowercase slug of at most 32 ASCII characters, starting with a letter and containing letters, digits or hyphens. |
| `factory_id` | A lowercase random UUID version 4. Wiz generates it once on the factory's home machine and can reset it. It is never derived from a login, repository or machine. |

Wiz supplies the fields and intake writes the accepted document. Keep all six values free of credentials, account labels, emails, repository names or URLs, machine names, private ids and local paths. The factory id is the only factory identifier in the report. A shared receipt contributes to counts. Verification of a driver or harness requires its kit receipt.

See the [synthetic shared receipt](../fixtures/v3/valid/shared-receipt/receipts/shared-driver/shared/example.json).

## Counts

Only WizMarket's intake writes `counts/<id>.json`. The author leaves `counts` out of the listing file. Counts are non-negative integers, and all five fields are required when the counts document exists.

| Field | Meaning |
| --- | --- |
| `installs` | Installs from accepted install reports and public download counts for the listing's release assets. |
| `checks_passed` | Number of accepted reported check results marked `pass`. |
| `checks_failed` | Number of accepted reported check results marked `fail`. |
| `factories` | Number of distinct random factory ids in the listing's accepted reports. |
| `updated` | UTC date when intake last updated the aggregate. |

See the [synthetic counts document](../fixtures/v3/valid/listed-driver/counts/listed-driver.json).

## Factory presets

The author adds `presets/<id>.json` with the same id as its factory listing. The preset is a UTF-8 JSON object whose optional `drivers`, `harnesses`, `skills`, and `loops` arrays hold distinct public WizMarket listing ids for pieces of the corresponding category. Harness ids refer to harness rows. Omit an array or make it empty to leave out that kind. The optional `settings` object maps public settings field names to values permitted by those fields.

Every named piece must exist in WizMarket. The preset check verifies those links and the settings rules, and refuses private settings fields, credentials, account labels, emails, private repositories, thread ids and local paths. A setting that refers to a piece uses its public id. See the [synthetic factory preset](../fixtures/v3/valid/factory-preset/presets/example-factory.json).

## Index and rank

The index generator writes the [v1 envelope](listing.v1.md#the-index), with listings in ascending id order and the existing v1 and v2 entry formats. Each v3 entry has `"contract": "listing.v3"`, its filename-derived `id`, `category`, `status`, and applicable `reason`, `since` or `gate_result`. The proof projection keeps the v1 and v2 shapes. The index includes the author's other listing fields and the maintainer's labelled referral when supplied. Its `counts` block is the intake document when present.

The ranking step writes the following fields. An index produced before ranking is available omits both.

- `success_rate` is the number of passed checks divided by all reported checks, a number from 0 through 1. Omit it when there are zero reported checks.
- `rank` is a one-based position within the listing's category. Every v3 listing participates, including listings without counts.

Within each category, compare the following in order. Move to the next item only on a tie.

1. Status group, in this order: `verified`, `listed`, `experimental`, `unverified`.
2. The lower bound of the two-sided 95% Wilson score interval, largest first. Let `n = checks_passed + checks_failed`, `p = checks_passed / n` and `z = 1.959963984540054`. The score is `(p + z²/(2n) - z × sqrt(p(1-p)/n + z²/(4n²))) / (1 + z²/n)`. Use zero for no reports or zero passes. Compare the score before any display rounding.
3. `installs`, largest first. Use zero when counts are absent.
4. `id`, ascending in ASCII order.

The referral's presence, vendor, link and label never enter any ranking step. In the [synthetic index](../fixtures/v3/index.json), the two verified drivers rank first. `verified-pinned` has 90 passes out of 100, giving a Wilson lower bound of about 0.826, ahead of `verified-sparse` with one pass out of one, about 0.207. The listed drivers with 4 passes out of 8 tie on Wilson score. Installs place `listed-driver` first among them and id places `listed-tie-a` ahead of `listed-tie-b`. The unverified driver is still visible at the bottom of the category, with its reason and date.

## Synthetic listing

`listings/example-skill.json`

```json
{
  "name": "Example skill",
  "summary": "A synthetic skill whose regression gate failed.",
  "tags": ["examples"],
  "url": "https://example.com/example-skill",
  "plugs_into": "An example OpenWiz factory",
  "publisher": "example-publisher",
  "stage": "available",
  "category": "skill",
  "status": "experimental",
  "gate_result": "Result: regression failed"
}
```
