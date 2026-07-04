#!/usr/bin/env python3
"""emit model_params.json · the parameter loop.

loads every research/season_dataset_{year}.csv, replays the shipped scoring
policy over all of it, and writes one machine-generated file holding every
number the live scripts and docs quote: policy constants (factor cutoffs,
point maps, thresholds, caps), measured hit rates with wilson CIs, and a
validated-through stamp. run_analysis.py, format_output.py, review.py,
revalidate.py, and season_review.py read it with hardcoded fallbacks; the
docs defer to it for every volatile number.

the emitter never re-fits policy · POLICY below is the shipped model, stated
once. re-learning thresholds is research/drift_lab.py's job, and a policy
change is a versioned model change, made by hand, with evidence.

usage:
    python3 research/emit_params.py                # writes ../model_params.json
    python3 research/emit_params.py --dry-run      # print, no write
"""

import csv, glob, json, math, os, argparse
from datetime import date
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
OUT = os.path.join(ROOT, "model_params.json")

# ── the shipped policy, stated once ──
POLICY = {
    "model": "v4",
    "model_version": "v4.3.1",
    "pick_threshold": 4,
    "hm_threshold": 2,
    "g1_cap": 3,
    "min_window_games": 5,
    "factors": {
        "r5": {"hi": 80, "mid": 70},
        "day_cutoff_et": 17,
        "goalie_pts": {"starter+starter": 2, "starter+tandem": 1,
                       "backup+starter": 1, "tandem+tandem": 0,
                       "backup+tandem": -1, "backup+backup": -1},
        "line": {"plus": 5.5, "zero": 6.0},
    },
}


def wilson(w, n, z=1.96):
    if n == 0:
        return (0.0, 0.0)
    p = w / n
    den = 1 + z * z / n
    c = (p + z * z / (2 * n)) / den
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return (round(100 * (c - half), 1), round(100 * (c + half), 1))


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


def line_of(r):
    v = fnum(r["total_line"])
    if v is None:
        v = fnum(r.get("espn_total"))
    return v


def score(r):
    f = POLICY["factors"]
    v5 = fnum(r["comb_r5_pct"])
    pair = r["goalie_pair"]
    if v5 is None or (not pair and r["phase"] != "po"):
        return None
    f5 = 2 if v5 >= f["r5"]["hi"] else (1 if v5 >= f["r5"]["mid"] else 0)
    eh = fnum(r["et_hour"])
    day = 1 if (eh is not None and eh < f["day_cutoff_et"]) else 0
    if r["phase"] == "po":
        fg = 2  # v4.2 playoff override: named goalie = starter
    else:
        fg = f["goalie_pts"].get(pair)
        if fg is None:
            return None
    ln = line_of(r)
    fl = 0 if ln is None else (1 if ln <= f["line"]["plus"]
                               else (0 if ln <= f["line"]["zero"] else -1))
    total = max(0, f5 + day + fg + fl)
    if r["phase"] == "po" and r.get("game_num") == 1:
        total = min(total, POLICY["g1_cap"])
    return total


def rate(pool):
    w = sum(r["u25"] for r in pool)
    n = len(pool)
    return (round(100 * w / n, 1) if n else None), n


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    rows = load_all()
    if not rows:
        raise SystemExit("no season_dataset_*.csv found · run build_dataset.py first")
    seasons = sorted({r["season"] for r in rows})

    scored = [(r, score(r)) for r in rows]
    got = [(r, c) for r, c in scored if c is not None]

    def tiers(pred):
        return [r for r, c in got if pred(c)]

    picks = tiers(lambda c: c >= POLICY["pick_threshold"])
    t5 = tiers(lambda c: c >= 5)
    hm = tiers(lambda c: POLICY["hm_threshold"] <= c < POLICY["pick_threshold"])
    avoid = tiers(lambda c: c < POLICY["hm_threshold"])

    pick_rate, pick_n = rate(picks)
    pick_ci = wilson(sum(r["u25"] for r in picks), pick_n)

    day_pool = [r for r in rows if fnum(r["et_hour"]) is not None
                and fnum(r["et_hour"]) < POLICY["factors"]["day_cutoff_et"]]
    night_pool = [r for r in rows if fnum(r["et_hour"]) is not None
                  and fnum(r["et_hour"]) >= POLICY["factors"]["day_cutoff_et"]]

    def line_bucket(r):
        v = line_of(r)
        if v is None:
            return None
        return "<=5.5" if v <= 5.5 else ("6.0" if v <= 6.0 else ">=6.5")

    line_rates = {}
    for b in ("<=5.5", "6.0", ">=6.5"):
        pool = [r for r in rows if line_bucket(r) == b]
        rt, n = rate(pool)
        line_rates[b] = {"rate": rt, "n": n}

    pair_rates = {}
    for pair in POLICY["factors"]["goalie_pts"]:
        pool = [r for r in rows if r["goalie_pair"] == pair and r["phase"] == "reg"]
        rt, n = rate(pool)
        pair_rates[pair] = {"rate": rt, "n": n}

    # parlay simulation: top-2 by (conf, r5) on nights with >=2 picks
    by_date = defaultdict(list)
    for r, c in got:
        by_date[r["date"]].append((c, fnum(r["comb_r5_pct"]) or 0, r["u25"]))
    pw = pl = 0
    for games in by_date.values():
        night_picks = [g for g in games if g[0] >= POLICY["pick_threshold"]]
        if len(night_picks) < 2:
            continue
        top2 = sorted(night_picks, key=lambda x: (-x[0], -x[1]))[:2]
        if all(g[2] for g in top2):
            pw += 1
        else:
            pl += 1

    po = [r for r in rows if r["phase"] == "po"]
    g1 = [r for r in po if r.get("game_num") == 1]
    g2p = [r for r in po if (r.get("game_num") or 0) >= 2]

    params = dict(POLICY)
    params.update({
        "watch": [
            "day factor inverted in 2023-24 (71.2% vs 73.7% night) and "
            "2024-25 (69.7% vs 75.3%) · pooled +2.0pp · re-audit after 2026-27",
            "conf-6 pooled 74.1% (n=27) · thin sample, monitor",
            "g1 cap basis: pooled g1 69.3% vs g2+ 77.0% · retire if live g1s "
            "keep tracking the pooled base rate",
            "2026-27 league changes: 84-game season, late-september opener, "
            "2 extra divisional games · verify season boundaries + day-share",
        ],
        "generated": date.today().isoformat(),
        "validated_through": max(r["date"] for r in rows),
        "seasons": seasons,
        "games_in_dataset": len(rows),
        "games_scored": len(got),
        "baselines": {
            "base_rate": rate(rows)[0],
            "pick_tier": pick_rate,
            "pick_tier_n": pick_n,
            "pick_ci": list(pick_ci),
            "tier5": rate(t5)[0],
            "tier5_n": len(t5),
            "hm": rate(hm)[0],
            "avoid": rate(avoid)[0],
            "day_rate": rate(day_pool)[0],
            "night_rate": rate(night_pool)[0],
            "line_rates": line_rates,
            "goalie_pair_rates": pair_rates,
        },
        "parlay_sim": {
            "wins": pw, "losses": pl,
            "rate": round(pw / (pw + pl), 3) if pw + pl else None,
            "nights_pct": round(100 * (pw + pl) / len(by_date), 1) if by_date else None,
        },
        "playoff": {
            "g1_rate": rate(g1)[0], "g1_n": len(g1),
            "g2plus_rate": rate(g2p)[0], "g2plus_n": len(g2p),
        },
    })

    text = json.dumps(params, indent=2)
    if args.dry_run:
        print(text)
        return
    with open(OUT, "w") as f:
        f.write(text + "\n")
    print(f"wrote {OUT}")
    print(f"  seasons {seasons} · {len(rows)} games · scored {len(got)}")
    print(f"  pick tier: {pick_rate}% (n={pick_n}, ci {pick_ci})")


if __name__ == "__main__":
    main()
