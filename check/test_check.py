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
        candidate = [s["run"] for s in workflow_steps()["candidate-check"]]
        self.assertIn('check.py check --base "$base" --rev HEAD', "".join(candidate))

    def test_r1_r2_no_required_job_runs_the_candidates_code(self):
        steps = workflow_steps()
        for job in ("check", "skill"):
            runs = "".join(s["run"] for s in steps[job] if s["name"] != GATE_STEP)
            self.assertNotRegex(runs, r"(?<!trusted/)check/(check|test_check)\.py", job)
            self.assertIn("../trusted/check/check.py", runs, job)
        skill = "".join(s["run"] for s in steps["skill"])
        self.assertIn("--isolate", skill)
        self.assertIn("skill-check", steps)


if __name__ == "__main__":
    unittest.main()
