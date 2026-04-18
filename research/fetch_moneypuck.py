#!/usr/bin/env python3
"""fetch moneypuck shot-level data for a season and aggregate per-game-per-team
1st period xG + actual goals. saves a CSV under research/.

usage:
    python3 research/fetch_moneypuck.py 2025          # fetch 2024-25 season
    python3 research/fetch_moneypuck.py 2025 --keep   # don't delete the raw zip

source: https://peter-tanner.com/moneypuck/downloads/shots_{year}.zip

the moneypuck file is ~100 mb and has ~400k rows (one per shot). we aggregate
down to ~2500 rows (one per game-team-period) with columns:

    game_id, team, season, period, xg_for, goals_for

integration status: NOT WIRED into the model. this is data collection for
future work. the idea is: 1p xG is a better forward-looking signal than r5/r15
aggregate rates because it captures shot quality, not just outcomes. once we
have enough seasons, we can backtest adding a 1p_xg factor to v5.

output file: research/moneypuck_1p_{year}.csv
"""

import sys, os, argparse, csv, io, urllib.request, zipfile
from collections import defaultdict

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
URL = "https://peter-tanner.com/moneypuck/downloads/shots_{}.zip"


def download_zip(year):
    """download shots_{year}.zip, return bytes."""
    url = URL.format(year)
    print(f"downloading {url}...", file=sys.stderr)
    with urllib.request.urlopen(url, timeout=120) as resp:
        data = resp.read()
    print(f"  {len(data) / 1e6:.1f} mb", file=sys.stderr)
    return data


def aggregate(zip_bytes, year):
    """parse shots csv, aggregate per-game-per-team-per-period.
    keys: (game_id, team, period). values: xg_for, goals_for, shots_for."""
    print("parsing shots csv...", file=sys.stderr)
    agg = defaultdict(lambda: {"xg": 0.0, "g": 0, "s": 0})
    row_count = 0
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as z:
        name = next((n for n in z.namelist() if n.endswith(".csv")), None)
        if not name:
            raise RuntimeError("no csv inside the zip")
        with z.open(name) as f:
            text = io.TextIOWrapper(f, encoding="utf-8", errors="replace")
            reader = csv.DictReader(text)
            for row in reader:
                row_count += 1
                try:
                    gid = int(row.get("game_id") or row.get("gameId") or 0)
                    period = int(row.get("period") or 0)
                    team = (row.get("teamCode") or row.get("team") or "").upper()
                    xg = float(row.get("xGoal") or row.get("xg") or 0.0)
                    is_goal = int(row.get("goal") or 0) == 1
                except (TypeError, ValueError):
                    continue
                if not gid or not team or period < 1 or period > 3:
                    continue
                key = (gid, team, period)
                agg[key]["xg"] += xg
                agg[key]["g"] += 1 if is_goal else 0
                agg[key]["s"] += 1
    print(f"  {row_count} shots aggregated to {len(agg)} game-team-period rows", file=sys.stderr)
    return agg


def write_1p_summary(agg, year):
    """filter to period=1 only and write summary CSV."""
    out_path = os.path.join(SCRIPT_DIR, f"moneypuck_1p_{year}.csv")
    rows = 0
    with open(out_path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["game_id", "team", "season", "period", "xg_for", "goals_for", "shots_for"])
        for (gid, team, period), v in sorted(agg.items()):
            if period != 1:
                continue
            w.writerow([gid, team, year, period, round(v["xg"], 3), v["g"], v["s"]])
            rows += 1
    print(f"wrote {rows} rows to {out_path}", file=sys.stderr)
    return out_path


def main():
    parser = argparse.ArgumentParser(description="fetch + aggregate moneypuck 1p xg")
    parser.add_argument("year", help="season end year, e.g., 2025 for 2024-25")
    args = parser.parse_args()

    zip_bytes = download_zip(args.year)
    agg = aggregate(zip_bytes, args.year)
    path = write_1p_summary(agg, args.year)
    print(path)


if __name__ == "__main__":
    main()
