"""Offline unit tests for the Official MCP Registry source plug-in."""
import hashlib
import json
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent / "sources"))
import mcp_registry as mr


def _item(name, desc="Provides SQL queries for Postgres databases.", title=None, repo=None, web=None,
          status="active", is_latest=True):
    server = {"name": name, "description": desc, "version": "1.0.0"}
    if title is not None:
        server["title"] = title
    if repo is not None:
        server["repository"] = {"url": repo, "source": "github"}
    if web is not None:
        server["websiteUrl"] = web
    return {
        "server": server,
        "_meta": {
            mr.OFFICIAL_META_KEY: {
                "status": status,
                "isLatest": is_latest,
            }
        },
    }


class TestMcpRegistry(unittest.TestCase):
    def test_normalise_shard_url(self):
        self.assertEqual(
            mr.normalise_shard_url("http://WWW.GitHub.com/Org/Repo.git/?foo=1#bar"),
            "https://github.com/Org/Repo",
        )
        self.assertEqual(
            mr.normalise_shard_url("https://github.com/Org/Repo/"),
            "https://github.com/Org/Repo",
        )
        self.assertEqual(
            mr.normalise_shard_url("https://www.Example.COM/"),
            "https://example.com",
        )
        self.assertEqual(
            mr.normalise_shard_url("https://github.com/Org/Repo.git"),
            "https://github.com/Org/Repo",
        )

    def test_shard_of_matches_sha1_spec(self):
        url = "https://www.github.com/ModelContextProtocol/servers.git/"
        norm = "https://github.com/ModelContextProtocol/servers"
        expected = int(hashlib.sha1(norm.encode("utf-8")).hexdigest(), 16) % 16
        self.assertEqual(mr.shard_of(url, 16), expected)

    def test_parse_github_repo(self):
        self.assertEqual(mr.parse_github_repo("https://github.com/acme/mcp-db.git"), ("acme", "mcp-db"))
        self.assertEqual(mr.parse_github_repo("https://www.github.com/acme/mcp-db/"), ("acme", "mcp-db"))
        self.assertIsNone(mr.parse_github_repo("https://github.com/topics/mcp"))
        self.assertIsNone(mr.parse_github_repo("https://github.com/acme"))
        self.assertIsNone(mr.parse_github_repo("https://gitlab.com/acme/mcp-db"))

    def test_is_placeholder(self):
        self.assertTrue(mr.is_placeholder("io.github.foo/hello-world", "", "A server"))
        self.assertTrue(mr.is_placeholder("io.github.foo/test-mcp", "", "Just a test server for testing."))
        self.assertTrue(mr.is_placeholder("io.github.foo/demo", "", "short"))
        self.assertFalse(mr.is_placeholder("io.github.acme/playwright-mcp", "Playwright",
                                           "Automates browser testing and screenshots via Playwright."))

    def test_make_id_and_name(self):
        s = {"name": "io.github.acme/mcp-postgres", "title": "Postgres MCP"}
        self.assertEqual(mr.make_id(s), "mcp-postgres")
        self.assertEqual(mr.make_name(s), "Postgres MCP")

        generic = {"name": "com.example/mcp", "title": ""}
        self.assertEqual(mr.make_id(generic), "mcp-example-mcp")
        self.assertEqual(mr.make_name(generic), "mcp")

        long_s = {"name": "io.github.acme/" + "a" * 60}
        self.assertLessEqual(len(mr.make_id(long_s)), 40)

    def test_clean_line_strips_controls(self):
        self.assertEqual(mr.clean_line("Hello\n\tWorld\u0085\u2028Test"), "Hello World Test")

    def test_shard_key_url_prefers_repo_over_website(self):
        s = {
            "repository": {"url": "https://www.GitHub.com/Acme/Tool.git/"},
            "websiteUrl": "https://tool.example.com/",
        }
        self.assertEqual(mr.shard_key_url(s), "https://github.com/Acme/Tool")
        s_web = {"websiteUrl": "http://www.Example.com/Docs/?a=1#b"}
        self.assertEqual(mr.shard_key_url(s_web), "https://example.com/Docs")

    def test_licence_mapping(self):
        repo = {"url": "https://github.com/acme/tool", "spdx_id": "MIT",
                "licence_file_url": "https://github.com/acme/tool/blob/main/LICENSE"}
        self.assertEqual(mr.licence_from_repo(repo, repo["url"]),
                         ("MIT", "https://github.com/acme/tool/blob/main/LICENSE"))

        noassertion = {"url": "https://github.com/acme/tool", "spdx_id": "NOASSERTION",
                       "licence_file_url": "https://github.com/acme/tool/blob/main/LICENSE"}
        self.assertEqual(mr.licence_from_repo(noassertion, noassertion["url"]),
                         ("other", "https://github.com/acme/tool/blob/main/LICENSE"))

        none_lic = {"url": "https://github.com/acme/tool", "spdx_id": "", "licence_file_url": ""}
        self.assertEqual(mr.licence_from_repo(none_lic, none_lic["url"]),
                         ("not stated", "https://github.com/acme/tool"))

    def test_filter_servers_honesty_and_ranking(self):
        items = [
            _item("io.github.acme/good-high", "Queries Postgres tables and schemas.", title="Good High",
                  repo="https://github.com/acme/good-high"),
            _item("io.github.acme/good-low", "Searches Slack messages and threads.", title="Good Low",
                  repo="https://github.com/acme/good-low"),
            _item("io.github.acme/dup-high", "Duplicate repo entry for Good High.",
                  repo="https://github.com/acme/good-high.git"),
            _item("io.github.acme/archived", "Archived server for old API.",
                  repo="https://github.com/acme/archived"),
            _item("io.github.acme/fork-empty", "Fork with empty repo description.",
                  repo="https://github.com/acme/fork-empty"),
            _item("io.github.acme/missing", "Missing repo on GitHub.",
                  repo="https://github.com/acme/missing"),
            _item("io.github.acme/inactive", "Inactive server.", status="deleted",
                  repo="https://github.com/acme/good-low"),
            _item("io.github.acme/no-url", "No repo or website."),
            _item("io.github.acme/hello-world", "Hello world MCP server",
                  repo="https://github.com/acme/hello-world"),
            _item("com.acme/web-ok", "Hosted weather forecast lookup server.", title="Weather Web",
                  web="https://weather.example.com"),
            _item("com.acme/web-dead", "Dead website server.", web="https://dead.example.com"),
        ]
        gh_repos = {
            "acme/good-high": {
                "url": "https://github.com/acme/good-high", "isPrivate": False, "isArchived": False,
                "isFork": False, "stargazerCount": 500, "description": "Postgres MCP",
                "spdx_id": "MIT", "licence_file_url": "https://github.com/acme/good-high/blob/main/LICENSE",
            },
            "acme/good-low": {
                "url": "https://github.com/acme/good-low", "isPrivate": False, "isArchived": False,
                "isFork": False, "stargazerCount": 12, "description": "Slack MCP",
                "spdx_id": "Apache-2.0", "licence_file_url": "https://github.com/acme/good-low/blob/main/LICENSE",
            },
            "acme/archived": {
                "url": "https://github.com/acme/archived", "isPrivate": False, "isArchived": True,
                "isFork": False, "stargazerCount": 900, "description": "Archived",
                "spdx_id": "MIT", "licence_file_url": "",
            },
            "acme/fork-empty": {
                "url": "https://github.com/acme/fork-empty", "isPrivate": False, "isArchived": False,
                "isFork": True, "stargazerCount": 3, "description": "",
                "spdx_id": "MIT", "licence_file_url": "",
            },
            "acme/hello-world": {
                "url": "https://github.com/acme/hello-world", "isPrivate": False, "isArchived": False,
                "isFork": False, "stargazerCount": 1, "description": "Hello world",
                "spdx_id": "MIT", "licence_file_url": "",
            },
            "acme/missing": None,
        }
        kept, drops = mr.filter_servers(
            items, gh_repos, url_resolves=lambda u: u == "https://weather.example.com"
        )
        self.assertEqual([e["id"] for _, e in kept], ["mcp-good-high", "mcp-good-low", "mcp-web-ok"])
        self.assertEqual([s for s, _ in kept], [500, 12, 0])
        self.assertEqual(drops["inactive_or_not_latest"], 1)
        self.assertEqual(drops["no_url"], 1)
        self.assertEqual(drops["duplicate_url"], 1)
        self.assertEqual(drops["repo_archived"], 1)
        self.assertEqual(drops["fork_no_description"], 1)
        self.assertEqual(drops["repo_missing_or_private"], 1)
        self.assertEqual(drops["placeholder_or_empty"], 1)
        self.assertEqual(drops["website_unresolved"], 1)
        # Never driver or harness tags
        by_id = {entry["id"]: entry for _, entry in kept}
        self.assertEqual(by_id["mcp-good-high"]["tags"], ["mcp-server", "database"])
        self.assertEqual(by_id["mcp-good-low"]["tags"], ["mcp-server", "communication"])
        for _, entry in kept:
            self.assertIn("mcp-server", entry["tags"])
            self.assertNotIn("driver", entry["tags"])
            self.assertNotIn("harness", entry["tags"])
            self.assertEqual(entry["plugs_into"], mr.PLUGS_INTO)

    def test_infer_tags_ignores_reverse_dns_namespace(self):
        self.assertEqual(
            mr.infer_tags({
                "name": "io.github.neiltron/apple-health-mcp",
                "title": "Apple Health",
                "description": "Local-first Apple Health MCP server for sleep and workouts.",
            }),
            ["mcp-server"],
        )
        self.assertEqual(
            mr.infer_tags({
                "name": "io.github.vercel/next-devtools-mcp",
                "title": "next-devtools-mcp",
                "description": "Next.js development tools MCP server with stdio transport.",
            }),
            ["mcp-server"],
        )
        self.assertEqual(
            mr.infer_tags({
                "name": "io.github.acme/agentshield",
                "title": "AgentShield",
                "description": "Secret defense and audit logging for autonomous agents.",
            }),
            ["mcp-server", "observability", "security"],
        )
        self.assertEqual(
            mr.infer_tags({
                "name": "io.github.acme/github-issues",
                "title": "GitHub Issues",
                "description": "Read and triage repository issues.",
            }),
            ["mcp-server", "git"],
        )

    def test_query_github_repos_graphql_retries_missing_data(self):
        good_payload = json.dumps({
            "data": {
                "r0": {
                    "url": "https://github.com/acme/tool",
                    "isPrivate": False,
                    "isArchived": False,
                    "isFork": False,
                    "stargazerCount": 7,
                    "description": "Tool",
                    "defaultBranchRef": {"name": "main"},
                    "licenseInfo": {"spdxId": "MIT"},
                    "lic1": {"oid": "abc"},
                    "lic2": None,
                }
            }
        })
        replies = [
            mock.Mock(stdout='{"message": "API rate limit exceeded"}'),
            mock.Mock(stdout='{"errors": [{"message": "502"}], "data": null}'),
            mock.Mock(stdout=good_payload),
        ]
        with mock.patch.object(mr.subprocess, "run", side_effect=replies) as run_mock, \
             mock.patch.object(mr.time, "sleep"):
            got = mr.query_github_repos_graphql([("acme", "tool")])
        self.assertEqual(run_mock.call_count, 3)
        self.assertEqual(got["acme/tool"]["url"], "https://github.com/acme/tool")

        not_found = [mock.Mock(stdout='{"data": {"r0": null}, "errors": [{"type": "NOT_FOUND"}]}')]
        with mock.patch.object(mr.subprocess, "run", side_effect=not_found) as run_mock, \
             mock.patch.object(mr.time, "sleep"):
            got_missing = mr.query_github_repos_graphql([("acme", "missing")])
        self.assertEqual(run_mock.call_count, 1)
        self.assertIsNone(got_missing["acme/missing"])

    def test_filter_servers_dedupes_github_case_and_canonical_url(self):
        items = [
            _item("io.github.acme/tool-upper", "Queries SQL tables for analytics.", title="Tool Upper",
                  repo="https://github.com/Acme/Tool"),
            _item("io.github.acme/tool-lower", "Same repo with lowercase URL.", title="Tool Lower",
                  repo="https://github.com/acme/tool"),
            _item("io.github.old/tool-renamed", "Renamed repo resolving to Acme/Tool.", title="Tool Renamed",
                  repo="https://github.com/old-org/tool"),
        ]
        repo_meta = {
            "url": "https://github.com/Acme/Tool", "isPrivate": False, "isArchived": False,
            "isFork": False, "stargazerCount": 20, "description": "SQL tool",
            "spdx_id": "MIT", "licence_file_url": "https://github.com/Acme/Tool/blob/main/LICENSE",
        }
        gh_repos = {"acme/tool": repo_meta, "old-org/tool": repo_meta}
        kept, drops = mr.filter_servers(items, gh_repos)
        self.assertEqual([e["id"] for _, e in kept], ["mcp-tool-upper"])
        self.assertEqual(drops["duplicate_url"], 2)

    def test_build_entry_includes_both_registry_and_repo_descriptions(self):
        server = {"name": "io.github.acme/tool", "title": "Tool", "description": "Registry description here."}
        repo = {"url": "https://github.com/acme/tool", "description": "Repository description here.",
                "spdx_id": "MIT", "licence_file_url": "https://github.com/acme/tool/blob/main/LICENSE"}
        entry = mr.build_entry(server, repo, repo["url"])
        self.assertEqual(entry["source_description"], "Registry description here. | Repository description here.")

        same_repo = {**repo, "description": "registry description here."}
        self.assertEqual(mr.build_entry(server, same_repo, repo["url"])["source_description"], "Registry description here.")

        empty_repo = {**repo, "description": ""}
        self.assertEqual(mr.build_entry(server, empty_repo, repo["url"])["source_description"], "Registry description here.")


if __name__ == "__main__":
    unittest.main()
