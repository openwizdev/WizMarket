"""Score and time the xn-- host rule.

Each case is a host the check should pass or fail. The score is how many
match. The timer repeats the same hosts and reports microseconds per call.
Run: python3 -I check/bench_idna.py
"""
import importlib.util
import time
from pathlib import Path


def load_check():
    path = Path(__file__).resolve().with_name("check.py")
    spec = importlib.util.spec_from_file_location("wizmarket_check", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


idn_host = load_check().idn_host

# (expected, host). expected is True when the host is allowed.
CASES = (
    ("utsav and bangla", True, "xn--d5b4e9a9e.xn--54b7fta0cc"),
    ("malayalam chillu", True, "xn--6yccdefg.example.com"),
    ("buecher", True, "xn--bcher-kva.example.com"),
    ("nko letter", True, "xn--lsb.example.com"),
    ("arabic letter after Unicode 3.2", True, "xn--ngb60d.example.com"),
    ("hebrew mark after Unicode 3.2", True, "xn--tcb5g.example.com"),
    ("cherokee mv, casefold keeps it", True, "xn--lce.example.com"),
    ("arabic letter and arabic-indic digit", True, "xn--ngb6i.example.com"),
    ("emoji", False, "xn--e28h.example.com"),
    ("control character", False, "xn--a.example.com"),
    ("zwj", False, "xn--1ug.example.com"),
    ("arabic with a bengali letter", False, "xn--ngb28p.example.com"),
    ("cherokee small letter, casefold maps it", False, "xn--tce.example.com"),
    ("old hangul jamo", False, "xn--hk9a.example.com"),
    ("unassigned", False, "xn--mce.example.com"),
    ("capital that casefold maps", False, "xn--wma.example.com"),
    ("leading combining mark", False, "xn--z0b.example.com"),
    ("variation selector", False, "xn--cd36e.example.com"),
    ("nko lajanyalan", False, "xn--ytb.example.com"),
)


def evaluate():
    missed = []
    for name, expected, host in CASES:
        if idn_host(host) != expected:
            missed.append(name)
    return missed


def bench(rounds=2000):
    started = time.perf_counter()
    for _ in range(rounds):
        for _, _, host in CASES:
            idn_host(host)
    elapsed = time.perf_counter() - started
    calls = rounds * len(CASES)
    return calls, elapsed


def main():
    missed = evaluate()
    passed = len(CASES) - len(missed)
    calls, elapsed = bench()
    print(f"eval: {passed}/{len(CASES)} pass")
    if missed:
        print("missed: " + ", ".join(missed))
    print(f"bench: {calls} calls in {elapsed:.3f}s, {elapsed / calls * 1e6:.2f} us/call")
    return 0 if not missed else 1


if __name__ == "__main__":
    raise SystemExit(main())
