"""Jev readings that sit beside listing.v1. They never replace check's verdict.

Proof kind is the tag rule in check_proof: driver or harness needs a receipt,
skill needs a pinned check, both tags need both, and any other tag needs neither.
Jev is asked three separate Nouls (driver, harness, skill) about the same state
in one request. Each Noul is one gut-check. Code combines the confident yeses
with KIND_WEIGHT_DRIVER, KIND_WEIGHT_HARNESS, and KIND_WEIGHT_SKILL.

A being-built listing's first link is checked only as a URL. With
--public-work-links, two more Nouls on that same state ask whether the link is
a work item and whether it is about this listing. WORK_WEIGHT_ITEM and
WORK_WEIGHT_ABOUT combine those yeses.

Each Noul is compared directly to the inclusive 0.7 (yes) and 0.3 (no)
thresholds (exact arithmetic equivalent of abs(2p - 1) >= 0.4). Strictly
between 0.3 and 0.7 on any factor, or with no key, the reading is the tag rule
and the link stays not judged.

The summary's length is checked by the contract. Two Scores on the same state
ask how specifically `summary` says what the listing does, and what it plugs
into. SUMMARY_WEIGHT_DOES and SUMMARY_WEIGHT_PLUG combine them. Below
SCORE_CONFIDENCE_MIN on either Score, or with no key, the summary stays not
judged.

Data scope: when TYPESAFE_API_KEY is set, only `name`, `summary`, and
`plugs_into` are sent (plus public `first_link` scheme, host, and path with
--public-work-links). By default, only listings matching
refs/remotes/origin/main are sent; unpublished drafts, local edits, and
unmerged commits stay local unless selected by id, --rev, or
--include-unpublished.
"""

import hashlib
import ipaddress
import re
import subprocess
import sys
import time
import urllib.parse
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
# Both factors have to be yes before the weighted fit clears WORK_FIT_YES.
WORK_WEIGHT_ITEM = 0.5
WORK_WEIGHT_ABOUT = 0.5
WORK_FIT_YES = 0.7
WORK_FIT_NO = 0.3
SCORE_CONFIDENCE_MIN = 0.7
SUMMARY_WEIGHT_DOES = 0.7
SUMMARY_WEIGHT_PLUG = 0.3
SUMMARY_FIT_MIN = 0.35
_KIND_WORDS = (
    ("driver", re.compile(r"\bdrivers?\b", re.I)),
    ("harness", re.compile(r"\bharnesses?\b", re.I)),
    ("skill", re.compile(r"\bskills?\b", re.I)),
)
_WORK_LINK = re.compile(r"(?:/pull/|/issues?/|/-/issues/|\bpull request\b|\bissue\b|\bticket\b)", re.I)
_SUMMARY_WORD = re.compile(r"[A-Za-z0-9]+")
_PRIVATE_HOST_SUFFIXES = (
    ".localhost", ".local", ".internal", ".intranet", ".corp",
    ".lan", ".home", ".localdomain", ".private", ".arpa",
)
_CREDENTIAL_PARAM = re.compile(
    r"(?:^|[._-])(?:token|secret|key|pass(?:word|wd)?|pwd|auth(?:orization)?|"
    r"sig(?:nature)?|session(?:id)?|sid|cookie|jwt|bearer|credential|pat|sas|code|invite|share)(?:$|[._-])",
    re.I,
)


def _noul_question(question, yes, no):
    return {"type": "noul", "instructions": question, "criteria": {"true": yes, "false": no}}


def _score_question(question, criteria):
    return {"type": "score", "instructions": question, "criteria": criteria}


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
WORK_QUESTIONS = {
    "is_work_item": _noul_question(
        "Is `first_link` a pull request, an issue, or a ticket?",
        "The URL or its label is a pull request, issue, or ticket on any tracker.",
        "It is a homepage, a docs page, a repo root, or another page that is not a work item.",
    ),
    "is_about_this_work": _noul_question(
        "Is `first_link` about the work `name` and `summary` say is being built?",
        "The link is the work this listing describes.",
        "The link is about something else.",
    ),
}
SUMMARY_QUESTIONS = {
    "says_what": _score_question(
        "How specifically does `summary` say what the listing does?",
        [
            "It does not say what the listing does.",
            "It names a category, such as a tool or a server, and not what it does.",
            "It says what it does in one concrete line.",
        ],
    ),
    "says_plug": _score_question(
        "How specifically does `summary` say what the listing plugs into?",
        [
            "It does not say what the listing plugs into.",
            "It names a platform in passing.",
            "It names the specific thing it plugs into.",
        ],
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


def _has_credential_param(text):
    if not text:
        return False
    for key, _ in urllib.parse.parse_qsl(text, keep_blank_values=True):
        if _CREDENTIAL_PARAM.search(key):
            return True
    return False


def _public_work_url(url, private_fn):
    """Return scheme://host[:port]/path for a public https URL, or None if private or credential-bearing."""
    if not isinstance(url, str) or private_fn(url) or private_fn(urllib.parse.unquote(url)):
        return None
    try:
        parts = urllib.parse.urlsplit(url)
    except ValueError:
        return None
    if parts.scheme.lower() != "https" or not parts.hostname:
        return None
    if parts.username is not None or parts.password is not None or "@" in parts.netloc:
        return None
    host = parts.hostname.rstrip(".").lower()
    if not host or "." not in host or host == "localhost" or host.endswith(_PRIVATE_HOST_SUFFIXES):
        return None
    try:
        ipaddress.ip_address(host)
        return None
    except ValueError:
        pass
    if _has_credential_param(parts.query) or _has_credential_param(parts.fragment):
        return None
    return urllib.parse.urlunsplit(("https", parts.netloc, parts.path, "", ""))


def first_link(listing, private_fn):
    if listing.get("stage") != "being-built":
        return None
    links = listing.get("links")
    if not isinstance(links, list) or not links or not isinstance(links[0], dict):
        return None
    label, url = links[0].get("label"), links[0].get("url")
    if not isinstance(label, str) or private_fn(label):
        return None
    clean_url = _public_work_url(url, private_fn)
    if clean_url is None:
        return None
    return {"label": label, "url": clean_url}


def listing_state(listing, private_fn, include_work_link=True):
    """Prose Jev may see. Tags stay out, so the answer is not a copy of the tag rule."""
    state = {}
    for key in ("name", "summary", "plugs_into"):
        value = listing.get(key)
        if not isinstance(value, str) or private_fn(value):
            return None
        state[key] = value
    if include_work_link:
        link = first_link(listing, private_fn)
        if link is not None:
            state["first_link"] = link
    return state


def questions_for(listing, private_fn, include_work_link=True):
    questions = dict(KIND_QUESTIONS)
    questions.update(SUMMARY_QUESTIONS)
    if include_work_link and first_link(listing, private_fn) is not None:
        questions.update(WORK_QUESTIONS)
    return questions


def heuristic_work_link(label, url):
    """Keyword baseline for the bench. The review command does not use it as a verdict."""
    return bool(_WORK_LINK.search(f"{label or ''}\n{url or ''}"))


def heuristic_summary(summary):
    """Word-count baseline for the bench. The review command does not use it as a verdict."""
    count = len(_SUMMARY_WORD.findall(summary or ""))
    if count < 4:
        return 0
    if count < 8:
        return 1
    if count < 14:
        return 2
    return 3


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


def _score(answers, name, top):
    if not isinstance(answers, dict):
        return None
    item = answers.get(name)
    if not isinstance(item, dict) or item.get("type") != "score":
        return None
    score, confidence = item.get("score"), item.get("confidence")
    if any(isinstance(value, bool) or not isinstance(value, (int, float)) for value in (score, confidence)):
        return None
    if not 0 <= score <= top or not 0 <= confidence <= 1:
        return None
    return float(score), float(confidence)


def summary_reading(listing, answers):
    """Length still accepts the line. A low weighted fit, at high confidence, is a finding."""
    does_top = len(SUMMARY_QUESTIONS["says_what"]["criteria"]) - 1
    plug_top = len(SUMMARY_QUESTIONS["says_plug"]["criteria"]) - 1
    does = _score(answers, "says_what", does_top)
    plug = _score(answers, "says_plug", plug_top)
    if does is None or plug is None or does[1] < SCORE_CONFIDENCE_MIN or plug[1] < SCORE_CONFIDENCE_MIN:
        return {"line": f"{listing['id']}: summary not judged", "source": "fallback", "score": None, "finding": None}
    fit = SUMMARY_WEIGHT_DOES * (does[0] / does_top) + SUMMARY_WEIGHT_PLUG * (plug[0] / plug_top)
    finding = None
    if fit < SUMMARY_FIT_MIN:
        finding = f"{listing['id']}: summary does not say what the listing does"
    return {"line": f"{listing['id']}: summary score {fit:.2f} (jev)", "source": "jev", "score": fit,
            "finding": finding}


def work_link_factors(answers):
    return (factor_yes(_noul(answers, "is_work_item")),
            factor_yes(_noul(answers, "is_about_this_work")))


def work_link_reading(listing, answers):
    """The check accepts the first link as a URL only. Jev may flag a confident no."""
    if listing.get("stage") != "being-built":
        return None
    item, about = work_link_factors(answers)
    if item is None or about is None:
        return {"line": f"{listing['id']}: work link not judged", "source": "fallback", "yes": None,
                "finding": None, "fit": None}
    fit = WORK_WEIGHT_ITEM * (1.0 if item else 0.0) + WORK_WEIGHT_ABOUT * (1.0 if about else 0.0)
    if fit >= WORK_FIT_YES:
        return {"line": f"{listing['id']}: work link yes (jev {fit:.2f})", "source": "jev", "yes": True,
                "finding": None, "fit": fit}
    if fit <= WORK_FIT_NO:
        return {"line": f"{listing['id']}: work link no (jev {fit:.2f})", "source": "jev", "yes": False, "fit": fit,
                "finding": f"{listing['id']}: first link does not read as the work's pull request or ticket"}
    return {"line": f"{listing['id']}: work link not judged", "source": "fallback", "yes": None,
            "finding": None, "fit": fit}


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


def ask_listing(listing, client, private_fn, include_work_link=True, *, timeout=None):
    if client is None:
        return None
    state = listing_state(listing, private_fn, include_work_link=include_work_link)
    if state is None:
        return None
    try:
        return _ask(client, state, questions_for(listing, private_fn, include_work_link=include_work_link),
                    timeout=timeout)
    except Exception:
        return None


def review_lines(entries, client, private_fn, include_work_links=False, *,
                 allowed_ids=None, deadline=REVIEW_DEADLINE, clock=time.monotonic):
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
            work = work_link_reading(entry, None)
            if work is not None:
                lines.append(work["line"])
            summary = summary_reading(entry, None)
            lines.append(summary["line"])
            continue
        answers = None
        if client is not None and stop_reason is None:
            if getattr(client, "unavailable", False):
                stop_reason = getattr(client, "stop_reason", None) or "service failure"
            elif end is not None and clock() >= end:
                stop_reason = "deadline"
            else:
                remaining = None if end is None else max(0.0, end - clock())
                state = listing_state(entry, private_fn, include_work_link=include_work_links)
                if state is not None:
                    try:
                        answers = _ask(client, state,
                                       questions_for(entry, private_fn, include_work_link=include_work_links),
                                       timeout=remaining)
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
        work = work_link_reading(entry, answers if include_work_links else None)
        if work is not None:
            lines.append(work["line"])
            if work["finding"]:
                findings.append("finding: " + work["finding"])
        summary = summary_reading(entry, answers)
        lines.append(summary["line"])
        if summary["finding"]:
            findings.append("finding: " + summary["finding"])
    lines.extend(findings)
    if unpublished_skipped:
        noun = "listing" if unpublished_skipped == 1 else "listings"
        lines.append(f"note: {unpublished_skipped} unpublished {noun} not sent to TypeSafe; "
                     "pass listing id(s), --rev <rev>, or --include-unpublished to send")
    if stop_reason:
        lines.append(f"note: stopped calling TypeSafe after {stop_reason}; using tag-rule fallback")
    lines.append(f"review: {len(entries)} listings, {len(findings)} findings")
    return lines, findings


def run(root, client, check_tree, files_fn, private_fn, include_work_links=False, *,
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
    lines, findings = review_lines(entries, client, private_fn, include_work_links=include_work_links,
                                   allowed_ids=allowed_ids, deadline=deadline, clock=clock)
    return (1 if findings else 0), "\n".join(lines) + "\n"


def client_from_env():
    return typesafe_client.client_from_env()
