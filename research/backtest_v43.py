#!/usr/bin/env python3
"""head-to-head backtest: v4.2 (current) vs v4.3 candidates on the
point-in-time season dataset.

variants:
  v4.2  = r5(0/1/2) + r15(0/1) + goalie[SS+2, S+T/B+S+1, TT 0, B+T -1, BB -1]
          + line(-1/0/+1), playoff goalie override (+2), g1 cap
  v4.3a = r5(0/1/2) + DAY(<5pm et +1) + goalie[SS+2, S+T/B+S+1, TT -1, B+T 0,
          BB -1] + line, playoff override, g1 cap     (r15 -> day swap)
  v4.3b = v4.3a but r5 <70 scores -1 instead of 0

scored on all games where r5/r15/goalie features exist. line factor uses the
logged-line subset; games without a line score f_line=0 in ALL variants (the
production line-missing cap is operational, not statistical — excluded here).

outputs per variant: confidence gradient, pick tier (>=4) hit rate + volume,
parlay-night simulation (top-2 by conf,r5).
"""

import csv, os, math
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
CSV_PATH = os.path.join(HERE, "season_dataset.csv")
SPLIT_DATE = "2026-02-15"


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


def load():
    rows = []
    with open(CSV_PATH) as f:
        for r in csv.DictReader(f):
            r["u25"] = int(r["u25"])
            rows.append(r)
    # derive playoff game-in-series: group by sorted team pair, number by date
    series = defaultdict(list)
    for r in rows:
        if r["phase"] == "po":
            series[tuple(sorted([r["away"], r["home"]]))].append(r)
    for pair, games in series.items():
        games.sort(key=lambda x: x["date"])
        for i, g in enumerate(games, 1):
            g["game_num"] = i
    return rows


GOALIE_42 = {"starter+starter": 2, "starter+tandem": 1, "backup+starter": 1,
             "tandem+tandem": 0, "backup+tandem": -1, "backup+backup": -1}
GOALIE_43 = {"starter+starter": 2, "starter+tandem": 1, "backup+starter": 1,
             "tandem+tandem": -1, "backup+tandem": 0, "backup+backup": -1}


def score(r, variant):
    v5, v15 = fnum(r["comb_r5_pct"]), fnum(r["comb_r15_pct"])
    pair = r["goalie_pair"]
    if v5 is None or v15 is None or (not pair and r["phase"] != "po"):
        return None
    f5 = 2 if v5 >= 80 else (1 if v5 >= 70 else 0)
    if variant == "v4.3b" and v5 < 70:
        f5 = -1
    f15 = 1 if v15 >= 70 else 0
    if r["phase"] == "po":
        fg = 2  # playoff override: named goalie = starter (all variants)
    else:
        fg = (GOALIE_42 if variant == "v4.2" else GOALIE_43).get(pair)
        if fg is None:
            return None
    line = fnum(r["total_line"])
    fl = 0 if line is None else (1 if line <= 5.5 else (0 if line <= 6.0 else -1))
    day = 0
    eh = fnum(r["et_hour"])
    if eh is not None and eh < 17:
        day = 1
    if variant == "v4.2":
        total = f5 + f15 + fg + fl
    else:
        total = f5 + day + fg + fl
    total = max(0, total)
    if r["phase"] == "po" and r.get("game_num") == 1:
        total = min(total, 3)
    return total


def evaluate(rows, variant):
    print(f"\n════ {variant} ════")
    d = defaultdict(lambda: [0, 0])
    train_d = defaultdict(lambda: [0, 0])
    hold_d = defaultdict(lambda: [0, 0])
    by_date = defaultdict(list)
    for r in rows:
        c = score(r, variant)
        if c is None:
            continue
        d[c][0] += r["u25"]
        d[c][1] += 1
        (train_d if r["date"] < SPLIT_DATE else hold_d)[c][0] += r["u25"]
        (train_d if r["date"] < SPLIT_DATE else hold_d)[c][1] += 1
        by_date[r["date"]].append((c, fnum(r["comb_r5_pct"]) or 0, r["u25"], r["date"]))

    print(f"{'conf':>4} {'full':>14} {'rate':>7} {'95% ci':>15} {'train':>14} {'holdout':>14}")
    for c in sorted(d, reverse=True):
        w, n = d[c]
        lo, hi = wilson(w, n)
        tw, tn = train_d.get(c, [0, 0])
        hw, hn = hold_d.get(c, [0, 0])
        ts = f"{100*tw/tn:5.1f}% ({tn:>3})" if tn else "—"
        hs = f"{100*hw/hn:5.1f}% ({hn:>3})" if hn else "—"
        print(f"{c:>4} {f'{w}/{n}':>14} {100*w/n:6.1f}% [{lo:4.1f},{hi:5.1f}] {ts:>14} {hs:>14}")

    for thresh in (4, 5):
        w = sum(d[c][0] for c in d if c >= thresh)
        n = sum(d[c][1] for c in d if c >= thresh)
        if n:
            lo, hi = wilson(w, n)
            print(f"  tier ≥{thresh}: {w}/{n} = {100*w/n:.1f}% [{lo:.1f},{hi:.1f}]")

    # parlay simulation: nights with >=2 picks, top-2 by (conf, r5)
    pw = pl = 0
    legs_w = legs_n = 0
    for date, games in by_date.items():
        picks = [g for g in games if g[0] >= 4]
        if len(picks) < 2:
            continue
        top2 = sorted(picks, key=lambda x: (-x[0], -x[1]))[:2]
        legs_w += sum(g[2] for g in top2)
        legs_n += 2
        if all(g[2] for g in top2):
            pw += 1
        else:
            pl += 1
    if pw + pl:
        print(f"  parlay nights: {pw}-{pl} ({100*pw/(pw+pl):.1f}%) | "
              f"bet legs {legs_w}/{legs_n} = {100*legs_w/legs_n:.1f}%")
    n_dates = len(by_date)
    n_parlay = pw + pl
    print(f"  volume: {n_parlay} parlay nights / {n_dates} slates ({100*n_parlay/n_dates:.0f}%)")


def main():
    rows = load()
    print(f"dataset: {len(rows)} games")
    for v in ("v4.2", "v4.3a", "v4.3b"):
        evaluate(rows, v)

    # day-factor fairness check: does v4.3a's day bonus just re-add games v4.2
    # already picked? show overlap of pick sets
    s42 = {(r["date"], r["away"], r["home"]) for r in rows if (score(r, "v4.2") or 0) >= 4}
    s43 = {(r["date"], r["away"], r["home"]) for r in rows if (score(r, "v4.3a") or 0) >= 4}
    only42, only43, both = s42 - s43, s43 - s42, s42 & s43
    def rate_of(keys):
        sub = [r for r in rows if (r["date"], r["away"], r["home"]) in keys]
        w = sum(r["u25"] for r in sub)
        return f"{w}/{len(sub)} = {100*w/len(sub):.1f}%" if sub else "n/a"
    print(f"\npick-set overlap: both {len(both)} ({rate_of(both)}) | "
          f"v4.2-only {len(only42)} ({rate_of(only42)}) | "
          f"v4.3a-only {len(only43)} ({rate_of(only43)})")


if __name__ == "__main__":
    main()
