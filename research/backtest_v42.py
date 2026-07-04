#!/usr/bin/env python3
"""backtest v4.2 playoff patches against 435-game playoff 1p sample.

derives game-in-series number from (season, round, team-pair) grouping
since the raw csv doesn't carry gameNumberOfSeries. validates:

  1. g1 u2.5 rate ≈ 63-72% (below regular-season 73% baseline) → g1 cap justified
  2. g2+ u2.5 rate ≈ 78-82% → non-g1 playoff edge is real
  3. v4.2 g1 cap: all g1s forced to HM max, regardless of other factors
"""

import csv
from collections import defaultdict

CSV_PATH = "/Users/raz/claude/nhl/research/playoff_1p_raw.csv"


def load_rows():
    rows = []
    with open(CSV_PATH) as f:
        reader = csv.DictReader(f)
        for r in reader:
            r["away_1p"] = int(r["away_1p"])
            r["home_1p"] = int(r["home_1p"])
            r["total_1p"] = int(r["total_1p"])
            r["u2.5_hit"] = int(r["u2.5_hit"])
            rows.append(r)
    return rows


def assign_game_numbers(rows):
    """group by (season, round, sorted-pair); within series sort by date; number 1..N."""
    series = defaultdict(list)
    for r in rows:
        pair = tuple(sorted([r["away"], r["home"]]))
        key = (r["season"], r["round"], pair)
        series[key].append(r)
    for key, games in series.items():
        games.sort(key=lambda x: x["date"])
        for i, g in enumerate(games, start=1):
            g["game_num"] = i
    return rows


def pct(w, n):
    return round(100.0 * w / n, 1) if n else 0.0


def summarize(label, subset):
    total = len(subset)
    hits = sum(r["u2.5_hit"] for r in subset)
    print(f"  {label:24s} n={total:4d}  hits={hits:4d}  rate={pct(hits, total):>5}%")


def main():
    rows = load_rows()
    rows = assign_game_numbers(rows)

    print("=== playoff 1p u2.5 by game-in-series ===\n")

    # overall
    summarize("all playoff games", rows)
    print()

    # by game number
    print("by game number (pooled 5 seasons):")
    for gn in range(1, 8):
        subset = [r for r in rows if r["game_num"] == gn]
        if subset:
            summarize(f"game {gn}", subset)
    print()

    # g1 vs g2+
    print("g1 vs g2+ (pooled):")
    summarize("game 1 only", [r for r in rows if r["game_num"] == 1])
    summarize("game 2+", [r for r in rows if r["game_num"] >= 2])
    print()

    # by season
    print("g1 rate by season:")
    for s in sorted(set(r["season"] for r in rows)):
        summarize(f"g1 {s}", [r for r in rows if r["game_num"] == 1 and r["season"] == s])
    print()

    print("g2+ rate by season:")
    for s in sorted(set(r["season"] for r in rows)):
        summarize(f"g2+ {s}", [r for r in rows if r["game_num"] >= 2 and r["season"] == s])
    print()

    # last 2 seasons (most relevant to current regime)
    recent = ["2023-24", "2024-25"]
    print("last 2 completed seasons (most predictive for current):")
    summarize("g1 last 2 sns", [r for r in rows if r["game_num"] == 1 and r["season"] in recent])
    summarize("g2+ last 2 sns", [r for r in rows if r["game_num"] >= 2 and r["season"] in recent])
    summarize("g4+ last 2 sns", [r for r in rows if r["game_num"] >= 4 and r["season"] in recent])
    print()

    # v4.2 patch impact simulation
    # assume without cap we'd have been tempted to pick on every playoff game with
    # starter+starter + decent r5/r15 · i.e., the upper band of playoff games.
    # the cap zeroes out all g1s from eligibility. effect on overall pick u2.5 rate:
    print("=== v4.2 g1 cap impact ===\n")
    pool_all = rows
    pool_no_g1 = [r for r in rows if r["game_num"] >= 2]
    print(f"  without g1 cap: u2.5 rate = {pct(sum(r['u2.5_hit'] for r in pool_all), len(pool_all))}%")
    print(f"  with g1 cap (only g2+ bet): u2.5 rate = {pct(sum(r['u2.5_hit'] for r in pool_no_g1), len(pool_no_g1))}%")
    print(f"  pp lift from cap: +{pct(sum(r['u2.5_hit'] for r in pool_no_g1), len(pool_no_g1)) - pct(sum(r['u2.5_hit'] for r in pool_all), len(pool_all))}%")
    print(f"  games forfeited by cap: {len(pool_all) - len(pool_no_g1)}/{len(pool_all)} ({pct(len(pool_all) - len(pool_no_g1), len(pool_all))}%)")
    print()

    # same analysis, last 2 seasons (more relevant)
    recent_all = [r for r in rows if r["season"] in recent]
    recent_no_g1 = [r for r in recent_all if r["game_num"] >= 2]
    print("  last 2 seasons:")
    print(f"    without g1 cap: u2.5 rate = {pct(sum(r['u2.5_hit'] for r in recent_all), len(recent_all))}%")
    print(f"    with g1 cap: u2.5 rate = {pct(sum(r['u2.5_hit'] for r in recent_no_g1), len(recent_no_g1))}%")


if __name__ == "__main__":
    main()
