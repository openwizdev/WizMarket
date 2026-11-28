import argparse
import datetime
import json
import os
import pwd
import re
import signal
import stringprep
import subprocess
import sys
import tempfile
import unicodedata
from pathlib import Path, PurePosixPath

SCHEMA = json.loads((Path(__file__).resolve().parent.parent / "schema" / "listing.v1.json").read_text())
V2_SCHEMA = json.loads((Path(__file__).resolve().parent.parent / "schema" / "listing.v2.json").read_text())
PROPS = SCHEMA["properties"]
DEFS = SCHEMA["$defs"]
FIELDS = set(PROPS)
V2_FIELDS = set(V2_SCHEMA["properties"])
PACKAGE_SCHEMA = V2_SCHEMA["properties"]["package"]
KEY_HOST_SCHEMA = V2_SCHEMA["properties"]["key_host"]
REQUIRED = SCHEMA["required"]
LINE = re.compile(DEFS["line"]["pattern"])
HTTPS = re.compile(DEFS["https"]["pattern"])
LOGIN = re.compile(DEFS["login"]["pattern"])
TAG = re.compile(PROPS["tags"]["items"]["pattern"])
RECEIPT_PATH = re.compile(PROPS["proof"]["properties"]["receipt"]["pattern"])
SOURCE = re.compile(PROPS["proof"]["properties"]["source"]["pattern"])
ID = re.compile(r"[a-z0-9-]{2,40}")
HOST = re.compile(r"https://([^:/?#]*)")
IDN_REFUSED = (stringprep.in_table_b1, stringprep.in_table_c12, stringprep.in_table_c22,
               stringprep.in_table_c3, stringprep.in_table_c4, stringprep.in_table_c5, stringprep.in_table_c6,
               stringprep.in_table_c7, stringprep.in_table_c8, stringprep.in_table_c9)
# RFC 5892's exception list. True is PVALID; the rest are CONTEXTJ, CONTEXTO or DISALLOWED.
IDNA2008_EXCEPTION = {
    0x00DF: True, 0x03C2: True, 0x06FD: True, 0x06FE: True, 0x0F0B: True, 0x3007: True,
    0x00B7: False, 0x0375: False, 0x05F3: False, 0x05F4: False, 0x0640: False, 0x07FA: False, 0x30FB: False,
    **{cp: False for cp in (*range(0x0660, 0x066A), *range(0x06F0, 0x06FA), *range(0x3031, 0x3036))},
    0x302E: False, 0x302F: False, 0x303B: False,
}
IDNA2008_IGNORABLE = (
    (0x00AD, 0x00AD), (0x034F, 0x034F), (0x061C, 0x061C), (0x115F, 0x1160), (0x17B4, 0x17B5),
    (0x180B, 0x180F), (0x200B, 0x200F), (0x202A, 0x202E), (0x2060, 0x206F), (0x3164, 0x3164),
    (0xFE00, 0xFE0F), (0xFEFF, 0xFEFF), (0xFFA0, 0xFFA0), (0xFFF0, 0xFFF8), (0x1BCA0, 0x1BCA3),
    (0x1D173, 0x1D17A), (0xE0000, 0xE001F), (0xE0020, 0xE007F), (0xE0080, 0xE00FF),
    (0xE0100, 0xE01EF), (0xE01F0, 0xE0FFF),
)
IDNA2008_BLOCKS = ((0x20D0, 0x20FF), (0x1D100, 0x1D1FF), (0x1D200, 0x1D24F))
IDNA2008_LETTERS = {"Ll", "Lu", "Lo", "Nd", "Lm", "Mn", "Mc"}
IDN_INVISIBLE = "\u115f\u1160\u17b4\u17b5\u3002"
BIDI_RTL = {"R", "AL", "AN", "EN", "ES", "CS", "ET", "ON", "BN", "NSM"}
BIDI_LTR = {"L", "EN", "ES", "CS", "ET", "ON", "BN", "NSM"}
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


def git(root, *args, binary=False, safe=()):
    result = subprocess.run(["git", *safe, "-C", str(root), *args], capture_output=True)
    if result.returncode:
        raise SystemExit(f"git {' '.join(args)}: {result.stderr.decode(errors='replace').strip()}")
    return result.stdout if binary else result.stdout.decode()


def commit_files(root, rev, safe=()):
    files = {}
    listing = git(root, "ls-tree", "-r", "-z", "--full-tree", rev, "--", "listings", "receipts", binary=True, safe=safe)
    for entry in filter(None, listing.split(b"\0")):
        meta, path = entry.decode("utf-8", "surrogateescape").split("\t", 1)
        mode, kind, sha = meta.split()
        regular = mode in ("100644", "100755") and "/" in path
        files[path] = git(root, "cat-file", "blob", sha, binary=True, safe=safe) if regular else None
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


def idna2008_pvalid(cp):
    """RFC 5892 PVALID, using this Python's Unicode and that RFC's exception list."""
    marked = IDNA2008_EXCEPTION.get(cp)
    if marked is not None:
        return marked
    character = chr(cp)
    category = unicodedata.category(character)
    noncharacter = 0xFDD0 <= cp <= 0xFDEF or (cp & 0xFFFE) == 0xFFFE
    if category == "Cn" and not noncharacter:
        return False
    if cp in (0x200C, 0x200D):
        return False
    normalized = unicodedata.normalize("NFKC", character)
    if unicodedata.normalize("NFKC", normalized.casefold()) != character:
        return False
    if any(start <= cp <= stop for start, stop in (*IDNA2008_IGNORABLE, *IDNA2008_BLOCKS)):
        return False
    name = unicodedata.name(character, "")
    if name.startswith(("HANGUL CHOSEONG ", "HANGUL JUNGSEONG ", "HANGUL JONGSEONG ")):
        return False
    return category in IDNA2008_LETTERS


def idn_label(label):
    code = label[4:]
    try:
        text = code.encode("ascii").decode("punycode")
        if text.encode("punycode").decode("ascii") != code:
            return None
    except (ValueError, IndexError, OverflowError):
        return None
    old = unicodedata.ucd_3_2_0
    if text.isascii() or text.startswith("-") or text.endswith("-") or text[2:4] == "--":
        return None
    if old.category(text[0])[0] == "M" or unicodedata.category(text[0])[0] == "M":
        return None
    if old.normalize("NFC", text) != text or unicodedata.normalize("NFC", text) != text:
        return None
    for c in text:
        if c.isascii():
            continue
        # A.1 is unassigned in Unicode 3.2, so Nameprep's tables are not about it.
        # map_table_b2 uses str.lower(), which is not IDNA casefold: Cherokee
        # U+13F5 casefolds to itself and lower() does not.
        if stringprep.in_table_a1(c):
            if not idna2008_pvalid(ord(c)):
                return None
            continue
        if any(table(c) for table in IDN_REFUSED) or old.normalize("NFKC", c) != c or c in IDN_INVISIBLE:
            return None
        if c not in "\u00df\u03c2" and (stringprep.map_table_b2(c) != c or unicodedata.normalize("NFKC", c.casefold()) != c):
            return None
    return text


def bidi_classes(classes):
    """Bidi class, falling back when Unicode 3.2 left the code point unassigned."""
    def kind(c):
        return classes(c) or unicodedata.bidirectional(c)
    return kind


def bidi_label(text, classes):
    kinds = [classes(c) for c in text]
    rtl = kinds[0] in ("R", "AL")
    if not rtl and kinds[0] != "L":
        return False
    allowed = BIDI_RTL if rtl else BIDI_LTR
    if not all(kind in allowed for kind in kinds) or (rtl and "EN" in kinds and "AN" in kinds):
        return False
    while kinds[-1] == "NSM":
        kinds.pop()
    return kinds[-1] in (("R", "AL", "EN", "AN") if rtl else ("L", "EN"))


def idn_host(host):
    labels = host.lower().split(".")
    texts = [idn_label(label) if label.startswith("xn--") else label for label in labels]
    if None in texts:
        return False
    for classes in (unicodedata.ucd_3_2_0.bidirectional, unicodedata.bidirectional):
        kind = bidi_classes(classes)
        if any(kind(c) in ("R", "AL", "AN") for text in texts for c in text):
            if not all(bidi_label(text, kind) for text in texts):
                return False
    return True


def check_https(failures, path, name, value):
    if not (isinstance(value, str) and HTTPS.fullmatch(value) and idn_host(HOST.match(value).group(1))):
        failures.add(path, f'"{name}" must be an https:// URL as the contract\'s URLs section says',
                     "write https://, a DNS host, an optional port, then a path, query or fragment of printable ASCII")


def field_schema(prop):
    if "$ref" in prop:
        merged = dict(V2_SCHEMA["$defs"][prop["$ref"].rsplit("/", 1)[-1]])
        merged.update({key: value for key, value in prop.items() if key != "$ref"})
        return merged
    return prop


def matches(prop, value):
    prop = field_schema(prop)
    if not isinstance(value, str):
        return False
    if "maxLength" in prop and len(value) > prop["maxLength"]:
        return False
    if "pattern" in prop and re.fullmatch(prop["pattern"], value) is None:
        return False
    return "const" not in prop or value == prop["const"]


def check_v2(failures, path, data, tags):
    """A listing with package or key_host is v2. Returns its package when the block is one this check can bind."""
    if "package" not in data and "key_host" not in data:
        return None
    if tags is not None and not (set(tags) & {"driver", "harness"}):
        failures.add(path, '"package" is only for a listing tagged driver or harness',
                     "remove package and key_host, or add the driver or harness tag")
        return None
    if "package" not in data:
        failures.add(path, '"key_host" needs a package block',
                     "add the package block the driver package contract defines, or remove key_host")
        return None
    package = data["package"]
    keys = set(PACKAGE_SCHEMA["properties"])
    if not isinstance(package, dict) or set(package) != keys:
        failures.add(path, '"package" must hold exactly ' + ", ".join(sorted(keys)),
                     "use the driver package contract's package block")
        return None
    shape = [key for key in sorted(keys - {"asset_url"}) if not matches(PACKAGE_SCHEMA["properties"][key], package[key])]
    if shape:
        for key in shape:
            failures.add(path, f'"package.{key}" is not the shape the driver package contract defines',
                         "fix it to that contract's package block")
        return None
    expected = f"https://github.com/{package['repository']}/releases/download/v{package['version']}/driver.tar.gz"
    if package.get("asset_url") != expected:
        failures.add(path, '"package.asset_url" is not a release asset of the listed repository',
                     "make it the package's release asset")
        return None
    if "key_host" in data:
        host, host_keys = data["key_host"], set(KEY_HOST_SCHEMA["properties"])
        if not isinstance(host, dict) or set(host) != host_keys:
            failures.add(path, '"key_host" must hold exactly ' + ", ".join(sorted(host_keys)),
                         "use the driver package contract's key_host block")
            return None
        bad = [key for key in sorted(host_keys) if not matches(KEY_HOST_SCHEMA["properties"][key], host[key])]
        if bad:
            for key in bad:
                failures.add(path, f'"key_host.{key}" is not the shape the driver package contract defines',
                             "use an https origin, a variable name and a keychain entry, never a key")
            return None
    return package


def bind_package_receipt(failures, path, package, header):
    if not header:
        return
    driver = f"{package['repository']}@{package['commit']}"
    if "driver" in header and header["driver"] != driver:
        failures.add(path, 'the receipt\'s "# driver:" line must name the package\'s repository and commit',
                     "use a receipt for this package's repository and commit")
    kit = f"openwizdev/OpenWiz@{package['kit_commit']}"
    if "kit" in header and header["kit"] != kit:
        failures.add(path, f'the receipt\'s "# kit:" line must be "{kit}", the package\'s kit commit',
                     "use a receipt for this package's kit commit")


def check_fields(failures, path, data):
    v2 = {"package", "key_host"} & set(data)
    fields = V2_FIELDS if v2 else FIELDS
    for key in sorted(set(data) - fields):
        contract = "listing.v2" if v2 else "listing.v1"
        failures.add(path, f'unknown field "{shown(key, "key")}"',
                     f"remove it: {contract} has only {', '.join(sorted(fields))}")
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
    return header


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
        if data is None and "/" not in path:
            failures.add(path, "must be a folder, not a file, link or submodule", "make it a folder, or remove it")
        elif data is None:
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
        package = check_v2(failures, path, data, tags)
        proof = check_proof(failures, path, listing_id, data, tags)
        if proof is not None and "receipt" in proof:
            if files.get(proof["receipt"]) is None:
                failures.add(path, f'"proof.receipt" names {shown_path(proof["receipt"])}, which is not there',
                             FALSE_VERIFIED_FIX)
            else:
                referenced.add(proof["receipt"])
        listings.append((path, listing_id, data, proof, package))
    headers = {}
    for path in sorted(p for p, d in files.items() if RECEIPT_PATH.fullmatch(p) and d is not None):
        fix = FALSE_VERIFIED_FIX if path in referenced else UNREFERENCED_FIX
        headers[path] = check_receipt(failures, path, PurePosixPath(path).parts[1], files[path], fix)
    entries = []
    for path, listing_id, data, proof, package in listings:
        entry = {**data, "id": listing_id}
        if package is not None:
            entry["contract"] = "listing.v2"
            if proof is not None and "receipt" in proof and proof["receipt"] in referenced:
                bind_package_receipt(failures, path, package, headers.get(proof["receipt"]))
        if proof is not None:
            entry["proof"] = {}
            if "receipt" in proof and proof["receipt"] in referenced:
                header = headers.get(proof["receipt"]) or {}
                entry["proof"]["receipt"] = {"path": proof["receipt"], "date": header.get("date")}
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
    safe = ("-c", f"safe.directory={root}")
    files = commit_files(root, args.rev, safe) if args.rev else worktree_files(root)
    files = {p: d for p, d in files.items() if p == path or p.startswith(f"receipts/{listing_id}/")}
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
            proof = parse_json(git(root, "cat-file", "blob", f"HEAD:{path}", binary=True))[0].get("proof")
            if not (isinstance(proof, dict) and "source" in proof):
                continue
        except (SystemExit, ValueError, AttributeError):
            pass
        print(name.stem)
    return 0


def main(argv):
    parser = argparse.ArgumentParser(prog="check.py", description="WizMarket's listing check")
    commands = parser.add_subparsers(dest="command", required=True)
    check = commands.add_parser("check", help="check every listing and receipt")
    check.add_argument("--base", help="also refuse a receipt edited or deleted since this commit")
    check.add_argument("--rev", help="check this commit's tree, every git entry included, not the working tree")
    check.set_defaults(run=cmd_check)
    commands.add_parser("index", help="print the registry index at HEAD").set_defaults(run=cmd_index)
    skill = commands.add_parser("skill", help="run a skill listing's check at its pinned commit")
    skill.add_argument("id")
    skill.add_argument("--rev", help="read the listing from this commit's tree, not the working tree")
    skill.add_argument("--timeout", type=int, default=1200, help="seconds the check may run (default 1200)")
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
