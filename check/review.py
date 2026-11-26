"""Jev readings that sit beside listing.v1. They never replace check's verdict.

Proof kind is the tag rule in check_proof: driver or harness needs a receipt,
skill needs a pinned check, both tags need both, and any other tag needs neither.
Jev is asked the same four-way Choice about the name, summary, and plugs_into.
A probability under 0.7, a missing key, or a failed call keeps the tag rule.
"""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import typesafe_client

CHOICE_MIN = 0.7
PROOF_OPTIONS = ("receipt", "skill", "both", "none")
PROOF_QUESTION = {
    "type": "choice",
    "instructions": "Which proof does this listing need, from its name, summary, and plugs_into?",
    "criteria": {
        "receipt": "It is a driver or a harness (or both), and not a skill. Proof is one kit receipt.",
        "skill": "It is a skill, and not a driver or a harness. Proof is a pinned source and check.",
        "both": "It is a skill and also a driver or a harness. It needs the receipt and the pinned check.",
        "none": "It is not a driver, a harness, or a skill, so it cannot be verified.",
    },
}
_KIND_WORDS = (
    ("driver", re.compile(r"\bdrivers?\b", re.I)),
    ("harness", re.compile(r"\bharnesses?\b", re.I)),
    ("skill", re.compile(r"\bskills?\b", re.I)),
)


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
    return {"proof_kind": PROOF_QUESTION}


def _choice(answers, name, options):
    if not isinstance(answers, dict):
        return None
    item = answers.get(name)
    if not isinstance(item, dict) or item.get("type") != "choice":
        return None
    choice = item.get("choice")
    probabilities = item.get("probabilities")
    if choice not in options or not isinstance(probabilities, dict):
        return None
    probability = probabilities.get(choice)
    if isinstance(probability, bool) or not isinstance(probability, (int, float)):
        return None
    if not 0 <= probability <= 1 or probability < CHOICE_MIN:
        return None
    return choice


def proof_reading(listing, answers):
    declared = declared_proof(listing.get("tags"))
    choice = _choice(answers, "proof_kind", PROOF_OPTIONS)
    if choice is None:
        return {"declared": declared, "read": declared, "source": "fallback", "finding": None}
    finding = None
    if choice != declared:
        finding = f"{listing['id']}: prose reads as {choice}, tags say {declared}"
    return {"declared": declared, "read": choice, "source": "jev", "finding": finding}


def ask_listing(listing, client, private_fn):
    if client is None:
        return None
    state = listing_state(listing, private_fn)
    if state is None:
        return None
    try:
        return client.ask(state, questions_for(listing))
    except Exception:
        return None


def review_lines(entries, client, private_fn):
    lines, findings = [], []
    for entry in sorted(entries, key=lambda item: item["id"]):
        reading = proof_reading(entry, ask_listing(entry, client, private_fn))
        lines.append(f"{entry['id']}: proof kind declared {reading['declared']}, "
                     f"read {reading['read']} ({reading['source']})")
        if reading["finding"]:
            findings.append("finding: " + reading["finding"])
    lines.extend(findings)
    lines.append(f"review: {len(entries)} listings, {len(findings)} findings")
    return lines, findings


def run(root, client, check_tree, worktree_files, private_fn):
    failures, entries = check_tree(worktree_files(Path(root)))
    if failures:
        return 1, "\n".join(failures) + "\n"
    lines, findings = review_lines(entries, client, private_fn)
    return (1 if findings else 0), "\n".join(lines) + "\n"


def client_from_env():
    return typesafe_client.client_from_env()
