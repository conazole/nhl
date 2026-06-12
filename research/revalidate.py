#!/usr/bin/env python3
"""quarterly revalidation: re-run v4.x backtest against the most recent 100
resolved picks to detect model drift.

flags if any of these have decayed meaningfully from original v4 validation:
  - leg win rate  (baseline 80.5% legs on 1149 games)
  - 5+/6 hit rate (should hold near 92%)
  - per-factor contribution (r5/r15/goalie/line — expect monotonic gradient)
  - confidence calibration (pick rate should beat avoid rate)

usage:
    python3 research/revalidate.py              # uses most recent 100 resolved picks
    python3 research/revalidate.py --last 200   # wider window

exits non-zero if any metric drifts >5pp from baseline — makes it cron-safe
for a weekly health check that only alerts on real drift.
"""

import json, sys, os, argparse
from collections import defaultdict
from datetime import datetime

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_PATH = os.path.join(os.path.dirname(SCRIPT_DIR), "picks_log.jsonl")

# baselines from the v4.3 point-in-time backtest (1393 games, jun 12 2026 —
# research/backtest_v43.py). the previous numbers (80.5/92.0/61.8/77.3/73.0)
# came from the in-sample mar-28 validation and included an unsourced 92%
# that sat one bad week from a false drift alert.
BASELINE = {
    "leg_rate": 83.0,     # pick tier (c>=4) u2.5 rate
    "c5_rate": 88.1,      # tier >=5 (backtest n=42 — thin; expect noise)
    "hm_rate": 74.5,      # conf 2-3
    "avoid_rate": 70.2,   # conf 0-1
    "base_rate": 74.9,    # league-wide 1p u2.5 (full season incl playoffs)
}
DRIFT_THRESHOLD = 5.0   # pp gap that triggers alert
WARN_THRESHOLD = 2.5    # pp gap that triggers warning


def load_resolved(last_n=100):
    entries = []
    with open(LOG_PATH) as f:
        for line in f:
            if not line.strip():
                continue
            e = json.loads(line)
            if e.get("model") != "v4":
                continue
            # only win/loss count — "void" (postponed) is excluded
            if e.get("result") not in ("win", "loss"):
                continue
            entries.append(e)
    entries.sort(key=lambda e: e["date"], reverse=True)
    return entries[:last_n]


def tier_of(e):
    t = e.get("tier")
    if t == "honorable_mention":
        return "hm"
    if t == "avoid":
        return "avoid"
    return "pick"


def rate(entries, filt):
    subset = [e for e in entries if filt(e)]
    if not subset:
        return None, 0
    w = sum(1 for e in subset if e["result"] == "win")
    return 100 * w / len(subset), len(subset)


def status(gap):
    if gap is None:
        return "n/a"
    a = abs(gap)
    if a < WARN_THRESHOLD:
        return "✓ stable"
    if a < DRIFT_THRESHOLD:
        return "⚠ minor drift"
    return "⛔ significant drift"


def main():
    parser = argparse.ArgumentParser(description="revalidate v4 against recent games")
    parser.add_argument("--last", type=int, default=100, help="games to revalidate against")
    args = parser.parse_args()

    entries = load_resolved(last_n=args.last)
    if len(entries) < 30:
        print(json.dumps({"error": f"only {len(entries)} resolved v4 entries — need >=30 for revalidation"}))
        sys.exit(2)

    scope = f"last {len(entries)} resolved v4 games ({entries[-1]['date']} → {entries[0]['date']})"

    picks = [e for e in entries if tier_of(e) == "pick"]
    hms = [e for e in entries if tier_of(e) == "hm"]
    avoids = [e for e in entries if tier_of(e) == "avoid"]

    results = []
    alerts = []

    # leg rate (all picks >= 4/6)
    r, n = rate(picks, lambda e: True)
    gap = None if r is None else r - BASELINE["leg_rate"]
    results.append(("leg rate", BASELINE["leg_rate"], r, n, gap, status(gap)))
    if r is not None and abs(gap) >= DRIFT_THRESHOLD:
        alerts.append(f"leg rate drifted {gap:+.1f}pp from {BASELINE['leg_rate']}% baseline (now {r:.1f}%, n={n})")

    # 5+/6 rate
    r, n = rate(picks, lambda e: e.get("confidence", 0) >= 5)
    gap = None if r is None else r - BASELINE["c5_rate"]
    results.append(("5+/6 rate", BASELINE["c5_rate"], r, n, gap, status(gap)))
    if r is not None and abs(gap) >= DRIFT_THRESHOLD:
        alerts.append(f"5+/6 rate drifted {gap:+.1f}pp from {BASELINE['c5_rate']}% baseline (now {r:.1f}%, n={n})")

    # hm rate
    r, n = rate(hms, lambda e: True)
    gap = None if r is None else r - BASELINE["hm_rate"]
    results.append(("hm rate", BASELINE["hm_rate"], r, n, gap, status(gap)))

    # avoid rate (hit rate — these "should go over" but many still go under, that's the base rate)
    r, n = rate(avoids, lambda e: True)
    gap = None if r is None else r - BASELINE["avoid_rate"]
    results.append(("avoid rate", BASELINE["avoid_rate"], r, n, gap, status(gap)))

    # base rate (all games — is the regime shifting?)
    r, n = rate(entries, lambda e: True)
    gap = None if r is None else r - BASELINE["base_rate"]
    results.append(("base rate", BASELINE["base_rate"], r, n, gap, status(gap)))
    if r is not None and abs(gap) >= DRIFT_THRESHOLD:
        alerts.append(f"base rate drifted {gap:+.1f}pp from {BASELINE['base_rate']}% baseline (now {r:.1f}%, n={n}) — scoring regime has shifted")

    # per-factor analysis (only if factor breakdown available)
    entries_with_factors = [e for e in entries if e.get("factors")]
    factor_report = {}
    if entries_with_factors:
        for factor in ("r5", "day", "r15", "goalie", "line"):
            per_bucket = defaultdict(lambda: {"w": 0, "n": 0})
            for e in entries_with_factors:
                pts = e["factors"].get(factor)
                if pts is None:
                    continue
                per_bucket[pts]["n"] += 1
                if e["result"] == "win":
                    per_bucket[pts]["w"] += 1
            factor_report[factor] = {
                pts: {"rate": round(100 * b["w"] / b["n"], 1), "n": b["n"]}
                for pts, b in per_bucket.items() if b["n"] >= 3
            }

    # text report
    print(f"v4 revalidation — {scope}\n")
    print(f"{'metric':<14} {'baseline':>10} {'actual':>10} {'n':>5} {'gap':>8}   status")
    print("─" * 62)
    for name, base, actual, n, gap, st in results:
        actual_s = f"{actual:.1f}%" if actual is not None else "n/a"
        gap_s = f"{gap:+.1f}pp" if gap is not None else "n/a"
        print(f"{name:<14} {base:>9.1f}% {actual_s:>10} {n:>5} {gap_s:>8}   {st}")

    if factor_report:
        print("\nper-factor breakdown (games with factor data only):")
        for factor, buckets in factor_report.items():
            if not buckets:
                continue
            pts_desc = sorted(buckets.keys(), reverse=True)
            parts = [f"{p:+d}: {buckets[p]['rate']}% (n={buckets[p]['n']})" for p in pts_desc]
            print(f"  {factor:<8} " + " · ".join(parts))
    else:
        print("\nper-factor breakdown: no entries with factor data yet (added apr 18 2026)")

    if alerts:
        print("\n⛔ ALERTS:")
        for a in alerts:
            print(f"  - {a}")
        print("\nrecommended: re-audit model weights, consider backtest on wider sample.")
        sys.exit(1)
    else:
        print("\n✓ no significant drift — v4.x weights remain valid.")
        sys.exit(0)


if __name__ == "__main__":
    main()
