import contextlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import unittest.mock
import urllib.error
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
    "url-last-label-hex": ("listings/example-tool.json", '"url" must be an https:// URL'),
    "url-last-label-hex-upper": ("listings/example-tool.json", '"url" must be an https:// URL'),
    "url-last-label-hex-empty": ("listings/example-tool.json", '"url" must be an https:// URL'),
    "link-url-last-label-hex": ("listings/example-tool.json", '"links[0].url" must be an https:// URL'),
    "url-punycode-malformed": ("listings/example-tool.json", '"url" must be an https:// URL'),
    "url-punycode-undecodable": ("listings/example-tool.json", '"url" must be an https:// URL'),
    "url-punycode-mapped": ("listings/example-tool.json", '"url" must be an https:// URL'),
    "link-url-punycode-malformed": ("listings/example-tool.json", '"links[0].url" must be an https:// URL'),
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
NAME_AND_URL_BOTH_END_IN_A_NEWLINE = {"name-final-newline": 2}

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
                self.assertEqual(len(lines), NAME_AND_URL_BOTH_END_IN_A_NEWLINE.get(name, 1), result.stdout)
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
        self.write(reg / "receipts/example-driver/2026-11-02-aaaaaaaaaaaa.txt",
                   receipt.read_text().replace("# date: 2026-11-01", "# date: 2026-11-02"))
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

    def test_idna2008_labels_beyond_unicode_3_2_are_accepted(self):
        reg = self.registry("valid/listed-available", commit=False)
        path = reg / "listings/example-tool.json"
        data = json.loads(path.read_text())
        data["url"] = "https://xn--d5b4e9a9e.xn--54b7fta0cc/"
        data["links"] = [{"label": "Chillu", "url": "https://xn--6yccdefg.example.com/"}]
        path.write_text(json.dumps(data, indent=2) + "\n")
        accepted = run("check", cwd=reg)
        self.assertEqual(accepted.returncode, 0, accepted.stdout)
        self.assertRegex(accepted.stdout, r"^check: ok, 1 listings and 0 receipts checked\n$")
        data["url"] = "https://xn--e28h.example.com/"
        del data["links"]
        path.write_text(json.dumps(data, indent=2) + "\n")
        refused = run("check", cwd=reg)
        lines = failures(refused)
        self.assertEqual(refused.returncode, 1, refused.stdout)
        self.assertEqual(len(lines), 1, lines)
        self.assertIn('"url" must be an https:// URL', lines[0])

    def test_idna2008_bidi_class_and_casefold_follow_the_current_unicode(self):
        reg = self.registry("valid/listed-available", commit=False)
        path = reg / "listings/example-tool.json"
        data = json.loads(path.read_text())
        cases = (
            ("arabic letter from after Unicode 3.2", "https://xn--ngb60d.example.com/", True),
            ("hebrew mark from after Unicode 3.2", "https://xn--tcb5g.example.com/", True),
            ("cherokee letter that IDNA2008 casefold keeps", "https://xn--lce.example.com/", True),
            ("right-to-left label with a left-to-right letter", "https://xn--ngb28p.example.com/", False),
            ("cherokee letter that casefold maps away", "https://xn--tce.example.com/", False),
            ("old hangul jamo", "https://xn--hk9a.example.com/", False),
            ("unassigned code point", "https://xn--mce.example.com/", False),
            ("capital letter that casefold maps", "https://xn--wma.example.com/", False),
            ("leading combining mark", "https://xn--z0b.example.com/", False),
            ("variation selector", "https://xn--cd36e.example.com/", False),
            ("nko lajanyalan", "https://xn--ytb.example.com/", False),
            ("zero width joiner", "https://xn--1ug.example.com/", False),
        )
        for name, url, ok in cases:
            with self.subTest(name):
                data["url"] = url
                path.write_text(json.dumps(data, indent=2) + "\n")
                result = run("check", cwd=reg)
                if ok:
                    self.assertEqual(result.returncode, 0, result.stdout)
                    self.assertRegex(result.stdout, r"^check: ok, 1 listings and 0 receipts checked\n$")
                else:
                    lines = failures(result)
                    self.assertEqual(result.returncode, 1, result.stdout)
                    self.assertEqual(len(lines), 1, lines)
                    self.assertIn('"url" must be an https:// URL', lines[0])


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
        self.source_base = (self.tmp / "remote").as_uri()
        self.home.mkdir()
        self.env = {"PATH": os.environ["PATH"], "HOME": str(self.home), "PLANTED_SECRET": "x"}

    def skill_registry(self, commit, check="python3 check.py"):
        reg = self.registry("valid/verified-skill", commit=False)
        path = reg / "listings/example-skill.json"
        data = json.loads(path.read_text())
        data["proof"] = {"source": f"example-owner/example-skills@{commit}", "check": check}
        path.write_text(json.dumps(data))
        return reg

    def skill(self, reg, *args, env=None):
        return run("skill", "--source-base", self.source_base, *args, "example-skill", cwd=reg, env=env or self.env)

    def test_skill_check_passes_only_at_a_passing_commit(self):
        passing = self.skill(self.skill_registry(self.commits["passes"]))
        self.assertEqual(passing.returncode, 0, passing.stdout + passing.stderr)
        self.assertIn("skill example-skill: pass", passing.stdout)
        shutil.rmtree(self.tmp / "registry")
        failing = self.skill(self.skill_registry(self.commits["fails"]))
        self.assertEqual(failing.returncode, 1, failing.stdout + failing.stderr)
        self.assertIn("skill example-skill: refused, the check exited 1", failing.stdout)

    def test_skill_check_refuses_a_missing_commit_and_a_timeout(self):
        missing = self.skill(self.skill_registry("e" * 40))
        self.assertEqual(missing.returncode, 1)
        self.assertIn("is not in", missing.stdout)
        shutil.rmtree(self.tmp / "registry")
        reg = self.skill_registry(self.commits["passes"], check="sleep 30")
        slow = self.skill(reg, "--timeout", "1")
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

    def ident_registry(self, check):
        reg = self.skill_registry(self.commits["passes"], check=check)
        self.write(reg / ".gitattributes", "listings/*.json ident\n")
        git(reg, "init", "-q", "-b", "main")
        git(reg, "add", "-A")
        git(reg, "commit", "-q", "-m", "registry")
        listing = reg / "listings/example-skill.json"
        listing.unlink()
        git(reg, "checkout", "--", "listings/example-skill.json")
        self.assertIn("$Id: ", listing.read_text(), "the checkout attribute did not rewrite the command")
        return reg

    def test_mk13_r2_skill_runs_the_commits_command_not_the_checkouts(self):
        reg = self.ident_registry("test '$Id$' = '$'Id'$'")
        self.assertEqual(run("check", "--rev", "HEAD", cwd=reg).returncode, 0)
        result = self.skill(reg, "--rev", "HEAD")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("skill example-skill: pass", result.stdout)

    def test_mk13_r2_the_skill_job_discovers_and_runs_the_commits_listing(self):
        reg = self.ident_registry("test '$Id$' = '$'Id'$'")
        for folder in ("check", "schema"):
            shutil.copytree(ROOT / folder, self.tmp / "trusted" / folder)
        shim = self.tmp / "shim/sudo"
        self.write(shim, '#!/bin/bash\n[ "$1" = -n ] && shift\nargs=()\nwhile [ $# -gt 0 ]; do\n'
                   '  if [ "$1" = --isolate ]; then shift 2; args+=(--source-base "$SOURCE_BASE")\n'
                   '  else args+=("$1"); shift; fi\ndone\nexec "${args[@]}"\n')
        shim.chmod(0o755)
        steps = workflow_steps()["skill"]
        step = [s["run"] for s in steps if s["name"].startswith("Run the skill's check at its pinned commit")]
        self.assertEqual(len(step), 1)
        empty = git(reg, "hash-object", "-t", "tree", "/dev/null")
        found = run("changed-skills", empty, cwd=reg)
        self.assertEqual(found.stdout, "example-skill\n", found.stdout + found.stderr)
        env = {"PATH": f"{shim.parent}:{os.environ['PATH']}", "HOME": str(self.home), "ID": "example-skill",
               "SOURCE_BASE": self.source_base}
        result = subprocess.run(["bash", "--noprofile", "--norc", "-eo", "pipefail", "-c", step[0]], cwd=reg, env=env,
                                capture_output=True, text=True, timeout=120)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("skill example-skill: pass", result.stdout)

RECEIPT = "receipts/example-driver/2026-11-01-aaaaaaaaaaaa.txt"
WORKFLOW = ROOT / ".github/workflows/check.yml"
REQUIRE_ISOLATION = os.environ.get("WIZMARKET_REQUIRE_ISOLATION") == "1"


def edit_json(path, change):
    data = json.loads(path.read_text())
    change(data)
    path.write_text(json.dumps(data))


class Review(Temp):
    """One case per finding of the review at c76e9d4 (R3 to R9)."""

    def refused(self, reg, *texts, count=1):
        result = run("check", cwd=reg)
        lines = failures(result)
        self.assertEqual((result.returncode, result.stderr, len(lines)), (1, "", count), result.stdout + result.stderr)
        for text in texts:
            self.assertIn(text, lines[0])
        self.assertTrue(all("; fix: " in line for line in lines), lines)
        return result

    def test_r3_version_and_stop_lines_are_the_kits_passing_forms(self):
        for n, old, new in ((9, "pass version: openwiz:records v1, and the schema is driver v1", "pass version: fine"),
                            (12, "pass stop: the run ended, and a wake after it is refused", "pass stop: it stopped")):
            with self.subTest(line=n):
                reg = self.registry("valid/verified-driver", commit=False)
                receipt = reg / RECEIPT
                self.assertIn(old + "\n", receipt.read_text())
                receipt.write_text(receipt.read_text().replace(old, new))
                result = self.refused(reg, f"line {n} must be")
                self.assertTrue(failures(result)[0].endswith(FALSE_VERIFIED_FIX))
                shutil.rmtree(reg)

    def test_r4_diagnostics_never_repeat_private_paths_or_keys(self):
        planted = "thr_syn-planted_4"
        cases = {
            "unknown key": lambda reg: edit_json(reg / "listings/example-tool.json", lambda d: d.update({planted: 1})),
            "repeated key": lambda reg: (reg / "listings/example-tool.json").write_text(
                (reg / "listings/example-tool.json").read_text().replace("{", f'{{"{planted}": 1, "{planted}": 2,', 1)),
            "file name": lambda reg: (reg / "listings/example-tool.json").rename(reg / f"listings/{planted}.json"),
            "receipt folder": lambda reg: self.write(reg / f"receipts/{planted}/x.txt", "x\n"),
            "line break in a name": lambda reg: (reg / "listings/example-tool.json").rename(
                reg / "listings/example\ntool.json"),
        }
        for name, plant in cases.items():
            with self.subTest(name):
                reg = self.registry("valid/listed-available", commit=False)
                plant(reg)
                result = run("check", cwd=reg)
                self.assertEqual((result.returncode, result.stderr), (1, ""), result.stdout + result.stderr)
                self.assertNotIn(planted, result.stdout)
                self.assertNotIn("example\ntool", result.stdout)
                self.assertTrue(all("; fix: " in line for line in failures(result)), result.stdout)
                shutil.rmtree(reg)

    def test_r10_v2_package_diagnostics_never_repeat_a_private_repository(self):
        planted = "thr_syn-planted_4"
        repository = f"example-owner/{planted}"
        cases = {
            "asset URL": ("v2/valid/listed-driver", "pinned-driver.json", False,
                          "not a release asset of the listed repository"),
            "receipt": ("v2/valid/verified-driver", "verified-pinned.json", True,
                        'the receipt\'s "# driver:" line must name'),
        }
        for name, (folder, listing, match_asset, reason) in cases.items():
            with self.subTest(name):
                reg = self.registry(folder, commit=False)
                path = reg / "listings" / listing
                data = json.loads(path.read_text())
                data["package"]["repository"] = repository
                if match_asset:
                    data["package"]["asset_url"] = ("https://github.com/" + repository
                                                    + "/releases/download/v1.0.0/driver.tar.gz")
                path.write_text(json.dumps(data, indent=2) + "\n")
                result = run("check", cwd=reg)
                self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                self.assertIn(reason, result.stdout)
                self.assertNotIn(planted, result.stdout)
                self.assertNotIn(repository, result.stdout)
                shutil.rmtree(reg)

    def test_r4_privacy_scan_finds_every_documented_id_shape(self):
        shapes = ["thr_s", "thr_syn-a_b-c", "thr_9" + "x" * 60, "prj_syn1", "proj_syn1", "mch_syn1", "usr_syn1",
                  "acct_syn1", "auto_syn1", "cr_0a1b2c3d-4e5f", "sess_synabcdef"]
        for shape in shapes:
            with self.subTest(shape):
                reg = self.registry("valid/listed-available", commit=False)
                edit_json(reg / "listings/example-tool.json", lambda d: d.update({"plugs_into": f"Fleet {shape} here"}))
                result = self.refused(reg, "looks like a private id")
                self.assertNotIn(shape, result.stdout)
                shutil.rmtree(reg)

    def test_r4_a_referenced_receipt_failing_the_scan_names_the_false_verified_fix(self):
        reg = self.registry("valid/verified-driver", commit=False)
        receipt = reg / RECEIPT
        receipt.write_text(receipt.read_text().replace("# host: example-host", "# host: /home/planted/host"))
        result = self.refused(reg, "looks like a machine path")
        self.assertTrue(failures(result)[0].endswith(FALSE_VERIFIED_FIX), result.stdout)

    def test_r5_every_receipt_is_checked_whether_or_not_a_listing_names_it(self):
        reg = self.registry("valid/listed-available", commit=False)
        self.write(reg / "receipts/example-tool/2026-11-01-aaaaaaaaaaaa.txt", "one line\n")
        self.refused(reg, "receipts/example-tool/2026-11-01-aaaaaaaaaaaa.txt: ", "must be exactly 14 lines")
        shutil.rmtree(reg)
        reg = self.registry("valid/listed-available", "valid/verified-driver", commit=False)
        edit_json(reg / "listings/example-driver.json", lambda d: (d.pop("proof"), d.update({"status": "listed"})))
        result = run("check", cwd=reg)
        self.assertEqual(result.stdout, "check: ok, 2 listings and 1 receipts checked\n", result.stdout)

    def test_r6_a_wrong_value_type_gets_its_file_and_fix_never_a_traceback(self):
        values = [5, None, True, "text", [], {}, [5], {"a": 1}, [["x"]]]
        for folder in ("valid/verified-driver", "valid/verified-skill", "valid/listed-being-built"):
            for field in ("name", "summary", "tags", "url", "plugs_into", "publisher", "stage", "login", "links",
                          "status", "proof"):
                for value in values:
                    with self.subTest(folder=folder, field=field, value=value):
                        reg = self.registry(folder, commit=False)
                        path = next((reg / "listings").iterdir())
                        edit_json(path, lambda d: d.update({field: value}))
                        result = run("check", cwd=reg)
                        self.assertEqual(result.stderr, "")
                        lines = failures(result)
                        if result.returncode:
                            self.assertTrue(lines and all("; fix: " in line for line in lines), result.stdout)
                        shutil.rmtree(reg)
        reg = self.registry("valid/verified-driver", commit=False)
        edit_json(reg / "listings/example-driver.json", lambda d: d.update({"tags": 5}))
        self.refused(reg, "listings/example-driver.json: ", '"tags" must be')

    def test_r7_index_refuses_ignored_files_and_an_ambiguous_origin_main(self):
        reg = self.registry("valid/listed-available")
        self.write(reg / ".git/info/exclude", "scratch.txt\n")
        self.write(reg / "scratch.txt", "scratch\n")
        result = run("index", cwd=reg)
        self.assertEqual((result.returncode, result.stdout), (1, ""), result.stdout)
        (reg / "scratch.txt").unlink()
        self.assertEqual(run("index", cwd=reg).returncode, 0)
        git(reg, "commit", "-q", "--allow-empty", "-m", "ahead")
        git(reg, "tag", "origin/main")
        result = run("index", cwd=reg)
        self.assertEqual((result.returncode, result.stdout), (1, ""), result.stdout)
        self.assertIn("not origin/main or an ancestor", result.stderr)

    def test_r8_an_unpaired_surrogate_is_refused_by_check_and_index_alike(self):
        for where in ("value", "key"):
            with self.subTest(where):
                reg = self.registry("valid/listed-available", commit=False)
                path = reg / "listings/example-tool.json"
                text = path.read_text()
                path.write_text(text.replace('"Example tool"', '"Example \\ud800 tool"') if where == "value"
                                else text.replace("{", '{"\\udc00": 1,', 1))
                self.assertNotEqual(path.read_text(), text)
                git(reg, "init", "-q", "-b", "main")
                git(reg, "add", "-A")
                git(reg, "commit", "-q", "-m", "registry")
                git(reg, "update-ref", "refs/remotes/origin/main", "HEAD")
                self.refused(reg, "listings/example-tool.json: ", "unpaired surrogate")
                index = run("index", cwd=reg)
                self.assertEqual((index.returncode, failures(index)), (1, failures(run("check", cwd=reg))),
                                 index.stdout + index.stderr)
                self.assertIn("index: HEAD does not pass check", index.stderr)
                self.assertNotIn("Traceback", index.stderr)
                shutil.rmtree(reg)


class SkillSandbox(Skill):
    """R2: the skill's check never reaches the verifier's config, output, processes or files."""

    def marker_check(self, marker, detach=""):
        return f"{detach} python3 -c 'import time; time.sleep(300)' {marker} >/dev/null 2>&1 & exit 0"

    def assertGone(self, marker):
        found = subprocess.run(["pgrep", "-f", marker], capture_output=True, text=True).stdout.split()
        for pid in found:
            subprocess.run(["sudo", "-n", "kill", "-9", pid], capture_output=True)
            subprocess.run(["kill", "-9", pid], capture_output=True)
        self.assertEqual(found, [], f"{marker} still runs")

    def test_source_acquisition_ignores_the_verifiers_git_config_and_env(self):
        hooks, marker = self.tmp / "hooks", self.tmp / "hook-ran"
        self.write(hooks / "post-checkout", f"#!/bin/sh\ntouch '{marker}'\n")
        (hooks / "post-checkout").chmod(0o755)
        self.write(self.home / ".gitconfig", f"[core]\n\thooksPath = {hooks}\n")
        env = {**self.env, "GIT_CONFIG_COUNT": "1", "GIT_CONFIG_KEY_0": "core.hooksPath", "GIT_CONFIG_VALUE_0": str(hooks)}
        result = self.skill(self.skill_registry(self.commits["passes"]), env=env)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertFalse(marker.exists(), "the verifier's git config ran a hook during source acquisition")

    def test_mk13_r2_replayed_output_holds_neither_workflow_command_format(self):
        cases = (("::", "echo '::error::planted'; echo '  ::set-output name=x::y'", r":\x3aerror:\x3aplanted"),
                 ("##[", "echo 'text ##[error]planted'; echo '###[set-output name=x;]y'", r"text #\x23[error]planted"))
        for form, check, shown in cases:
            with self.subTest(form):
                shutil.rmtree(self.tmp / "registry", ignore_errors=True)
                result = self.skill(self.skill_registry(self.commits["passes"], check=check))
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertNotIn(form, result.stdout + result.stderr)
                self.assertIn("  | " + shown + "\n", result.stdout)

    def test_processes_the_check_started_end_with_it(self):
        marker = "wizmarket-marker-" + os.urandom(4).hex()
        result = self.skill(self.skill_registry(self.commits["passes"], check=self.marker_check(marker)))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertGone(marker)


def isolation_available():
    probe = ["sudo", "-n", "unshare", "--pid", "--fork", "--kill-child", "--mount-proc", "--net", "--", "true"]
    try:
        return subprocess.run(probe, capture_output=True, timeout=30).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


class IsolatedSkill(SkillSandbox):
    """R2 under --isolate, as CI runs it: root launches, the check runs as another user in fresh namespaces."""

    def setUp(self):
        if not isolation_available():
            if REQUIRE_ISOLATION:
                self.fail("WIZMARKET_REQUIRE_ISOLATION=1 but sudo -n unshare is not available")
            self.skipTest("needs sudo -n and unshare (CI sets WIZMARKET_REQUIRE_ISOLATION=1)")
        super().setUp()
        self.tmp.chmod(0o755)

    def skill(self, reg, *args, env=None):
        env = env or self.env
        launch = ["sudo", "-n", "env", "-i", *(f"{k}={v}" for k, v in env.items()), sys.executable, "-I", str(CHECK),
                  "skill", "--isolate", "nobody", "--source-base", self.source_base, *args, "example-skill"]
        return subprocess.run(launch, cwd=reg, capture_output=True, text=True, timeout=120)

    def test_isolated_check_passes_and_fails_by_its_commit(self):
        self.test_skill_check_passes_only_at_a_passing_commit()

    def test_isolated_check_has_no_network(self):
        probe = ("python3 -c \"import socket, sys; s = socket.socket(); s.settimeout(5); "
                 "sys.exit(0 if s.connect_ex(('1.1.1.1', 53)) else 1)\"")
        result = self.skill(self.skill_registry(self.commits["passes"], check=probe))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_isolated_check_cannot_touch_the_registry_or_see_the_verifier(self):
        reg = self.tmp / "registry"
        listing = reg / "listings/example-skill.json"
        source = self.tmp / "remote/example-owner/example-skills"
        self.write(source / "attack.sh", f"echo planted >> '{listing}'; touch '{reg}/listings/planted.json'\n"
                   f"test ! -e /proc/{os.getpid()} && kill -0 1 && ! kill -0 {os.getpid()}\n")
        git(source, "add", "-A")
        git(source, "commit", "-q", "-m", "attack")
        self.skill_registry(git(source, "rev-parse", "HEAD"), check="sh attack.sh")
        before = listing.read_bytes()
        result = self.skill(reg)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(listing.read_bytes(), before)
        self.assertFalse((reg / "listings/planted.json").exists())

    def test_isolated_processes_end_even_when_detached(self):
        marker = "wizmarket-marker-" + os.urandom(4).hex()
        result = self.skill(self.skill_registry(self.commits["passes"], check=self.marker_check(marker, "setsid")))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertGone(marker)

    def test_isolated_timeout_tears_down(self):
        marker = "wizmarket-marker-" + os.urandom(4).hex()
        reg = self.skill_registry(self.commits["passes"],
                                  check=f"setsid python3 -c 'import time; time.sleep(300)' {marker} & sleep 30")
        result = self.skill(reg, "--timeout", "2")
        self.assertEqual(result.returncode, 1)
        self.assertIn("did not finish in 2 seconds", result.stdout)
        self.assertGone(marker)


V2 = FIXTURES / "v2"
V2_VALID = ["listed-driver", "verified-driver", "verified-harness"]
V2_BROKEN = {
    "malformed-package": ("listings/pinned-driver.json", '"package" must hold exactly'),
    "malformed-key-host": ("listings/pinned-driver.json", '"key_host.origin" is not the shape'),
    "key-host-without-package": ("listings/pinned-driver.json", '"key_host" needs a package block'),
    "package-other-kind": ("listings/example-tool.json", '"package" is only for a listing tagged driver or harness'),
    "asset-not-release": ("listings/pinned-driver.json", "not a release asset of the listed repository"),
    "verified-other-commit": ("listings/verified-pinned.json", 'the receipt\'s "# driver:" line must name'),
    "verified-other-kit": ("listings/verified-pinned.json", 'the receipt\'s "# kit:" line must be'),
}


class V2Fixtures(unittest.TestCase):
    def test_every_v2_fixture_is_in_a_table(self):
        self.assertEqual(sorted(p.name for p in (V2 / "broken").iterdir()), sorted(V2_BROKEN))
        self.assertEqual(sorted(p.name for p in (V2 / "valid").iterdir()), V2_VALID)

    def test_valid_v2_fixtures_are_accepted(self):
        for name in V2_VALID:
            with self.subTest(name):
                result = run("check", cwd=V2 / "valid" / name)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertRegex(result.stdout, r"^check: ok, \d+ listings and \d+ receipts checked\n$")

    def test_each_v2_refusal_fails_first_for_its_reason(self):
        for name, (path, reason) in V2_BROKEN.items():
            with self.subTest(name):
                result = run("check", cwd=V2 / "broken" / name)
                lines = failures(result)
                self.assertEqual(result.returncode, 1, result.stdout)
                self.assertEqual(len(lines), 1, result.stdout)
                self.assertTrue(lines[0].startswith(path + ": "), lines)
                self.assertIn(reason, lines[0])
                self.assertIn("; fix: ", lines[0])


class V2Index(Temp):
    def test_key_host_refuses_a_64_character_dns_label(self):
        reg = self.registry("v2/valid/verified-harness", commit=False)
        path = reg / "listings/verified-harness.json"
        data = json.loads(path.read_text())
        data["key_host"]["origin"] = "https://" + "a" * 64 + ".example.com"
        path.write_text(json.dumps(data, indent=2) + "\n")
        refused = failures(run("check", cwd=reg))
        self.assertEqual(len(refused), 1, refused)
        self.assertIn('"key_host.origin" is not the shape', refused[0])

    def test_verified_v2_passes_only_for_its_package_commit(self):
        reg = self.registry("v2/valid/verified-driver", commit=False)
        self.assertEqual(run("check", cwd=reg).returncode, 0)
        path = reg / "listings/verified-pinned.json"
        data = json.loads(path.read_text())
        data["package"]["commit"] = "c" * 40
        path.write_text(json.dumps(data, indent=2) + "\n")
        refused = failures(run("check", cwd=reg))
        self.assertEqual(len(refused), 1, refused)
        self.assertIn('"# driver:" line must name', refused[0])
        self.assertIn("package's repository and commit", refused[0])
        data["package"]["commit"] = "a" * 40
        data["package"]["kit_commit"] = "c" * 40
        path.write_text(json.dumps(data, indent=2) + "\n")
        kit = failures(run("check", cwd=reg))
        self.assertEqual(len(kit), 1, kit)
        self.assertIn('"# kit:" line must be', kit[0])

    def test_v2_index_carries_the_package_and_names_its_contract(self):
        reg = self.registry(*(f"v2/valid/{name}" for name in V2_VALID))
        result = run("index", cwd=reg)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        head = git(reg, "rev-parse", "HEAD")
        self.assertEqual(result.stdout.replace(head, SYNTHETIC_COMMIT), (V2 / "index.json").read_text())
        index = json.loads(result.stdout)
        self.assertEqual(index["contract"], "listing.v1")
        by_id = {entry["id"]: entry for entry in index["listings"]}
        for entry in by_id.values():
            self.assertEqual(entry["contract"], "listing.v2")
            self.assertEqual(set(entry["package"]),
                             {"driver", "version", "repository", "commit", "asset_url", "sha256", "kit_commit"})
        self.assertEqual(by_id["verified-harness"]["key_host"]["origin"], "https://api.example.com")
        self.assertNotIn("key_host", by_id["verified-pinned"])
        pinned = by_id["verified-pinned"]
        self.assertEqual(pinned["proof"]["receipt"]["date"], "2026-11-01")
        self.assertIn(head, pinned["proof"]["receipt"]["url"])

    def test_a_v1_listing_beside_a_v2_listing_is_byte_identical(self):
        folders = [f"valid/{path.name}" for path in (FIXTURES / "valid").iterdir()]
        folders += [f"v2/valid/{name}" for name in V2_VALID]
        reg = self.registry(*folders)
        result = run("index", cwd=reg)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        head = git(reg, "rev-parse", "HEAD")
        got = {entry["id"]: entry for entry in json.loads(result.stdout)["listings"]}
        want = json.loads((FIXTURES / "index.json").read_text().replace(SYNTHETIC_COMMIT, head))
        for entry in want["listings"]:
            self.assertEqual(json.dumps(got[entry["id"]], indent=2, sort_keys=True, ensure_ascii=False),
                             json.dumps(entry, indent=2, sort_keys=True, ensure_ascii=False))
            self.assertNotIn("contract", got[entry["id"]])
            self.assertNotIn("package", got[entry["id"]])


def workflow_steps():
    """Each job's steps as (name, run) from check.yml, read by indentation: enough for this one file."""
    jobs, job, step, block = {}, None, None, None
    for line in WORKFLOW.read_text().splitlines():
        indent = len(line) - len(line.lstrip(" "))
        if block is not None:
            if line.strip() and indent <= block:
                block = None
            else:
                step["run"] += line[block + 2:] + "\n"
                continue
        if indent == 2 and line.rstrip().endswith(":") and job is not False:
            job = line.strip()[:-1]
            jobs[job] = []
        elif line.startswith("jobs:"):
            job = None
        elif job and indent == 6 and line.lstrip().startswith("- "):
            step = {"name": "", "run": ""}
            jobs[job].append(step)
            if line.lstrip().startswith("- name: "):
                step["name"] = line.split("- name: ", 1)[1].strip()
        elif job and step is not None and indent == 8 and line.lstrip().startswith("name: "):
            step["name"] = line.split("name: ", 1)[1].strip()
        elif job and step is not None and line.strip() == "run: |":
            block = indent
    return {name: steps for name, steps in jobs.items() if steps}


GATE_STEP = "Take the gate from the base revision"


class Workflow(Temp):
    """R1 and R9: the gate step every required job runs, executed on synthetic repositories."""

    def gate_script(self):
        gates = {job: [s["run"] for s in steps if s["name"] == GATE_STEP] for job, steps in workflow_steps().items()}
        for job in ("check", "skill"):
            self.assertEqual(len(gates.get(job, [])), 1, f"job {job} has no step {GATE_STEP!r}")
        scripts = {run for runs in gates.values() for run in runs}
        self.assertEqual(len(scripts), 1, "every job's gate step is the same script")
        return scripts.pop()

    def repo(self):
        repo = self.tmp / "work/candidate"
        repo.mkdir(parents=True)
        git(repo, "init", "-q", "-b", "main")
        return repo

    def commit(self, repo, files, message, parents=()):
        for path, text in files.items():
            if text is None:
                (repo / path).unlink()
            else:
                self.write(repo / path, text)
        git(repo, "add", "-A")
        git(repo, "commit", "-q", "--allow-empty", "-m", message)
        return git(repo, "rev-parse", "HEAD")

    def gate(self, event, base):
        env_file = self.tmp / "github-env"
        env_file.write_text("")
        env = {"PATH": os.environ["PATH"], "HOME": str(self.tmp), "EVENT": event, "BASE_SHA": base,
               "GITHUB_ENV": str(env_file)}
        result = subprocess.run(["bash", "--noprofile", "--norc", "-eo", "pipefail", "-c", self.gate_script()],
                                cwd=self.tmp / "work", env=env, capture_output=True, text=True, timeout=60)
        values = dict(line.split("=", 1) for line in env_file.read_text().splitlines() if "=" in line)
        return result, values

    def trusted(self, path="check/check.py"):
        return (self.tmp / "work/trusted" / path).read_text()

    def test_r1_a_pull_request_is_checked_by_the_base_revisions_check(self):
        repo = self.repo()
        base = self.commit(repo, {"check/check.py": "base\n", "schema/listing.v1.json": "base\n"}, "main")
        self.commit(repo, {"check/check.py": "candidate\n", "schema/listing.v1.json": "candidate\n",
                           "listings/x.json": "{}\n"}, "pull request")
        result, values = self.gate("pull_request", base)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual((self.trusted(), self.trusted("schema/listing.v1.json")), ("base\n", "base\n"))
        self.assertEqual(values, {"GATE": "base", "RECEIPT_BASE": base})

    def test_r1_the_first_installation_bootstraps_explicitly(self):
        repo = self.repo()
        base = self.commit(repo, {"README.md": "registry\n"}, "main")
        self.commit(repo, {"check/check.py": "candidate\n"}, "install the check")
        result, values = self.gate("pull_request", base)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.trusted(), "candidate\n")
        self.assertEqual(values, {"GATE": "bootstrap", "RECEIPT_BASE": base})
        self.assertIn("gate: bootstrap", result.stdout)

    def test_r1_a_change_cannot_remove_the_gate(self):
        repo = self.repo()
        base = self.commit(repo, {"check/check.py": "base\n"}, "main")
        self.commit(repo, {"check/check.py": None}, "remove the check")
        result, _ = self.gate("pull_request", base)
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn("removes check/check.py", result.stdout)

    def test_r9_an_unresolved_base_fails_and_the_first_push_is_explicit(self):
        repo = self.repo()
        head = self.commit(repo, {"check/check.py": "candidate\n"}, "main")
        for event, base in (("pull_request", "e" * 40), ("push", "e" * 40), ("pull_request", ""), ("push", ""),
                            ("pull_request", "0" * 40)):
            with self.subTest(event=event, base=base):
                result, values = self.gate(event, base)
                self.assertNotEqual(result.returncode, 0, result.stdout)
                self.assertNotIn("RECEIPT_BASE", values)
        result, values = self.gate("push", "0" * 40)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        empty = git(repo, "hash-object", "-t", "tree", "/dev/null")
        self.assertEqual(values, {"GATE": "bootstrap", "RECEIPT_BASE": empty})
        self.assertEqual(head, git(repo, "rev-parse", "HEAD"))

    def test_mk13_r1_the_gate_refuses_a_submodule_in_the_candidates_commit(self):
        step = [s["run"] for s in workflow_steps()["check"] if s["name"] == "Check the registry (base revision's check)"]
        self.assertEqual(len(step), 1)
        for folder in ("check", "schema"):
            shutil.copytree(ROOT / folder, self.tmp / "work/trusted" / folder)
        repo = self.repo()
        shutil.copytree(FIXTURES / "valid/verified-driver", repo, dirs_exist_ok=True)
        base = self.commit(repo, {}, "main")
        for path in ("listings/example-module", "receipts/example-driver/2026-11-02-aaaaaaaaaaaa.txt"):
            with self.subTest(path):
                git(repo, "update-index", "--add", "--cacheinfo", f"160000,{'e' * 40},{path}")
                git(repo, "commit", "-q", "-m", "a submodule")
                env = {"PATH": os.environ["PATH"], "HOME": str(self.tmp), "RECEIPT_BASE": base}
                result = subprocess.run(["bash", "--noprofile", "--norc", "-eo", "pipefail", "-c", step[0]], cwd=repo,
                                        env=env, capture_output=True, text=True, timeout=60)
                self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn(f"{path}: must be a regular file or folder, not a link or submodule", result.stdout)
                git(repo, "reset", "-q", "--hard", base)

    def test_mk13_r1_the_gate_refuses_a_file_where_listings_or_receipts_must_be_a_folder(self):
        step = [s["run"] for s in workflow_steps()["check"] if s["name"] == "Check the registry (base revision's check)"]
        self.assertEqual(len(step), 1)
        for folder in ("check", "schema"):
            shutil.copytree(ROOT / folder, self.tmp / "work/trusted" / folder)
        repo = self.repo()
        base = self.commit(repo, {"README.md": "registry\n"}, "main")
        env = {"PATH": os.environ["PATH"], "HOME": str(self.tmp), "RECEIPT_BASE": base}

        def gate():
            return subprocess.run(["bash", "--noprofile", "--norc", "-eo", "pipefail", "-c", step[0]], cwd=repo,
                                  env=env, capture_output=True, text=True, timeout=60)
        absent = gate()
        self.assertEqual(absent.returncode, 0, absent.stdout + absent.stderr)
        for path in ("listings", "receipts"):
            with self.subTest(path):
                self.commit(repo, {path: "{}\n"}, "a file in place of the folder")
                result = gate()
                self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn(f"{path}: must be a folder", result.stdout)
                git(repo, "reset", "-q", "--hard", base)

    def test_r1_r2_no_required_job_runs_the_candidates_code(self):
        steps = workflow_steps()
        for job in ("check", "skill"):
            runs = "".join(s["run"] for s in steps[job] if s["name"] != GATE_STEP)
            self.assertNotRegex(runs, r"(?<!trusted/)check/(check|test_check)\.py", job)
            self.assertIn("../trusted/check/check.py", runs, job)
        skill = "".join(s["run"] for s in steps["skill"])
        self.assertIn("--isolate", skill)
        self.assertIn("skill-check", steps)


class JevProofKind(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, str(ROOT / "check"))
        import check as check_mod
        import jev_bench
        import review
        import typesafe_client
        cls.check_mod = check_mod
        cls.bench = jev_bench
        cls.review = review
        cls.client_mod = typesafe_client

    def test_missing_or_bad_key_builds_no_client(self):
        cases = [None, "", "   ", "has space", "has\nline", "café-key", "bad\x7fkey"]
        for value in cases:
            with self.subTest(value=value):
                env = os.environ.copy()
                env.pop("TYPESAFE_API_KEY", None)
                if value is not None:
                    env["TYPESAFE_API_KEY"] = value
                with tempfile.TemporaryDirectory():
                    old = os.environ.get("TYPESAFE_API_KEY")
                    os.environ.pop("TYPESAFE_API_KEY", None)
                    if value is not None:
                        os.environ["TYPESAFE_API_KEY"] = value
                    try:
                        self.assertIsNone(self.client_mod.client_from_env(opener=lambda *a, **k: (_ for _ in ()).throw(
                            AssertionError("opener called"))))
                    finally:
                        if old is None:
                            os.environ.pop("TYPESAFE_API_KEY", None)
                        else:
                            os.environ["TYPESAFE_API_KEY"] = old

    def test_request_uses_the_documented_endpoint_and_hides_the_key(self):
        seen = {}

        def opener(request, timeout):
            seen["url"] = request.full_url
            seen["method"] = request.method
            seen["timeout"] = timeout
            seen["headers"] = {key.lower(): value for key, value in request.header_items()}
            seen["body"] = json.loads(request.data.decode())
            payload = json.dumps({"model": "jev-1.14.0", "answers": {"is_driver": {"type": "noul", "noul": 0.91}},
                                   "usage": {"input_tokens": 10, "output_tokens": 2}}).encode()
            return _Body(payload)

        key = "unit-test-key"
        client = self.client_mod.HttpSystemOneClient(key, opener=opener, sleep=lambda delay: None)
        question = self.review.KIND_QUESTIONS["is_driver"]
        answers = client.ask({"name": "Example"}, {"is_driver": question})
        self.assertEqual(seen["url"], "https://api.typesafe.ai/v1/systemone")
        self.assertEqual(seen["method"], "POST")
        self.assertEqual(seen["timeout"], 20)
        self.assertEqual(seen["headers"]["authorization"], "Bearer " + key)
        self.assertEqual(seen["headers"]["content-type"], "application/json")
        self.assertEqual(seen["body"]["model"], "jev-1.14.0")
        self.assertEqual(seen["body"]["state"], {"name": "Example"})
        self.assertEqual(seen["body"]["questions"]["is_driver"]["type"], "noul")
        self.assertEqual(answers["is_driver"]["noul"], 0.91)
        self.assertNotIn(key, repr(client))
        self.assertNotIn(key, json.dumps(answers))

    def test_http_failure_and_bad_body_return_none_without_the_key(self):
        key = "unit-test-key"

        def boom(request, timeout):
            raise urllib.error.HTTPError(request.full_url, 401, "Unauthorized", {}, io.BytesIO(b""))

        client = self.client_mod.HttpSystemOneClient(key, opener=boom, sleep=lambda delay: None)
        self.assertIsNone(client.ask({"name": "x"}, {"is_driver": {"type": "noul"}}))

        def garbage(request, timeout):
            return _Body(b"not-json")

        client = self.client_mod.HttpSystemOneClient(key, opener=garbage, sleep=lambda delay: None)
        self.assertIsNone(client.ask({}, {"q": {"type": "noul"}}))

    def test_retry_after_zero_then_success(self):
        calls = []

        def opener(request, timeout):
            calls.append(1)
            if len(calls) == 1:
                raise urllib.error.HTTPError(request.full_url, 429, "Too Many Requests",
                                              {"Retry-After": "0"}, io.BytesIO(b""))
            body = json.dumps({"answers": {"is_driver": {"type": "noul", "noul": 0.04}}}).encode()
            return _Body(body)

        slept = []
        client = self.client_mod.HttpSystemOneClient("unit-test-key", opener=opener, sleep=slept.append)
        answers = client.ask({"name": "x"}, {"is_driver": {"type": "noul", "instructions": "Is it a driver?"}})
        self.assertEqual(len(calls), 2)
        self.assertEqual(slept, [0.0])
        self.assertEqual(answers["is_driver"]["noul"], 0.04)

    def test_long_retry_after_falls_back(self):
        def opener(request, timeout):
            raise urllib.error.HTTPError(request.full_url, 529, "Overloaded",
                                          {"Retry-After": "30"}, io.BytesIO(b""))

        client = self.client_mod.HttpSystemOneClient("unit-test-key", opener=opener,
                                                      sleep=lambda delay: (_ for _ in ()).throw(AssertionError("slept")))
        self.assertIsNone(client.ask({}, {"q": {"type": "noul"}}))

    def test_fallback_keeps_the_tag_rule_and_a_confident_disagreement_is_a_finding(self):
        listing = {"id": "local-runner", "name": "Local runner",
                   "summary": "A driver that starts and stops OpenWiz agents on this machine.",
                   "plugs_into": "OpenWiz driver v1", "tags": ["mcp-server"]}
        fallback = self.review.proof_reading(listing, None)
        self.assertEqual((fallback["read"], fallback["source"], fallback["finding"]), ("none", "fallback", None))
        low = self._kind(0.91, 0.5, 0.05)
        unsure = self.review.proof_reading(listing, low)
        self.assertEqual((unsure["read"], unsure["source"], unsure["finding"]), ("none", "fallback", None))
        sure = self._kind(0.91, 0.05, 0.05)
        hit = self.review.proof_reading(listing, sure)
        self.assertEqual(hit["read"], "receipt")
        self.assertEqual(hit["source"], "jev")
        self.assertIn("prose reads as receipt, tags say none", hit["finding"])

    def _kind(self, driver, harness, skill):
        return {name: {"type": "noul", "noul": value}
                for name, value in (("is_driver", driver), ("is_harness", harness), ("is_skill", skill))}

    def test_kind_questions_share_one_request(self):
        seen = []

        class Fake:
            def ask(self, state, questions):
                seen.append(questions)
                return None

        listing = {"id": "example-driver", "name": "Example driver", "summary": "A driver.",
                   "plugs_into": "OpenWiz driver v1", "tags": ["driver"]}
        self.review.ask_listing(listing, Fake(), lambda text: False)
        self.assertEqual(len(seen), 1)
        self.assertEqual(set(seen[0]), {"is_driver", "is_harness", "is_skill"})

    def test_private_prose_is_not_sent(self):
        sent = []

        class Fake:
            def ask(self, state, questions):
                sent.append(state)
                return None

        listing = {"id": "leaky", "name": "Tool", "summary": "Uses a password: hunter2 now.",
                   "plugs_into": "The agent's MCP servers", "tags": ["mcp-server"]}
        self.review.ask_listing(listing, Fake(), self.review_private)
        self.assertEqual(sent, [])
        reading = self.review.proof_reading(listing, None)
        self.assertEqual(reading["source"], "fallback")
        self.assertNotIn("hunter2", json.dumps(reading))

    def review_private(self, text):
        return "password:" in text

    def test_client_exception_falls_back(self):
        class Fake:
            def ask(self, state, questions):
                raise RuntimeError("down")

        listing = {"id": "example-driver", "name": "Example driver", "summary": "A driver.",
                   "plugs_into": "OpenWiz driver v1", "tags": ["driver"]}
        self.assertIsNone(self.review.ask_listing(listing, Fake(), lambda text: False))
        lines, findings = self.review.review_lines([listing], Fake(), lambda text: False)
        self.assertEqual(findings, [])
        self.assertIn("(fallback)", lines[0])

    def test_review_command_on_a_valid_fixture_uses_the_tag_rule_offline(self):
        env = os.environ.copy()
        env.pop("TYPESAFE_API_KEY", None)
        result = run("review", cwd=FIXTURES / "valid" / "verified-driver", env=env)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(result.stdout, "example-driver: proof kind declared receipt, read receipt (fallback)\n"
                         "review: 1 listings, 0 findings\n")
        self.assertNotIn("TYPESAFE", result.stdout)

    def test_review_command_stops_on_a_contract_failure(self):
        env = os.environ.copy()
        env.pop("TYPESAFE_API_KEY", None)
        result = run("review", cwd=FIXTURES / "broken" / "unknown-field", env=env)
        self.assertEqual(result.returncode, 1)
        self.assertIn('unknown field "price"', result.stdout)
        self.assertNotIn("proof kind", result.stdout)

    def test_bench_reports_the_fixture_counts(self):
        text = self.bench.report(live=False)
        kind = self.bench.score_kind(self.bench.load()["kind"])
        work = self.bench.score_work_link(self.bench.load()["work_link"])
        self.assertEqual(text, f"kind tags: {kind['tags']}/{kind['n']}\n"
                         f"kind heuristic: {kind['heuristic']}/{kind['n']}\n"
                         f"work_link url-only: {work['url_only']}/{work['n']}\n"
                         f"work_link heuristic: {work['heuristic']}/{work['n']}\n"
                         "jev: not run; set TYPESAFE_API_KEY and run python3 -I check/jev_bench.py --live\n")
        self.assertEqual((kind["tags"], kind["heuristic"], kind["n"]), (9, 11, 12))

    def test_live_bench_without_a_key_skips_jev(self):
        old = os.environ.pop("TYPESAFE_API_KEY", None)
        try:
            text = self.bench.report(live=True, client=None)
        finally:
            if old is not None:
                os.environ["TYPESAFE_API_KEY"] = old
        self.assertIn("jev: skipped, TYPESAFE_API_KEY is not set", text)
        self.assertIn("kind tags: 9/12", text)
        self.assertIn("work_link url-only: 6/10", text)

    def _run_review_cli(self, cwd, argv, client):
        buf = io.StringIO()
        old_cwd = os.getcwd()
        try:
            os.chdir(cwd)
            with unittest.mock.patch.object(self.review, "client_from_env", return_value=client):
                with contextlib.redirect_stdout(buf):
                    code = self.check_mod.main(["review", *argv])
        finally:
            os.chdir(old_cwd)
        return code, buf.getvalue()

    def _synthetic_checkout(self, root):
        shutil.copytree(FIXTURES / "valid" / "verified-driver", root, dirs_exist_ok=True)
        git(root, "init", "-q", "-b", "main")
        git(root, "add", "-A")
        git(root, "commit", "-q", "-m", "published")
        git(root, "update-ref", "refs/remotes/origin/main", "HEAD")

        branch_listing = {
            "name": "Local branch runner",
            "summary": "A driver committed locally ahead of main.",
            "tags": ["mcp-server"],
            "url": "https://example.com/local-branch-runner",
            "plugs_into": "OpenWiz driver v1",
            "publisher": "example-publisher",
            "stage": "available",
            "status": "listed",
        }
        (root / "listings" / "local-branch-runner.json").write_text(json.dumps(branch_listing) + "\n")
        git(root, "add", "listings/local-branch-runner.json")
        git(root, "commit", "-q", "-m", "local branch commit")

        draft_listing = {
            "name": "Embargoed Draft Tool",
            "summary": "Unannounced partner integration under embargo.",
            "tags": ["mcp-server"],
            "url": "https://example.com/embargoed-draft",
            "plugs_into": "OpenWiz driver v1",
            "publisher": "example-publisher",
            "stage": "available",
            "status": "listed",
        }
        (root / "listings" / "embargoed-draft.json").write_text(json.dumps(draft_listing) + "\n")
        return root

    def test_noul_inclusive_0_3_and_0_7_boundaries(self):
        self.assertIs(self.review.factor_yes(0.7), True)
        self.assertIs(self.review.factor_yes(0.3), False)
        self.assertIs(self.review.factor_yes(1.0), True)
        self.assertIs(self.review.factor_yes(0.0), False)
        self.assertIsNone(self.review.factor_yes(0.6999999999999999))
        self.assertIsNone(self.review.factor_yes(0.30000000000000004))
        self.assertIsNone(self.review.factor_yes(0.5))

        driver_prose = {
            "id": "local-runner",
            "name": "Local runner",
            "summary": "A driver that starts and stops OpenWiz agents.",
            "plugs_into": "OpenWiz driver v1",
            "tags": ["mcp-server"],
        }
        at_yes = self.review.proof_reading(driver_prose, self._kind(0.7, 0.3, 0.3))
        self.assertEqual((at_yes["source"], at_yes["read"]), ("jev", "receipt"))
        self.assertIn("prose reads as receipt, tags say none", at_yes["finding"])

        below_yes = self.review.proof_reading(driver_prose, self._kind(0.6999999999999999, 0.3, 0.3))
        self.assertEqual((below_yes["source"], below_yes["read"], below_yes["finding"]), ("fallback", "none", None))

        non_driver_prose = {
            "id": "mcp-tagged-driver",
            "name": "Browser tools",
            "summary": "An MCP server exposing browser tools.",
            "plugs_into": "The agent's MCP servers",
            "tags": ["driver"],
        }
        at_no = self.review.proof_reading(non_driver_prose, self._kind(0.3, 0.3, 0.3))
        self.assertEqual((at_no["source"], at_no["read"]), ("jev", "none"))
        self.assertIn("prose reads as none, tags say receipt", at_no["finding"])

        above_no = self.review.proof_reading(non_driver_prose, self._kind(0.30000000000000004, 0.3, 0.3))
        self.assertEqual((above_no["source"], above_no["read"], above_no["finding"]), ("fallback", "receipt", None))

    def test_timeout_stops_calling_jev_and_falls_back_for_remaining_listings(self):
        calls = []

        def stalled(request, timeout):
            calls.append(timeout)
            raise TimeoutError("timed out")

        entries = [
            {"id": f"tool-{i:02d}", "name": f"Tool {i}", "summary": "A tool.",
             "plugs_into": "The agent's MCP servers", "tags": ["mcp-server"]}
            for i in range(12)
        ]
        client = self.client_mod.HttpSystemOneClient("unit-test-key", opener=stalled, sleep=lambda d: None)
        lines, findings = self.review.review_lines(entries, client, lambda text: False)
        self.assertEqual(len(calls), 1)
        self.assertTrue(client.unavailable)
        self.assertEqual(findings, [])
        self.assertEqual(sum("(fallback)" in line for line in lines), 12)
        self.assertTrue(any("stopped calling TypeSafe" in line for line in lines))
        self.assertEqual(lines[-1], "review: 12 listings, 0 findings")

    def test_service_wide_http_failures_stop_sweep_while_per_listing_400_continues(self):
        entries = [
            {"id": f"tool-{i:02d}", "name": f"Tool {i}", "summary": "A tool.",
             "plugs_into": "The agent's MCP servers", "tags": ["mcp-server"]}
            for i in range(5)
        ]
        cases = [
            ("urlerror", 1, lambda req, t: (_ for _ in ()).throw(urllib.error.URLError("dns down"))),
            ("401", 1, lambda req, t: (_ for _ in ()).throw(
                urllib.error.HTTPError(req.full_url, 401, "Unauthorized", {}, io.BytesIO(b"")))),
            ("503", 3, lambda req, t: (_ for _ in ()).throw(
                urllib.error.HTTPError(req.full_url, 503, "Unavailable", {}, io.BytesIO(b"")))),
            ("529-long-retry", 1, lambda req, t: (_ for _ in ()).throw(
                urllib.error.HTTPError(req.full_url, 529, "Overloaded", {"Retry-After": "30"}, io.BytesIO(b"")))),
        ]
        for label, expected_calls, opener in cases:
            with self.subTest(label):
                count = []

                def wrapped(req, timeout, fn=opener, counter=count):
                    counter.append(1)
                    return fn(req, timeout)

                client = self.client_mod.HttpSystemOneClient("unit-test-key", opener=wrapped, sleep=lambda d: None)
                lines, findings = self.review.review_lines(entries, client, lambda text: False)
                self.assertEqual(len(count), expected_calls)
                self.assertTrue(client.unavailable)
                self.assertEqual(findings, [])
                self.assertEqual(lines[-1], "review: 5 listings, 0 findings")

        fake_calls = []

        class FailingFake:
            def ask(self, state, questions):
                fake_calls.append(state)
                raise RuntimeError("down")

        lines, findings = self.review.review_lines(entries, FailingFake(), lambda text: False)
        self.assertEqual(len(fake_calls), 1)
        self.assertEqual(findings, [])

        mixed_calls = []

        def first_400_then_ok(req, timeout):
            mixed_calls.append(1)
            if len(mixed_calls) == 1:
                raise urllib.error.HTTPError(req.full_url, 400, "Bad Request", {}, io.BytesIO(b""))
            return _Body(json.dumps({"answers": self._kind(0.05, 0.05, 0.05)}).encode())

        client = self.client_mod.HttpSystemOneClient("unit-test-key", opener=first_400_then_ok, sleep=lambda d: None)
        lines, findings = self.review.review_lines(entries[:3], client, lambda text: False)
        self.assertEqual(len(mixed_calls), 3)
        self.assertFalse(client.unavailable)
        self.assertIn("(fallback)", lines[0])
        self.assertIn("(jev)", lines[1])
        self.assertIn("(jev)", lines[2])

    def test_overall_deadline_caps_request_timeouts_and_falls_back(self):
        now = [0.0]
        seen_timeouts = []

        def fake_clock():
            return now[0]

        def slow_opener(req, timeout):
            seen_timeouts.append(timeout)
            now[0] += 10.0
            return _Body(json.dumps({"answers": self._kind(0.05, 0.05, 0.05)}).encode())

        entries = [
            {"id": f"tool-{i:02d}", "name": f"Tool {i}", "summary": "A tool.",
             "plugs_into": "The agent's MCP servers", "tags": ["mcp-server"]}
            for i in range(6)
        ]
        client = self.client_mod.HttpSystemOneClient(
            "unit-test-key", opener=slow_opener, sleep=lambda d: None, clock=fake_clock)
        lines, findings = self.review.review_lines(
            entries, client, lambda text: False, deadline=25.0, clock=fake_clock)
        self.assertEqual(seen_timeouts, [20, 15.0, 5.0])
        self.assertEqual(findings, [])
        self.assertEqual(sum("(jev)" in line for line in lines), 3)
        self.assertEqual(sum("(fallback)" in line for line in lines), 3)
        self.assertTrue(any("deadline" in line for line in lines))

        bad_deadline = run("review", "--deadline", "0", cwd=FIXTURES / "valid" / "verified-driver")
        self.assertNotEqual(bad_deadline.returncode, 0)

    def test_review_skips_unpublished_drafts_edits_and_unmerged_commits_by_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            reg = self._synthetic_checkout(Path(tmp) / "repo")
            sent = []

            def opener(request, timeout):
                body = json.loads(request.data.decode())
                sent.append(body["state"])
                return _Body(json.dumps({"answers": self._kind(0.9, 0.05, 0.05)}).encode())

            client = self.client_mod.HttpSystemOneClient("unit-test-key", opener=opener, sleep=lambda d: None)
            code, out = self._run_review_cli(reg, [], client)
            self.assertEqual(code, 0, out)
            self.assertEqual([item["name"] for item in sent], ["Example driver"])
            self.assertNotIn("Embargoed", json.dumps(sent))
            self.assertNotIn("Local branch runner", json.dumps(sent))
            self.assertIn("embargoed-draft: proof kind declared none, read none (fallback, unpublished)", out)
            self.assertIn("local-branch-runner: proof kind declared none, read none (fallback, unpublished)", out)
            self.assertIn("example-driver: proof kind declared receipt, read receipt (jev)", out)
            self.assertIn("unpublished", out)

            # Locally modifying the published listing makes it unpublished until committed/merged.
            sent.clear()
            driver_path = reg / "listings" / "example-driver.json"
            data = json.loads(driver_path.read_text())
            data["summary"] = "Embargoed local edit to an existing published listing."
            driver_path.write_text(json.dumps(data) + "\n")
            client = self.client_mod.HttpSystemOneClient("unit-test-key", opener=opener, sleep=lambda d: None)
            code, out = self._run_review_cli(reg, [], client)
            self.assertEqual(code, 0, out)
            self.assertEqual(sent, [])
            self.assertIn("example-driver: proof kind declared receipt, read receipt (fallback, unpublished)", out)

            # Outside a git repo (or without origin/main), nothing is sent by default.
            nongit = Path(tmp) / "nongit"
            shutil.copytree(FIXTURES / "valid" / "listed-available", nongit)
            client = self.client_mod.HttpSystemOneClient("unit-test-key", opener=opener, sleep=lambda d: None)
            code, out = self._run_review_cli(nongit, [], client)
            self.assertEqual(code, 0, out)
            self.assertEqual(sent, [])
            self.assertIn("(fallback, unpublished)", out)

    def test_review_sends_selected_ids_rev_and_include_unpublished_on_opt_in(self):
        with tempfile.TemporaryDirectory() as tmp:
            reg = self._synthetic_checkout(Path(tmp) / "repo")
            sent = []

            def opener(request, timeout):
                body = json.loads(request.data.decode())
                sent.append(body["state"])
                return _Body(json.dumps({"answers": self._kind(0.7, 0.3, 0.3)}).encode())

            # Selecting a draft by id sends only that draft and reports its finding.
            client = self.client_mod.HttpSystemOneClient("unit-test-key", opener=opener, sleep=lambda d: None)
            code, out = self._run_review_cli(reg, ["embargoed-draft"], client)
            self.assertEqual(code, 1, out)
            self.assertEqual([item["name"] for item in sent], ["Embargoed Draft Tool"])
            self.assertIn("finding: embargoed-draft: prose reads as receipt, tags say none", out)
            self.assertIn("review: 1 listings, 1 findings", out)

            # --rev HEAD reads only committed listings from HEAD, never untracked drafts.
            sent.clear()
            client = self.client_mod.HttpSystemOneClient("unit-test-key", opener=opener, sleep=lambda d: None)
            code, out = self._run_review_cli(reg, ["--rev", "HEAD"], client)
            self.assertEqual(code, 1, out)
            self.assertEqual(sorted(item["name"] for item in sent), ["Example driver", "Local branch runner"])
            self.assertNotIn("Embargoed", json.dumps(sent))

            # --include-unpublished explicitly opts all working-tree listings in.
            sent.clear()
            client = self.client_mod.HttpSystemOneClient("unit-test-key", opener=opener, sleep=lambda d: None)
            code, out = self._run_review_cli(reg, ["--include-unpublished"], client)
            self.assertEqual(code, 1, out)
            self.assertEqual(
                sorted(item["name"] for item in sent),
                ["Embargoed Draft Tool", "Example driver", "Local branch runner"],
            )

            # Invalid and missing listing ids are refused without calling TypeSafe.
            sent.clear()
            client = self.client_mod.HttpSystemOneClient("unit-test-key", opener=opener, sleep=lambda d: None)
            code, out = self._run_review_cli(reg, ["Bad_Id"], client)
            self.assertEqual(code, 1)
            self.assertEqual(sent, [])
            self.assertIn("not a listing id", out)

            code, out = self._run_review_cli(reg, ["missing-tool"], client)
            self.assertEqual(code, 1)
            self.assertEqual(sent, [])
            self.assertIn("listings/missing-tool.json is not there", out)

            # Even with opt-in, private credential patterns stay blocked and never reach TypeSafe.
            leaky = reg / "listings" / "leaky-draft.json"
            leaky.write_text(json.dumps({
                "name": "Leaky",
                "summary": "Uses password: supersecretvalue here.",
                "tags": ["mcp-server"],
                "url": "https://example.com/leaky",
                "plugs_into": "The agent's MCP servers",
                "publisher": "example-publisher",
                "stage": "available",
                "status": "listed",
            }) + "\n")
            client = self.client_mod.HttpSystemOneClient("unit-test-key", opener=opener, sleep=lambda d: None)
            code, out = self._run_review_cli(reg, ["--include-unpublished"], client)
            self.assertEqual(code, 1)
            self.assertEqual(sent, [])
            self.assertIn("a token", out)


class JevWorkLink(Temp):
    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, str(ROOT / "check"))
        import jev_bench
        import review
        cls.bench = jev_bench
        cls.review = review

    def _listing(self, item=None, about=None):
        listing = {"id": "example-harness", "name": "Example harness", "summary": "A synthetic harness still being built.",
                   "plugs_into": "The local driver", "tags": ["harness"], "stage": "being-built",
                   "links": [{"label": "Docs", "url": "https://example.com/docs"}]}
        if item is None:
            return listing, None
        answers = {"is_work_item": {"type": "noul", "noul": item},
                   "is_about_this_work": {"type": "noul", "noul": item if about is None else about}}
        return listing, answers

    def test_no_answer_leaves_the_link_unjudged(self):
        listing, answers = self._listing()
        reading = self.review.work_link_reading(listing, answers)
        self.assertEqual(reading["source"], "fallback")
        self.assertIsNone(reading["finding"])
        self.assertIsNone(self.review.work_link_reading({"id": "x", "stage": "available"}, answers))

    def test_confident_no_is_a_finding_and_a_yes_or_a_middle_value_is_not(self):
        listing, no = self._listing(0.12, 0.08)
        reading = self.review.work_link_reading(listing, no)
        self.assertEqual(reading["yes"], False)
        self.assertIn("does not read as the work's pull request or ticket", reading["finding"])
        listing, yes = self._listing(0.91, 0.88)
        self.assertIsNone(self.review.work_link_reading(listing, yes)["finding"])
        self.assertEqual(self.review.work_link_reading(listing, yes)["yes"], True)
        listing, middle = self._listing(0.5, 0.91)
        middle_reading = self.review.work_link_reading(listing, middle)
        self.assertEqual(middle_reading["source"], "fallback")
        self.assertIsNone(middle_reading["finding"])
        mixed = self.review.work_link_reading(listing, self._listing(0.91, 0.12)[1])
        self.assertEqual(mixed["source"], "fallback")
        self.assertIsNone(mixed["finding"])

    def test_a_private_link_is_not_sent(self):
        sent = []

        class Fake:
            def ask(self, state, questions):
                sent.append(questions)
                return None

        listing, _ = self._listing()
        listing["links"] = [{"label": "Ticket", "url": "https://example.com/password: hunter2"}]
        self.review.ask_listing(listing, Fake(), lambda text: "password:" in text)
        self.assertEqual(len(sent), 1)
        self.assertNotIn("is_work_item", sent[0])
        self.assertNotIn("is_about_this_work", sent[0])
        self.assertNotIn("hunter2", json.dumps(sent[0]))

    def test_work_link_questions_share_the_listing_request_and_state(self):
        seen = []

        class Fake:
            def ask(self, state, questions):
                seen.append((state, questions))
                return None

        listing, _ = self._listing()
        self.review.ask_listing(listing, Fake(), lambda text: False)
        self.assertEqual(len(seen), 1)
        state, questions = seen[0]
        self.assertEqual(state["first_link"]["url"], "https://example.com/docs")
        self.assertTrue({"is_driver", "is_harness", "is_skill", "is_work_item", "is_about_this_work"} <= set(questions))

    def test_review_of_a_being_built_fixture_does_not_judge_the_link_offline(self):
        env = os.environ.copy()
        env.pop("TYPESAFE_API_KEY", None)
        result = run("review", cwd=FIXTURES / "valid" / "listed-being-built", env=env)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("example-harness: work link not judged\n", result.stdout)
        self.assertIn("review: 1 listings, 0 findings\n", result.stdout)

    def test_bench_counts(self):
        work = self.bench.score_work_link(self.bench.load()["work_link"])
        self.assertEqual((work["url_only"], work["heuristic"], work["n"]), (6, 9, 10))

    def test_review_does_not_send_work_link_without_public_confirmation(self):
        seen = []
        work_link = "https://github.com/example-owner/example-harness/pull/1"

        class Fake:
            def ask(self, state, questions):
                seen.append((state, questions))
                return {"is_driver": {"type": "noul", "noul": 0.05},
                        "is_harness": {"type": "noul", "noul": 0.91},
                        "is_skill": {"type": "noul", "noul": 0.05},
                        "is_work_item": {"type": "noul", "noul": 0.91},
                        "is_about_this_work": {"type": "noul", "noul": 0.91}}

        import check as check_mod
        reg = self.registry("valid/listed-being-built")
        code, text = self.review.run(reg, Fake(),
                                     check_mod.check_tree, check_mod.worktree_files, check_mod.private)
        self.assertEqual(code, 0, text)
        self.assertEqual(len(seen), 1)
        state, questions = seen[0]
        self.assertNotIn("first_link", state)
        self.assertNotIn(work_link, json.dumps((state, questions)))
        self.assertNotIn("is_work_item", questions)
        self.assertNotIn("is_about_this_work", questions)
        self.assertIn("example-harness: work link not judged\n", text)

        seen.clear()
        code, text = self.review.run(reg, Fake(),
                                     check_mod.check_tree, check_mod.worktree_files, check_mod.private,
                                     include_work_links=True)
        self.assertEqual(code, 0, text)
        self.assertEqual(len(seen), 1)
        state, questions = seen[0]
        self.assertEqual(state["first_link"]["url"], work_link)
        self.assertIn("is_work_item", questions)
        self.assertIn("is_about_this_work", questions)
        self.assertIn("example-harness: work link yes (jev 1.00)\n", text)

    def test_credential_bearing_and_private_work_links_are_never_sent(self):
        import check as check_mod
        urls = [
            ("https://tracker.example.com/org/repo/-/issues/1?token=secret123", "secret123"),
            ("https://tracker.example.com/org/repo/-/issues/1?api_key=abc123", "abc123"),
            ("https://tracker.example.com/org/repo/-/issues/1#token=fragsecret", "fragsecret"),
            ("https://tracker.example.com/org/repo/-/issues/1?sig=deadbeef", "deadbeef"),
            ("https://user:pass@tracker.example.com/org/repo/-/issues/1", "user:pass"),
            ("https://user@tracker.example.com/org/repo/-/issues/1", "user@"),
            ("https://localhost/org/repo/issues/1", "localhost"),
            ("https://tracker.internal/org/repo/issues/1", "tracker.internal"),
            ("https://tracker.local/org/repo/issues/1", "tracker.local"),
            ("https://10.0.0.1/org/repo/issues/1", "10.0.0.1"),
            ("https://127.0.0.1/org/repo/issues/1", "127.0.0.1"),
            ("https://tracker.example.com/org/password%3A%20hunter2", "hunter2"),
        ]
        for url, secret in urls:
            with self.subTest(url=url):
                seen = []

                class Fake:
                    def ask(self, state, questions):
                        seen.append((state, questions))
                        return None

                listing, _ = self._listing()
                listing["links"] = [{"label": "Ticket", "url": url}]
                self.review.ask_listing(listing, Fake(), check_mod.private)
                self.assertEqual(len(seen), 1)
                state, questions = seen[0]
                self.assertNotIn("first_link", state)
                self.assertNotIn("is_work_item", questions)
                self.assertNotIn("is_about_this_work", questions)
                self.assertNotIn(secret, json.dumps(state))

    def test_query_and_fragment_are_stripped_from_sent_work_link(self):
        seen = []

        class Fake:
            def ask(self, state, questions):
                seen.append(state)
                return None

        listing, _ = self._listing()
        listing["links"] = [{"label": "Ticket",
                             "url": "https://tracker.example.com/example-owner/example-harness/-/issues/1?view=full#note-2"}]
        self.review.ask_listing(listing, Fake(), lambda text: False)
        self.assertEqual(len(seen), 1)
        self.assertEqual(seen[0]["first_link"]["url"],
                         "https://tracker.example.com/example-owner/example-harness/-/issues/1")
        self.assertNotIn("view=full", json.dumps(seen[0]))
        self.assertNotIn("note-2", json.dumps(seen[0]))

    def test_live_bench_uses_listing_prose_and_scores_item_and_about_separately(self):
        work_states = []

        class Fake:
            def ask(self, state, questions):
                if "is_work_item" in questions:
                    work_states.append(state)
                    item = 0.91 if "pull" in state["first_link"]["url"] or "issues" in state["first_link"]["url"] else 0.09
                    return {"is_work_item": {"type": "noul", "noul": item},
                            "is_about_this_work": {"type": "noul", "noul": 0.91}}
                return {"is_driver": {"type": "noul", "noul": 0.91},
                        "is_harness": {"type": "noul", "noul": 0.05},
                        "is_skill": {"type": "noul", "noul": 0.05}}

        data = self.bench.load()["work_link"]
        for case in data:
            self.assertIn("name", case)
            self.assertIn("summary", case)
            self.assertIn("plugs_into", case)
            self.assertIn("is_work_item", case)
            self.assertIn("is_about_this_work", case)
            self.assertNotEqual(case["name"], case["id"])
            self.assertNotEqual(case["summary"], "Being built.")

        text = self.bench.report(live=True, client=Fake())
        self.assertEqual(len(work_states), len(data))
        self.assertEqual(work_states[0]["name"], data[0]["name"])
        self.assertEqual(work_states[0]["summary"], data[0]["summary"])
        self.assertNotIn("view=full", json.dumps(work_states))
        self.assertIn("work_link jev (", text)
        self.assertIn("work_link item jev (", text)
        self.assertIn("work_link about jev (", text)


class _Body:
    def __init__(self, payload, status=200):
        self._payload = payload
        self.status = status

    def read(self, limit=-1):
        return self._payload if limit < 0 else self._payload[:limit]

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


if __name__ == "__main__":
    unittest.main()
