#!/usr/bin/env python3
"""head-to-head backtest of scoring variants on the multi-season point-in-time
datasets · successor to backtest_v43.py (which compared v4.2 vs v4.3 on the
2025-26 season only).

variants:
  v4.3      r5(0/1/2) + day(0/1) + goalie(-1..+2) + line(-1..+1)   pick ≥4
  no-day    r5 + goalie + line (/5 scale)                          pick ≥3
  no-goalie r5 + day + line (/4 scale)                             pick ≥3
  line-only the line factor alone (≤5.5 = the "pick")
  v4.2-r15  r5 + r15(0/1) + goalie + line                          pick ≥4

all variants share the playoff goalie override + g1 cap. games without any
line score f_line = 0 (the production line-missing cap is operational, not
statistical). output per variant: full gradient with wilson CIs, tier rates
at several thresholds, per-season pick rate at the designated threshold, and
a parlay-night simulation (top-2 by conf,r5).

usage:
    python3 research/backtest_variants.py
"""

import csv, glob, math, os
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))


def wilson(w, n, z=1.96):
    if n == 0:
        return (0.0, 0.0)
    p = w / n
    den = 1 + z * z / n
    c = (p + z * z / (2 * n)) / den
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return (100 * (c - half), 100 * (c + half))


def fnum(v):
    try:
        return float(v)
    except (ValueError, TypeError):
        return None


def load_all():
    rows = []
    for path in sorted(glob.glob(os.path.join(HERE, "season_dataset_*.csv"))):
        with open(path) as f:
            for r in csv.DictReader(f):
                r["u25"] = int(r["u25"])
                r["season"] = int(r.get("season") or path.split("_")[-1][:4])
                rows.append(r)
    series = defaultdict(list)
    for r in rows:
        if r["phase"] == "po":
            series[(r["season"], tuple(sorted([r["away"], r["home"]])))].append(r)
    for games in series.values():
        games.sort(key=lambda x: x["date"])
        for i, g in enumerate(games, 1):
            g["game_num"] = i
    return rows


GOALIE_PTS = {"starter+starter": 2, "starter+tandem": 1, "backup+starter": 1,
              "tandem+tandem": 0, "backup+tandem": -1, "backup+backup": -1}


def line_of(r):
    v = fnum(r["total_line"])
    if v is None:
        v = fnum(r.get("espn_total"))
    return v


def parts(r):
    """factor components, or None if the row lacks required features."""
    v5 = fnum(r["comb_r5_pct"])
    pair = r["goalie_pair"]
    if v5 is None or (not pair and r["phase"] != "po"):
        return None
    f5 = 2 if v5 >= 80 else (1 if v5 >= 70 else 0)
    eh = fnum(r["et_hour"])
    day = 1 if (eh is not None and eh < 17) else 0
    if r["phase"] == "po":
        fg = 2
    else:
        fg = GOALIE_PTS.get(pair)
        if fg is None:
            return None
    ln = line_of(r)
    fl = 0 if ln is None else (1 if ln <= 5.5 else (0 if ln <= 6.0 else -1))
    v15 = fnum(r["comb_r15_pct"])
    f15 = 1 if (v15 is not None and v15 >= 70) else 0
    return f5, day, fg, fl, f15


def cap(r, total):
    total = max(0, total)
    if r["phase"] == "po" and r.get("game_num") == 1:
        total = min(total, 3)
    return total


VARIANTS = {
    "v4.3":      {"score": lambda p: p[0] + p[1] + p[2] + p[3], "pick": 4},
    "no-day":    {"score": lambda p: p[0] + p[2] + p[3],        "pick": 3},
    "no-goalie": {"score": lambda p: p[0] + p[1] + p[3],        "pick": 3},
    "v4.2-r15":  {"score": lambda p: p[0] + p[4] + p[2] + p[3], "pick": 4},
}


def evaluate(rows, name, spec):
    print(f"\n════ {name} (pick ≥{spec['pick']}) ════")
    seasons = sorted({r["season"] for r in rows})
    d = defaultdict(lambda: [0, 0])
    by_date = defaultdict(list)
    per_season = defaultdict(lambda: [0, 0])
    for r in rows:
        p = parts(r)
        if p is None:
            continue
        c = cap(r, spec["score"](p))
        d[c][0] += r["u25"]
        d[c][1] += 1
        by_date[r["date"]].append((c, fnum(r["comb_r5_pct"]) or 0, r["u25"]))
        if c >= spec["pick"]:
            per_season[r["season"]][0] += r["u25"]
            per_season[r["season"]][1] += 1

    print(f"{'conf':>4} {'w/n':>12} {'rate':>7} {'95% ci':>15}")
    for c in sorted(d, reverse=True):
        w, n = d[c]
        lo, hi = wilson(w, n)
        print(f"{c:>4} {f'{w}/{n}':>12} {100*w/n:6.1f}% [{lo:4.1f},{hi:5.1f}]")

    for thresh in sorted({spec["pick"] - 1, spec["pick"], spec["pick"] + 1}):
        w = sum(d[c][0] for c in d if c >= thresh)
        n = sum(d[c][1] for c in d if c >= thresh)
        if n:
            lo, hi = wilson(w, n)
            mark = " ← pick tier" if thresh == spec["pick"] else ""
            print(f"  tier ≥{thresh}: {w}/{n} = {100*w/n:.1f}% [{lo:.1f},{hi:.1f}]{mark}")

    cells = []
    for s in seasons:
        w, n = per_season[s]
        cells.append(f"{s}: {100*w/n:.1f}% ({n})" if n else f"{s}: ·")
    print("  per season: " + " · ".join(cells))

    pw = pl = 0
    for games in by_date.values():
        picks = [g for g in games if g[0] >= spec["pick"]]
        if len(picks) < 2:
            continue
        top2 = sorted(picks, key=lambda x: (-x[0], -x[1]))[:2]
        if all(g[2] for g in top2):
            pw += 1
        else:
            pl += 1
    if pw + pl:
        print(f"  parlay sim: {pw}-{pl} ({100*pw/(pw+pl):.1f}%) on "
              f"{pw+pl}/{len(by_date)} slates ({100*(pw+pl)/len(by_date):.0f}%)")


def main():
    rows = load_all()
    print(f"variant backtest · {len(rows)} games · seasons "
          f"{sorted({r['season'] for r in rows})}")
    base_w = sum(r["u25"] for r in rows)
    print(f"base rate {100*base_w/len(rows):.1f}%")

    for name, spec in VARIANTS.items():
        evaluate(rows, name, spec)

    # line factor alone, for scale
    print("\n════ line-only (for scale) ════")
    for b, lo_, hi_ in (("≤5.5", -1, 5.5), ("6.0", 5.5, 6.0), ("≥6.5", 6.0, 99)):
        pool = [r for r in rows if line_of(r) is not None and lo_ < line_of(r) <= hi_]
        w = sum(r["u25"] for r in pool)
        if pool:
            l, h = wilson(w, len(pool))
            print(f"  {b:<5} {w}/{len(pool)} = {100*w/len(pool):.1f}% [{l:.1f},{h:.1f}]")


if __name__ == "__main__":
    main()
