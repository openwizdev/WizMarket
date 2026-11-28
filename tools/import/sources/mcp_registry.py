"""Official MCP Registry source plug-in for WizMarket's importer.

Fetches active latest servers from https://registry.modelcontextprotocol.io/v0/servers,
enriches GitHub repositories via public GitHub GraphQL metadata, applies the honesty
filter, and returns entry dicts conforming to WizMarket's source plug-in interface.

Standard library only.
"""
import hashlib
import json
import re
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

NAME = "Official MCP Registry"
API_BASE = "https://registry.modelcontextprotocol.io/v0/servers"
OFFICIAL_META_KEY = "io.modelcontextprotocol.registry/official"
PLUGS_INTO = "The MCP servers your agents load"
USER_AGENT = "WizMarket-import/1 (+https://github.com/openwizdev/WizMarket)"

GITHUB_RESERVED_OWNERS = frozenset({
    "about", "collections", "contact", "enterprise", "events", "explore",
    "features", "join", "login", "marketplace", "orgs", "pricing", "resources",
    "search", "security", "settings", "site", "solutions", "sponsors",
    "topics", "trending", "users",
})

GENERIC_SLUGS = frozenset({
    "mcp", "server", "mcp-server", "api", "app", "site", "web", "docs",
    "docs-mcp", "registry", "service", "client", "tool", "tools", "plugin",
    "agent", "ai", "main", "default", "index", "core", "v1", "v2",
})

PLACEHOLDER_NAME_RE = re.compile(
    r"(?:^|[\s/_.-])(?:"
    r"hello[-_ ]?world|placeholder|lorem[-_ ]?ipsum|asdf+|foobar|foo[-_ ]?bar|"
    r"my[-_ ]?(?:first|new|test|sample|demo|awesome)[-_ ]?mcp|"
    r"(?:test|sample|demo|example|dummy|fake)[-_ ]?(?:mcp|server|mcp[-_ ]?server)|"
    r"(?:mcp|server)[-_ ]?(?:test|sample|demo|example|template|starter|boilerplate|dummy|fake)|"
    r"test[-_ ]?only|do[-_ ]?not[-_ ]?use|wip[-_ ]?test|smoke[-_ ]?test"
    r")(?:$|[\s/_.-])",
    re.IGNORECASE,
)

PLACEHOLDER_DESC_RE = re.compile(
    r"(?:"
    r"^\s*(?:test|testing|hello\s*world|placeholder|todo|tbd|wip|asdf+|foo\s*bar|none|n/a|desc|description|my\s+mcp\s+server)\s*\.?\s*$|"
    r"\b(?:lorem\s+ipsum|this\s+is\s+a\s+(?:test|sample|demo|example|dummy)\s+(?:mcp\s+)?server|"
    r"just\s+a\s+test|for\s+testing\s+only|do\s+not\s+use\s+in\s+production|smoke\s+test\s+server|"
    r"starter\s+template\s+for\s+building\s+mcp)\b"
    r")",
    re.IGNORECASE,
)

# Topical tag keywords (max 2 added besides mcp-server; never driver or harness)
TOPIC_RULES = [
    ("database", re.compile(r"\b(?:postgres|postgresql|mysql|sqlite|mongodb|redis|supabase|snowflake|bigquery|clickhouse|duckdb|sql|database|dynamodb|firestore|neon|prisma)\b", re.I)),
    ("cloud", re.compile(r"\b(?:aws|azure|gcp|google\s+cloud|cloudflare|kubernetes|k8s|docker|terraform|vercel|netlify|heroku|fly\.io|digitalocean)\b", re.I)),
    ("search", re.compile(r"\b(?:search|crawler|crawl|scrape|scraping|browser|playwright|puppeteer|web\s+fetch|firecrawl|tavily|brave\s+search|exa|serp)\b", re.I)),
    ("git", re.compile(r"\b(?:github|gitlab|bitbucket|git\s+repo|pull\s+request|commit|issue\s+tracker)\b", re.I)),
    ("docs", re.compile(r"\b(?:documentation|docs|knowledge\s+base|wiki|notion|confluence|obsidian|rag|markdown)\b", re.I)),
    ("finance", re.compile(r"\b(?:finance|financial|stock|crypto|bitcoin|ethereum|solana|defi|trading|payment|stripe|invoice|accounting|tax|banking|market\s+data)\b", re.I)),
    ("communication", re.compile(r"\b(?:slack|discord|telegram|whatsapp|email|gmail|outlook|sms|twilio|calendar|teams|messaging)\b", re.I)),
    ("observability", re.compile(r"\b(?:monitoring|observability|logging|logs|metrics|tracing|sentry|datadog|grafana|prometheus|opentelemetry|incident)\b", re.I)),
    ("security", re.compile(r"\b(?:security|vulnerability|cve|pentest|audit|auth|oauth|vault|secrets|compliance|firewall|malware)\b", re.I)),
    ("design", re.compile(r"\b(?:figma|design|image|video|audio|svg|3d|blender|canvas|diagram|chart|pdf)\b", re.I)),
    ("productivity", re.compile(r"\b(?:jira|linear|asana|trello|todoist|clickup|monday\.com|airtable|hubspot|salesforce|crm|project\s+management|task\s+management)\b", re.I)),
    ("analytics", re.compile(r"\b(?:analytics|bi|dashboard|metrics|mixpanel|amplitude|posthog|ga4|google\s+analytics|seo)\b", re.I)),
    ("developer-tools", re.compile(r"\b(?:debugger|linter|compiler|ide|code\s+review|ast|lsp|refactor|ci/cd|package\s+manager|npm|pypi)\b", re.I)),
    ("memory", re.compile(r"\b(?:memory|vector\s+store|embeddings|graph\s+memory|knowledge\s+graph|context\s+store)\b", re.I)),
    ("data", re.compile(r"\b(?:dataset|csv|excel|spreadsheet|weather|maps|geocoding|gis|open\s+data|statistics)\b", re.I)),
]


def normalise_shard_url(url: str) -> str:
    """Exact shard and dedupe URL normaliser.

    'https://' + host.lower().removeprefix('www.') + path
    where path is kept as written (case unchanged), then a trailing '/' and then
    a trailing '.git' are removed; query and fragment dropped; scheme always 'https://'.
    """
    parsed = urllib.parse.urlsplit((url or "").strip())
    host = (parsed.hostname or "").lower().removeprefix("www.")
    if not host:
        return ""
    path = parsed.path or ""
    if path.endswith("/"):
        path = path[:-1]
    if path.endswith(".git"):
        path = path[:-4]
    return f"https://{host}{path}"


def shard_of(url: str, total_shards: int = 16) -> int:
    """Deterministic shard number in [0, total_shards) from the normalised URL."""
    norm = normalise_shard_url(url)
    return int(hashlib.sha1(norm.encode("utf-8")).hexdigest(), 16) % total_shards


def parse_github_repo(url: str) -> tuple[str, str] | None:
    """Extract (owner, repo) from a public GitHub repository URL, or None."""
    if not url or not isinstance(url, str):
        return None
    parsed = urllib.parse.urlsplit(url.strip())
    if parsed.scheme.lower() not in ("http", "https"):
        return None
    host = (parsed.hostname or "").lower().removeprefix("www.")
    if host != "github.com":
        return None
    parts = [p for p in parsed.path.split("/") if p]
    if len(parts) < 2:
        return None
    owner, repo = parts[0], parts[1]
    if owner.lower() in GITHUB_RESERVED_OWNERS:
        return None
    if repo.endswith(".git"):
        repo = repo[:-4]
    if not owner or not repo:
        return None
    if not re.fullmatch(r"[A-Za-z0-9._-]+", owner) or not re.fullmatch(r"[A-Za-z0-9._-]+", repo):
        return None
    return owner, repo


def shard_key_url(server: dict) -> str:
    """Return the exact normalised shard key: repository.url if present, else websiteUrl."""
    raw = ((server.get("repository") or {}).get("url") or "").strip()
    if not raw:
        raw = (server.get("websiteUrl") or "").strip()
    return normalise_shard_url(raw) if raw else ""


def canonical_url_for_server(server: dict) -> tuple[str, tuple[str, str] | None]:
    """Return (primary_url, github_owner_repo_or_None) for a registry server dict."""
    repo_url = ((server.get("repository") or {}).get("url") or "").strip()
    gh = parse_github_repo(repo_url)
    if gh:
        return f"https://github.com/{gh[0]}/{gh[1]}", gh
    web_url = (server.get("websiteUrl") or "").strip()
    if web_url.startswith("http://"):
        web_url = "https://" + web_url[len("http://"):]
    if web_url.startswith("https://"):
        gh_web = parse_github_repo(web_url)
        if gh_web:
            return f"https://github.com/{gh_web[0]}/{gh_web[1]}", gh_web
        return web_url, None
    return "", None


def clean_line(text: str) -> str:
    """Collapse whitespace and control characters into a single clean line."""
    if not isinstance(text, str):
        return ""
    return re.sub(r"[\x00-\x1f\x7f-\x9f\u2028\u2029\s]+", " ", text).strip()


def is_placeholder(name: str, title: str, description: str) -> bool:
    """True when an entry is empty, placeholder, or clearly a test/example/template."""
    desc = clean_line(description)
    if len(desc) < 10:
        return True
    if PLACEHOLDER_DESC_RE.search(desc):
        return True
    for candidate in (name or "", title or ""):
        if candidate and PLACEHOLDER_NAME_RE.search(candidate):
            return True
    return False


def slugify(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")
    return re.sub(r"-{2,}", "-", s)


def make_id(server: dict) -> str:
    """Generate a valid listing id `mcp-<slug>` of 2..40 chars."""
    raw_name = (server.get("name") or "").strip()
    title = clean_line(server.get("title") or "")
    if "/" in raw_name:
        ns, tail = raw_name.split("/", 1)
    else:
        ns, tail = "", raw_name

    slug = slugify(tail)
    # Strip redundant leading/trailing mcp
    if slug.startswith("mcp-") and len(slug) > 4:
        slug = slug[4:]
    elif slug.endswith("-mcp") and len(slug) > 4:
        slug = slug[:-4]

    if not slug or slug in GENERIC_SLUGS or len(slug) < 2:
        ns_parts = [p for p in re.split(r"[./_-]+", ns.lower()) if p and p not in ("io", "github", "com", "org", "net", "dev", "ai", "app", "www")]
        prefix = slugify(ns_parts[-1]) if ns_parts else slugify(title)
        if prefix and slug and prefix != slug:
            slug = f"{prefix}-{slug}"
        elif prefix:
            slug = prefix
        else:
            slug = slugify(title) or "server"

    slug = re.sub(r"-{2,}", "-", slug).strip("-")
    if not slug:
        slug = "server"
    full = f"mcp-{slug}"
    if len(full) > 40:
        full = full[:40].rstrip("-")
    return full


def make_name(server: dict) -> str:
    """Return the server's title or the readable last part of its registry name."""
    title = clean_line(server.get("title") or "")
    if title:
        return title
    raw_name = clean_line(server.get("name") or "")
    if "/" in raw_name:
        tail = raw_name.rsplit("/", 1)[1].strip()
        if tail:
            return tail
    return raw_name or "MCP Server"


def make_source_url(server_name: str) -> str:
    return f"{API_BASE}?search={urllib.parse.quote(server_name, safe='')}"


def infer_tags(server: dict, repo_info: dict | None = None) -> list[str]:
    """Return ['mcp-server'] plus at most 2 topical tags (never driver or harness)."""
    raw_name = (server.get("name") or "").strip()
    slug = raw_name.split("/", 1)[1] if "/" in raw_name else raw_name
    text = " ".join(filter(None, [
        slug,
        server.get("title") or "",
        server.get("description") or "",
        (repo_info or {}).get("description") or "",
    ]))
    tags = ["mcp-server"]
    for tag, pattern in TOPIC_RULES:
        if pattern.search(text):
            tags.append(tag)
            if len(tags) >= 3:
                break
    return tags


def licence_from_repo(repo_info: dict | None, fallback_url: str) -> tuple[str, str]:
    """Return (licence_label, licence_url) from GitHub GraphQL repo metadata."""
    if not repo_info:
        return "not stated", fallback_url
    repo_url = repo_info.get("url") or fallback_url
    spdx = repo_info.get("spdx_id") or ""
    lic_file_url = repo_info.get("licence_file_url") or ""
    if not spdx:
        if lic_file_url:
            return "other", lic_file_url
        return "not stated", repo_url
    if spdx == "NOASSERTION":
        return "other", lic_file_url or repo_url
    return spdx, lic_file_url or repo_url


def build_entry(server: dict, repo_info: dict | None, url: str) -> dict:
    """Build a WizMarket importer entry dict for one kept MCP server."""
    server_name = clean_line(server.get("name") or "")
    reg_desc = clean_line(server.get("description") or "")
    repo_desc = clean_line((repo_info or {}).get("description") or "")
    if reg_desc and repo_desc and repo_desc.lower() != reg_desc.lower():
        source_desc = f"{reg_desc} | {repo_desc}"
    else:
        source_desc = reg_desc or repo_desc
    licence, licence_url = licence_from_repo(repo_info, url)
    return {
        "id": make_id(server),
        "name": make_name(server),
        "source_description": source_desc,
        "url": url,
        "licence": licence,
        "licence_url": licence_url,
        "source_url": make_source_url(server_name),
        "tags": infer_tags(server, repo_info),
        "plugs_into": PLUGS_INTO,
    }


def is_active_latest(item: dict) -> bool:
    meta = (item.get("_meta") or {}).get(OFFICIAL_META_KEY) or {}
    return bool(meta.get("isLatest")) and meta.get("status") == "active"


def _dedupe_key(url: str) -> str:
    gh = parse_github_repo(url)
    if gh:
        return f"https://github.com/{gh[0].lower()}/{gh[1].lower()}"
    return normalise_shard_url(url)


def filter_servers(
    raw_items: list[dict],
    gh_repos: dict[str, dict | None],
    url_resolves=None,
    shard: int | None = None,
    total_shards: int = 16,
) -> tuple[list[tuple[int, dict]], dict[str, int]]:
    """Apply the honesty filter and optional shard filter.

    Returns (list of (stars, entry_dict) sorted by stars desc, drop_counts).
    """
    drops = {
        "inactive_or_not_latest": 0,
        "no_url": 0,
        "other_shard": 0,
        "duplicate_url": 0,
        "repo_missing_or_private": 0,
        "repo_archived": 0,
        "fork_no_description": 0,
        "website_unresolved": 0,
        "placeholder_or_empty": 0,
    }
    seen_urls: set[str] = set()
    kept: list[tuple[int, dict]] = []

    for item in raw_items:
        if not is_active_latest(item):
            drops["inactive_or_not_latest"] += 1
            continue
        server = item.get("server") or {}
        key_url = shard_key_url(server)
        if not key_url:
            drops["no_url"] += 1
            continue
        if shard is not None and shard_of(key_url, total_shards) != shard:
            drops["other_shard"] += 1
            continue
        url, gh = canonical_url_for_server(server)
        if not url:
            drops["no_url"] += 1
            continue
        pre_key = _dedupe_key(url)
        if not pre_key:
            drops["no_url"] += 1
            continue
        if pre_key in seen_urls:
            drops["duplicate_url"] += 1
            continue

        repo_info = None
        stars = 0
        if gh:
            key = f"{gh[0].lower()}/{gh[1].lower()}"
            repo_info = gh_repos.get(key)
            if not repo_info or repo_info.get("isPrivate"):
                drops["repo_missing_or_private"] += 1
                continue
            if repo_info.get("isArchived"):
                drops["repo_archived"] += 1
                continue
            if repo_info.get("isFork") and not clean_line(repo_info.get("description") or ""):
                drops["fork_no_description"] += 1
                continue
            url = repo_info.get("url") or url
            stars = int(repo_info.get("stargazerCount") or 0)
        else:
            if url_resolves is not None and not url_resolves(url):
                drops["website_unresolved"] += 1
                continue

        post_key = _dedupe_key(url)
        if post_key in seen_urls:
            drops["duplicate_url"] += 1
            continue

        reg_desc = clean_line(server.get("description") or "")
        repo_desc = clean_line((repo_info or {}).get("description") or "")
        if is_placeholder(server.get("name") or "", server.get("title") or "", reg_desc or repo_desc):
            drops["placeholder_or_empty"] += 1
            continue

        seen_urls.add(pre_key)
        seen_urls.add(post_key)
        entry = build_entry(server, repo_info, url)
        kept.append((stars, entry))

    kept.sort(key=lambda pair: (-pair[0], pair[1]["id"]))
    return kept, drops


def fetch_registry_pages(cache_dir: Path | None = None) -> list[dict]:
    """Fetch all latest pages from the Official MCP Registry, optionally caching on disk."""
    items: list[dict] = []
    if cache_dir and cache_dir.exists():
        pages = sorted(cache_dir.glob("page_*.json"))
        if pages:
            for p in pages:
                data = json.loads(p.read_text())
                items.extend(data.get("servers") or [])
            return items

    cursor = None
    page_num = 0
    while True:
        params = {"limit": "100", "version": "latest"}
        if cursor:
            params["cursor"] = cursor
        req_url = f"{API_BASE}?{urllib.parse.urlencode(params)}"
        req = urllib.request.Request(req_url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        if cache_dir:
            cache_dir.mkdir(parents=True, exist_ok=True)
            (cache_dir / f"page_{page_num:05d}.json").write_text(json.dumps(data, ensure_ascii=False))
        servers = data.get("servers") or []
        items.extend(servers)
        cursor = (data.get("metadata") or {}).get("nextCursor")
        page_num += 1
        if not cursor or not servers:
            break
    return items


def query_github_repos_graphql(repos: list[tuple[str, str]], batch_size: int = 40) -> dict[str, dict | None]:
    """Batch-query public GitHub repository metadata via `gh api graphql`."""
    results: dict[str, dict | None] = {}
    unique = list(dict.fromkeys((o, r) for o, r in repos))
    for i in range(0, len(unique), batch_size):
        chunk = unique[i:i + batch_size]
        lines = ["query {"]
        for idx, (owner, repo) in enumerate(chunk):
            o_esc = owner.replace("\\", "\\\\").replace('"', '\\"')
            r_esc = repo.replace("\\", "\\\\").replace('"', '\\"')
            lines.append(
                f'  r{idx}: repository(owner: "{o_esc}", name: "{r_esc}") {{ '
                f'url isPrivate isArchived isFork stargazerCount description '
                f'defaultBranchRef {{ name }} '
                f'licenseInfo {{ spdxId }} '
                f'lic1: object(expression: "HEAD:LICENSE") {{ oid }} '
                f'lic2: object(expression: "HEAD:LICENSE.md") {{ oid }} '
                f'}}'
            )
        lines.append("}")
        query = "\n".join(lines)
        data = {}
        for attempt in range(3):
            proc = subprocess.run(
                ["gh", "api", "graphql", "-f", f"query={query}"],
                capture_output=True,
                text=True,
            )
            if proc.stdout:
                try:
                    parsed = json.loads(proc.stdout)
                except json.JSONDecodeError:
                    parsed = None
                if isinstance(parsed, dict) and isinstance(parsed.get("data"), dict) and parsed["data"]:
                    data = parsed["data"]
                    break
            if attempt < 2:
                time.sleep(2 * (attempt + 1))
        for idx, (owner, repo) in enumerate(chunk):
            key = f"{owner.lower()}/{repo.lower()}"
            node = data.get(f"r{idx}")
            if not node:
                results[key] = None
                continue
            branch = (node.get("defaultBranchRef") or {}).get("name") or "main"
            repo_url = node.get("url") or f"https://github.com/{owner}/{repo}"
            lic_file_url = ""
            for field, fname in (("lic1", "LICENSE"), ("lic2", "LICENSE.md")):
                if node.get(field):
                    lic_file_url = f"{repo_url}/blob/{branch}/{fname}"
                    break
            results[key] = {
                "url": repo_url,
                "isPrivate": bool(node.get("isPrivate")),
                "isArchived": bool(node.get("isArchived")),
                "isFork": bool(node.get("isFork")),
                "stargazerCount": int(node.get("stargazerCount") or 0),
                "description": (node.get("description") or "").strip(),
                "spdx_id": (node.get("licenseInfo") or {}).get("spdxId") or "",
                "licence_file_url": lic_file_url,
            }
        time.sleep(0.1)
    return results


def fetch(cache_dir: str | Path | None = None, shard: int | None = None, total_shards: int = 16) -> list[dict]:
    """Fetch, filter, and rank Official MCP Registry entries for run.py."""
    raw_items = fetch_registry_pages(Path(cache_dir) if cache_dir else None)
    gh_pairs: list[tuple[str, str]] = []
    for item in raw_items:
        if not is_active_latest(item):
            continue
        server = item.get("server") or {}
        key_url = shard_key_url(server)
        if not key_url:
            continue
        if shard is not None and shard_of(key_url, total_shards) != shard:
            continue
        _, gh = canonical_url_for_server(server)
        if gh:
            gh_pairs.append(gh)
    gh_repos = query_github_repos_graphql(gh_pairs) if gh_pairs else {}
    kept, _ = filter_servers(raw_items, gh_repos, shard=shard, total_shards=total_shards)
    return [entry for _, entry in kept]
