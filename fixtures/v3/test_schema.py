"""Run the synthetic v3 contract proof from any working directory."""

import json
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator


FIXTURES = Path(__file__).resolve().parent
SCHEMA = FIXTURES.parents[1] / "schema" / "listing.v3.json"
DOCUMENT_TYPES = {
    "listings": "listing",
    "receipts": "shared_receipt",
    "counts": "counts",
    "presets": "preset",
}


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


class ListingV3(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.schema = read(SCHEMA)
        Draft202012Validator.check_schema(cls.schema)

    def validator(self, definition):
        ref = "#" if definition == "listing" else f"#/$defs/{definition}"
        return Draft202012Validator({"$ref": ref, "$defs": self.schema["$defs"]} if ref != "#" else self.schema,
                                    format_checker=Draft202012Validator.FORMAT_CHECKER)

    def test_fixture_documents(self):
        for expected in ("valid", "broken"):
            cases = sorted((FIXTURES / expected).iterdir())
            self.assertTrue(cases)
            for case in cases:
                documents = sorted(case.rglob("*.json"))
                self.assertTrue(documents, case.name)
                failures = []
                for path in documents:
                    with self.subTest(expected=expected, document=str(path.relative_to(FIXTURES))):
                        validator = self.validator(DOCUMENT_TYPES[path.relative_to(case).parts[0]])
                        errors = list(validator.iter_errors(read(path)))
                        if errors:
                            failures.append(path.relative_to(case).as_posix())
                            if expected == "valid":
                                self.fail(errors[0].message)
                if expected == "broken":
                    self.assertEqual(len(failures), 1, (case.name, failures))

    def test_every_category_is_accepted(self):
        example, = (FIXTURES / "valid" / "listed-driver").glob("listings/*.json")
        listing = read(example)
        listing.pop("package")
        for category in ("driver", "harness", "agent-cloud", "compute", "ci", "model-provider",
                         "skill", "loop", "plugin", "tool", "factory"):
            with self.subTest(category=category):
                candidate = dict(listing, category=category)
                if category == "factory":
                    candidate["preset"] = "presets/example.json"
                self.validator("listing").validate(candidate)

    def test_pinned_blocks_keep_v2_shape(self):
        v2 = read(SCHEMA.with_name("listing.v2.json"))
        for field in ("package", "key_host"):
            self.assertEqual(self.schema["properties"][field], v2["properties"][field])
            for prop in v2["properties"][field]["properties"].values():
                if "$ref" in prop:
                    name = prop["$ref"].split("/")[-1]
                    self.assertEqual(self.schema["$defs"][name], v2["$defs"][name])

    def test_index_shows_status_details_and_rank(self):
        index = read(FIXTURES / "index.json")
        self.validator("index").validate(index)
        entries = {row["id"]: row for row in index["listings"]}
        unverified = entries["unverified-driver"]
        self.assertEqual((unverified["status"], unverified["reason"], unverified["since"]),
                         ("unverified", "no current receipt", "2026-11-02"))
        self.assertEqual(entries["experimental-skill"]["gate_result"], "Result: regression failed")
        expected = [
            "verified-pinned", "verified-sparse", "listed-driver", "listed-tie-a",
            "listed-tie-b", "listed-no-reports", "unverified-driver",
        ]
        drivers = sorted((row for row in entries.values() if row["category"] == "driver"),
                         key=lambda row: row["rank"])
        self.assertEqual([row["id"] for row in drivers], expected)
        self.assertEqual([row["rank"] for row in drivers], list(range(1, len(expected) + 1)))
        self.assertEqual(entries["verified-pinned"]["success_rate"], 0.9)
        self.assertNotIn("success_rate", entries["listed-no-reports"])
        self.assertEqual(entries["listed-driver"]["referral"]["label"], "referral")
        # The same comparison without a referral must leave the expected order intact.
        for row in drivers:
            row.pop("referral", None)
        ranked = sorted(drivers, key=rank_key)
        self.assertEqual([row["id"] for row in ranked], expected)


def rank_key(row):
    status_group = ("verified", "listed", "experimental", "unverified").index(row["status"])
    counts = row.get("counts", {})
    passed = counts.get("checks_passed", 0)
    total = passed + counts.get("checks_failed", 0)
    lower = 0
    if passed:
        p = passed / total
        z = 1.959963984540054
        lower = (p + z**2 / (2 * total) - z * (p * (1 - p) / total + z**2 / (4 * total**2))**0.5)
        lower /= 1 + z**2 / total
    return status_group, -lower, -counts.get("installs", 0), row["id"]


if __name__ == "__main__":
    unittest.main(verbosity=2)
