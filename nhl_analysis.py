"""
nhl_analysis.py — deterministic 1p u2.5 analysis engine

fetches game data from the nhl api and computes all metrics:
- 15-game histories per team
- weighted poisson probabilities
- u2.5 stats (recent 5, last 15, venue splits)
- league-wide base rate
- h2h results
- b2b detection
- deterministic confidence sub-scores (r5, r15, poisson, b2b)

subjective factors (goalies +0/1, context -1/0/+1) are added by claude.

usage: python3 nhl_analysis.py [--date YYYY-MM-DD]
output: structured json to stdout
"""

import json
import sys
import math
import argparse
from datetime import datetime, timedelta
from urllib.request import urlopen, Request
from urllib.error import HTTPError


BASE_URL = "https://api-web.nhle.com/v1"
USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"


# ---------------------------------------------------------------------------
# data fetching
# ---------------------------------------------------------------------------

def fetch_json(url):
    """fetch json from a url, return parsed dict or none on error."""
    try:
        req = Request(url, headers={"User-Agent": USER_AGENT})
        with urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode())
    except (HTTPError, Exception) as e:
        print(f"warning: failed to fetch {url}: {e}", file=sys.stderr)
        return None


def get_todays_games(date_str):
    """get tonight's matchups. tries /score/{date} first, falls back to /schedule/now."""
    data = fetch_json(f"{BASE_URL}/score/{date_str}")
    if not data or "games" not in data or not data["games"]:
        data = fetch_json(f"{BASE_URL}/schedule/now")

    games = []
    if data and "games" in data:
        for g in data["games"]:
            away = g["awayTeam"]["abbrev"].lower()
            home = g["homeTeam"]["abbrev"].lower()
            games.append({"away": away, "home": home})
    elif data and "gameWeek" in data:
        # schedule/now returns a different structure
        for day in data["gameWeek"]:
            if day.get("date") == date_str:
                for g in day.get("games", []):
                    away = g["awayTeam"]["abbrev"].lower()
                    home = g["homeTeam"]["abbrev"].lower()
                    games.append({"away": away, "home": home})
                break

    return games


def parse_1p_from_game(game_data):
    """
    extract 1p goals per team from a completed game.
    handles teamAbbrev as either a string or {"default": "XYZ"}.
    returns dict with away, home, away_1p, home_1p, total_1p or none if not completed.
    """
    state = game_data.get("gameState", "")
    if state not in ("OFF", "FINAL"):
        return None

    away = game_data["awayTeam"]["abbrev"].lower()
    home = game_data["homeTeam"]["abbrev"].lower()
    counts = {away: 0, home: 0}

    for goal in game_data.get("goals", []):
        if goal.get("period") != 1:
            continue
        ta = goal.get("teamAbbrev", "")
        if isinstance(ta, dict):
            team = ta.get("default", "").lower()
        else:
            team = str(ta).lower()
        if team in counts:
            counts[team] += 1

    return {
        "away": away,
        "home": home,
        "away_1p": counts[away],
        "home_1p": counts[home],
        "total_1p": counts[away] + counts[home],
    }


def fetch_historical_data(target_teams, date_str, max_games=15, max_lookback=60):
    """
    walk backward from the day before date_str. fetch each date once.
    collect up to max_games completed games per target team.
    track league-wide u2.5 stats from ALL completed games encountered.
    track h2h games between tonight's opponents.

    returns: (team_games, league_total, league_u25, h2h_games)
    """
    target_date = datetime.strptime(date_str, "%Y-%m-%d")
    team_games = {t: [] for t in target_teams}
    teams_done = set()

    league_total = 0
    league_u25 = 0
    h2h_games = {}  # key: tuple(sorted([t1, t2])), value: list of dicts

    current = target_date - timedelta(days=1)
    cutoff = target_date - timedelta(days=max_lookback)

    while current >= cutoff and len(teams_done) < len(target_teams):
        date_key = current.strftime("%Y-%m-%d")
        data = fetch_json(f"{BASE_URL}/score/{date_key}")

        if data and "games" in data:
            for game in data["games"]:
                parsed = parse_1p_from_game(game)
                if parsed is None:
                    continue

                away = parsed["away"]
                home = parsed["home"]
                total = parsed["total_1p"]
                u25 = total <= 2

                # league-wide
                league_total += 1
                if u25:
                    league_u25 += 1

                # h2h: both teams playing tonight against each other
                if away in target_teams and home in target_teams:
                    key = tuple(sorted([away, home]))
                    h2h_games.setdefault(key, []).append({
                        "date": date_key,
                        "away": away,
                        "home": home,
                        "away_1p": parsed["away_1p"],
                        "home_1p": parsed["home_1p"],
                        "total_1p": total,
                    })

                # per-team collection
                for team in (away, home):
                    if team not in target_teams or team in teams_done:
                        continue
                    is_home = team == home
                    gf = parsed["home_1p"] if is_home else parsed["away_1p"]
                    ga = parsed["away_1p"] if is_home else parsed["home_1p"]
                    opp = home if team == away else away

                    team_games[team].append({
                        "date": date_key,
                        "opponent": opp,
                        "venue": "h" if is_home else "a",
                        "goals_for": gf,
                        "goals_against": ga,
                        "total_1p": total,
                        "u25": u25,
                    })

                    if len(team_games[team]) >= max_games:
                        teams_done.add(team)

        current -= timedelta(days=1)

    return team_games, league_total, league_u25, h2h_games


# ---------------------------------------------------------------------------
# deterministic computation
# ---------------------------------------------------------------------------

def weighted_avg_gf(games):
    """
    weighted average 1p goals-for using exponential decay.
    games are ordered most-recent-first (index 0 = latest game).

    weight formula:
        w(i) = 1.0 - 0.6 * (i / (n - 1))
    where i=0 is most recent (weight=1.0), i=n-1 is oldest (weight=0.4).

    this is equivalent to the nhl.md spec:
        "most recent game = 1.0, oldest (15th) game = 0.4"
    """
    n = len(games)
    if n == 0:
        return 0.0
    if n == 1:
        return float(games[0]["goals_for"])

    w_sum = 0.0
    gf_sum = 0.0
    for i, g in enumerate(games):
        w = 1.0 - 0.6 * (i / (n - 1))
        gf_sum += g["goals_for"] * w
        w_sum += w

    return gf_sum / w_sum


def poisson_pmf(k, lam):
    """P(X = k) for poisson distribution."""
    if lam <= 0:
        return 1.0 if k == 0 else 0.0
    return (lam ** k) * math.exp(-lam) / math.factorial(k)


def poisson_u25(lam_a, lam_b):
    """
    P(total 1p goals <= 2) assuming independent poisson for each team.
    enumerate all (a, b) pairs where a + b <= 2.
    """
    p = 0.0
    for a in range(3):          # a = 0, 1, 2
        for b in range(3 - a):  # b such that a + b <= 2
            p += poisson_pmf(a, lam_a) * poisson_pmf(b, lam_b)
    return p


def u25_stats(games, venue_filter=None):
    """compute u2.5 count/pct from a list of games, optionally filtered by venue."""
    if venue_filter:
        g = [x for x in games if x["venue"] == venue_filter]
    else:
        g = list(games)

    total = len(g)
    u25 = sum(1 for x in g if x["u25"])
    return {
        "total": total,
        "u25": u25,
        "pct": round(100 * u25 / total, 1) if total > 0 else 0.0,
    }


def confidence_deterministic(r5_pct, r15_pct, poisson_pct, is_b2b):
    """
    compute the formula-based confidence sub-scores.

    | factor                       | criteria                              | points |
    |------------------------------|---------------------------------------|--------|
    | combined recent 5 u2.5 rate  | 0-49%: 0, 50-69%: 1, 70-89%: 2, 90+: 3 | 0-3 |
    | combined 15-game u2.5 rate   | 0-49%: 0, 50-64%: 1, 65+: 2           | 0-2    |
    | poisson p(u2.5)              | <60%: 0, 60-74%: 1, 75+: 2            | 0-2    |
    | b2b / fatigue                | any team on b2b: +1                    | 0-1    |
    | subtotal (deterministic)     |                                        | 0-8    |

    goalie quality (0-1) and context modifier (-1 to +1) added by claude → max 10.
    """
    # recent 5
    if r5_pct >= 90:
        r5 = 3
    elif r5_pct >= 70:
        r5 = 2
    elif r5_pct >= 50:
        r5 = 1
    else:
        r5 = 0

    # last 15
    if r15_pct >= 65:
        r15 = 2
    elif r15_pct >= 50:
        r15 = 1
    else:
        r15 = 0

    # poisson
    if poisson_pct >= 75:
        poi = 2
    elif poisson_pct >= 60:
        poi = 1
    else:
        poi = 0

    b2b = 1 if is_b2b else 0

    return {
        "r5_pts": r5,
        "r15_pts": r15,
        "poisson_pts": poi,
        "b2b_pts": b2b,
        "subtotal": r5 + r15 + poi + b2b,
    }


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="nhl 1p u2.5 deterministic analysis")
    parser.add_argument("--date", default=datetime.now().strftime("%Y-%m-%d"),
                        help="analysis date YYYY-MM-DD (default: today)")
    args = parser.parse_args()
    date_str = args.date

    # --- tonight's games ---
    tonight = get_todays_games(date_str)
    if not tonight:
        json.dump({"error": "no games found", "date": date_str}, sys.stdout, indent=2)
        sys.exit(1)

    all_teams = set()
    matchups = []
    for g in tonight:
        all_teams.add(g["away"])
        all_teams.add(g["home"])
        matchups.append((g["away"], g["home"]))

    # --- historical data ---
    team_games, league_total, league_u25, h2h_all = fetch_historical_data(
        all_teams, date_str, max_games=15, max_lookback=60
    )

    league_base_rate = round(100 * league_u25 / league_total, 1) if league_total > 0 else 0.0

    # --- b2b detection ---
    yesterday = (datetime.strptime(date_str, "%Y-%m-%d") - timedelta(days=1)).strftime("%Y-%m-%d")
    b2b_teams = [t for t in all_teams if team_games.get(t) and team_games[t][0]["date"] == yesterday]

    # --- per-matchup analysis ---
    output_matchups = []

    for away, home in matchups:
        ag = team_games.get(away, [])
        hg = team_games.get(home, [])

        # per-team stats
        a_r5 = u25_stats(ag[:5])
        a_r15 = u25_stats(ag)
        a_venue = u25_stats(ag, venue_filter="a")
        a_wavg = round(weighted_avg_gf(ag), 2)

        h_r5 = u25_stats(hg[:5])
        h_r15 = u25_stats(hg)
        h_venue = u25_stats(hg, venue_filter="h")
        h_wavg = round(weighted_avg_gf(hg), 2)

        # combined
        c_r5_u25 = a_r5["u25"] + h_r5["u25"]
        c_r5_total = a_r5["total"] + h_r5["total"]
        c_r5_pct = round(100 * c_r5_u25 / c_r5_total, 1) if c_r5_total > 0 else 0.0

        c_r15_u25 = a_r15["u25"] + h_r15["u25"]
        c_r15_total = a_r15["total"] + h_r15["total"]
        c_r15_pct = round(100 * c_r15_u25 / c_r15_total, 1) if c_r15_total > 0 else 0.0

        # poisson
        p_u25 = round(100 * poisson_u25(a_wavg, h_wavg), 1)
        p_edge = round(p_u25 - league_base_rate, 1)

        # h2h
        key = tuple(sorted([away, home]))
        h2h = h2h_all.get(key, [])[:3]

        # b2b
        is_b2b = away in b2b_teams or home in b2b_teams
        b2b_who = [t for t in (away, home) if t in b2b_teams]

        # confidence (deterministic portion)
        conf = confidence_deterministic(c_r5_pct, c_r15_pct, p_u25, is_b2b)

        output_matchups.append({
            "away": away,
            "home": home,
            "away_games": ag,
            "home_games": hg,
            "away_stats": {
                "r5": a_r5,
                "r15": a_r15,
                "venue": a_venue,
                "weighted_avg_gf": a_wavg,
            },
            "home_stats": {
                "r5": h_r5,
                "r15": h_r15,
                "venue": h_venue,
                "weighted_avg_gf": h_wavg,
            },
            "combined": {
                "r5_u25": c_r5_u25,
                "r5_total": c_r5_total,
                "r5_pct": c_r5_pct,
                "r15_u25": c_r15_u25,
                "r15_total": c_r15_total,
                "r15_pct": c_r15_pct,
            },
            "poisson": {
                "away_lambda": a_wavg,
                "home_lambda": h_wavg,
                "p_u25": p_u25,
                "edge": p_edge,
            },
            "h2h": h2h,
            "b2b": {
                "any": is_b2b,
                "teams": b2b_who,
            },
            "confidence_deterministic": conf,
        })

    result = {
        "date": date_str,
        "league_base_rate": league_base_rate,
        "league_total_games": league_total,
        "league_u25_games": league_u25,
        "matchups": output_matchups,
    }

    json.dump(result, sys.stdout, indent=2)
    print()  # trailing newline


if __name__ == "__main__":
    main()
