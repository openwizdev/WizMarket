"""T1 schema and offline canary proof for the market trust contract."""
import hashlib
import json
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
import unittest

from jsonschema import Draft202012Validator, FormatChecker


FIXTURES = Path(__file__).resolve().parent
SCHEMA = FIXTURES.parents[1] / "schema" / "trust.v1.json"


class TrustFixtures(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
        cls.validators = {
            "trust": Draft202012Validator(schema),
            "approval": cls.definition_validator(schema, "installApproval"),
            "profile": cls.definition_validator(schema, "sandboxProfile"),
        }

    @staticmethod
    def definition_validator(schema, name):
        return Draft202012Validator(
            {"$defs": schema["$defs"], "$ref": f"#/$defs/{name}"},
            format_checker=FormatChecker(),
        )

    def test_schema_accepts_valid_and_refuses_broken_fixtures(self):
        index = (FIXTURES / "README.md").read_text(encoding="utf-8")
        total = 0
        for kind, validator in self.validators.items():
            for outcome in ("valid", "broken"):
                cases = sorted((FIXTURES / outcome / kind).glob("*.json"))
                self.assertTrue(cases, f"no {outcome} {kind} fixtures")
                for case in cases:
                    with self.subTest(case=case.relative_to(FIXTURES)):
                        self.assertIn(f"]({case.relative_to(FIXTURES).as_posix()})", index)
                        instance = json.loads(case.read_text(encoding="utf-8"))
                        errors = list(validator.iter_errors(instance))
                        if outcome == "valid":
                            self.assertEqual(errors, [])
                        else:
                            self.assertTrue(errors, "the schema accepted a broken fixture")
                    total += 1
        print(f"trust fixtures: {total} JSON documents checked")

    def test_synthetic_package_and_detached_signature(self):
        trust = json.loads((FIXTURES / "valid/trust/full.json").read_text(encoding="utf-8"))
        package = (FIXTURES / "canary/package.txt").read_bytes()
        digest = hashlib.sha256(package).hexdigest()
        self.assertEqual(trust["sha256"], digest)

        with TemporaryDirectory() as directory:
            signature = Path(directory) / "checksum.sig"
            signature.write_bytes(trust["signature"]["sshsig"].encode("ascii"))
            subprocess.run(
                [
                    "ssh-keygen", "-Y", "verify",
                    "-f", str(FIXTURES / "canary/allowed_signers"),
                    "-I", trust["publisher"],
                    "-n", trust["signature"]["namespace"],
                    "-s", str(signature),
                ],
                input=digest.encode("ascii"),
                check=True,
                capture_output=True,
            )


if __name__ == "__main__":
    unittest.main()
