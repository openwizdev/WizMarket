"""Public GitHub repositories and official sites for agent CI tools (plus Limitr usage limits/billing)."""
import fetching

NAME = "GitHub public repositories"

# (id, display name, GitHub owner/repo, tags, plugs_into)
REPOS = [
    ("dagger", "Dagger", "dagger/dagger", ["ci", "containers"], "Your repository's CI"),
    ("claude-code-action", "Claude Code Action", "anthropics/claude-code-action", ["ci", "github-actions"], "Your repository's CI"),
    ("codex-action", "Codex Action", "openai/codex-action", ["ci", "github-actions"], "Your repository's CI"),
    ("run-gemini-cli", "Run Gemini CLI Action", "google-github-actions/run-gemini-cli", ["ci", "github-actions"], "Your repository's CI"),
    ("pr-agent", "PR-Agent", "The-PR-Agent/pr-agent", ["ci", "code-review"], "Your repository's CI"),
    ("runs-on", "RunsOn", "runs-on/runs-on", ["ci", "github-actions"], "Your repository's CI"),
    ("semgrep", "Semgrep", "semgrep/semgrep", ["ci", "security"], "Your repository's CI"),
    ("qodo-cover", "Qodo Cover", "qodo-ai/qodo-cover", ["ci", "testing"], "Your repository's CI"),
    ("codecov-action", "Codecov Action", "codecov/codecov-action", ["ci", "testing"], "Your repository's CI"),
    ("act", "act", "nektos/act", ["ci", "github-actions"], "Your repository's CI"),
    ("github-actions-runner", "GitHub Actions Runner", "actions/runner", ["ci", "github-actions"], "Your repository's CI"),
    ("actions-runner-controller", "Actions Runner Controller", "actions/actions-runner-controller", ["ci", "kubernetes"], "Your repository's CI"),
    ("reviewdog", "reviewdog", "reviewdog/reviewdog", ["ci", "code-review"], "Your repository's CI"),
    ("pre-commit", "pre-commit", "pre-commit/pre-commit", ["ci", "linting"], "Your repository's CI"),
    ("earthly", "Earthly", "earthly/earthly", ["ci", "containers"], "Your repository's CI"),
    ("buildkite-agent", "Buildkite Agent", "buildkite/agent", ["ci", "runners"], "Your repository's CI"),
    ("limitr", "Limitr", "dev-formata-io/limitr", ["billing", "usage-limits"], "Usage caps and billing around your agents"),
]

# Official sites without a public repository
# (id, display name, url, catalog name, tags, plugs_into)
SITES = [
    ("jog", "Jog", "https://usejog.com", "Jog official site", ["ci", "github-actions"], "Your repository's CI"),
]


def fetch():
    facts = fetching.repos([repo for _, _, repo, _, _ in REPOS])
    entries = []
    for listing_id, name, full_name, tags, plugs_into in REPOS:
        info = facts.get(full_name)
        if not info:
            continue
        entries.append({
            "id": listing_id,
            "name": name,
            "source_description": info["description"],
            "url": info["url"],
            "licence": info["licence"],
            "licence_url": info["licence_url"],
            "source_url": info["url"],
            "tags": list(tags),
            "plugs_into": plugs_into,
        })
    for listing_id, name, url, catalog, tags, plugs_into in SITES:
        entries.append({
            "id": listing_id,
            "name": name,
            "catalog": catalog,
            "source_description": fetching.site_description(url),
            "url": url,
            "licence": "not stated",
            "licence_url": url,
            "source_url": url,
            "tags": list(tags),
            "plugs_into": plugs_into,
        })
    return entries
