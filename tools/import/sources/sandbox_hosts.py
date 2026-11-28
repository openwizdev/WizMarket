"""Public GitHub repositories and official sites for agent sandbox and compute hosts."""
import fetching

NAME = "GitHub public repositories"
PLUGS_INTO = "A machine your agents run on"

# (id, display name, GitHub owner/repo, extra topical tags)
REPOS = [
    ("e2b", "E2B", "e2b-dev/E2B", ["microvm"]),
    ("e2b-code-interpreter", "E2B Code Interpreter", "e2b-dev/code-interpreter", ["sdk"]),
    ("e2b-runtime", "E2B Runtime", "e2b-dev/runtime", ["microvm"]),
    ("modal", "Modal", "modal-labs/modal-client", ["cloud", "sdk"]),
    ("morph-cloud", "Morph", "morph-labs/morph-python-sdk", ["cloud", "sdk"]),
    ("runloop", "Runloop", "runloopai/api-client-python", ["cloud", "sdk"]),
    ("cloudflare-sandbox", "Cloudflare Sandbox SDK", "cloudflare/sandbox-sdk", ["edge", "sdk"]),
    ("coder", "Coder", "coder/coder", ["workspaces"]),
    ("microsandbox", "Microsandbox", "superradcompany/microsandbox", ["microvm", "local"]),
    ("arrakis", "Arrakis", "abshkbh/arrakis", ["microvm", "self-hosted"]),
    ("k8s-agent-sandbox", "Kubernetes Agent Sandbox", "kubernetes-sigs/agent-sandbox", ["kubernetes"]),
    ("cua", "Cua", "trycua/cua", ["computer-use"]),
    ("steel-browser", "Steel Browser", "steel-dev/steel-browser", ["browser"]),
    ("container-use", "Container Use", "dagger/container-use", ["containers"]),
    ("vercel-sandbox", "Vercel Sandbox", "vercel/sandbox", ["cloud", "sdk"]),
    ("codesandbox-sdk", "CodeSandbox SDK", "codesandbox/codesandbox-sdk", ["cloud", "sdk"]),
    ("blaxel", "Blaxel", "blaxel-ai/sdk-typescript", ["cloud", "sdk"]),
    ("ubicloud", "Ubicloud", "ubicloud/ubicloud", ["cloud", "self-hosted"]),
    ("anthropic-sandbox-runtime", "Anthropic Sandbox Runtime", "anthropics/sandbox-runtime", ["local"]),
    ("vibekit", "VibeKit", "superagent-ai/vibekit", ["containers"]),
    ("gitpod", "Gitpod", "gitpod-io/gitpod", ["workspaces"]),
    ("openvscode-server", "OpenVSCode Server", "gitpod-io/openvscode-server", ["workspaces"]),
    ("devcontainers-cli", "Dev Containers CLI", "devcontainers/cli", ["containers"]),
    ("codex-universal", "Codex Universal", "openai/codex-universal", ["containers"]),
    ("flyctl", "Fly.io CLI (flyctl)", "superfly/flyctl", ["cloud", "cli"]),
]

# Official vendor sites when no active public repo represents the host
# (id, display name, url, catalog name, extra topical tags)
SITES = [
    ("daytona", "Daytona", "https://www.daytona.io", "Daytona official site", ["cloud"]),
    ("fly-machines", "Fly Machines", "https://docs.fly.io/machines", "Fly.io documentation", ["microvm", "cloud"]),
]


def fetch():
    facts = fetching.repos([repo for _, _, repo, _ in REPOS])
    entries = []
    for listing_id, name, full_name, extra_tags in REPOS:
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
            "tags": ["sandbox-host", *extra_tags],
            "plugs_into": PLUGS_INTO,
        })
    for listing_id, name, url, catalog, extra_tags in SITES:
        entries.append({
            "id": listing_id,
            "name": name,
            "catalog": catalog,
            "source_description": fetching.site_description(url),
            "url": url,
            "licence": "not stated",
            "licence_url": url,
            "source_url": url,
            "tags": ["sandbox-host", *extra_tags],
            "plugs_into": PLUGS_INTO,
        })
    return entries
