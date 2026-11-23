import argparse
import datetime
import json
import os
import pwd
import re
import signal
import subprocess
import sys
import tempfile
from pathlib import Path, PurePosixPath

SCHEMA = json.loads((Path(__file__).resolve().parent.parent / "schema" / "listing.v1.json").read_text())
PROPS = SCHEMA["properties"]
DEFS = SCHEMA["$defs"]
FIELDS = set(PROPS)
REQUIRED = SCHEMA["required"]
LINE = re.compile(DEFS["line"]["pattern"])
HTTPS = re.compile(DEFS["https"]["pattern"])
LOGIN = re.compile(DEFS["login"]["pattern"])
TAG = re.compile(PROPS["tags"]["items"]["pattern"])
RECEIPT_PATH = re.compile(PROPS["proof"]["properties"]["receipt"]["pattern"])
SOURCE = re.compile(PROPS["proof"]["properties"]["source"]["pattern"])
ID = re.compile(r"[a-z0-9-]{2,40}")
KIT = re.compile(r"openwizdev/OpenWiz@[0-9a-f]{40}")
DATE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")
CLONE_TIMEOUT = 300

FALSE_VERIFIED_FIX = "drop status to listed, or add the proof"
RECEIPT_KEYS = {"receipt"}
SKILL_KEYS = {"source", "check"}
TOKEN_LINE = "pass token: no login or token passed through the driver"
HEADER = ["listing", "host", "driver", "kit", "harness", "model", "date", "run by"]
VERSION_LINE = "pass version: openwiz:records v<N>, and the schema is driver v1"
PASS_LINES = [
    (VERSION_LINE, re.compile(r"pass version: openwiz:records v[1-9][0-9]{0,8}, and the schema is driver v1")),
    *((line, re.compile(re.escape(line))) for line in (
        "pass start: the run posted builder status note <note>",
        "pass wake: the run edited builder status note <note>",
        "pass stop: the run ended, and a wake after it is refused",
        TOKEN_LINE,
        "Result: 5 of 5 pass",
    )),
]
PRIVATE = [
    ("a token", re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|glpat-[A-Za-z0-9_-]{20,}"
                           r"|xox[abposr]-[A-Za-z0-9-]{10,}|sk-[A-Za-z0-9_-]{16,}|AIza[0-9A-Za-z_-]{30,}"
                           r"|npm_[A-Za-z0-9]{30,}|(?:AKIA|ASIA)[0-9A-Z]{16}|eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.)")),
    ("a token", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----|[A-Za-z][A-Za-z0-9+.-]*://[^/\s:@]+:[^/\s@]+@")),
    ("a token", re.compile(r"(?i)\b(?:password|passwd|secret|api[_-]?key|access[_-]?key|private[_-]?key|client[_-]?secret"
                           r"|auth[_-]?token|access[_-]?token)\b\s*[:=]\s*\S|\bbearer\s+[A-Za-z0-9._~+/-]{16,}")),
    ("a private id", re.compile(r"\bthr_[A-Za-z0-9]|\b(?:proj|prj|mch|usr|acct|auto|sess?|sbx)_[A-Za-z0-9]"
                                r"|\bcr_[0-9a-fA-F]{8}-[0-9a-fA-F]{4}"
                                r"|\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b")),
    ("a machine path", re.compile(r"(?<![\w.~%/-])/(?:home|Users|root|tmp|var/folders|private/var)/"
                                  r"|(?<![A-Za-z0-9])[A-Za-z]:\\")),
]


SHOWN = re.compile(r"[A-Za-z0-9._-]{1,100}")
UNREFERENCED_FIX = "fix it to the contract's receipt, or remove it"


def private(text):
    return next((label for label, pattern in PRIVATE if pattern.search(text)), None)


def shown(text, what="name"):
    """A path part or key as a diagnostic may print it: plain characters and nothing private-looking, else hidden."""
    return text if isinstance(text, str) and SHOWN.fullmatch(text) and not private(text) else f"<hidden {what}>"


def shown_path(path):
    return "/".join(shown(part) for part in path.split("/"))


class Failures(list):
    def add(self, path, problem, fix):
        self.append(f"{shown_path(path)}: {problem}; fix: {fix}")


def worktree_files(root):
    files = {}
    for top in ("listings", "receipts"):
        base = root / top
        if base.is_symlink() or (base.exists() and not base.is_dir()):
            files[top] = None
            continue
        for path in sorted(base.rglob("*")) if base.exists() else []:
            rel = path.relative_to(root).as_posix()
            if path.is_symlink() or not (path.is_dir() or path.is_file()):
                files[rel] = None
            elif path.is_file():
                files[rel] = path.read_bytes()
    return files


def git(root, *args, binary=False):
    result = subprocess.run(["git", "-C", str(root), *args], capture_output=True)
    if result.returncode:
        raise SystemExit(f"git {' '.join(args)}: {result.stderr.decode(errors='replace').strip()}")
    return result.stdout if binary else result.stdout.decode()


def commit_files(root, rev):
    files = {}
    listing = git(root, "ls-tree", "-r", "-z", "--full-tree", rev, "--", "listings", "receipts", binary=True)
    for entry in filter(None, listing.split(b"\0")):
        meta, path = entry.decode("utf-8", "surrogateescape").split("\t", 1)
        mode, kind, sha = meta.split()
        files[path] = git(root, "cat-file", "blob", sha, binary=True) if mode in ("100644", "100755") else None
    return files


def parse_json(data):
    repeated = []

    def pairs(items):
        seen = {}
        for key, value in items:
            if key in seen:
                repeated.append(key)
            seen[key] = value
        return seen

    def constant(name):
        raise ValueError(f"{name} is not standard JSON")

    value = json.loads(data.decode("utf-8"), object_pairs_hook=pairs, parse_constant=constant)
    for text in [*strings(value), *repeated]:
        try:
            text.encode("utf-8")
        except UnicodeEncodeError:
            raise ValueError("an escaped unpaired surrogate, \\ud800 to \\udfff, is not UTF-8 text") from None
    return value, repeated


def is_line(value):
    return isinstance(value, str) and LINE.fullmatch(value) is not None


def check_https(failures, path, name, value):
    if not (isinstance(value, str) and HTTPS.fullmatch(value)):
        failures.add(path, f'"{name}" must be an https:// URL as the contract\'s URLs section says',
                     "write https://, a DNS host, an optional port, then a path, query or fragment of printable ASCII")


def check_fields(failures, path, data):
    for key in sorted(set(data) - FIELDS):
        failures.add(path, f'unknown field "{shown(key, "key")}"', f"remove it: listing.v1 has only {', '.join(sorted(FIELDS))}")
    for key in REQUIRED:
        if key not in data:
            failures.add(path, f'missing field "{key}"', "add it")
    line_fix = "write it on one line: at least one character, no line break or control character"
    for key in ("name", "plugs_into", "login"):
        if key in data and not is_line(data[key]):
            failures.add(path, f'"{key}" must be one line', line_fix)
    if "summary" in data and not (is_line(data["summary"]) and len(data["summary"]) <= PROPS["summary"]["maxLength"]):
        failures.add(path, '"summary" must be one line of at most 140 characters', "shorten it to one line")
    tags = data.get("tags")
    if not (isinstance(tags, list) and PROPS["tags"]["minItems"] <= len(tags) <= PROPS["tags"]["maxItems"]
            and all(isinstance(t, str) and TAG.fullmatch(t) for t in tags) and len(set(tags)) == len(tags)):
        tags = None
        if "tags" in data:
            failures.add(path, '"tags" must be 1 to 8 tags, each lowercase letters, digits and hyphens, none twice',
                         "fix the tags")
    if "url" in data:
        check_https(failures, path, "url", data["url"])
    if "publisher" in data and not (isinstance(data["publisher"], str) and LOGIN.fullmatch(data["publisher"])):
        failures.add(path, '"publisher" must be a GitHub login', "write your GitHub login")
    for key in ("stage", "status"):
        if key in data and data[key] not in PROPS[key]["enum"]:
            failures.add(path, f'"{key}" must be ' + " or ".join(f'"{v}"' for v in PROPS[key]["enum"]), "use one of them")
    if "links" in data:
        links = data["links"]
        if not (isinstance(links, list) and links):
            failures.add(path, '"links" must be a list of at least one {"label", "url"}', "fix links")
        else:
            for n, link in enumerate(links):
                if not (isinstance(link, dict) and set(link) == {"label", "url"}):
                    failures.add(path, f'"links[{n}]" must hold exactly "label" and "url"', "fix the link")
                    continue
                if not is_line(link["label"]):
                    failures.add(path, f'"links[{n}].label" must be one line', line_fix)
                check_https(failures, path, f"links[{n}].url", link["url"])
    if data.get("stage") == "being-built" and "links" not in data:
        failures.add(path, '"being-built" needs links, the first one its public pull request or ticket',
                     "add links with the work link first")
    return tags


def check_proof(failures, path, listing_id, data, tags):
    status, proof = data.get("status"), data.get("proof")
    if status == "listed" and "proof" in data:
        failures.add(path, '"listed" has no proof', "remove proof, or set status to verified")
        return None
    if status != "verified":
        return None
    if proof is None:
        failures.add(path, '"verified" needs proof', FALSE_VERIFIED_FIX)
        return None
    if not (isinstance(proof, dict) and proof and set(proof) <= RECEIPT_KEYS | SKILL_KEYS):
        failures.add(path, '"proof" must be an object of receipt, or source and check', FALSE_VERIFIED_FIX)
        return None
    if "receipt" in proof and not (isinstance(proof["receipt"], str) and RECEIPT_PATH.fullmatch(proof["receipt"])):
        failures.add(path, '"proof.receipt" must be receipts/<id>/<date>-<commit>.txt', FALSE_VERIFIED_FIX)
        return None
    if "source" in proof and not (isinstance(proof["source"], str) and SOURCE.fullmatch(proof["source"])):
        failures.add(path, '"proof.source" must be <owner>/<repo>@<40-hex commit>', FALSE_VERIFIED_FIX)
        return None
    if "check" in proof and not is_line(proof["check"]):
        failures.add(path, '"proof.check" must be one command line', FALSE_VERIFIED_FIX)
        return None
    if tags is None:
        return None
    tags = set(tags)
    needed = (RECEIPT_KEYS if tags & {"driver", "harness"} else set()) | (SKILL_KEYS if "skill" in tags else set())
    if not needed:
        failures.add(path, '"verified" has no tag with a test (driver, harness or skill), so it cannot be verified',
                     FALSE_VERIFIED_FIX)
        return None
    if set(proof) != needed:
        failures.add(path, f"proof must hold exactly {', '.join(sorted(needed))} for its tags, "
                     f"not {', '.join(sorted(proof))}", FALSE_VERIFIED_FIX)
        return None
    if "receipt" in proof and PurePosixPath(proof["receipt"]).parts[1] != listing_id:
        failures.add(path, f'"proof.receipt" must be under receipts/{shown(listing_id)}/', FALSE_VERIFIED_FIX)
        return None
    return proof


def check_receipt(failures, path, listing_id, data, fix):
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        failures.add(path, "is not UTF-8 text", fix)
        return None
    lines = text.split("\n")
    if "\r" in text:
        failures.add(path, "must end its lines in \\n alone, not \\r\\n", fix)
        return None
    if not text.endswith("\n") or len(lines) != 15:
        failures.add(path, "must be exactly 14 lines, each ending in a newline", fix)
        return None
    header = {}
    for n, key in enumerate(HEADER, 1):
        prefix, line = f"# {key}: ", lines[n - 1]
        value = line[len(prefix):] if line.startswith(prefix) else None
        valid = value is not None and is_line(value) and not value.startswith(" ") and {
            "listing": lambda v: v == listing_id,
            "driver": lambda v: SOURCE.fullmatch(v),
            "kit": lambda v: KIT.fullmatch(v),
            "date": valid_date,
            "run by": lambda v: LOGIN.fullmatch(v),
        }.get(key, bool)(value)
        if not valid:
            shape = f'"# listing: {shown(listing_id)}"' if key == "listing" else f'"{prefix}<{key}>" as the contract says'
            failures.add(path, f"line {n} must be {shape}", fix)
        else:
            header[key] = value
    for n, (shape, pattern) in enumerate(PASS_LINES, 9):
        if not pattern.fullmatch(lines[n - 1]):
            failures.add(path, f'line {n} must be exactly "{shape}": only a 5 of 5 kit run verifies', fix)
            break
    if "date" in header and "driver" in header:
        name = f"{header['date']}-{header['driver'].rsplit('@', 1)[1][:12]}.txt"
        if PurePosixPath(path).name != name:
            failures.add(path, f"file name must be {name}, from its # date: and # driver: lines", fix)
    return header.get("date")


def valid_date(value):
    try:
        return DATE.fullmatch(value) and datetime.date.fromisoformat(value)
    except ValueError:
        return False


def scan_private(failures, path, data, referenced):
    public = "remove it: listings and receipts are public"
    where_fix = (lambda label: (f"{label} ({public})", FALSE_VERIFIED_FIX)) if referenced else (lambda label: (label, public))
    label = private(path)
    if label:
        failures.add(path, f"the file's path holds what looks like {label}", "rename it: file names are public")
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        failures.add(path, "is not UTF-8 text", "save it as UTF-8")
        return
    texts = [(f"line {n}", line) for n, line in enumerate(text.split("\n"), 1)
             if not (path.startswith("receipts/") and n == 13 and line == TOKEN_LINE)]
    if path.startswith("listings/"):
        try:
            texts += [("a decoded value", value) for value in strings(parse_json(data)[0])]
        except ValueError:
            pass
    found = set()
    for where, value in texts:
        for label, pattern in PRIVATE:
            if label not in found and pattern.search(value):
                found.add(label)
                failures.add(path, *where_fix(f"{where} holds what looks like {label}"))


def strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for key, item in value.items():
            yield key
            yield from strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from strings(item)


def check_tree(files):
    failures, listings, referenced = Failures(), [], set()
    for path, data in files.items():
        if data is None:
            failures.add(path, "must be a regular file or folder, not a link or submodule",
                         "replace it with the file itself")
        elif path.startswith("receipts/") and not RECEIPT_PATH.fullmatch(path):
            failures.add(path, "is not at receipts/<id>/<date>-<commit>.txt", "move it, or remove it")
    for path in sorted(p for p, d in files.items() if p.startswith("listings/") and d is not None):
        name = PurePosixPath(path)
        if len(name.parts) != 2 or name.suffix != ".json":
            failures.add(path, "listings/ holds only <id>.json files", "move or rename it")
            continue
        listing_id = name.stem
        if not ID.fullmatch(listing_id):
            failures.add(path, f'the file name "{shown(listing_id)}" is not a valid id', "rename it to 2 to 40 "
                         "lowercase letters, digits and hyphens")
        try:
            data, repeated = parse_json(files[path])
        except (UnicodeDecodeError, ValueError) as error:
            failures.add(path, f"is not standard JSON in UTF-8 ({str(error).splitlines()[0]})", "fix the JSON")
            continue
        if repeated:
            for key in repeated:
                failures.add(path, f'key "{shown(key, "key")}" appears twice', "keep one")
            continue
        if not isinstance(data, dict):
            failures.add(path, "must be one JSON object", "fix the JSON")
            continue
        tags = check_fields(failures, path, data)
        proof = check_proof(failures, path, listing_id, data, tags)
        if proof is not None and "receipt" in proof:
            if files.get(proof["receipt"]) is None:
                failures.add(path, f'"proof.receipt" names {shown_path(proof["receipt"])}, which is not there',
                             FALSE_VERIFIED_FIX)
            else:
                referenced.add(proof["receipt"])
        listings.append((listing_id, data, proof))
    dates = {}
    for path in sorted(p for p, d in files.items() if RECEIPT_PATH.fullmatch(p) and d is not None):
        fix = FALSE_VERIFIED_FIX if path in referenced else UNREFERENCED_FIX
        dates[path] = check_receipt(failures, path, PurePosixPath(path).parts[1], files[path], fix)
    entries = []
    for listing_id, data, proof in listings:
        entry = {**data, "id": listing_id}
        if proof is not None:
            entry["proof"] = {}
            if "receipt" in proof and proof["receipt"] in referenced:
                entry["proof"]["receipt"] = {"path": proof["receipt"], "date": dates[proof["receipt"]]}
            if "source" in proof:
                repo, commit = proof["source"].split("@")
                entry["proof"]["skill"] = {"source": proof["source"], "check": proof["check"],
                                           "url": f"https://github.com/{repo}/tree/{commit}"}
        entries.append(entry)
    for path, data in files.items():
        if data is not None:
            scan_private(failures, path, data, path in referenced)
    return failures, entries


def report(failures, entries, files):
    if failures:
        print("\n".join(failures))
        return 1
    receipts = sum(1 for p in files if p.startswith("receipts/"))
    print(f"check: ok, {len(entries)} listings and {receipts} receipts checked")
    return 0


def changed_receipts(root, base, rev):
    failures = Failures()
    diff = git(root, "diff", "--name-status", "--no-renames", base, *([rev] if rev else []), "--", "receipts")
    for line in diff.splitlines():
        status, path = line.split("\t", 1)
        if status != "A":
            failures.add(path, "a merged receipt never changes, and is never deleted",
                         "restore it, and add a new receipt for a new run")
    return failures


def cmd_check(args):
    root = Path.cwd()
    files = commit_files(root, args.rev) if args.rev else worktree_files(root)
    failures, entries = check_tree(files)
    if args.base:
        failures += changed_receipts(root, args.base, args.rev)
    return report(failures, entries, files)


def refuse(message):
    print(f"index: {message}", file=sys.stderr)
    return 1


def cmd_index(args):
    root = Path.cwd()
    if git(root, "rev-parse", "--show-prefix").strip():
        return refuse("run it from the checkout's root")
    if git(root, "status", "--porcelain", "--untracked-files=all", "--ignored=matching", "--ignore-submodules=none"):
        return refuse("the checkout has uncommitted, untracked or ignored files; commit or remove them")
    if subprocess.run(["git", "-C", str(root), "rev-parse", "--verify", "--quiet", "refs/remotes/origin/main"],
                      capture_output=True).returncode:
        return refuse("the checkout has no origin/main; fetch it")
    if subprocess.run(["git", "-C", str(root), "merge-base", "--is-ancestor", "HEAD", "refs/remotes/origin/main"],
                      capture_output=True).returncode:
        return refuse("HEAD is not origin/main or an ancestor of it; take the index only from WizMarket main")
    commit = git(root, "rev-parse", "HEAD").strip()
    files = commit_files(root, commit)
    failures, entries = check_tree(files)
    if failures:
        print("\n".join(failures))
        return refuse("HEAD does not pass check")
    for entry in entries:
        receipt = entry.get("proof", {}).get("receipt")
        if receipt:
            receipt["url"] = f"https://github.com/openwizdev/WizMarket/blob/{commit}/{receipt['path']}"
    index = {"contract": "listing.v1", "commit": commit, "listings": sorted(entries, key=lambda e: e["id"])}
    sys.stdout.buffer.write((json.dumps(index, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode())
    return 0


OUTPUT_LINES = 40
SANDBOX = ["unshare", "--pid", "--fork", "--kill-child", "--mount-proc", "--net", "--ipc", "--uts", "--"]


def run_limited(command, cwd, env, timeout, output):
    """Run with a deadline, output to a file, and end the whole process group on every exit."""
    with open(output, "ab") as out:
        process = subprocess.Popen(command, cwd=cwd, env=env, stdin=subprocess.DEVNULL, stdout=out, stderr=out,
                                   start_new_session=True)
    try:
        return process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        return None
    finally:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass
        process.wait()


INERT = re.compile(r"(?<=:):|(?<=#)#(?=\[)")


def inert(line):
    line = "".join(c if c.isprintable() and c != "\\" else f"\\x{ord(c):02x}" for c in line)
    return INERT.sub(lambda m: f"\\x{ord(m[0]):02x}", line)


def show_output(listing_id, output):
    with open(output, "rb") as f:
        f.seek(max(0, os.path.getsize(output) - 65536))
        lines = f.read().decode("utf-8", "replace").splitlines()[-OUTPUT_LINES:]
    if lines:
        print(f"skill {listing_id}: the last {len(lines)} lines it printed:")
    for line in lines:
        print("  | " + inert(line))


def cmd_skill(args):
    root, listing_id = Path.cwd(), args.id
    if not ID.fullmatch(listing_id):
        print(f"skill {shown(listing_id)}: refused, not a listing id")
        return 1
    path = f"listings/{listing_id}.json"
    files = {p: d for p, d in worktree_files(root).items() if p == path or p.startswith(f"receipts/{listing_id}/")}
    if path not in files:
        print(f"skill {listing_id}: refused, {path} is not there")
        return 1
    failures, entries = check_tree(files)
    if failures:
        print("\n".join(failures))
        return 1
    skill = entries[0].get("proof", {}).get("skill")
    if not skill:
        print(f"skill {listing_id}: refused, it is not a verified skill with a source and a check")
        return 1
    as_user, sandbox = [], []
    if args.isolate:
        if os.geteuid() != 0:
            print(f"skill {listing_id}: refused, --isolate runs as root and drops to {args.isolate}")
            return 1
        user = pwd.getpwnam(args.isolate)
        as_user = ["setpriv", f"--reuid={user.pw_uid}", f"--regid={user.pw_gid}", "--clear-groups",
                   "--no-new-privs", "--"]
        sandbox = SANDBOX
    repo, commit = skill["source"].split("@")
    path_env = os.environ.get("PATH", os.defpath)
    with tempfile.TemporaryDirectory() as tmp:
        home, src, output = Path(tmp) / "home", Path(tmp) / "src", Path(tmp) / "output"
        home.mkdir()
        src.mkdir()
        if args.isolate:
            os.chmod(tmp, 0o711)
            for folder in (home, src):
                os.chown(folder, user.pw_uid, user.pw_gid)
        env = {"PATH": path_env, "HOME": str(home)}
        git_env = {**env, "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull, "GIT_TERMINAL_PROMPT": "0"}
        git_cmd = [*as_user, "git", "-c", "credential.helper=", "-c", "core.hooksPath=" + os.devnull,
                   "-c", "advice.detachedHead=false"]
        steps = [[*git_cmd, "clone", "--quiet", "--no-checkout", "--", f"{args.source_base}/{repo}", str(src)],
                 [*git_cmd, "-C", str(src), "checkout", "--quiet", "--detach", commit, "--"]]
        acquired = all(run_limited(step, tmp, git_env, CLONE_TIMEOUT, output) == 0 for step in steps)
        head = subprocess.run([*git_cmd, "-C", str(src), "rev-parse", "HEAD"], env=git_env, capture_output=True,
                              text=True, timeout=CLONE_TIMEOUT).stdout.strip() if acquired else ""
        if head != commit:
            print(f"skill {listing_id}: refused, commit {commit} is not in https://github.com/{repo}")
            return 1
        output.write_bytes(b"")
        code = run_limited([*sandbox, *as_user, "/bin/sh", "-c", skill["check"]], src, env, args.timeout, output)
        show_output(listing_id, output)
    if code is None:
        print(f"skill {listing_id}: refused, the check did not finish in {args.timeout} seconds")
        return 1
    if code:
        print(f"skill {listing_id}: refused, the check exited {code} at {commit}")
        return 1
    print(f"skill {listing_id}: pass, the check exited 0 at {commit}")
    return 0


def cmd_changed_skills(args):
    root = Path.cwd()
    diff = git(root, "diff", "--name-only", "--no-renames", "--diff-filter=AMT", args.base, "HEAD", "--", "listings")
    for path in diff.splitlines():
        name = PurePosixPath(path)
        if len(name.parts) != 2 or name.suffix != ".json" or not ID.fullmatch(name.stem):
            continue
        try:
            proof = parse_json((root / path).read_bytes())[0].get("proof")
            if not (isinstance(proof, dict) and "source" in proof):
                continue
        except (OSError, ValueError, AttributeError):
            pass
        print(name.stem)
    return 0


def main(argv):
    parser = argparse.ArgumentParser(prog="check.py", description="WizMarket's listing.v1 check")
    commands = parser.add_subparsers(dest="command", required=True)
    check = commands.add_parser("check", help="check every listing and receipt")
    check.add_argument("--base", help="also refuse a receipt edited or deleted since this commit")
    check.add_argument("--rev", help="check this commit's tree, every git entry included, not the working tree")
    check.set_defaults(run=cmd_check)
    commands.add_parser("index", help="print the registry index at HEAD").set_defaults(run=cmd_index)
    skill = commands.add_parser("skill", help="run a skill listing's check at its pinned commit")
    skill.add_argument("id")
    skill.add_argument("--timeout", type=int, default=600, help="seconds the check may run (default 600)")
    skill.add_argument("--isolate", metavar="USER", help="run as root: acquire the source and run the check as USER, "
                       "the check in new process, network, IPC and host-name namespaces")
    skill.add_argument("--source-base", default="https://github.com", help=argparse.SUPPRESS)
    skill.set_defaults(run=cmd_skill)
    changed = commands.add_parser("changed-skills", help="print skill listings added or changed since a commit")
    changed.add_argument("base")
    changed.set_defaults(run=cmd_changed_skills)
    args = parser.parse_args(argv)
    return args.run(args)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
