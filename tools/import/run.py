"""WizMarket's importer: listings from public catalogs, each labelled as listed from a public source and unverified.

    python3 -I tools/import/run.py <source> --out listings/   fetch one source, write new listings and its manifest
    python3 -I tools/import/run.py <source> --offline          the same, from tools/import/pending/<source>.json only
    python3 -I tools/import/run.py --check-summaries           the copy check over every public-source listing
    python3 -I tools/import/run.py count                       totals by status, kind tag and source

See tools/import/README.md for the conventions. Standard library only.
"""
import argparse
import datetime
import importlib.util
import json
import re
import string
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(HERE))  # -I leaves the script's folder off sys.path; the plug-ins import fetching from here

PUBLISHER = "openwizdev"
PUBLIC = "public-source"
KINDS = ("coding-agent-cli", "sandbox-host", "ci", "skill", "skill-collection", "mcp-server")
FORBIDDEN_TAGS = ("driver", "harness")  # they mean an OpenWiz driver or harness row exists
ENTRY_KEYS = ("id", "name", "source_description", "url", "licence", "licence_url", "source_url", "tags", "plugs_into")
ID = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,38}[a-z0-9])?")
LINE = re.compile(r"[^\x00-\x1f\x7f]+")
RUN = 5
MARKETING = ("best", "powerful", "revolutionary", "ultimate", "world-class", "cutting-edge", "blazing", "seamless",
             "seamlessly", "effortless", "effortlessly", "game-changing", "next-generation", "next-gen", "supercharge",
             "unleash", "amazing", "incredible", "magical", "lightning-fast", "state-of-the-art")
SOURCE_LABEL = "Listed from public source, unverified: "


def norm_url(url):
    """Lowercase scheme and host, www. stripped, no .git, no trailing slash: the dedupe key."""
    m = re.match(r"(?i)(https?)://([^/?#]+)(.*)", url.strip())
    if not m:
        return url.strip().lower()
    host = m.group(2).lower()
    host = host[4:] if host.startswith("www.") else host
    rest = m.group(3)
    rest = rest[:-4] if rest.endswith(".git") else rest
    return f"{host}{rest.rstrip('/')}"


def words(text):
    table = str.maketrans({c: " " for c in string.punctuation + "—–‘’“”…"})
    return text.lower().translate(table).split()


def summary_problem(summary, source_description):
    """Why a summary is refused, or None: the length and one-line rule, no marketing words, and no copying."""
    if not (isinstance(summary, str) and LINE.fullmatch(summary) and len(summary) <= 140):
        return "must be one line of at most 140 characters"
    mine = words(summary)
    hype = sorted(set(mine) & set(MARKETING))
    if hype:
        return f"uses marketing words: {', '.join(hype)}"
    theirs = words(source_description or "")
    if mine == theirs:
        return "equals the source description"
    grams = {tuple(theirs[i:i + RUN]) for i in range(len(theirs) - RUN + 1)}
    for i in range(len(mine) - RUN + 1):
        if tuple(mine[i:i + RUN]) in grams:
            return f'shares the run "{" ".join(mine[i:i + RUN])}" with the source description'
    return None


def entry_problem(entry):
    missing = [k for k in ENTRY_KEYS if k not in entry]
    if missing:
        return f"missing {', '.join(missing)}"
    if not ID.fullmatch(entry["id"]) or len(entry["id"]) > 40:
        return "id must be 2 to 40 lowercase letters, digits and hyphens"
    tags = entry["tags"]
    if not tags or not set(tags) & set(KINDS) or set(tags) & set(FORBIDDEN_TAGS) or len(set(tags)) != len(tags):
        return "tags need one kind tag, no driver or harness tag, none twice"
    if len(tags) > 7:
        return "at most 7 tags (public-source is added)"
    for key in ("name", "plugs_into", "licence"):
        if not (isinstance(entry[key], str) and LINE.fullmatch(entry[key])):
            return f"{key} must be one line"
    for key in ("url", "licence_url", "source_url"):
        if not str(entry[key]).startswith("https://"):
            return f"{key} must be https://"
    return None


def load_json(path, default):
    return json.loads(path.read_text()) if path.exists() else default


def save_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")


def load_listings(out):
    return {p.stem: json.loads(p.read_text()) for p in sorted(Path(out).glob("*.json"))}


def manifests(base=HERE):
    """{source: {id: record}} for every manifest."""
    return {p.stem: json.loads(p.read_text()) for p in sorted((base / "manifest").glob("*.json"))}


def listing_for(entry, summary, catalog):
    tags = [PUBLIC] + [t for t in entry["tags"] if t != PUBLIC]
    return {
        "name": entry["name"],
        "summary": summary,
        "tags": tags,
        "url": entry["url"],
        "plugs_into": entry["plugs_into"],
        "publisher": PUBLISHER,
        "stage": "available",
        "links": [
            {"label": SOURCE_LABEL + entry.get("catalog", catalog), "url": entry["source_url"]},
            {"label": f"Licence: {entry['licence']}", "url": entry["licence_url"]},
        ],
        "status": "listed",
    }


def owner_of(entry):
    m = re.match(r"https://github\.com/([^/]+)/", entry["url"] + "/")
    owner = m.group(1) if m else re.sub(r"^www\.", "", entry["url"].split("/")[2]).split(".")[0]
    return re.sub(r"[^a-z0-9-]+", "-", owner.lower()).strip("-")


def run_source(name, catalog, entries, out, base=HERE, today=None, resolves=None, log=print):
    """Dedupe, write listings that have a written summary, queue the rest in pending/, and update the manifest.

    Returns a dict of counts. `resolves(url) -> bool` is the at-write-time URL check (fetching.resolves by default).
    """
    out, today = Path(out), today or datetime.date.today().isoformat()
    if resolves is None:
        import fetching
        resolves = fetching.resolves
    listings = load_listings(out)
    all_manifests = manifests(base)
    mine = all_manifests.get(name, {})
    owned_elsewhere = {i for s, m in all_manifests.items() if s != name for i in m}
    pending_path = base / "pending" / f"{name}.json"
    pending = load_json(pending_path, {})
    taken_urls = {norm_url(d["url"]): i for i, d in listings.items() if isinstance(d.get("url"), str)}
    for other in sorted((base / "pending").glob("*.json")):
        if other != pending_path:
            taken_urls.update({norm_url(e["url"]): i for i, e in load_json(other, {}).items()})
    counts = dict(written=0, refreshed=0, pending=0, duplicate=0, invalid=0, unresolved=0, refused_summary=0)
    seen, new_pending = set(), {}
    for entry in entries:
        problem = entry_problem(entry)
        if problem:
            log(f"{name}: skipped {entry.get('id', '<no id>')}: {problem}")
            counts["invalid"] += 1
            continue
        key = norm_url(entry["url"])
        if key in seen:
            counts["duplicate"] += 1
            continue
        seen.add(key)
        listing_id = entry["id"]
        ours = listing_id in mine and listing_id in listings
        if not ours:
            if taken_urls.get(key) not in (None, listing_id) or (taken_urls.get(key) == listing_id and listing_id in listings):
                counts["duplicate"] += 1
                continue
            if listing_id in listings or listing_id in owned_elsewhere:
                suffix = f"-{owner_of(entry)}"
                listing_id = (entry["id"][:40 - len(suffix)].rstrip("-") + suffix)
                entry = {**entry, "id": listing_id}
                if listing_id in listings or listing_id in owned_elsewhere or entry_problem(entry):
                    counts["duplicate"] += 1
                    continue
        summary = listings[listing_id]["summary"] if ours else (pending.get(listing_id) or {}).get("summary", "")
        if not summary:
            new_pending[listing_id] = {**{k: entry[k] for k in ENTRY_KEYS}, **({"catalog": entry["catalog"]} if
                                       "catalog" in entry else {}), "summary": ""}
            counts["pending"] += 1
            continue
        problem = summary_problem(summary, entry["source_description"])
        if problem and not ours:
            log(f"{name}: kept {listing_id} pending: its summary {problem}")
            new_pending[listing_id] = {**pending[listing_id], **{k: entry[k] for k in ENTRY_KEYS}}
            counts["refused_summary"] += 1
            continue
        listing = listing_for(entry, summary, catalog)
        dead = [u for u in [listing["url"]] + [link["url"] for link in listing["links"]] if not resolves(u)]
        if dead:
            log(f"{name}: dropped {listing_id}: no 2xx/3xx from {', '.join(dead)}")
            counts["unresolved"] += 1
            continue
        save_json(out / f"{listing_id}.json", listing)
        mine[listing_id] = {"source_url": entry["source_url"], "url": entry["url"],
                            "source_description": entry["source_description"], "licence": entry["licence"],
                            "licence_url": entry["licence_url"], "fetched": today}
        taken_urls[key] = listing_id
        counts["refreshed" if ours else "written"] += 1
    if mine:
        save_json(base / "manifest" / f"{name}.json", dict(sorted(mine.items())))
    if new_pending:
        save_json(pending_path, dict(sorted(new_pending.items())))
    elif pending_path.exists():
        pending_path.unlink()
    return counts


def load_source(name, base=HERE):
    if not re.fullmatch(r"[a-z0-9_]+", name):
        raise SystemExit(f"run.py: {name!r} is not a source name")
    path = base / "sources" / f"{name}.py"
    if not path.exists():
        raise SystemExit(f"run.py: no source {name}: write tools/import/sources/{name}.py")
    spec = importlib.util.spec_from_file_location(f"wizmarket_source_{name}", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def check_summaries(out, base=HERE, log=print):
    """Every public-source listing (and every written pending summary) against its manifest's source description."""
    records = {i: r for m in manifests(base).values() for i, r in m.items()}
    failures, checked = [], 0
    for listing_id, data in load_listings(out).items():
        if PUBLIC not in data.get("tags", []):
            continue
        checked += 1
        if listing_id not in records:
            failures.append(f"{listing_id}: tagged {PUBLIC} but in no manifest")
            continue
        problem = summary_problem(data.get("summary"), records[listing_id]["source_description"])
        if problem:
            failures.append(f"{listing_id}: summary {problem}")
        if set(data.get("tags", [])) & set(FORBIDDEN_TAGS):
            failures.append(f"{listing_id}: an imported listing is never tagged driver or harness")
    for path in sorted((base / "pending").glob("*.json")):
        for listing_id, entry in load_json(path, {}).items():
            if entry.get("summary"):
                checked += 1
                problem = summary_problem(entry["summary"], entry["source_description"])
                if problem:
                    failures.append(f"pending/{path.name} {listing_id}: summary {problem}")
    for line in failures:
        log(line)
    log(f"check-summaries: {'ok' if not failures else 'refused'}, {checked} summaries checked, {len(failures)} refused")
    return 1 if failures else 0


def count(out, base=HERE, log=print):
    listings = load_listings(out)
    owner = {i: s for s, m in manifests(base).items() for i in m}
    by_status, by_kind, by_source = {}, {}, {}
    for listing_id, data in listings.items():
        by_status[data.get("status")] = by_status.get(data.get("status"), 0) + 1
        for tag in data.get("tags", []):
            if tag in KINDS + FORBIDDEN_TAGS + ("loop", "plugin"):
                by_kind[tag] = by_kind.get(tag, 0) + 1
        source = owner.get(listing_id, "hand-written") if PUBLIC in data.get("tags", []) or listing_id not in owner \
            else owner[listing_id]
        by_source[source] = by_source.get(source, 0) + 1
    waiting = {p.stem: len(load_json(p, {})) for p in sorted((base / "pending").glob("*.json"))}
    log(f"listings: {len(listings)}")
    for title, table in (("by status", by_status), ("by kind tag", by_kind), ("by source", by_source),
                         ("pending a summary", waiting)):
        log(f"{title}:")
        for key, n in sorted(table.items(), key=lambda kv: (-kv[1], kv[0])):
            log(f"  {key}: {n}")
    return 0


def main(argv):
    parser = argparse.ArgumentParser(prog="run.py", description="WizMarket's importer for public catalogs")
    parser.add_argument("source", nargs="?", help="a source in tools/import/sources/, or count")
    parser.add_argument("--out", default=str(ROOT / "listings"), help="the listings folder (default listings/)")
    parser.add_argument("--offline", action="store_true", help="use the pending file's entries, fetch nothing")
    parser.add_argument("--check-summaries", action="store_true", help="run the copy check and exit")
    args = parser.parse_args(argv)
    if args.check_summaries:
        return check_summaries(args.out)
    if args.source == "count":
        return count(args.out)
    if not args.source:
        parser.error("name a source, count, or --check-summaries")
    module = load_source(args.source)
    if args.offline:
        entries = list(load_json(HERE / "pending" / f"{args.source}.json", {}).values())
    else:
        entries = module.fetch()
    counts = run_source(args.source, module.NAME, entries, args.out)
    print(f"{args.source}: " + ", ".join(f"{k} {v}" for k, v in counts.items()))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
