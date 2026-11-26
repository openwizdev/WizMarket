"""Offline comparison of the tag rule and a keyword baseline on check/jev_fixtures.json.

`python3 -I check/jev_bench.py --live` also asks Jev, once TYPESAFE_API_KEY is set.
Without the key, --live prints the offline numbers and says the live count was not run.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import review
import typesafe_client

FIXTURES = Path(__file__).resolve().parent / "jev_fixtures.json"


def load():
    return json.loads(FIXTURES.read_text())


def score_kind(cases):
    tags = heuristic = 0
    for case in cases:
        label = case["prose_kind"]
        if review.declared_proof(case["tags"]) == label:
            tags += 1
        if review.heuristic_proof(case["name"], case["summary"], case["plugs_into"]) == label:
            heuristic += 1
    return {"n": len(cases), "tags": tags, "heuristic": heuristic}


def score_kind_live(cases, client):
    agreed = unanswered = 0
    for case in cases:
        answers = client.ask(
            {"name": case["name"], "summary": case["summary"], "plugs_into": case["plugs_into"]},
            {"proof_kind": review.PROOF_QUESTION})
        reading = review.proof_reading(case, answers)
        if reading["source"] != "jev":
            unanswered += 1
        elif reading["read"] == case["prose_kind"]:
            agreed += 1
    return {"agreed": agreed, "unanswered": unanswered, "n": len(cases)}


def report(live=False, client=None):
    kind = score_kind(load()["kind"])
    lines = [
        f"kind tags: {kind['tags']}/{kind['n']}",
        f"kind heuristic: {kind['heuristic']}/{kind['n']}",
    ]
    if not live:
        lines.append("kind jev: not run; set TYPESAFE_API_KEY and run python3 -I check/jev_bench.py --live")
        return "\n".join(lines) + "\n"
    if client is None:
        lines.append("kind jev: skipped, TYPESAFE_API_KEY is not set")
        return "\n".join(lines) + "\n"
    result = score_kind_live(load()["kind"], client)
    lines.append(
        f"kind jev ({typesafe_client.MODEL}): {result['agreed']}/{result['n']} agreed, "
        f"{result['unanswered']} unanswered")
    return "\n".join(lines) + "\n"


def main(argv):
    live = "--live" in argv
    text = report(live=live, client=typesafe_client.client_from_env() if live else None)
    sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
