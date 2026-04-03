#!/usr/bin/env python3
"""prefetch goalies + lines from external sources in parallel.

usage:
    python3 prefetch.py 2026-04-03

fetches goalie confirmations from dailyfaceoff and game lines from
ESPN/oddsshark in parallel. outputs JSON to stdout:

{
    "goalies": {"PHI": {"name": "vladar", "status": "unconfirmed", "source": "dfo"}, ...},
    "lines": {"PHI@NYI": 5.5, "STL@ANA": 6.0},
    "injuries": {"PHI": "player (status), ...", ...},
    "errors": ["source X failed: reason"]
}

the claude agent can use this output directly for --goalies and --lines
args to run_analysis.py, optionally supplementing with 1-2 web searches
for verification.
"""

import json, sys, os, re, urllib.request, argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from html.parser import HTMLParser

HDR = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
       "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"}

# team name → abbreviation mapping
TEAM_ABBREVS = {
    "anaheim ducks": "ANA", "arizona coyotes": "UTA", "utah hockey club": "UTA",
    "boston bruins": "BOS", "buffalo sabres": "BUF", "calgary flames": "CGY",
    "carolina hurricanes": "CAR", "chicago blackhawks": "CHI",
    "colorado avalanche": "COL", "columbus blue jackets": "CBJ",
    "dallas stars": "DAL", "detroit red wings": "DET",
    "edmonton oilers": "EDM", "florida panthers": "FLA",
    "los angeles kings": "LAK", "minnesota wild": "MIN",
    "montreal canadiens": "MTL", "nashville predators": "NSH",
    "new jersey devils": "NJD", "new york islanders": "NYI",
    "new york rangers": "NYR", "ottawa senators": "OTT",
    "philadelphia flyers": "PHI", "pittsburgh penguins": "PIT",
    "san jose sharks": "SJS", "seattle kraken": "SEA",
    "st. louis blues": "STL", "st louis blues": "STL",
    "tampa bay lightning": "TBL", "toronto maple leafs": "TOR",
    "vancouver canucks": "VAN", "vegas golden knights": "VGK",
    "washington capitals": "WSH", "winnipeg jets": "WPG",
    # short forms
    "ducks": "ANA", "bruins": "BOS", "sabres": "BUF", "flames": "CGY",
    "hurricanes": "CAR", "blackhawks": "CHI", "avalanche": "COL",
    "blue jackets": "CBJ", "stars": "DAL", "red wings": "DET",
    "oilers": "EDM", "panthers": "FLA", "kings": "LAK", "wild": "MIN",
    "canadiens": "MTL", "predators": "NSH", "devils": "NJD",
    "islanders": "NYI", "rangers": "NYR", "senators": "OTT",
    "flyers": "PHI", "penguins": "PIT", "sharks": "SJS", "kraken": "SEA",
    "blues": "STL", "lightning": "TBL", "maple leafs": "TOR",
    "canucks": "VAN", "golden knights": "VGK", "capitals": "WSH", "jets": "WPG",
}

ESPN_ABBREV_MAP = {
    "WSH": "WSH", "WAS": "WSH", "VGS": "VGK", "VGK": "VGK",
    "UTAH": "UTA", "UTA": "UTA", "MON": "MTL", "MTL": "MTL",
    "TB": "TBL", "TBL": "TBL", "NJ": "NJD", "NJD": "NJD",
    "SJ": "SJS", "SJS": "SJS", "LA": "LAK", "LAK": "LAK",
    "CLS": "CBJ", "CBJ": "CBJ", "ARI": "UTA",
}


def progress(msg):
    print(msg, file=sys.stderr, flush=True)


def fetch_url(url, timeout=15, max_redirects=5):
    """fetch URL with redirect following (handles 301/302/307/308)."""
    from urllib.parse import urljoin
    for _ in range(max_redirects):
        req = urllib.request.Request(url, headers=HDR)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as e:
            if e.code in (301, 302, 307, 308):
                loc = e.headers.get("Location", "")
                if not loc:
                    raise
                url = urljoin(url, loc)  # handle relative redirects
                continue
            raise
    raise Exception(f"too many redirects for {url}")


def fetch_json(url, timeout=15):
    req = urllib.request.Request(url, headers=HDR)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def normalize_abbrev(abbrev):
    s = abbrev.strip().upper()
    return ESPN_ABBREV_MAP.get(s, s)


def team_name_to_abbrev(name):
    """convert team name to abbreviation."""
    n = name.strip().lower()
    if n in TEAM_ABBREVS:
        return TEAM_ABBREVS[n]
    # try partial match
    for k, v in TEAM_ABBREVS.items():
        if k in n or n in k:
            return v
    return None


class TextExtractor(HTMLParser):
    """strip HTML tags, return plain text."""
    def __init__(self):
        super().__init__()
        self.text = []
    def handle_data(self, data):
        self.text.append(data)
    def get_text(self):
        return " ".join(self.text)


def strip_html(html_str):
    p = TextExtractor()
    p.feed(html_str)
    return p.get_text()


# ============================================================
# goalie fetching — dailyfaceoff
# ============================================================

def fetch_dfo_goalies():
    """fetch starting goalies from dailyfaceoff.com.
    DFO embeds structured JSON in __NEXT_DATA__ script tag.
    returns {TEAM: {"name": "lastname", "status": "confirmed|...", ...}}
    """
    progress("  fetching dailyfaceoff goalies...")
    try:
        html = fetch_url("https://www.dailyfaceoff.com/starting-goalies/", timeout=20)

        # extract __NEXT_DATA__ JSON blob (Next.js SSR data)
        m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.DOTALL)
        if not m:
            progress("  dfo: no __NEXT_DATA__ found")
            return {"_error": "no __NEXT_DATA__ in DFO page"}

        next_data = json.loads(m.group(1))
        games = next_data.get("props", {}).get("pageProps", {}).get("data", [])

        goalies = {}
        for g in games:
            for side in ("home", "away"):
                team_name = g.get(f"{side}TeamName", "")
                goalie_name = g.get(f"{side}GoalieName", "")
                strength = g.get(f"{side}NewsStrengthName")  # "Confirmed" or null
                news = g.get(f"{side}NewsDetails", "")
                sv_pct = g.get(f"{side}GoalieSavePercentage", "")
                gaa = g.get(f"{side}GoalieGoalsAgainstAvg", "")

                abbrev = team_name_to_abbrev(team_name)
                if not abbrev or not goalie_name:
                    continue

                last_name = goalie_name.strip().split()[-1].lower()
                status = (strength or "unconfirmed").lower()

                goalies[abbrev] = {
                    "name": last_name,
                    "full_name": goalie_name.strip().lower(),
                    "status": status,
                    "source": "dfo",
                    "sv_pct": sv_pct,
                    "gaa": gaa,
                    "news": news.strip() if news else "",
                }

        progress(f"  dfo: found {len(goalies)} goalies")
        return goalies

    except Exception as e:
        progress(f"  dfo failed: {e}")
        return {"_error": str(e)}


def fetch_nhl_goalies():
    """fetch projected goalies from nhl.com lineup projections page.
    returns {TEAM: {"name": "lastname", "source": "nhl.com"}}
    """
    progress("  fetching nhl.com lineup projections...")
    try:
        html = fetch_url(
            "https://www.nhl.com/news/nhl-lineup-projections-2025-26-season",
            timeout=20
        )
        text = strip_html(html)
        goalies = {}

        # NHL.com projections page lists projected goalies per game
        # look for team names near goalie role indicators
        # patterns: "Projected goalie: Name" or "Name is projected to start"

        team_pattern = (
            r'(Philadelphia|Islanders|Rangers|Anaheim|St\.? Louis|Boston|Buffalo|'
            r'Calgary|Carolina|Chicago|Colorado|Columbus|Dallas|Detroit|Edmonton|'
            r'Florida|Los Angeles|Minnesota|Montreal|Nashville|New Jersey|Ottawa|'
            r'Pittsburgh|San Jose|Seattle|Tampa Bay|Toronto|Utah|Vancouver|Vegas|'
            r'Washington|Winnipeg|Flyers|Ducks|Blues|Bruins|Sabres|Flames|'
            r'Hurricanes|Blackhawks|Avalanche|Blue Jackets|Stars|Red Wings|'
            r'Oilers|Panthers|Kings|Wild|Canadiens|Predators|Devils|Senators|'
            r'Penguins|Sharks|Kraken|Lightning|Maple Leafs|Canucks|Golden Knights|'
            r'Capitals|Jets)'
        )

        # look for explicit goalie projection patterns:
        # "Goalie Name could start" / "Goalie Name is projected" / "Goalie Name will start"
        # "Projected goalie: Name" / "Name gets the nod" / "Name between the pipes"
        goalie_patterns = [
            # "Name could/will/is expected to start" near team context
            r'([A-Z][a-z]+-?[A-Z]?[a-z]* [A-Z][a-z]+-?[A-Z]?[a-z]*)\s+(?:could|will|is expected to|is projected to|gets the|should)\s+start',
            # "projected goalie: Name" or "starting goalie: Name"
            r'(?:projected|starting|expected)\s+goalie[:\s]+([A-Z][a-z]+-?[A-Z]?[a-z]* [A-Z][a-z]+-?[A-Z]?[a-z]*)',
            # "Name in goal" / "Name in net" / "Name between the pipes"
            r'([A-Z][a-z]+-?[A-Z]?[a-z]* [A-Z][a-z]+-?[A-Z]?[a-z]*)\s+(?:in goal|in net|between the pipes|gets the nod|starts in)',
            # "look for Name to start"
            r'(?:look for|expect)\s+([A-Z][a-z]+-?[A-Z]?[a-z]* [A-Z][a-z]+-?[A-Z]?[a-z]*)\s+to\s+start',
            # "Name made X saves" (indicates recent starter, next game different)
            r'after\s+([A-Z][a-z]+-?[A-Z]?[a-z]* [A-Z][a-z]+-?[A-Z]?[a-z]*)\s+made\s+\d+\s+saves',
        ]

        # first pass: find all goalie mentions in text
        all_mentions = []
        for pat in goalie_patterns:
            for m in re.finditer(pat, text, re.IGNORECASE):
                name = m.group(1).strip()
                # skip if it looks like a team name or common word
                if name.lower() in TEAM_ABBREVS or len(name.split()) < 2:
                    continue
                pos = m.start()
                all_mentions.append((pos, name))

        # for each mention, find the nearest team name
        team_positions = []
        for match in re.finditer(team_pattern, text, re.IGNORECASE):
            team_word = match.group(1)
            abbrev = team_name_to_abbrev(team_word)
            if abbrev:
                team_positions.append((match.start(), abbrev))

        for g_pos, g_name in all_mentions:
            # find nearest team within 500 chars
            best_team = None
            best_dist = 500
            for t_pos, t_abbrev in team_positions:
                dist = abs(g_pos - t_pos)
                if dist < best_dist:
                    best_dist = dist
                    best_team = t_abbrev

            if best_team and best_team not in goalies:
                last_name = g_name.split()[-1].lower()
                goalies[best_team] = {
                    "name": last_name,
                    "full_name": g_name.lower(),
                    "source": "nhl.com",
                }

        progress(f"  nhl.com: found {len(goalies)} goalies")
        return goalies

    except Exception as e:
        progress(f"  nhl.com failed: {e}")
        return {"_error": str(e)}


# ============================================================
# line fetching — ESPN API + HTML fallback
# ============================================================

def fetch_espn_lines(target_date):
    """fetch game lines from ESPN.
    returns {"AWAY@HOME": 5.5, ...}
    """
    progress("  fetching espn lines...")
    lines = {}

    try:
        # try ESPN scoreboard API first (JSON)
        date_compact = target_date.replace("-", "")
        api_url = f"https://site.api.espn.com/apis/site/v2/sports/hockey/nhl/scoreboard?dates={date_compact}"
        data = fetch_json(api_url, timeout=15)

        for event in data.get("events", []):
            comp = event.get("competitions", [{}])[0]
            teams = comp.get("competitors", [])
            if len(teams) != 2:
                continue

            away_raw = home_raw = None
            for t in teams:
                abbrev = normalize_abbrev(t.get("team", {}).get("abbreviation", ""))
                if t.get("homeAway") == "away":
                    away_raw = abbrev
                else:
                    home_raw = abbrev

            if not away_raw or not home_raw:
                continue

            # check for odds in the competition data
            odds_list = comp.get("odds", [])
            for odd in odds_list:
                total = odd.get("overUnder")
                if total is not None:
                    key = f"{away_raw}@{home_raw}"
                    lines[key] = float(total)
                    break

        if lines:
            progress(f"  espn api: found {len(lines)} lines")
            return lines

    except Exception as e:
        progress(f"  espn api failed: {e}")

    # fallback: try ESPN odds HTML page
    try:
        html = fetch_url("https://www.espn.com/nhl/odds", timeout=15)
        text = strip_html(html)

        # look for team abbreviations near total numbers
        # ESPN odds page has patterns like "O 5.5" or "U 5.5"
        total_pattern = re.findall(
            r'([A-Z]{2,4})\s.*?([A-Z]{2,4})\s.*?(?:O|Over|U|Under)\s*(\d+\.?\d*)',
            text, re.IGNORECASE
        )
        for away, home, total in total_pattern:
            away_n = normalize_abbrev(away)
            home_n = normalize_abbrev(home)
            key = f"{away_n}@{home_n}"
            if key not in lines:
                lines[key] = float(total)

        progress(f"  espn html: found {len(lines)} lines")

    except Exception as e:
        progress(f"  espn html failed: {e}")

    return lines


# ============================================================
# line fetching — OddsShark (backup source for 6.0 detection)
# ============================================================

def fetch_oddsshark_lines(games, target_date):
    """fetch lines from oddsshark for specific games.
    games = [("AWAY", "HOME"), ...]
    returns {"AWAY@HOME": 6.0, ...}
    """
    progress("  fetching oddsshark lines...")
    lines = {}

    # oddsshark URLs follow a pattern
    team_slugs = {
        "ANA": "anaheim", "BOS": "boston", "BUF": "buffalo", "CGY": "calgary",
        "CAR": "carolina", "CHI": "chicago", "COL": "colorado", "CBJ": "columbus",
        "DAL": "dallas", "DET": "detroit", "EDM": "edmonton", "FLA": "florida",
        "LAK": "los-angeles", "MIN": "minnesota", "MTL": "montreal",
        "NSH": "nashville", "NJD": "new-jersey", "NYI": "new-york-islanders",
        "NYR": "new-york-rangers", "OTT": "ottawa", "PHI": "philadelphia",
        "PIT": "pittsburgh", "SJS": "san-jose", "SEA": "seattle", "STL": "st-louis",
        "TBL": "tampa-bay", "TOR": "toronto", "UTA": "utah", "VAN": "vancouver",
        "VGK": "vegas", "WSH": "washington", "WPG": "winnipeg",
    }

    dt = datetime.strptime(target_date, "%Y-%m-%d")

    # try multiple URL formats that oddsshark uses
    def make_urls(away, home):
        a_slug = team_slugs.get(away, away.lower())
        h_slug = team_slugs.get(home, home.lower())
        month = dt.strftime("%B").lower()
        day = dt.day
        year = dt.year
        # oddsshark uses numeric IDs in URLs — we can't guess those
        # instead try the odds listing page
        return [
            f"https://www.oddsshark.com/nhl/{a_slug}-{h_slug}-odds-{month}-{day}-{year}",
            f"https://www.oddsshark.com/nhl/odds",
        ]

    def fetch_one_game(away, home):
        for url in make_urls(away, home):
            try:
                html = fetch_url(url, timeout=15)
                text = strip_html(html)
                # look for total values near team names
                a_slug = team_slugs.get(away, away.lower())
                h_slug = team_slugs.get(home, home.lower())
                # find total values: "5.5", "6.0", "6.5" in game context
                totals = re.findall(r'(\d+\.5|\d+\.0)', text)
                if totals:
                    from collections import Counter
                    counts = Counter(float(t) for t in totals if 4.5 <= float(t) <= 8.0)
                    if counts:
                        best = counts.most_common(1)[0][0]
                        return (f"{away}@{home}", best)
            except Exception:
                continue
        return None

    with ThreadPoolExecutor(max_workers=5) as ex:
        futs = [ex.submit(fetch_one_game, a, h) for a, h in games]
        for f in as_completed(futs):
            result = f.result()
            if result:
                lines[result[0]] = result[1]

    progress(f"  oddsshark: found {len(lines)} lines")
    return lines


# ============================================================
# injury check — nhl.com status report
# ============================================================

def fetch_injuries(teams):
    """quick injury check for specific teams.
    returns {TEAM: "player (status), ..."}
    """
    progress("  fetching injury info...")
    injuries = {}

    try:
        html = fetch_url(
            "https://www.nhl.com/news/nhl-lineup-projections-2025-26-season",
            timeout=15
        )
        text = strip_html(html)

        for team in teams:
            # look for injury mentions near team name
            team_pattern = None
            for name, abbr in TEAM_ABBREVS.items():
                if abbr == team and len(name.split()) > 1:
                    team_pattern = name
                    break
            if not team_pattern:
                continue

            idx = text.lower().find(team_pattern.lower())
            if idx < 0:
                continue
            context = text[idx:idx + 500]
            # look for injury keywords
            inj_matches = re.findall(
                r'([A-Z][a-z]+ [A-Z][a-z]+)\s*\(([^)]+(?:body|knee|acl|shoulder|'
                r'concussion|undisclosed|upper|lower|leg|arm|hand|foot|head|back)[^)]*)\)',
                context, re.IGNORECASE
            )
            if inj_matches:
                parts = [f"{n.lower()} ({s.lower()})" for n, s in inj_matches]
                injuries[team] = ", ".join(parts)

    except Exception as e:
        progress(f"  injuries failed: {e}")

    return injuries


# ============================================================
# merge + reconcile
# ============================================================

def merge_goalie_sources(dfo, nhl):
    """merge goalie data from multiple sources. DFO is primary, nhl.com is backup.
    two sources agreeing = confirmed.
    """
    merged = {}
    all_teams = set(list(dfo.keys()) + list(nhl.keys()))
    all_teams.discard("_error")

    for team in all_teams:
        d = dfo.get(team, {})
        n = nhl.get(team, {})

        if not d and not n:
            continue

        name = d.get("name") or n.get("name")
        if not name:
            continue

        # determine confirmation status
        dfo_status = d.get("status", "unknown")
        nhl_name = n.get("name", "")

        if dfo_status == "confirmed":
            confirmed = True
        elif name == nhl_name and dfo_status in ("expected", "likely", "unconfirmed"):
            # two independent sources agree → confirmed
            confirmed = True
        elif dfo_status in ("expected", "likely") and not nhl_name:
            confirmed = False
        else:
            confirmed = dfo_status == "confirmed"

        merged[team] = {
            "name": name,
            "confirmed": confirmed,
            "dfo_status": dfo_status,
            "sources": [s for s in [
                "dfo" if d else None,
                "nhl.com" if n else None,
            ] if s],
        }

    return merged


def reconcile_lines(espn_lines, oddsshark_lines):
    """reconcile lines from multiple sources.
    ESPN API returns clean JSON per-game totals — primary source.
    OddsShark is a backup but noisy from HTML scraping.
    ESPN sometimes shows 5.5/6.5 when the real line is 6.0 —
    if ESPN shows X.5 and OddsShark disagrees with a .0 value, trust OddsShark.
    """
    final = dict(espn_lines)  # start with ESPN

    # only override ESPN with OddsShark if OddsShark found game-specific data
    for key, val in oddsshark_lines.items():
        espn_val = final.get(key)
        if espn_val is None:
            final[key] = val
        elif val != espn_val:
            # if OddsShark says 6.0 and ESPN says 5.5 or 6.5, trust 6.0
            # (ESPN's known rounding issue)
            if val == 6.0 and espn_val in (5.5, 6.5):
                final[key] = 6.0

    return final


# ============================================================
# main
# ============================================================

def main():
    parser = argparse.ArgumentParser(description="prefetch goalies + lines")
    parser.add_argument("target_date", help="YYYY-MM-DD")
    parser.add_argument("--games", default="", help='JSON: [["AWAY","HOME"], ...] — if empty, auto-detect from NHL API')
    args = parser.parse_args()

    target_date = args.target_date
    errors = []

    # get tonight's games if not provided
    if args.games:
        games = json.loads(args.games)
    else:
        try:
            progress("fetching tonight's games...")
            score_url = f"https://api-web.nhle.com/v1/score/{target_date}"
            data = fetch_json(score_url, timeout=15)
            games = []
            for g in data.get("games", []):
                away = normalize_abbrev(g.get("awayTeam", {}).get("abbrev", ""))
                home = normalize_abbrev(g.get("homeTeam", {}).get("abbrev", ""))
                if away and home:
                    games.append([away, home])
            if not games:
                # try schedule endpoint
                data = fetch_json("https://api-web.nhle.com/v1/schedule/now", timeout=15)
                for day in data.get("gameWeek", []):
                    if day.get("date") == target_date:
                        for g in day.get("games", []):
                            away = normalize_abbrev(g.get("awayTeam", {}).get("abbrev", ""))
                            home = normalize_abbrev(g.get("homeTeam", {}).get("abbrev", ""))
                            if away and home:
                                games.append([away, home])
            progress(f"  {len(games)} games: {', '.join(f'{a}@{h}' for a,h in games)}")
        except Exception as e:
            errors.append(f"games fetch failed: {e}")
            games = []

    teams_needed = set()
    for a, h in games:
        teams_needed.add(a)
        teams_needed.add(h)

    # fetch all sources in parallel
    progress("fetching all sources in parallel...")
    with ThreadPoolExecutor(max_workers=6) as ex:
        fut_dfo = ex.submit(fetch_dfo_goalies)
        fut_nhl = ex.submit(fetch_nhl_goalies)
        fut_espn = ex.submit(fetch_espn_lines, target_date)
        fut_inj = ex.submit(fetch_injuries, teams_needed)

        dfo_goalies = fut_dfo.result()
        nhl_goalies = fut_nhl.result()
        espn_lines = fut_espn.result()
        injuries = fut_inj.result()
    odds_lines = {}  # oddsshark generic page scraping is unreliable — disabled

    # collect errors from failed sources
    if "_error" in dfo_goalies:
        errors.append(f"dfo: {dfo_goalies['_error']}")
        dfo_goalies = {}
    if "_error" in nhl_goalies:
        errors.append(f"nhl.com: {nhl_goalies['_error']}")
        nhl_goalies = {}

    # merge sources
    merged_goalies = merge_goalie_sources(dfo_goalies, nhl_goalies)
    merged_lines = reconcile_lines(espn_lines, odds_lines)

    # build output in format ready for run_analysis.py
    goalies_for_engine = {}
    for team, info in merged_goalies.items():
        if team in teams_needed:
            goalies_for_engine[team] = {
                "name": info["name"],
                "confirmed": info["confirmed"],
            }

    # flag lines that need manual verification
    # ESPN is known to round 6.0 → 5.5 or 6.5. since 6.0 is the most common
    # line (43% of games) and 6.5 triggers a -1 penalty in the model, any game
    # ESPN shows as 6.5 COULD actually be 6.0 — which changes the pick decision.
    # the agent MUST verify these with an additional source before running the engine.
    lines_needing_verification = []
    for key, val in merged_lines.items():
        espn_val = espn_lines.get(key)
        odds_val = odds_lines.get(key)
        if espn_val is not None and odds_val is not None and espn_val != odds_val:
            lines_needing_verification.append({
                "game": key, "espn": espn_val, "oddsshark": odds_val,
                "using": val, "reason": "sources disagree"
            })
        elif espn_val == 6.5 and odds_val is None:
            # ESPN says 6.5 but no second source to verify — could be 6.0
            lines_needing_verification.append({
                "game": key, "espn": espn_val,
                "using": val, "reason": "ESPN 6.5 unverified — could be 6.0"
            })
        elif espn_val == 5.5 and odds_val is None:
            # less critical but ESPN could be rounding down from 6.0
            lines_needing_verification.append({
                "game": key, "espn": espn_val,
                "using": val, "reason": "ESPN 5.5 unverified — could be 6.0"
            })

    output = {
        "target_date": target_date,
        "games": games,
        "goalies": merged_goalies,
        "goalies_engine": goalies_for_engine,
        "lines": merged_lines,
        "lines_needing_verification": lines_needing_verification,
        "injuries": injuries,
        "errors": errors,
        "source_counts": {
            "dfo_goalies": len([k for k in dfo_goalies if k != "_error"]),
            "nhl_goalies": len([k for k in nhl_goalies if k != "_error"]),
            "espn_lines": len(espn_lines),
            "odds_lines": len(odds_lines),
        },
    }

    json.dump(output, sys.stdout)
    progress(f"\nprefetch done: {len(merged_goalies)} goalies, {len(merged_lines)} lines, {len(errors)} errors")


if __name__ == "__main__":
    main()
