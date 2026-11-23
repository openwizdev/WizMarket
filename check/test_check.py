import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CHECK = ROOT / "check" / "check.py"
FIXTURES = ROOT / "fixtures"
SYNTHETIC_COMMIT = "d" * 40
FALSE_VERIFIED_FIX = "fix: drop status to listed, or add the proof"

BROKEN = {
    "unknown-field": ("listings/example-tool.json", 'unknown field "price"'),
    "being-built-without-link": ("listings/example-harness.json", '"being-built" needs links'),
    "name-final-newline": ("listings/example-tool.json", '"name" must be one line'),
    "tag-final-newline": ("listings/example-tool.json", '"tags" must be'),
    "publisher-final-newline": ("listings/example-tool.json", '"publisher" must be a GitHub login'),
    "source-final-newline": ("listings/example-skill.json", '"proof.source" must be'),
    "url-port-out-of-range": ("listings/example-tool.json", '"url" must be an https:// URL'),
    "url-bad-host": ("listings/example-tool.json", '"url" must be an https:// URL'),
    "verified-without-proof": ("listings/example-driver.json", '"verified" needs proof'),
    "listed-with-proof": ("listings/example-skill.json", '"listed" has no proof'),
    "bad-id": ("listings/Example_Tool.json", '"Example_Tool" is not a valid id'),
    "repeated-key": ("listings/example-tool.json", 'key "status" appears twice'),
    "false-verified-driver-skill-proof": ("listings/example-driver.json", "proof must hold exactly receipt"),
    "false-verified-harness-missing-receipt": ("listings/example-harness.json", "is not there"),
    "false-verified-skill-receipt-proof": ("listings/example-skill.json", "proof must hold exactly check, source"),
    "false-verified-other-kind": ("listings/example-tool.json", "no tag with a test"),
    "false-verified-driver-and-skill-one-proof": ("listings/example-driver-kit.json", "proof must hold exactly check, receipt, source"),
    "receipt-4-of-5": ("receipts/example-driver/2026-11-01-aaaaaaaaaaaa.txt", "line 11 must be"),
    "receipt-names-another-listing": ("receipts/example-driver/2026-11-01-aaaaaaaaaaaa.txt", 'line 1 must be "# listing: example-driver"'),
    "receipt-lines-out-of-order": ("receipts/example-driver/2026-11-01-aaaaaaaaaaaa.txt", "line 11 must be"),
    "receipt-token-line-other-text": ("receipts/example-driver/2026-11-01-aaaaaaaaaaaa.txt", "line 13 must be"),
    "receipt-raw-note-id": ("receipts/example-driver/2026-11-01-aaaaaaaaaaaa.txt", "line 10 must be"),
}
FALSE_VERIFIED = {name for name in BROKEN if name.startswith(("false-verified", "receipt-", "verified-"))}
EXTRA_FAILURES = {"name-final-newline": 2}  # its url also ends in a newline: openwizdev/OpenWiz#2654

DRIVER_RECEIPT = FIXTURES / "valid/verified-driver/receipts/example-driver/2026-11-01-aaaaaaaaaaaa.txt"


def run(*args, cwd, env=None):
    return subprocess.run([sys.executable, "-I", str(CHECK), *args], cwd=cwd, env=env,
                          capture_output=True, text=True, timeout=120)


def git(cwd, *args):
    return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.com", *args],
                          cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()


def failures(result):
    return [line for line in result.stdout.splitlines() if line]


class Temp(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)

    def registry(self, *folders, commit=True):
        reg = self.tmp / "registry"
        for folder in folders:
            shutil.copytree(FIXTURES / folder, reg, dirs_exist_ok=True)
        if commit:
            git(reg, "init", "-q", "-b", "main")
            git(reg, "add", "-A")
            git(reg, "commit", "-q", "-m", "registry")
            git(reg, "update-ref", "refs/remotes/origin/main", "HEAD")
        return reg

    def write(self, path, text):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)


class Fixtures(unittest.TestCase):
    def test_every_fixture_is_in_a_table(self):
        self.assertEqual(sorted(p.name for p in (FIXTURES / "broken").iterdir()), sorted(BROKEN))
        self.assertEqual(len(list((FIXTURES / "valid").iterdir())), 6)

    def test_valid_fixtures_are_accepted(self):
        for folder in sorted((FIXTURES / "valid").iterdir()):
            with self.subTest(folder.name):
                result = run("check", cwd=folder)
                self.assertEqual((result.returncode, len(failures(result))), (0, 1), result.stdout)
                self.assertRegex(result.stdout, r"^check: ok, \d+ listings and \d+ receipts checked\n$")

    def test_broken_fixtures_are_refused_for_their_reason(self):
        for name, (path, reason) in BROKEN.items():
            with self.subTest(name):
                result = run("check", cwd=FIXTURES / "broken" / name)
                lines = failures(result)
                self.assertEqual(result.returncode, 1, result.stdout)
                self.assertEqual(len(lines), EXTRA_FAILURES.get(name, 1), result.stdout)
                self.assertTrue(lines[0].startswith(path + ": "), lines)
                self.assertIn(reason, lines[0])
                self.assertTrue(all("; fix: " in line for line in lines), lines)
                if name in FALSE_VERIFIED:
                    self.assertTrue(lines[0].endswith(FALSE_VERIFIED_FIX), lines[0])


class Rules(Temp):
    def test_receipt_file_name_must_match_its_date_and_driver_commit(self):
        reg = self.registry("valid/verified-driver", commit=False)
        receipt = reg / "receipts/example-driver/2026-11-01-aaaaaaaaaaaa.txt"
        receipt.write_text(receipt.read_text().replace("# date: 2026-11-01", "# date: 2026-11-02"))
        lines = failures(run("check", cwd=reg))
        self.assertEqual(len(lines), 1, lines)
        self.assertIn("file name must be 2026-11-02-aaaaaaaaaaaa.txt", lines[0])

    def test_privacy_scan_refuses_tokens_ids_and_machine_paths(self):
        token = "gh" + "p_" + "A1b2" * 9
        planted = {
            "summary": ("listing", f"Uses {token} to sign in.", "a token"),
            "login": ("listing", "Your login under /home/example-user/.config", "a machine path"),
            "plugs_into": ("listing", "Thread thr_" + "a1b2c3d4e5 of a fleet", "a private id"),
            "host": ("receipt", "C:\\Users\\example\\host", "a machine path"),
        }
        for field, (where, value, label) in planted.items():
            with self.subTest(field):
                reg = self.registry("valid/verified-driver", commit=False)
                if where == "listing":
                    path = reg / "listings/example-driver.json"
                    data = json.loads(path.read_text())
                    data[field] = value
                    path.write_text(json.dumps(data))
                else:
                    receipt = reg / "receipts/example-driver/2026-11-01-aaaaaaaaaaaa.txt"
                    receipt.write_text(receipt.read_text().replace("# host: example-host", "# host: " + value))
                result = run("check", cwd=reg)
                lines = failures(result)
                self.assertEqual((result.returncode, len(lines)), (1, 1), lines)
                self.assertIn(f"looks like {label}", lines[0])
                self.assertNotIn(value, result.stdout)

    def test_receipt_edit_or_delete_against_a_base_is_refused(self):
        reg = self.registry("valid/verified-driver")
        receipt = reg / "receipts/example-driver/2026-11-01-aaaaaaaaaaaa.txt"
        self.write(reg / "receipts/example-driver/2026-11-02-aaaaaaaaaaaa.txt", receipt.read_text())
        self.assertEqual(run("check", "--base", "HEAD", cwd=reg).returncode, 0)
        receipt.write_text(receipt.read_text().replace("Harness 1.0", "Harness 1.1"))
        edited = failures(run("check", "--base", "HEAD", cwd=reg))
        self.assertEqual(len(edited), 1, edited)
        self.assertIn("a merged receipt never changes", edited[0])
        receipt.unlink()
        deleted = failures(run("check", "--base", "HEAD", cwd=reg))
        self.assertTrue(any("a merged receipt never changes" in line for line in deleted), deleted)

    def test_symlinked_listing_is_refused(self):
        reg = self.registry("valid/listed-available", commit=False)
        (reg / "listings/example-tool.json").rename(self.tmp / "outside.json")
        (reg / "listings/example-tool.json").symlink_to(self.tmp / "outside.json")
        lines = failures(run("check", cwd=reg))
        self.assertEqual(len(lines), 1, lines)
        self.assertIn("must be a regular file", lines[0])


class Index(Temp):
    def test_index_of_the_valid_fixtures_is_the_contract_example(self):
        reg = self.registry(*(f"valid/{p.name}" for p in (FIXTURES / "valid").iterdir()))
        result = run("index", cwd=reg)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        head = git(reg, "rev-parse", "HEAD")
        self.assertEqual(json.loads(result.stdout)["commit"], head)
        self.assertEqual(result.stdout.replace(head, SYNTHETIC_COMMIT), (FIXTURES / "index.json").read_text())

    def test_index_reads_head_and_refuses_an_unsafe_checkout(self):
        reg = self.registry("valid/listed-available", "valid/verified-driver")
        cases = {
            "untracked": lambda: self.write(reg / "listings/new-tool.json", "{}"),
            "uncommitted": lambda: (reg / "listings/example-tool.json").write_text("{}"),
            "not on origin/main": lambda: git(reg, "commit", "-q", "--allow-empty", "-m", "ahead"),
        }
        for name, change in cases.items():
            with self.subTest(name):
                change()
                result = run("index", cwd=reg)
                self.assertEqual((result.returncode, result.stdout), (1, ""), result.stdout)
                self.assertIn("index:", result.stderr)
                git(reg, "reset", "-q", "--hard", "origin/main")
                git(reg, "clean", "-qfd")
        self.assertEqual(run("index", cwd=reg).returncode, 0)

    def test_index_refuses_a_head_that_fails_check(self):
        reg = self.registry("broken/receipt-4-of-5")
        result = run("index", cwd=reg)
        self.assertEqual((result.returncode, result.stdout.count("\n")), (1, 1), result.stdout)
        self.assertIn("line 11 must be", result.stdout)


class Skill(Temp):
    def setUp(self):
        super().setUp()
        self.home = self.tmp / "home"
        source = self.tmp / "remote/example-owner/example-skills"
        source.mkdir(parents=True)
        git(source, "init", "-q", "-b", "main")
        self.write(source / "check.py", "import os, sys\n"
                   "assert 'PLANTED_SECRET' not in os.environ, 'secret leaked'\n"
                   "assert set(os.environ) <= {'PATH', 'HOME', 'PWD', 'SHLVL', '_', 'LC_CTYPE'}, sorted(os.environ)\n"
                   "sys.exit(int(open('result').read()))\n")
        self.commits = {}
        for name, code in (("passes", "0"), ("fails", "1")):
            self.write(source / "result", code)
            git(source, "add", "-A")
            git(source, "commit", "-q", "-m", name)
            self.commits[name] = git(source, "rev-parse", "HEAD")
        self.write(self.home / ".gitconfig",
                   f'[url "{(self.tmp / "remote").as_uri()}/"]\n\tinsteadOf = https://github.com/\n')
        self.env = {"PATH": os.environ["PATH"], "HOME": str(self.home), "PLANTED_SECRET": "x"}

    def skill_registry(self, commit, check="python3 check.py"):
        reg = self.registry("valid/verified-skill", commit=False)
        path = reg / "listings/example-skill.json"
        data = json.loads(path.read_text())
        data["proof"] = {"source": f"example-owner/example-skills@{commit}", "check": check}
        path.write_text(json.dumps(data))
        return reg

    def test_skill_check_passes_only_at_a_passing_commit(self):
        passing = run("skill", "example-skill", cwd=self.skill_registry(self.commits["passes"]), env=self.env)
        self.assertEqual(passing.returncode, 0, passing.stdout + passing.stderr)
        self.assertIn("skill example-skill: pass", passing.stdout)
        shutil.rmtree(self.tmp / "registry")
        failing = run("skill", "example-skill", cwd=self.skill_registry(self.commits["fails"]), env=self.env)
        self.assertEqual(failing.returncode, 1, failing.stdout + failing.stderr)
        self.assertIn("skill example-skill: refused, the check exited 1", failing.stdout)

    def test_skill_check_refuses_a_missing_commit_and_a_timeout(self):
        missing = run("skill", "example-skill", cwd=self.skill_registry("e" * 40), env=self.env)
        self.assertEqual(missing.returncode, 1)
        self.assertIn("is not in", missing.stdout)
        shutil.rmtree(self.tmp / "registry")
        reg = self.skill_registry(self.commits["passes"], check="sleep 30")
        slow = run("skill", "example-skill", "--timeout", "1", cwd=reg, env=self.env)
        self.assertEqual(slow.returncode, 1)
        self.assertIn("did not finish in 1 seconds", slow.stdout)

    def test_changed_skills_lists_added_or_changed_skill_listings(self):
        reg = self.registry("valid/listed-available", "valid/verified-skill")
        base = git(reg, "rev-parse", "HEAD")
        self.assertEqual(run("changed-skills", base, cwd=reg).stdout, "")
        shutil.copytree(FIXTURES / "valid/verified-driver-and-skill", reg, dirs_exist_ok=True)
        tool = reg / "listings/example-tool.json"
        tool.write_text(tool.read_text().replace("A synthetic tool", "A tool"))
        git(reg, "add", "-A")
        git(reg, "commit", "-q", "-m", "change")
        self.assertEqual(run("changed-skills", base, cwd=reg).stdout, "example-driver-kit\n")


if __name__ == "__main__":
    unittest.main()
