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
from datetime import datetime, timedelta
from html.parser import HTMLParser

HDR = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
       "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"}

# team name → abbreviation mapping
TEAM_ABBREVS = {
    "anaheim ducks": "ANA", "arizona coyotes": "UTA", "utah hockey club": "UTA",
    "utah mammoth": "UTA",  # renamed may 2025 · the old name silently missed
                            # dfo/pinnacle matches all of 2025-26 (jul 2026 audit)
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
    "mammoth": "UTA",
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


def lineup_projections_url(target_date):
    """nhl.com lineup-projections url for the season the date belongs to.
    was hardcoded to the 2025-26 slug · would have 404'd all of next season
    and silently killed goalie source 2 + the injuries fetch (jul 2026 audit)."""
    y, m = int(target_date[:4]), int(target_date[5:7])
    start = y if m >= 9 else y - 1   # 2026-27 opens in late september
    return (f"https://www.nhl.com/news/nhl-lineup-projections-"
            f"{start}-{str(start + 1)[2:]}-season")


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
# goalie fetching · dailyfaceoff
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
                if team_name and not abbrev:
                    # an unmapped team name means a rename/relocation the map
                    # hasn't heard about (utah mammoth, may 2025). loud, never
                    # silent · this cost a season of uta goalie confirmations.
                    progress(f"  dfo: UNMAPPED TEAM NAME {team_name!r} · "
                             f"update TEAM_ABBREVS in prefetch.py")
                    goalies.setdefault("_unmapped", []).append(team_name)
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


def fetch_nhl_goalies(target_date):
    """fetch projected goalies from nhl.com lineup projections page.
    returns {TEAM: {"name": "lastname", "source": "nhl.com"}}
    """
    progress("  fetching nhl.com lineup projections...")
    try:
        html = fetch_url(lineup_projections_url(target_date), timeout=20)
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
# line fetching · ESPN API + HTML fallback
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
# line fetching · Pinnacle (sharpest book, public JSON API)
# ============================================================

PINNACLE_NHL_LEAGUE_ID = 1456  # NHL league ID in Pinnacle's system

# pinnacle team names → our abbreviations
PINNACLE_TEAM_MAP = {
    "Anaheim Ducks": "ANA", "Boston Bruins": "BOS", "Buffalo Sabres": "BUF",
    "Calgary Flames": "CGY", "Carolina Hurricanes": "CAR", "Chicago Blackhawks": "CHI",
    "Colorado Avalanche": "COL", "Columbus Blue Jackets": "CBJ", "Dallas Stars": "DAL",
    "Detroit Red Wings": "DET", "Edmonton Oilers": "EDM", "Florida Panthers": "FLA",
    "Los Angeles Kings": "LAK", "Minnesota Wild": "MIN", "Montreal Canadiens": "MTL",
    "Nashville Predators": "NSH", "New Jersey Devils": "NJD", "New York Islanders": "NYI",
    "New York Rangers": "NYR", "Ottawa Senators": "OTT", "Philadelphia Flyers": "PHI",
    "Pittsburgh Penguins": "PIT", "San Jose Sharks": "SJS", "Seattle Kraken": "SEA",
    "St. Louis Blues": "STL", "Tampa Bay Lightning": "TBL", "Toronto Maple Leafs": "TOR",
    "Utah Hockey Club": "UTA", "Utah Mammoth": "UTA", "Vancouver Canucks": "VAN",
    "Vegas Golden Knights": "VGK", "Washington Capitals": "WSH", "Winnipeg Jets": "WPG",
}


def fetch_pinnacle_lines(target_date):
    """fetch game totals from Pinnacle's public API.
    Pinnacle is the sharpest book · their lines are the market benchmark.
    returns {"AWAY@HOME": 6.0, ...}
    """
    progress("  fetching pinnacle lines...")
    lines = {}
    try:
        # step 1: get all NHL matchups
        url = f"https://guest.api.arcadia.pinnacle.com/0.1/leagues/{PINNACLE_NHL_LEAGUE_ID}/matchups?brandId=0"
        matchups = fetch_json(url, timeout=15)

        # find today's games (some start after midnight UTC)
        target_dt = datetime.strptime(target_date, "%Y-%m-%d")
        next_day = (target_dt + timedelta(days=1)).strftime("%Y-%m-%d")
        today_ids = []
        for m in matchups:
            if m.get("type") != "matchup":
                continue
            start = m.get("startTime", "")
            if target_date not in start and f"{next_day}T0" not in start:
                continue
            parts = m.get("participants", [])
            home = away = None
            for p in parts:
                pname = p.get("name", "")
                abbrev = PINNACLE_TEAM_MAP.get(pname)
                if not abbrev:
                    if pname and p.get("alignment") in ("home", "away"):
                        progress(f"  pinnacle: UNMAPPED TEAM NAME {pname!r} · "
                                 f"update PINNACLE_TEAM_MAP in prefetch.py")
                    continue
                if p.get("alignment") == "home":
                    home = abbrev
                elif p.get("alignment") == "away":
                    away = abbrev
            if away and home:
                today_ids.append((m["id"], away, home))

        # step 2: fetch odds for each game in parallel
        def fetch_game_total(mid, away, home):
            try:
                url = f"https://guest.api.arcadia.pinnacle.com/0.1/matchups/{mid}/markets/related/straight"
                markets = fetch_json(url, timeout=10)
                for mkt in markets:
                    if mkt.get("type") == "total" and mkt.get("period") == 0:
                        for price in mkt.get("prices", []):
                            if price.get("designation") == "over":
                                return (f"{away}@{home}", price.get("points"))
                        break
            except Exception:
                pass
            return None

        with ThreadPoolExecutor(max_workers=5) as ex:
            futs = [ex.submit(fetch_game_total, mid, aw, hm) for mid, aw, hm in today_ids]
            for f in as_completed(futs):
                result = f.result()
                if result and result[1] is not None:
                    lines[result[0]] = float(result[1])

        progress(f"  pinnacle: found {len(lines)} lines")

    except Exception as e:
        progress(f"  pinnacle failed: {e}")

    return lines


# ============================================================
# injury check · nhl.com status report
# ============================================================

def fetch_injuries(teams, target_date):
    """quick injury check for specific teams.
    returns {TEAM: "player (status), ..."}
    """
    progress("  fetching injury info...")
    injuries = {}

    try:
        html = fetch_url(lineup_projections_url(target_date), timeout=15)
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


def reconcile_lines(espn_lines, pinnacle_lines):
    """reconcile lines from ESPN API + Pinnacle API.
    Pinnacle is the sharpest book in the market · when ESPN and Pinnacle
    disagree, Pinnacle is almost always correct. ESPN is known to round
    6.0 → 5.5 or 6.5.

    priority: Pinnacle > ESPN > nothing.
    """
    all_keys = set(list(espn_lines.keys()) + list(pinnacle_lines.keys()))
    final = {}

    for key in all_keys:
        e = espn_lines.get(key)
        p = pinnacle_lines.get(key)

        if p is not None and e is not None:
            if p == e:
                final[key] = p  # sources agree
            else:
                # sources disagree · trust Pinnacle (sharper line)
                final[key] = p
        elif p is not None:
            final[key] = p  # Pinnacle only
        elif e is not None:
            final[key] = e  # ESPN only

    return final


# ============================================================
# main
# ============================================================

def main():
    parser = argparse.ArgumentParser(description="prefetch goalies + lines")
    parser.add_argument("target_date", help="YYYY-MM-DD")
    parser.add_argument("--games", default="", help='JSON: [["AWAY","HOME"], ...] · if empty, auto-detect from NHL API')
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

    # short-circuit on zero games: skip all source fetches to avoid
    # scraping page chrome into bogus line entries (ESPN HTML returns
    # junk like NTON@LERS, TTLE@STON 100.0 when no real matchups exist).
    if not games:
        progress("no games tonight · skipping goalie/line fetches")
        result = {
            "target_date": target_date,
            "games": [],
            "goalies": {},
            "goalies_engine": {},
            "lines": {},
            "lines_needing_verification": [],
            "injuries": {},
            "errors": errors,
            "source_counts": {"dfo_goalies": 0, "nhl_goalies": 0, "espn_lines": 0, "pinnacle_lines": 0},
        }
        progress(f"prefetch done: 0 goalies, 0 lines, {len(errors)} errors")
        print(json.dumps(result))
        return

    # fetch all sources in parallel
    progress("fetching all sources in parallel...")
    with ThreadPoolExecutor(max_workers=6) as ex:
        fut_dfo = ex.submit(fetch_dfo_goalies)
        fut_nhl = ex.submit(fetch_nhl_goalies, target_date)
        fut_espn = ex.submit(fetch_espn_lines, target_date)
        fut_pinnacle = ex.submit(fetch_pinnacle_lines, target_date)
        fut_inj = ex.submit(fetch_injuries, teams_needed, target_date)

        dfo_goalies = fut_dfo.result()
        nhl_goalies = fut_nhl.result()
        espn_lines = fut_espn.result()
        pinnacle_lines = fut_pinnacle.result()
        injuries = fut_inj.result()

    # collect errors from failed sources
    unmapped = dfo_goalies.pop("_unmapped", None) if isinstance(dfo_goalies, dict) else None
    if unmapped:
        errors.append(f"dfo: unmapped team name(s) {sorted(set(unmapped))} · "
                      f"update TEAM_ABBREVS in prefetch.py")
    if "_error" in dfo_goalies:
        errors.append(f"dfo: {dfo_goalies['_error']}")
        dfo_goalies = {}
    if "_error" in nhl_goalies:
        errors.append(f"nhl.com: {nhl_goalies['_error']}")
        nhl_goalies = {}

    # merge sources
    merged_goalies = merge_goalie_sources(dfo_goalies, nhl_goalies)
    merged_lines = reconcile_lines(espn_lines, pinnacle_lines)

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
    # ESPN shows as 6.5 COULD actually be 6.0 · which changes the pick decision.
    # the agent MUST verify these with an additional source before running the engine.
    # flag disagreements between sources (informational · Pinnacle wins)
    def line_factor_bucket(v):
        """the engine's f_line bucket: +1 (≤5.5), 0 (6.0), -1 (≥6.5)."""
        return 1 if v <= 5.5 else (0 if v <= 6.0 else -1)

    lines_needing_verification = []
    for key, val in merged_lines.items():
        espn_val = espn_lines.get(key)
        pin_val = pinnacle_lines.get(key)
        if espn_val is not None and pin_val is not None and espn_val != pin_val:
            straddle = line_factor_bucket(espn_val) != line_factor_bucket(pin_val)
            reason = f"ESPN={espn_val} vs Pinnacle={pin_val} · using Pinnacle"
            if straddle:
                # the books disagree about which side of a scoring gate the
                # total sits on · a half-point here flips f_line and can flip
                # the pick decision. knife-edge: verify before betting.
                reason = f"GATE STRADDLE: {reason} · f_line flips between sources, verify before betting"
            lines_needing_verification.append({
                "game": key, "espn": espn_val, "pinnacle": pin_val,
                "using": val, "gate_straddle": straddle, "reason": reason
            })
        elif espn_val is not None and pin_val is None:
            # only ESPN available · flag for awareness
            lines_needing_verification.append({
                "game": key, "espn": espn_val,
                "using": val, "reason": "ESPN only · no Pinnacle confirmation"
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
            "pinnacle_lines": len(pinnacle_lines),
        },
    }

    json.dump(output, sys.stdout)
    progress(f"\nprefetch done: {len(merged_goalies)} goalies, {len(merged_lines)} lines, {len(errors)} errors")


if __name__ == "__main__":
    main()
