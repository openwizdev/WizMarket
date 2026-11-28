"""Jev readings that sit beside listing.v1. They never replace check's verdict.

Proof kind is the tag rule in check_proof: driver or harness needs a receipt,
skill needs a pinned check, both tags need both, and any other tag needs neither.
Jev is asked three separate Nouls (driver, harness, skill) about the same state
in one request. Each Noul is one gut-check. Code combines the confident yeses
with KIND_WEIGHT_DRIVER, KIND_WEIGHT_HARNESS, and KIND_WEIGHT_SKILL.

Each Noul is compared directly to the inclusive 0.7 (yes) and 0.3 (no)
thresholds (exact arithmetic equivalent of abs(2p - 1) >= 0.4). Strictly
between 0.3 and 0.7 on any factor, the reading is the tag rule, the same result
as when TYPESAFE_API_KEY is unset.

Data scope: when TYPESAFE_API_KEY is set, only `name`, `summary`, and
`plugs_into` are sent. By default, only listings matching
refs/remotes/origin/main are sent; unpublished drafts, local edits, and
unmerged commits stay local unless selected by id, --rev, or
--include-unpublished.
"""

import hashlib
import re
import subprocess
import sys
import time
from pathlib import Path, PurePosixPath

sys.path.insert(0, str(Path(__file__).resolve().parent))

import typesafe_client

# Inclusive Noul thresholds (0.3 / 0.7) matching abs(2p - 1) >= 0.4 in exact arithmetic.
NOUL_CONFIDENCE_MIN = 0.4
NOUL_YES = 0.7
NOUL_NO = 0.3
REVIEW_DEADLINE = 60.0
_LISTING_ID = re.compile(r"[a-z0-9-]{2,40}")
# A confident yes contributes its weight. One full driver or harness weight is enough for a receipt.
KIND_WEIGHT_DRIVER = 1.0
KIND_WEIGHT_HARNESS = 1.0
KIND_WEIGHT_SKILL = 1.0
_KIND_WORDS = (
    ("driver", re.compile(r"\bdrivers?\b", re.I)),
    ("harness", re.compile(r"\bharnesses?\b", re.I)),
    ("skill", re.compile(r"\bskills?\b", re.I)),
)


def _noul_question(question, yes, no):
    return {"type": "noul", "instructions": question, "criteria": {"true": yes, "false": no}}


KIND_QUESTIONS = {
    "is_driver": _noul_question(
        "Does `name`, `summary`, or `plugs_into` describe an OpenWiz driver?",
        "It starts, wakes, or stops agents on a host.",
        "It is not a driver.",
    ),
    "is_harness": _noul_question(
        "Does `name`, `summary`, or `plugs_into` describe a harness?",
        "A driver runs it, such as a coding-agent CLI.",
        "It is not a harness.",
    ),
    "is_skill": _noul_question(
        "Does `name`, `summary`, or `plugs_into` describe a skill an OpenWiz agent runs?",
        "It is a skill with its own check.",
        "It is not a skill.",
    ),
}


def declared_proof(tags):
    """The proof kind check_proof already requires from these tags."""
    names = set(tags or [])
    receipt = bool(names & {"driver", "harness"})
    skill = "skill" in names
    if receipt and skill:
        return "both"
    if receipt:
        return "receipt"
    if skill:
        return "skill"
    return "none"


def heuristic_proof(name, summary, plugs_into):
    """Keyword baseline for the bench. The review command does not use it as a verdict."""
    text = f"{name or ''}\n{summary or ''}\n{plugs_into or ''}"
    found = {kind for kind, pattern in _KIND_WORDS if pattern.search(text)}
    return declared_proof(found)


def listing_state(listing, private_fn):
    """Prose Jev may see. Tags stay out, so the answer is not a copy of the tag rule."""
    state = {}
    for key in ("name", "summary", "plugs_into"):
        value = listing.get(key)
        if not isinstance(value, str) or private_fn(value):
            return None
        state[key] = value
    return state


def questions_for(listing):
    return dict(KIND_QUESTIONS)


def _noul(answers, name):
    if not isinstance(answers, dict):
        return None
    item = answers.get(name)
    if not isinstance(item, dict) or item.get("type") != "noul":
        return None
    value = item.get("noul")
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 <= value <= 1:
        return None
    return float(value)


def noul_confidence(value):
    """Documented confidence-style number for a Noul: abs(2p - 1)."""
    return abs(2 * value - 1)


def factor_yes(value):
    """True or False at the inclusive 0.7 / 0.3 Noul thresholds, else None to fall back."""
    if value is None or isinstance(value, bool) or not 0 <= value <= 1:
        return None
    if value >= NOUL_YES:
        return True
    if value <= NOUL_NO:
        return False
    return None


def _meets(total, weights):
    needed = [weight for weight in weights if weight > 0]
    if not needed or total <= 0:
        return False
    return total >= min(needed)


def combine_kind(driver, harness, skill):
    receipt = KIND_WEIGHT_DRIVER * (1.0 if driver else 0.0) + KIND_WEIGHT_HARNESS * (1.0 if harness else 0.0)
    skill_mass = KIND_WEIGHT_SKILL * (1.0 if skill else 0.0)
    has_receipt = _meets(receipt, (KIND_WEIGHT_DRIVER, KIND_WEIGHT_HARNESS))
    has_skill = _meets(skill_mass, (KIND_WEIGHT_SKILL,))
    if has_receipt and has_skill:
        return "both"
    if has_receipt:
        return "receipt"
    if has_skill:
        return "skill"
    return "none"


def proof_reading(listing, answers):
    declared = declared_proof(listing.get("tags"))
    fallback = {"declared": declared, "read": declared, "source": "fallback", "finding": None}
    factors = [factor_yes(_noul(answers, name)) for name in ("is_driver", "is_harness", "is_skill")]
    if any(factor is None for factor in factors):
        return fallback
    read = combine_kind(*factors)
    finding = None
    if read != declared:
        finding = f"{listing['id']}: prose reads as {read}, tags say {declared}"
    return {"declared": declared, "read": read, "source": "jev", "finding": finding}


def _git_blob_hash(data, hex_len):
    algo = hashlib.sha256 if hex_len == 64 else hashlib.sha1
    return algo(f"blob {len(data)}\0".encode("ascii") + data).hexdigest()


def published_listings(root, files):
    """Listing ids whose working-tree bytes match refs/remotes/origin/main."""
    try:
        ref = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "--verify", "--quiet", "refs/remotes/origin/main^{commit}"],
            capture_output=True,
        )
        if ref.returncode != 0:
            return set()
        listing = subprocess.run(
            ["git", "-C", str(root), "ls-tree", "-z", "refs/remotes/origin/main", "--", "listings/"],
            capture_output=True,
        )
        if listing.returncode != 0:
            return set()
    except OSError:
        return set()
    published = set()
    for entry in filter(None, listing.stdout.split(b"\0")):
        try:
            meta, path = entry.decode("utf-8", "surrogateescape").split("\t", 1)
            mode, kind, sha = meta.split()
        except ValueError:
            continue
        if kind != "blob" or mode not in ("100644", "100755"):
            continue
        data = files.get(path)
        if data is None:
            continue
        if _git_blob_hash(data, len(sha)) == sha:
            name = PurePosixPath(path)
            if len(name.parts) == 2 and name.suffix == ".json":
                published.add(name.stem)
    return published


def _ask(client, state, questions, timeout=None):
    if timeout is not None and isinstance(client, typesafe_client.HttpSystemOneClient):
        return client.ask(state, questions, timeout=timeout)
    return client.ask(state, questions)


def ask_listing(listing, client, private_fn, *, timeout=None):
    if client is None:
        return None
    state = listing_state(listing, private_fn)
    if state is None:
        return None
    try:
        return _ask(client, state, questions_for(listing), timeout=timeout)
    except Exception:
        return None


def review_lines(entries, client, private_fn, *, allowed_ids=None, deadline=REVIEW_DEADLINE, clock=time.monotonic):
    lines, findings = [], []
    end = None if deadline is None else clock() + deadline
    stop_reason = None
    unpublished_skipped = 0
    for entry in sorted(entries, key=lambda item: item["id"]):
        if client is not None and allowed_ids is not None and entry["id"] not in allowed_ids:
            unpublished_skipped += 1
            reading = proof_reading(entry, None)
            lines.append(f"{entry['id']}: proof kind declared {reading['declared']}, "
                         f"read {reading['read']} ({reading['source']}, unpublished)")
            continue
        answers = None
        if client is not None and stop_reason is None:
            if getattr(client, "unavailable", False):
                stop_reason = getattr(client, "stop_reason", None) or "service failure"
            elif end is not None and clock() >= end:
                stop_reason = "deadline"
            else:
                remaining = None if end is None else max(0.0, end - clock())
                state = listing_state(entry, private_fn)
                if state is not None:
                    try:
                        answers = _ask(client, state, questions_for(entry), timeout=remaining)
                    except Exception:
                        stop_reason = "service failure"
                        answers = None
                    if stop_reason is None and getattr(client, "unavailable", False):
                        stop_reason = getattr(client, "stop_reason", None) or "service failure"
        reading = proof_reading(entry, answers)
        lines.append(f"{entry['id']}: proof kind declared {reading['declared']}, "
                     f"read {reading['read']} ({reading['source']})")
        if reading["finding"]:
            findings.append("finding: " + reading["finding"])
    lines.extend(findings)
    if unpublished_skipped:
        noun = "listing" if unpublished_skipped == 1 else "listings"
        lines.append(f"note: {unpublished_skipped} unpublished {noun} not sent to TypeSafe; "
                     "pass listing id(s), --rev <rev>, or --include-unpublished to send")
    if stop_reason:
        lines.append(f"note: stopped calling TypeSafe after {stop_reason}; using tag-rule fallback")
    lines.append(f"review: {len(entries)} listings, {len(findings)} findings")
    return lines, findings


def run(root, client, check_tree, files_fn, private_fn, *,
        ids=None, include_unpublished=False, published_ids=None,
        deadline=REVIEW_DEADLINE, clock=time.monotonic):
    if ids:
        for listing_id in ids:
            if not isinstance(listing_id, str) or not _LISTING_ID.fullmatch(listing_id):
                return 1, "review <hidden name>: refused, not a listing id\n"
    files = files_fn(Path(root))
    failures, entries = check_tree(files)
    if failures:
        return 1, "\n".join(failures) + "\n"
    if ids:
        by_id = {entry["id"]: entry for entry in entries}
        wanted = list(dict.fromkeys(ids))
        missing = [listing_id for listing_id in wanted if listing_id not in by_id]
        if missing:
            return 1, "\n".join(
                f"review {listing_id}: refused, listings/{listing_id}.json is not there" for listing_id in missing
            ) + "\n"
        entries = [by_id[listing_id] for listing_id in wanted]
        allowed_ids = None
    elif client is None or include_unpublished:
        allowed_ids = None
    else:
        allowed_ids = published_listings(Path(root), files) if published_ids is None else set(published_ids)
    lines, findings = review_lines(entries, client, private_fn, allowed_ids=allowed_ids,
                                   deadline=deadline, clock=clock)
    return (1 if findings else 0), "\n".join(lines) + "\n"


def client_from_env():
    return typesafe_client.client_from_env()
