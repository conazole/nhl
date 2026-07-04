#!/usr/bin/env python3
"""drift lab · multi-season stability check for every shipped v4.3 rule.

loads every research/season_dataset_{year}.csv and reports, with numbers:
  1. league environment per season (base rate, 1p goals, day-game volume)
  2. each factor's edge per season (r5, day game, goalie pair, total line)
  3. trailing-2-season vs earlier-seasons z-test per rule (drift monitor)
  4. threshold re-learning on recent windows (r5 cutoffs, day cutoff hour,
     line gate)
  5. the shipped v4.3 score replayed per season: pick-tier rate + parlay sim
  6. playoff g1 cap: g1 vs g2+ per season
  7. espn-stored-total vs logged-line agreement (how much to trust the
     historical line columns)

a |z| >= 2 flag is a research prompt, not a switch · small recent windows lie.

usage:
    python3 research/drift_lab.py
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
    # playoff game number within each series (same derivation as backtest_v43)
    series = defaultdict(list)
    for r in rows:
        if r["phase"] == "po":
            series[(r["season"], tuple(sorted([r["away"], r["home"]])))].append(r)
    for games in series.values():
        games.sort(key=lambda x: x["date"])
        for i, g in enumerate(games, 1):
            g["game_num"] = i
    return rows


def rate_str(w, n):
    if not n:
        return "     ·      "
    lo, hi = wilson(w, n)
    return f"{100*w/n:5.1f}% ({n:>4}) [{lo:4.1f},{hi:5.1f}]"


def per_season_table(rows, bucket_fn, title, order, min_n=10):
    seasons = sorted({r["season"] for r in rows})
    print(f"\n── {title} ──")
    hdr = f"{'bucket':<18}" + "".join(f"{s}-{str(s+1)[2:]:>2}".rjust(15) for s in seasons) + f"{'all':>15}"
    print(hdr)
    agg = defaultdict(lambda: defaultdict(lambda: [0, 0]))
    for r in rows:
        b = bucket_fn(r)
        if b is None:
            continue
        agg[b][r["season"]][0] += r["u25"]
        agg[b][r["season"]][1] += 1
        agg[b]["all"][0] += r["u25"]
        agg[b]["all"][1] += 1
    for b in order:
        if b not in agg:
            continue
        cells = []
        for s in seasons + ["all"]:
            w, n = agg[b][s]
            cells.append(f"{100*w/n:5.1f}% ({n:>4})" if n >= min_n else f"{'·':>13}")
        print(f"{str(b):<18}" + "".join(c.rjust(15) for c in cells))
    return agg


def gap_z(rows_a, rows_b, bucket_fn, hi_bucket, lo_bucket):
    """u2.5-rate gap (hi minus lo bucket) in two disjoint row sets + z of the
    difference of gaps."""
    def gap(rows):
        w_hi = n_hi = w_lo = n_lo = 0
        for r in rows:
            b = bucket_fn(r)
            if b == hi_bucket:
                w_hi += r["u25"]; n_hi += 1
            elif b == lo_bucket:
                w_lo += r["u25"]; n_lo += 1
        if not n_hi or not n_lo:
            return None, None
        p_hi, p_lo = w_hi / n_hi, w_lo / n_lo
        var = p_hi * (1 - p_hi) / n_hi + p_lo * (1 - p_lo) / n_lo
        return (p_hi - p_lo), var
    g_a, v_a = gap(rows_a)
    g_b, v_b = gap(rows_b)
    if g_a is None or g_b is None:
        return g_a, g_b, None
    z = (g_a - g_b) / math.sqrt(v_a + v_b) if (v_a + v_b) > 0 else 0.0
    return g_a, g_b, z


# ── factor bucket functions (mirror the shipped v4.3 definitions) ──

def b_r5(r):
    v = fnum(r["comb_r5_pct"])
    if v is None:
        return None
    return "≥80" if v >= 80 else ("70-79" if v >= 70 else "<70")


def b_day(r):
    v = fnum(r["et_hour"])
    if v is None:
        return None
    return "day <5pm et" if v < 17 else "night"


def b_goalie(r):
    return r["goalie_pair"] or None


def line_of(r):
    """line of record for research: logged line (pinnacle consensus) when a
    run recorded one, else the espn stored median."""
    v = fnum(r["total_line"])
    if v is None:
        v = fnum(r["espn_total"])
    return v


def b_line(r):
    v = line_of(r)
    if v is None:
        return None
    return "≤5.5" if v <= 5.5 else ("6.0" if v <= 6.0 else "≥6.5")


GOALIE_43 = {"starter+starter": 2, "starter+tandem": 1, "backup+starter": 1,
             "tandem+tandem": -1, "backup+tandem": 0, "backup+backup": -1}


def v43_score(r):
    """the shipped v4.3 confidence, computed from dataset columns.
    line factor uses line_of(); a game with no line scores 0 (the production
    line-missing cap is operational, not statistical)."""
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
        fg = GOALIE_43.get(pair)
        if fg is None:
            return None
    line = line_of(r)
    fl = 0 if line is None else (1 if line <= 5.5 else (0 if line <= 6.0 else -1))
    total = max(0, f5 + day + fg + fl)
    if r["phase"] == "po" and r.get("game_num") == 1:
        total = min(total, 3)
    return total


def main():
    rows = load_all()
    seasons = sorted({r["season"] for r in rows})
    print(f"drift lab · {len(rows)} games across seasons {seasons}")

    # ── 1. environment per season ──
    print("\n══ 1. league environment per season ══")
    print(f"{'season':<10}{'games':>7}{'u2.5':>8}{'1p gpg':>8}{'reg u2.5':>10}{'po u2.5':>9}{'day games':>11}{'day share':>11}")
    for s in seasons:
        sub = [r for r in rows if r["season"] == s]
        reg = [r for r in sub if r["phase"] == "reg"]
        po = [r for r in sub if r["phase"] == "po"]
        day = [r for r in sub if b_day(r) == "day <5pm et"]
        gpg = sum(int(r["total_1p"]) for r in sub) / len(sub)
        print(f"{s}-{str(s+1)[2:]:<6}{len(sub):>7}"
              f"{100*sum(r['u25'] for r in sub)/len(sub):>7.1f}%"
              f"{gpg:>8.2f}"
              f"{100*sum(r['u25'] for r in reg)/len(reg):>9.1f}%"
              f"{(100*sum(r['u25'] for r in po)/len(po)) if po else 0:>8.1f}%"
              f"{len(day):>11}{100*len(day)/len(sub):>10.1f}%")

    # ── 2. factors per season ──
    print("\n══ 2. factor edge per season ══")
    per_season_table(rows, b_r5, "combined r5 (de-duped, both teams 5+ games)", ["≥80", "70-79", "<70"])
    per_season_table(rows, b_day, "day game (<5pm et)", ["day <5pm et", "night"])
    per_season_table(rows, b_goalie, "goalie pair (starts-share to date)",
                     ["starter+starter", "starter+tandem", "backup+starter",
                      "tandem+tandem", "backup+tandem", "backup+backup"])
    per_season_table(rows, b_line, "total line (logged else espn median)", ["≤5.5", "6.0", "≥6.5"])

    # ── 3. trailing-2-season vs earlier z-tests ──
    print("\n══ 3. drift monitor · trailing 2 seasons vs earlier seasons ══")
    trail = [r for r in rows if r["season"] >= seasons[-2]] if len(seasons) >= 2 else rows
    early = [r for r in rows if r["season"] < seasons[-2]] if len(seasons) >= 2 else []
    checks = [
        ("r5 ≥80 vs <70", b_r5, "≥80", "<70"),
        ("day vs night", b_day, "day <5pm et", "night"),
        ("s+s vs rest", lambda r: ("s+s" if r["goalie_pair"] == "starter+starter"
                                   else ("rest" if r["goalie_pair"] else None)), "s+s", "rest"),
        ("line ≤5.5 vs ≥6.5", b_line, "≤5.5", "≥6.5"),
    ]
    print(f"{'rule':<22}{'trailing-2 gap':>16}{'earlier gap':>14}{'z':>7}   verdict")
    for name, fn, hi, lo in checks:
        g_t, g_e, z = gap_z(trail, early, fn, hi, lo)
        gt = f"{100*g_t:+.1f}pp" if g_t is not None else "·"
        ge = f"{100*g_e:+.1f}pp" if g_e is not None else "·"
        zs = f"{z:+.2f}" if z is not None else "·"
        verdict = ("investigate" if z is not None and abs(z) >= 2 else "stable")
        print(f"{name:<22}{gt:>16}{ge:>14}{zs:>7}   {verdict}")

    # ── 4. threshold re-learning ──
    print("\n══ 4. threshold re-learning ══")
    print("\nr5 high-bucket cutoff · u2.5 rate above cutoff, per window")
    windows = [("all seasons", rows)]
    if len(seasons) >= 2:
        windows.append((f"last 2 ({seasons[-2]}+)", trail))
    windows.append((f"last 1 ({seasons[-1]})", [r for r in rows if r["season"] == seasons[-1]]))
    cuts = [70, 75, 80, 85, 90]
    print(f"{'window':<20}" + "".join(f"≥{c}".rjust(14) for c in cuts))
    for name, sub in windows:
        cells = []
        for c in cuts:
            g = [r for r in sub if (fnum(r["comb_r5_pct"]) or -1) >= c]
            w = sum(r["u25"] for r in g)
            cells.append(f"{100*w/len(g):5.1f}% ({len(g):>4})" if len(g) >= 20 else f"{'·':>12}")
        print(f"{name:<20}" + "".join(x.rjust(14) for x in cells))

    print("\nday-game cutoff hour (et) · u2.5 rate for starts before the hour")
    hours = [14, 15, 16, 17, 18, 19]
    print(f"{'window':<20}" + "".join(f"<{h}:00".rjust(14) for h in hours))
    for name, sub in windows:
        cells = []
        for h in hours:
            g = [r for r in sub if fnum(r["et_hour"]) is not None and fnum(r["et_hour"]) < h]
            w = sum(r["u25"] for r in g)
            cells.append(f"{100*w/len(g):5.1f}% ({len(g):>4})" if len(g) >= 20 else f"{'·':>12}")
        print(f"{name:<20}" + "".join(x.rjust(14) for x in cells))

    print("\ntotal-line buckets per window (line of record else espn median)")
    print(f"{'window':<20}" + "".join(b.rjust(16) for b in ["≤5.5", "6.0", "6.5", "≥7.0"]))
    def b_line4(r):
        v = line_of(r)
        if v is None:
            return None
        if v <= 5.5:
            return "≤5.5"
        if v <= 6.0:
            return "6.0"
        if v <= 6.5:
            return "6.5"
        return "≥7.0"
    for name, sub in windows:
        agg = defaultdict(lambda: [0, 0])
        for r in sub:
            b = b_line4(r)
            if b:
                agg[b][0] += r["u25"]
                agg[b][1] += 1
        cells = []
        for b in ["≤5.5", "6.0", "6.5", "≥7.0"]:
            w, n = agg[b]
            cells.append(f"{100*w/n:5.1f}% ({n:>4})" if n >= 20 else f"{'·':>13}")
        print(f"{name:<20}" + "".join(x.rjust(16) for x in cells))

    # ── 5. shipped v4.3 per season ──
    print("\n══ 5. shipped v4.3 score replayed per season ══")
    print(f"{'season':<10}{'scored':>8}{'pick ≥4':>22}{'tier ≥5':>22}{'parlay nights':>16}{'excluded (no r5)':>18}")
    for s in seasons:
        sub = [r for r in rows if r["season"] == s]
        scored = [(r, v43_score(r)) for r in sub]
        got = [(r, c) for r, c in scored if c is not None]
        skipped = len(sub) - len(got)
        p4 = [(r, c) for r, c in got if c >= 4]
        p5 = [(r, c) for r, c in got if c >= 5]
        w4 = sum(r["u25"] for r, _ in p4)
        w5 = sum(r["u25"] for r, _ in p5)
        by_date = defaultdict(list)
        for r, c in got:
            by_date[r["date"]].append((c, fnum(r["comb_r5_pct"]) or 0, r["u25"]))
        pw = pl = 0
        for games in by_date.values():
            picks = [g for g in games if g[0] >= 4]
            if len(picks) < 2:
                continue
            top2 = sorted(picks, key=lambda x: (-x[0], -x[1]))[:2]
            if all(g[2] for g in top2):
                pw += 1
            else:
                pl += 1
        r4 = rate_str(w4, len(p4)) if p4 else "·"
        r5s = rate_str(w5, len(p5)) if p5 else "·"
        par = f"{pw}-{pl} ({100*pw/(pw+pl):.0f}%)" if pw + pl else "·"
        print(f"{s}-{str(s+1)[2:]:<6}{len(got):>8}{r4:>28}{r5s:>28}{par:>16}{skipped:>14}")

    # combined pick tier
    all_scored = [(r, v43_score(r)) for r in rows]
    p4 = [(r, c) for r, c in all_scored if c is not None and c >= 4]
    w4 = sum(r["u25"] for r, _ in p4)
    lo, hi = wilson(w4, len(p4))
    print(f"\nall seasons pick tier ≥4: {w4}/{len(p4)} = {100*w4/len(p4):.1f}% [{lo:.1f},{hi:.1f}]")

    # ── 6. playoff g1 cap ──
    print("\n══ 6. playoff g1 vs g2+ per season ══")
    print(f"{'season':<10}{'g1':>22}{'g2+':>22}")
    for s in seasons:
        po = [r for r in rows if r["season"] == s and r["phase"] == "po"]
        g1 = [r for r in po if r.get("game_num") == 1]
        g2 = [r for r in po if (r.get("game_num") or 0) >= 2]
        c1 = rate_str(sum(r["u25"] for r in g1), len(g1)) if g1 else "·"
        c2 = rate_str(sum(r["u25"] for r in g2), len(g2)) if g2 else "·"
        print(f"{s}-{str(s+1)[2:]:<6}{c1:>28}{c2:>28}")

    # ── 7. espn totals vs logged lines ──
    print("\n══ 7. espn stored total vs logged line (overlap subset) ══")
    both = [(fnum(r["total_line"]), fnum(r["espn_total"])) for r in rows
            if fnum(r["total_line"]) is not None and fnum(r["espn_total"]) is not None]
    if both:
        exact = sum(1 for a, b in both if a == b)
        d = [abs(a - b) for a, b in both]
        print(f"overlap n={len(both)} · exact match {100*exact/len(both):.1f}% · "
              f"mean |delta| {sum(d)/len(d):.3f} · off by ≥1.0: {sum(1 for x in d if x >= 1)}")
        # which bucket flips: does espn move a game across the 6.0/6.5 gate?
        flips = sum(1 for a, b in both
                    if (a <= 6.0) != (b <= 6.0) or (a <= 5.5) != (b <= 5.5))
        print(f"gate-bucket disagreements (would change f_line): {flips} "
              f"({100*flips/len(both):.1f}%)")
    else:
        print("no overlap rows")


if __name__ == "__main__":
    main()
