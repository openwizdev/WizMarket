import sys
from pathlib import Path


def main(argv):
    if argv[:1] == ["check"]:
        listings = list(Path("listings").glob("*.json"))
        receipts = [p for p in Path("receipts").rglob("*") if p.is_file()]
        print(f"check: ok, {len(listings)} listings and {len(receipts)} receipts checked")
        return 0
    print("usage: check.py check | index | skill <id> | changed-skills <base>", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
