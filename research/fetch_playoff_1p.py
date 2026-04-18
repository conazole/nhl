"""
fetch playoff 1p u2.5 base rate for 2020-21 through 2024-25 seasons.
output: playoff_1p_raw.csv + playoff_1p_summary.json
"""
import csv
import json
import urllib.request
import urllib.error
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, timedelta
from collections import defaultdict

API = "https://api-web.nhle.com/v1/score/{d}"

SEASONS = [
    ("2020-21", date(2021, 4, 15), date(2021, 7, 15)),
    ("2021-22", date(2022, 4, 15), date(2022, 7, 15)),
    ("2022-23", date(2023, 4, 15), date(2023, 7, 15)),
    ("2023-24", date(2024, 4, 15), date(2024, 7, 15)),
    ("2024-25", date(2025, 4, 15), date(2025, 7, 15)),
]


def daterange(start, end):
    d = start
    while d <= end:
        yield d
        d += timedelta(days=1)


def fetch_date(d):
    url = API.format(d=d.isoformat())
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "research/1.0"})
        with urllib.request.urlopen(req, timeout=15) as r:
            return d, json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return d, {"_error": f"http {e.code}"}
    except Exception as e:
        return d, {"_error": str(e)}


def extract_playoff_games(payload, season_label):
    out = []
    for g in payload.get("games", []) or []:
        if g.get("gameType") != 3:
            continue
        if g.get("gameState") not in ("OFF", "FINAL"):
            # skip any game not final (shouldn't happen for completed seasons but defensive)
            continue
        away = g["awayTeam"]["abbrev"]
        home = g["homeTeam"]["abbrev"]
        away_1p = 0
        home_1p = 0
        for goal in g.get("goals", []) or []:
            if goal.get("period") != 1:
                continue
            ta = goal.get("teamAbbrev")
            # teamAbbrev can be a dict {"default": "FLA"} in some years
            if isinstance(ta, dict):
                ta = ta.get("default")
            if ta == away:
                away_1p += 1
            elif ta == home:
                home_1p += 1
        total_1p = away_1p + home_1p
        series = g.get("seriesStatus") or {}
        rnd = series.get("round", "")
        out.append({
            "date": g.get("gameDate", ""),
            "season": season_label,
            "round": rnd,
            "away": away,
            "home": home,
            "away_1p": away_1p,
            "home_1p": home_1p,
            "total_1p": total_1p,
            "u2.5_hit": 1 if total_1p <= 2 else 0,
            "game_id": g.get("id"),
        })
    return out


def main():
    all_games = []
    errors = []
    for season_label, start, end in SEASONS:
        dates = list(daterange(start, end))
        print(f"[{season_label}] fetching {len(dates)} dates...")
        with ThreadPoolExecutor(max_workers=8) as ex:
            futures = {ex.submit(fetch_date, d): d for d in dates}
            for fut in as_completed(futures):
                d, payload = fut.result()
                if "_error" in payload:
                    errors.append((d.isoformat(), payload["_error"]))
                    continue
                games = extract_playoff_games(payload, season_label)
                all_games.extend(games)
        season_games = [g for g in all_games if g["season"] == season_label]
        print(f"  -> {len(season_games)} playoff games")

    # dedupe by game_id (API sometimes lists a game under adjacent dates due to tz)
    seen = set()
    deduped = []
    for g in all_games:
        gid = g["game_id"]
        if gid in seen:
            continue
        seen.add(gid)
        deduped.append(g)
    all_games = deduped

    # sort
    all_games.sort(key=lambda x: (x["season"], x["date"], x["game_id"]))

    # write csv
    csv_path = "/Users/raz/claude/nhl/research/playoff_1p_raw.csv"
    with open(csv_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["date", "season", "round", "away", "home",
                                          "away_1p", "home_1p", "total_1p", "u2.5_hit", "game_id"])
        w.writeheader()
        for g in all_games:
            w.writerow(g)
    print(f"\nwrote {len(all_games)} games to {csv_path}")

    # aggregate
    n = len(all_games)
    hits = sum(g["u2.5_hit"] for g in all_games)
    overall_rate = hits / n if n else 0

    per_season = {}
    for label, _, _ in SEASONS:
        games = [g for g in all_games if g["season"] == label]
        if not games:
            per_season[label] = {"n": 0, "hits": 0, "rate": None}
            continue
        h = sum(g["u2.5_hit"] for g in games)
        per_season[label] = {
            "n": len(games),
            "hits": h,
            "rate": round(h / len(games), 4),
        }

    # distribution
    dist = defaultdict(int)
    for g in all_games:
        t = g["total_1p"]
        key = str(t) if t < 5 else "5+"
        dist[key] += 1
    dist_sorted = {k: dist[k] for k in ["0", "1", "2", "3", "4", "5+"] if k in dist}

    # by round
    by_round = {}
    for r in [1, 2, 3, 4]:
        games = [g for g in all_games if g["round"] == r]
        if not games:
            continue
        h = sum(g["u2.5_hit"] for g in games)
        by_round[r] = {"n": len(games), "hits": h, "rate": round(h / len(games), 4)}

    # by round per season (sanity)
    by_round_season = {}
    for label, _, _ in SEASONS:
        by_round_season[label] = {}
        for r in [1, 2, 3, 4]:
            games = [g for g in all_games if g["season"] == label and g["round"] == r]
            if not games:
                continue
            h = sum(g["u2.5_hit"] for g in games)
            by_round_season[label][r] = {"n": len(games), "hits": h, "rate": round(h / len(games), 4)}

    REG_BASELINE = 0.730
    gap_pp = round((overall_rate - REG_BASELINE) * 100, 2)

    summary = {
        "baseline_regular_season_u2.5": REG_BASELINE,
        "overall": {
            "n": n,
            "hits": hits,
            "rate": round(overall_rate, 4),
            "gap_vs_regular_pp": gap_pp,
        },
        "per_season": per_season,
        "distribution_1p_totals": dist_sorted,
        "by_round": by_round,
        "by_round_season": by_round_season,
        "errors_count": len(errors),
        "errors_sample": errors[:5],
    }

    summary_path = "/Users/raz/claude/nhl/research/playoff_1p_summary.json"
    with open(summary_path, "w") as f:
        json.dump(summary, f, indent=2)
    print(f"wrote summary to {summary_path}")

    print("\n=== summary ===")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
