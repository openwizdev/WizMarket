"""Jev readings that sit beside listing.v1. They never replace check's verdict.

Proof kind is the tag rule in check_proof: driver or harness needs a receipt,
skill needs a pinned check, both tags need both, and any other tag needs neither.
Jev is asked three separate Nouls (driver, harness, skill) about the same state
in one request. Each Noul is one gut-check. Code combines the confident yeses
with KIND_WEIGHT_DRIVER, KIND_WEIGHT_HARNESS, and KIND_WEIGHT_SKILL.

A being-built listing's first link is checked only as a URL. Two more Nouls on
that same state ask whether the link is a work item and whether it is about
this listing. WORK_WEIGHT_ITEM and WORK_WEIGHT_ABOUT combine those yeses.
Below NOUL_CONFIDENCE_MIN on any factor used, or with no key, the reading is
the tag rule and the link stays not judged.
"""

import ipaddress
import re
import sys
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import typesafe_client

# abs(2p - 1) of 0.4 is the documented 0.3 / 0.7 Noul band.
NOUL_CONFIDENCE_MIN = 0.4
NOUL_YES = 0.7
NOUL_NO = 0.3
# A confident yes contributes its weight. One full driver or harness weight is enough for a receipt.
KIND_WEIGHT_DRIVER = 1.0
KIND_WEIGHT_HARNESS = 1.0
KIND_WEIGHT_SKILL = 1.0
# Both factors have to be yes before the weighted fit clears WORK_FIT_YES.
WORK_WEIGHT_ITEM = 0.5
WORK_WEIGHT_ABOUT = 0.5
WORK_FIT_YES = 0.7
WORK_FIT_NO = 0.3
_KIND_WORDS = (
    ("driver", re.compile(r"\bdrivers?\b", re.I)),
    ("harness", re.compile(r"\bharnesses?\b", re.I)),
    ("skill", re.compile(r"\bskills?\b", re.I)),
)
_WORK_LINK = re.compile(r"(?:/pull/|/issues?/|/-/issues/|\bpull request\b|\bissue\b|\bticket\b)", re.I)
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
    if include_work_link and first_link(listing, private_fn) is not None:
        questions.update(WORK_QUESTIONS)
    return questions


def heuristic_work_link(label, url):
    """Keyword baseline for the bench. The review command does not use it as a verdict."""
    return bool(_WORK_LINK.search(f"{label or ''}\n{url or ''}"))


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
    """True or False when the Noul is confident, else None so the caller falls back."""
    if value is None or noul_confidence(value) < NOUL_CONFIDENCE_MIN:
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


def ask_listing(listing, client, private_fn, include_work_link=True):
    if client is None:
        return None
    state = listing_state(listing, private_fn, include_work_link=include_work_link)
    if state is None:
        return None
    try:
        return client.ask(state, questions_for(listing, private_fn, include_work_link=include_work_link))
    except Exception:
        return None


def review_lines(entries, client, private_fn, include_work_links=False):
    lines, findings = [], []
    for entry in sorted(entries, key=lambda item: item["id"]):
        answers = ask_listing(entry, client, private_fn, include_work_link=include_work_links)
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
    lines.extend(findings)
    lines.append(f"review: {len(entries)} listings, {len(findings)} findings")
    return lines, findings


def run(root, client, check_tree, worktree_files, private_fn, include_work_links=False):
    failures, entries = check_tree(worktree_files(Path(root)))
    if failures:
        return 1, "\n".join(failures) + "\n"
    lines, findings = review_lines(entries, client, private_fn, include_work_links=include_work_links)
    return (1 if findings else 0), "\n".join(lines) + "\n"


def client_from_env():
    return typesafe_client.client_from_env()
