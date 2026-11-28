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


def score_work_link(cases):
    url_only = heuristic = 0
    for case in cases:
        if case["work_link"]:
            url_only += 1
        if review.heuristic_work_link(case["label"], case["url"]) == case["work_link"]:
            heuristic += 1
    return {"n": len(cases), "url_only": url_only, "heuristic": heuristic}


def _ask(listing, client):
    private = lambda text: False
    return client.ask(review.listing_state(listing, private), review.questions_for(listing, private))


def score_kind_live(cases, client):
    agreed = unanswered = 0
    for case in cases:
        answers = _ask(case, client)
        reading = review.proof_reading(case, answers)
        if reading["source"] != "jev":
            unanswered += 1
        elif reading["read"] == case["prose_kind"]:
            agreed += 1
    return {"agreed": agreed, "unanswered": unanswered, "n": len(cases)}


def score_work_link_live(cases, client):
    agreed = unanswered = 0
    item_agreed = item_unanswered = 0
    about_agreed = about_unanswered = 0
    for case in cases:
        listing = {"id": case["id"], "name": case["name"], "summary": case["summary"],
                   "plugs_into": case["plugs_into"], "stage": "being-built",
                   "links": [{"label": case["label"], "url": case["url"]}]}
        answers = _ask(listing, client)
        reading = review.work_link_reading(listing, answers)
        if reading["source"] != "jev":
            unanswered += 1
        elif reading["yes"] == case["work_link"]:
            agreed += 1
        item, about = review.work_link_factors(answers)
        if item is None:
            item_unanswered += 1
        elif item == case["is_work_item"]:
            item_agreed += 1
        if about is None:
            about_unanswered += 1
        elif about == case["is_about_this_work"]:
            about_agreed += 1
    n = len(cases)
    return {
        "agreed": agreed, "unanswered": unanswered, "n": n,
        "item": {"agreed": item_agreed, "unanswered": item_unanswered, "n": n},
        "about": {"agreed": about_agreed, "unanswered": about_unanswered, "n": n},
    }


def _jev_line(name, result):
    return (f"{name} jev ({typesafe_client.MODEL}): {result['agreed']}/{result['n']} agreed, "
            f"{result['unanswered']} unanswered")


def report(live=False, client=None):
    data = load()
    kind = score_kind(data["kind"])
    work = score_work_link(data["work_link"])
    lines = [
        f"kind tags: {kind['tags']}/{kind['n']}",
        f"kind heuristic: {kind['heuristic']}/{kind['n']}",
        f"work_link url-only: {work['url_only']}/{work['n']}",
        f"work_link heuristic: {work['heuristic']}/{work['n']}",
    ]
    if not live:
        lines.append("jev: not run; set TYPESAFE_API_KEY and run python3 -I check/jev_bench.py --live")
        return "\n".join(lines) + "\n"
    if client is None:
        lines.append("jev: skipped, TYPESAFE_API_KEY is not set")
        return "\n".join(lines) + "\n"
    lines.append(_jev_line("kind", score_kind_live(data["kind"], client)))
    work_live = score_work_link_live(data["work_link"], client)
    lines.append(_jev_line("work_link", work_live))
    lines.append(_jev_line("work_link item", work_live["item"]))
    lines.append(_jev_line("work_link about", work_live["about"]))
    return "\n".join(lines) + "\n"


def main(argv):
    live = "--live" in argv
    text = report(live=live, client=typesafe_client.client_from_env() if live else None)
    sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
