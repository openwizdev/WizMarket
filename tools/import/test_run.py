"""Offline unit tests for tools/import/run.py (no network)."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / "check"))

import check as wizcheck
import run


def sample_entry(**overrides):
    entry = {
        "id": "acme-agent",
        "name": "Acme Agent",
        "source_description": "Acme Agent runs terminal coding tasks across multiple repositories with local tools.",
        "url": "https://github.com/acme/agent",
        "licence": "MIT",
        "licence_url": "https://github.com/acme/agent/blob/main/LICENSE",
        "source_url": "https://github.com/acme/agent",
        "tags": ["coding-agent-cli"],
        "plugs_into": "An agent CLI you run yourself",
    }
    entry.update(overrides)
    return entry


class TestHelpers(unittest.TestCase):
    def test_norm_url(self):
        self.assertEqual(run.norm_url("https://www.GitHub.com/Acme/Agent.git/"), "github.com/Acme/Agent")
        self.assertEqual(run.norm_url("https://github.com/Acme/Agent/"), "github.com/Acme/Agent")
        self.assertEqual(run.norm_url("HTTPS://Example.COM/foo/"), "example.com/foo")

    def test_summary_problem(self):
        src = "Open source AI coding agent designed for large projects and real world tasks."
        self.assertIsNone(run.summary_problem("Terminal coding tool built to handle multi-file edits.", src))
        # 4 consecutive words in common is allowed
        self.assertIsNone(run.summary_problem("An open source AI coding tool for your shell.", src))
        # 5 consecutive words (ignoring case and punctuation) is refused
        self.assertIn("shares the run", run.summary_problem("An open-source AI coding agent designed to help.", src))
        # Exact equality is refused
        self.assertEqual(run.summary_problem(src, src), "equals the source description")
        # Marketing words refused
        self.assertIn("marketing words", run.summary_problem("A powerful terminal tool for edits.", src))
        # Too long or multiline refused
        self.assertIn("140", run.summary_problem("x" * 141, src))
        self.assertIn("one line", run.summary_problem("line one\nline two", src))

    def test_entry_problem(self):
        self.assertIsNone(run.entry_problem(sample_entry()))
        self.assertIsNone(run.entry_problem(sample_entry(tags=["billing", "usage-limits"])))
        self.assertIsNotNone(run.entry_problem(sample_entry(id="a")))
        self.assertIsNotNone(run.entry_problem(sample_entry(id="a" * 41)))
        self.assertIsNotNone(run.entry_problem(sample_entry(tags=["driver", "coding-agent-cli"])))
        self.assertIsNotNone(run.entry_problem(sample_entry(tags=["harness", "coding-agent-cli"])))
        self.assertIsNotNone(run.entry_problem(sample_entry(tags=["misc"])))
        self.assertIsNotNone(run.entry_problem(sample_entry(tags=["coding-agent-cli"] + [f"t{i}" for i in range(7)])))
        self.assertIsNotNone(run.entry_problem(sample_entry(licence="NOASSERTION")))
        self.assertIsNotNone(run.entry_problem(sample_entry(url="http://example.com")))


class TestRunSource(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.out = self.root / "listings"
        self.base = self.root / "import"
        self.out.mkdir()
        self.base.mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def test_pending_then_write_and_refresh_keeps_summary(self):
        entry = sample_entry()
        logs = []
        counts = run.run_source("demo", "GitHub public repositories", [entry], self.out,
                                base=self.base, today="2026-11-25", resolves=lambda u: True, log=logs.append)
        self.assertEqual(counts["pending"], 1)
        self.assertEqual(counts["written"], 0)
        self.assertFalse((self.out / "acme-agent.json").exists())

        pending_path = self.base / "pending" / "demo.json"
        pending = json.loads(pending_path.read_text())
        pending["acme-agent"]["summary"] = "Terminal coding tool that edits code in a local repository."
        pending_path.write_text(json.dumps(pending))

        counts = run.run_source("demo", "GitHub public repositories", [entry], self.out,
                                base=self.base, today="2026-11-25", resolves=lambda u: True, log=logs.append)
        self.assertEqual(counts["written"], 1)
        self.assertFalse(pending_path.exists())
        listing_path = self.out / "acme-agent.json"
        data = json.loads(listing_path.read_text())
        self.assertEqual(data["publisher"], "openwizdev")
        self.assertEqual(data["status"], "listed")
        self.assertEqual(data["stage"], "available")
        self.assertEqual(data["tags"], ["public-source", "coding-agent-cli"])
        self.assertEqual(data["links"][0]["label"], "Listed from public source, unverified: GitHub public repositories")
        self.assertEqual(data["links"][1]["label"], "Licence: MIT")
        self.assertNotIn("proof", data)
        self.assertNotIn("login", data)

        # Passes WizMarket's own contract check
        failures, _ = wizcheck.check_tree({"listings/acme-agent.json": listing_path.read_bytes()})
        self.assertEqual(failures, [])

        # Re-running refreshes metadata without overwriting the written summary
        updated = sample_entry(name="Acme Agent v2", licence="Apache-2.0")
        counts = run.run_source("demo", "GitHub public repositories", [updated], self.out,
                                base=self.base, today="2026-11-26", resolves=lambda u: True, log=logs.append)
        self.assertEqual(counts["refreshed"], 1)
        refreshed = json.loads(listing_path.read_text())
        self.assertEqual(refreshed["name"], "Acme Agent v2")
        self.assertEqual(refreshed["summary"], "Terminal coding tool that edits code in a local repository.")
        self.assertEqual(refreshed["links"][1]["label"], "Licence: Apache-2.0")

    def test_dedupe_and_id_clash(self):
        # Pre-existing hand-written listing
        (self.out / "acme-agent.json").write_text(json.dumps({
            "name": "Existing Acme",
            "summary": "Hand-written listing.",
            "tags": ["harness"],
            "url": "https://example.com/existing",
            "plugs_into": "Harnesses",
            "publisher": "openwizdev",
            "stage": "available",
            "status": "listed",
        }))
        # Same normalised URL -> skipped as duplicate
        dup = sample_entry(id="other-id", url="https://www.example.com/existing/")
        # Different URL, same id -> renamed with -<owner>
        clash = sample_entry(id="acme-agent", url="https://github.com/otherorg/agent")
        counts = run.run_source("demo", "GitHub", [dup, clash], self.out,
                                base=self.base, today="2026-11-25", resolves=lambda u: True, log=lambda _: None)
        self.assertEqual(counts["duplicate"], 1)
        self.assertEqual(counts["pending"], 1)
        pending = json.loads((self.base / "pending" / "demo.json").read_text())
        self.assertIn("acme-agent-otherorg", pending)

    def test_refused_summary_and_unresolved_url(self):
        entry = sample_entry()
        run.run_source("demo", "GitHub", [entry], self.out,
                       base=self.base, today="2026-11-25", resolves=lambda u: True, log=lambda _: None)
        pending_path = self.base / "pending" / "demo.json"
        pending = json.loads(pending_path.read_text())
        # Marketing word -> stays pending
        pending["acme-agent"]["summary"] = "The best terminal coding tool for engineers."
        pending_path.write_text(json.dumps(pending))
        counts = run.run_source("demo", "GitHub", [entry], self.out,
                                base=self.base, today="2026-11-25", resolves=lambda u: True, log=lambda _: None)
        self.assertEqual(counts["refused_summary"], 1)
        self.assertFalse((self.out / "acme-agent.json").exists())

        # Valid summary but URL does not resolve -> dropped
        pending["acme-agent"]["summary"] = "Terminal coding tool that edits code in a local repository."
        pending_path.write_text(json.dumps(pending))
        counts = run.run_source("demo", "GitHub", [entry], self.out,
                                base=self.base, today="2026-11-25", resolves=lambda u: False, log=lambda _: None)
        self.assertEqual(counts["unresolved"], 1)
        self.assertFalse((self.out / "acme-agent.json").exists())

    def test_check_summaries_and_count(self):
        entry = sample_entry(catalog="Custom Catalog")
        run.run_source("demo", "GitHub", [entry], self.out,
                       base=self.base, today="2026-11-25", resolves=lambda u: True, log=lambda _: None)
        pending_path = self.base / "pending" / "demo.json"
        pending = json.loads(pending_path.read_text())
        pending["acme-agent"]["summary"] = "Terminal coding tool that edits code in a local repository."
        pending_path.write_text(json.dumps(pending))
        run.run_source("demo", "GitHub", [entry], self.out,
                       base=self.base, today="2026-11-25", resolves=lambda u: True, log=lambda _: None)

        data = json.loads((self.out / "acme-agent.json").read_text())
        self.assertEqual(data["links"][0]["label"], "Listed from public source, unverified: Custom Catalog")

        logs = []
        self.assertEqual(run.check_summaries(self.out, base=self.base, log=logs.append), 0)
        self.assertIn("check-summaries: ok, 1 summaries checked, 0 refused", logs[-1])

        # Corrupt summary to copy source description -> check_summaries fails
        data["summary"] = entry["source_description"]
        (self.out / "acme-agent.json").write_text(json.dumps(data))
        logs = []
        self.assertEqual(run.check_summaries(self.out, base=self.base, log=logs.append), 1)
        self.assertIn("refused", logs[-1])

        count_logs = []
        self.assertEqual(run.count(self.out, base=self.base, log=count_logs.append), 0)
        text = "\n".join(count_logs)
        self.assertIn("listings: 1", text)
        self.assertIn("coding-agent-cli: 1", text)
        self.assertIn("demo: 1", text)


if __name__ == "__main__":
    unittest.main()
