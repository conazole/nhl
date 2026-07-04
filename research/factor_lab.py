#!/usr/bin/env python3
"""factor lab · evaluate current + candidate 1p u2.5 factors on the
point-in-time season dataset (research/season_dataset.csv).

methodology:
  - chronological split: train < 2026-02-15, holdout >= 2026-02-15.
    a factor is credible only if its direction holds in BOTH halves.
  - wilson 95% CIs on every bucket · a bucket whose CI straddles the
    base rate is noise, not signal.
  - candidates additionally get stratified checks against combined r5
    (does the candidate separate WITHIN r5 strata, or is it just r5 in
    disguise?).

usage:
    python3 research/factor_lab.py
"""

import csv, os, math, sys
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
# single-season lab (the jun 2026 v4.3 decision tool). datasets are per-season
# files since jul 2026; point CSV_PATH at the season under study. for
# multi-season work use drift_lab.py / backtest_variants.py.
CSV_PATH = os.path.join(HERE, "season_dataset_2025.csv")
SPLIT_DATE = "2026-02-15"


def wilson(w, n, z=1.96):
    if n == 0:
        return (0.0, 0.0)
    p = w / n
    den = 1 + z * z / n
    c = (p + z * z / (2 * n)) / den
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return (100 * (c - half), 100 * (c + half))


def load():
    rows = []
    with open(CSV_PATH) as f:
        for r in csv.DictReader(f):
            r["u25"] = int(r["u25"])
            rows.append(r)
    return rows


def fnum(v):
    try:
        return float(v)
    except (ValueError, TypeError):
        return None


def bucket_table(rows, bucket_fn, title, order=None, min_n=15):
    """print train/holdout/full u2.5 rate per bucket."""
    train = [r for r in rows if r["date"] < SPLIT_DATE]
    hold = [r for r in rows if r["date"] >= SPLIT_DATE]

    def agg(sub):
        d = defaultdict(lambda: [0, 0])
        for r in sub:
            b = bucket_fn(r)
            if b is None:
                continue
            d[b][0] += r["u25"]
            d[b][1] += 1
        return d

    at, ah, af = agg(train), agg(hold), agg(rows)
    keys = order if order else sorted(af.keys(), key=str)
    print(f"\n── {title} ──")
    print(f"{'bucket':<22} {'train':>16} {'holdout':>16} {'full':>16}  {'full 95% ci':>14}")
    for k in keys:
        if k not in af or af[k][1] < min_n:
            continue
        parts = []
        for d in (at, ah, af):
            w, n = d.get(k, [0, 0])
            parts.append(f"{100*w/n:5.1f}% ({n:>4})" if n else f"{'·':>12}")
        lo, hi = wilson(af[k][0], af[k][1])
        print(f"{str(k):<22} {parts[0]:>16} {parts[1]:>16} {parts[2]:>16}  [{lo:4.1f},{hi:5.1f}]")


def main():
    rows = load()
    base_w = sum(r["u25"] for r in rows)
    print(f"dataset: {len(rows)} games | base rate {100*base_w/len(rows):.1f}% "
          f"| train < {SPLIT_DATE} ({sum(1 for r in rows if r['date'] < SPLIT_DATE)}) "
          f"| holdout ({sum(1 for r in rows if r['date'] >= SPLIT_DATE)})")
    reg = [r for r in rows if r["phase"] == "reg"]
    po = [r for r in rows if r["phase"] == "po"]
    print(f"regular: {sum(r['u25'] for r in reg)}/{len(reg)} = {100*sum(r['u25'] for r in reg)/len(reg):.1f}% | "
          f"playoff: {sum(r['u25'] for r in po)}/{len(po)} = {100*sum(r['u25'] for r in po)/len(po):.1f}%")

    # ════ current factors ════
    def b_r5(r):
        v = fnum(r["comb_r5_pct"])
        if v is None:
            return None
        return "≥80" if v >= 80 else ("70-79" if v >= 70 else "<70")
    bucket_table(rows, b_r5, "factor 1: combined r5 (de-duped)", ["≥80", "70-79", "<70"])

    def b_r15(r):
        v = fnum(r["comb_r15_pct"])
        if v is None:
            return None
        return "≥70" if v >= 70 else "<70"
    bucket_table(rows, b_r15, "factor 2: combined r15 (de-duped)", ["≥70", "<70"])

    def b_goalie(r):
        return r["goalie_pair"] or None
    bucket_table(rows, b_goalie, "factor 3: goalie pair (starts-share to date, ACTUAL starters)",
                 ["starter+starter", "starter+tandem", "backup+starter",
                  "tandem+tandem", "backup+tandem", "backup+backup"])

    def b_line(r):
        v = fnum(r["total_line"])
        if v is None:
            return None
        return "≤5.5" if v <= 5.5 else ("6.0" if v <= 6.0 else "≥6.5")
    bucket_table(rows, b_line, "factor 4: total line (logged subset, feb 26+)", ["≤5.5", "6.0", "≥6.5"])

    # ════ candidate: start time (user hypothesis: early games go under) ════
    def b_start(r):
        v = fnum(r["et_hour"])
        if v is None:
            return None
        if v < 14:
            return "matinee <2pm et"
        if v < 17:
            return "afternoon 2-5pm"
        if v < 19.5:
            return "early eve 5-7:30"
        return "prime ≥7:30pm"
    bucket_table(rows, b_start, "candidate: start time (et)",
                 ["matinee <2pm et", "afternoon 2-5pm", "early eve 5-7:30", "prime ≥7:30pm"])

    def b_wk_start(r):
        v = fnum(r["et_hour"])
        wk = r["weekend"]
        if v is None or wk == "":
            return None
        early = v < 17
        return f"{'wknd' if wk == '1' else 'wkday'} {'day' if early else 'night'}"
    bucket_table(rows, b_wk_start, "candidate: weekend × day/night (day = before 5pm et)",
                 ["wknd day", "wknd night", "wkday day", "wkday night"])

    def b_weekend(r):
        return {"1": "weekend", "0": "weekday"}.get(r["weekend"])
    bucket_table(rows, b_weekend, "candidate: weekend vs weekday", ["weekend", "weekday"])

    dow_names = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
    bucket_table(rows, lambda r: dow_names[int(r["dow"])] if r["dow"] != "" else None,
                 "candidate: day of week", dow_names)

    # ════ candidate: venue-specific form ════
    def b_venue(r):
        hv, av = fnum(r["home_venue_r10"]), fnum(r["away_road_r10"])
        if hv is None or av is None:
            return None
        m = (hv + av) / 2
        return "≥80" if m >= 80 else ("70-79" if m >= 70 else ("60-69" if m >= 60 else "<60"))
    bucket_table(rows, b_venue, "candidate: venue-split form (avg of home-at-home, away-on-road r10)",
                 ["≥80", "70-79", "60-69", "<60"])

    # ════ candidate: rolling 1p scoring environment ════
    def b_env_g(r):
        v = fnum(r["env_1p_goals"])
        if v is None:
            return None
        if v <= 1.6:
            return "≤1.6"
        if v <= 2.0:
            return "1.6-2.0"
        if v <= 2.4:
            return "2.0-2.4"
        return ">2.4"
    bucket_table(rows, b_env_g, "candidate: rolling 1p goals/game (r15 both teams)",
                 ["≤1.6", "1.6-2.0", "2.0-2.4", ">2.4"])

    def b_env_sog(r):
        v = fnum(r["env_1p_sog"])
        if v is None:
            return None
        if v <= 17:
            return "≤17"
        if v <= 19:
            return "17-19"
        if v <= 21:
            return "19-21"
        return ">21"
    bucket_table(rows, b_env_sog, "candidate: rolling 1p sog/game (r15)", ["≤17", "17-19", "19-21", ">21"])

    def b_env_xg(r):
        v = fnum(r["env_1p_xg"])
        if v is None:
            return None
        if v <= 1.4:
            return "≤1.4"
        if v <= 1.7:
            return "1.4-1.7"
        return ">1.7"
    bucket_table(rows, b_env_xg, "candidate: rolling 1p xg/game (r15)", ["≤1.4", "1.4-1.7", ">1.7"])

    # ════ candidate: rest / b2b ════
    def b_b2b(r):
        ar, hr = fnum(r["away_rest"]), fnum(r["home_rest"])
        if ar is None or hr is None:
            return None
        if ar == 1 and hr == 1:
            return "both b2b"
        if ar == 1 or hr == 1:
            return "one b2b"
        return "both rested"
    bucket_table(rows, b_b2b, "candidate: back-to-back", ["both b2b", "one b2b", "both rested"])

    # ════ candidate: h2h last meeting ════
    def b_h2h(r):
        v = r["h2h_last_u25"]
        return {"1": "last h2h under", "0": "last h2h over"}.get(v)
    bucket_table(rows, b_h2h, "candidate: last h2h meeting 1p result", ["last h2h under", "last h2h over"])

    # ════ regime: month ════
    bucket_table(rows, lambda r: r["date"][:7], "regime check: by month")

    # ════ stratified: candidates within r5 strata (incremental signal?) ════
    print("\n══ stratified checks (candidate within combined-r5 strata) ══")
    for strat_name, strat_fn in [("r5 <70", lambda r: (fnum(r["comb_r5_pct"]) or -1) < 70 and fnum(r["comb_r5_pct"]) is not None),
                                 ("r5 ≥70", lambda r: (fnum(r["comb_r5_pct"]) or -1) >= 70)]:
        sub = [r for r in rows if strat_fn(r)]
        bucket_table(sub, b_start, f"start time | {strat_name}",
                     ["matinee <2pm et", "afternoon 2-5pm", "early eve 5-7:30", "prime ≥7:30pm"])
        bucket_table(sub, b_env_g, f"rolling 1p goals | {strat_name}",
                     ["≤1.6", "1.6-2.0", "2.0-2.4", ">2.4"])
        bucket_table(sub, b_venue, f"venue form | {strat_name}", ["≥80", "70-79", "60-69", "<60"])

    # ════ v4.2 reconstruction on the lines subset ════
    print("\n══ v4.2 score reconstruction (lines subset only) ══")
    lined = [r for r in rows if fnum(r["total_line"]) is not None]
    print(f"games with lines: {len(lined)}")

    def v42_conf(r):
        v5, v15 = fnum(r["comb_r5_pct"]), fnum(r["comb_r15_pct"])
        pair = r["goalie_pair"]
        line = fnum(r["total_line"])
        if v5 is None or v15 is None or not pair:
            return None
        f5 = 2 if v5 >= 80 else (1 if v5 >= 70 else 0)
        f15 = 1 if v15 >= 70 else 0
        if r["phase"] == "po":
            fg = 2  # v4.2 playoff override: named goalies = starters
        elif pair == "starter+starter":
            fg = 2
        elif pair in ("starter+tandem", "backup+starter"):
            fg = 1
        elif pair == "tandem+tandem":
            fg = 0
        else:
            fg = -1
        fl = 1 if line <= 5.5 else (0 if line <= 6.0 else -1)
        c = max(0, f5 + f15 + fg + fl)
        return min(c, 3) if r["phase"] == "po" and False else c  # g1 flag not in dataset; noted

    d = defaultdict(lambda: [0, 0])
    for r in lined:
        c = v42_conf(r)
        if c is None:
            continue
        d[c][0] += r["u25"]
        d[c][1] += 1
    print(f"{'conf':>4} {'w/n':>10} {'rate':>7}  {'95% ci':>14}")
    for c in sorted(d, reverse=True):
        w, n = d[c]
        lo, hi = wilson(w, n)
        print(f"{c:>4} {f'{w}/{n}':>10} {100*w/n:6.1f}%  [{lo:4.1f},{hi:5.1f}]")
    picks = [(d[c][0], d[c][1]) for c in d if c >= 4]
    pw, pn = sum(x[0] for x in picks), sum(x[1] for x in picks)
    if pn:
        lo, hi = wilson(pw, pn)
        print(f"\nreconstructed pick tier (≥4): {pw}/{pn} = {100*pw/pn:.1f}%  [{lo:.1f},{hi:.1f}]")

    # conf-4 composition: which factor mixes make up 4/6, and how do they hit?
    print("\nconf-4 composition (lines subset):")
    comp = defaultdict(lambda: [0, 0])
    for r in lined:
        v5, v15 = fnum(r["comb_r5_pct"]), fnum(r["comb_r15_pct"])
        pair, line = r["goalie_pair"], fnum(r["total_line"])
        if v5 is None or v15 is None or not pair:
            continue
        f5 = 2 if v5 >= 80 else (1 if v5 >= 70 else 0)
        f15 = 1 if v15 >= 70 else 0
        fg = 2 if (r["phase"] == "po" or pair == "starter+starter") else (
            1 if pair in ("starter+tandem", "backup+starter") else (
                0 if pair == "tandem+tandem" else -1))
        fl = 1 if line <= 5.5 else (0 if line <= 6.0 else -1)
        if max(0, f5 + f15 + fg + fl) == 4:
            key = f"r5={f5} r15={f15} g={fg} l={fl}"
            comp[key][0] += r["u25"]
            comp[key][1] += 1
    for k in sorted(comp, key=lambda x: -comp[x][1]):
        w, n = comp[k]
        if n >= 3:
            print(f"  {k:<24} {w}/{n} = {100*w/n:.0f}%")


if __name__ == "__main__":
    main()
