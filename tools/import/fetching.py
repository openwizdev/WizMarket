"""Network helpers for source plug-ins: public GitHub API reads and plain HTTPS GETs. Never used by the tests."""
import html.parser
import json
import os
import urllib.error
import urllib.request

AGENT = "WizMarket-import/1 (+https://github.com/openwizdev/WizMarket)"
TIMEOUT = 30


def get(url, headers=None):
    request = urllib.request.Request(url, headers={"User-Agent": AGENT, **(headers or {})})
    with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
        return response.status, response.geturl(), response.read()


def github(path):
    """GET https://api.github.com/<path> as JSON, or None on 404. Uses GITHUB_TOKEN or GH_TOKEN when set (rate limit)."""
    headers = {"Accept": "application/vnd.github+json"}
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        return json.loads(get(f"https://api.github.com/{path}", headers)[2])
    except urllib.error.HTTPError as error:
        if error.code == 404:
            return None
        raise


def repo(full_name):
    """A public repository's facts, read from GitHub's API, or None when it is missing, private or archived.

    The licence follows the convention: the SPDX id, "other" when GitHub finds a licence file it can't match to an
    SPDX id (NOASSERTION), or "not stated" when there is no licence file; licence_url is the file, else the repository.
    """
    data = github(f"repos/{full_name}")
    if not data or data.get("private") or data.get("archived") or data.get("disabled"):
        return None
    home = data["html_url"]
    licence, licence_url = "not stated", home
    info = github(f"repos/{data['full_name']}/license")
    if info and info.get("html_url"):
        spdx = (info.get("license") or {}).get("spdx_id") or "NOASSERTION"
        licence, licence_url = ("other" if spdx == "NOASSERTION" else spdx), info["html_url"]
    return {"full_name": data["full_name"], "url": home, "description": (data.get("description") or "").strip(),
            "licence": licence, "licence_url": licence_url, "fork": data.get("fork", False),
            "pushed_at": data.get("pushed_at", ""), "stars": data.get("stargazers_count", 0)}


class _Meta(html.parser.HTMLParser):
    def __init__(self):
        super().__init__()
        self.found = {}

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        key = (attrs.get("name") or attrs.get("property") or "").lower()
        if tag == "meta" and key in ("description", "og:description") and attrs.get("content"):
            self.found.setdefault(key, attrs["content"].strip())


def site_description(url):
    """A public page's own meta description (or og:description), or "" when it has none."""
    parser = _Meta()
    parser.feed(get(url)[2].decode("utf-8", "replace"))
    return parser.found.get("description") or parser.found.get("og:description") or ""


def resolves(url):
    """True when a plain GET of url ends in HTTP 2xx (after redirects), the 'resolves at write time' rule."""
    try:
        return 200 <= get(url)[0] < 400
    except (urllib.error.URLError, OSError, ValueError):
        return False
