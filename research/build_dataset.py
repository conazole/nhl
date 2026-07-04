#!/usr/bin/env python3
"""build a full-season point-in-time dataset for 1p u2.5 factor research.
this is also the DATA LOOP's refresh script: run it once per finished season
(--season {start_year}) and every downstream script rides the new file.

one row per final game (regular season + playoffs; preseason and special
events excluded via gameType). every feature is computed from information
available BEFORE that game (point-in-time correctness):

  - rolling r5/r15 u2.5 per team + de-duped combined (engine semantics)
  - venue splits (home team's last-10 home games, away team's last-10 road)
  - rolling 1p goal/sog/xg environment (r15, both teams combined)
  - rest days / b2b per team
  - h2h last-meeting 1p result
  - start time (ET hour via America/New_York), day of week, weekend flag
  - goalie starters per game derived from the moneypuck shot file (the
    goalie facing each side's first 1p shot), classified by STARTS SHARE
    TO DATE (≥60% starter / 40-59 tandem / <40 backup, ≥10 team games) ·
    no end-of-season leakage
  - total_line where a logged run recorded one (2025 season, feb 26+ subset)
  - espn stored per-event totals (median across books) for EVERY season ·
    espn_total / espn_books / espn_span. historical closing consensus;
    espn rounds and books disagree, so espn_span flags knife-edge games.

output: research/season_dataset_{season}.csv + a stderr progress log.
score fetches reuse the engine's .cache/scores bucket (read + populate);
espn odds are cached under .cache/espn_sb + .cache/espn_odds.

wrong-date guard: every nhl score payload game and every espn scoreboard
event is checked against the requested date · a mismatch is fatal, never
silent (the nfl repo's espn scoreboard silently served the wrong season;
assume nothing).

usage:
    python3 research/build_dataset.py                  # current season, through yesterday
    python3 research/build_dataset.py --season 2023    # a finished past season
    python3 research/build_dataset.py --season 2025 --end 2026-06-11
    python3 research/build_dataset.py --season 2025 --validate  # rebuild + diff vs existing csv
"""

import json, sys, os, csv, io, zipfile, argparse, time, urllib.request
from datetime import datetime, timedelta, date as date_cls
from zoneinfo import ZoneInfo
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from record import read_log  # noqa: E402

CACHE_DIR = os.path.join(ROOT, ".cache")
SCORE_URL = "https://api-web.nhle.com/v1/score/{}"
ESPN_SB_URL = ("https://site.api.espn.com/apis/site/v2/sports/hockey/nhl/"
               "scoreboard?dates={}")
ESPN_ODDS_URL = ("https://sports.core.api.espn.com/v2/sports/hockey/leagues/"
                 "nhl/events/{eid}/competitions/{eid}/odds")
MP_ZIP_URL = "https://peter-tanner.com/moneypuck/downloads/shots_{}.zip"
HDR = {"User-Agent": "Mozilla/5.0"}
# regular-season opening night per season start-year. a season not listed
# falls back to oct 1 (the walk skips empty dates, so the only cost is a few
# extra cached fetches · never wrong data).
SEASON_STARTS = {2021: "2021-10-12", 2022: "2022-10-07", 2023: "2023-10-10",
                 2024: "2024-10-04", 2025: "2025-10-07"}
# unlisted seasons fall back to sep 20 · 2026-27 opens in late september
# (84-game cba schedule) and the walk skips empty dates harmlessly.
SEASON_START_FALLBACK_MMDD = "-09-20"
# breaks with no nhl games · skipped to save fetches (all-star weekends are
# short enough not to bother). key = season start-year.
SEASON_BREAKS = {2025: [("2026-02-07", "2026-02-22")],   # milan olympics
                 2024: [("2025-02-10", "2025-02-19")]}   # 4 nations face-off
ET = ZoneInfo("America/New_York")

NORM = {"WAS": "WSH", "VGS": "VGK", "UTAH": "UTA", "MON": "MTL",
        "TB": "TBL", "NJ": "NJD", "SJ": "SJS", "LA": "LAK", "CLS": "CBJ",
        "ARI": "UTA", "PHX": "UTA"}


def norm(abbrev):
    s = str(abbrev or "").strip().upper()
    return NORM.get(s, s)


def progress(msg):
    print(msg, file=sys.stderr, flush=True)


def api_get(url, timeout=20):
    req = urllib.request.Request(url, headers=HDR)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def cache_path(bucket, key):
    d = os.path.join(CACHE_DIR, bucket)
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, f"{key}.json")


def get_scores_for_date(ds, today_str):
    """cached score payload for a date; fetch + cache if missing.
    only dates < today-1 are cached (matches engine policy).
    guard: the payload's own currentDate must match the request · a served
    wrong-date slate is fatal, never silent."""
    p = cache_path("scores", ds)
    if os.path.exists(p):
        with open(p) as f:
            return json.load(f)
    data = api_get(SCORE_URL.format(ds))
    got = data.get("currentDate", ds)
    if got != ds:
        raise RuntimeError(f"nhl score api returned currentDate {got} for a "
                           f"{ds} request · refusing the slate")
    if ds < (datetime.strptime(today_str, "%Y-%m-%d") - timedelta(days=1)).strftime("%Y-%m-%d"):
        with open(p, "w") as f:
            json.dump(data, f)
    return data


# ── espn stored odds: historical per-event totals, all seasons ──

def espn_scoreboard(ds):
    """cached espn scoreboard for a date → {(AWAY, HOME): event_id}.
    every event's own date must match the requested date (espn's nfl
    scoreboard silently served the wrong season once · enforce, don't trust)."""
    p = cache_path("espn_sb", ds)
    if os.path.exists(p):
        with open(p) as f:
            return {tuple(k.split("@")): v for k, v in json.load(f).items()}
    out = {}
    try:
        data = api_get(ESPN_SB_URL.format(ds.replace("-", "")))
    except Exception as exc:
        progress(f"  espn scoreboard {ds} failed: {exc}")
        return out
    for ev in data.get("events", []):
        ev_date = (ev.get("date") or "")[:10]
        # espn stamps events in utc; a late us game can land on the next utc
        # day. accept ds or ds+1, refuse anything else.
        next_day = (datetime.strptime(ds, "%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%d")
        if ev_date not in (ds, next_day):
            raise RuntimeError(f"espn scoreboard returned event dated {ev_date} "
                               f"for a {ds} request · refusing the slate")
        comp = (ev.get("competitions") or [{}])[0]
        aw = hm = None
        for c in comp.get("competitors", []):
            ab = norm(c.get("team", {}).get("abbreviation", ""))
            if c.get("homeAway") == "away":
                aw = ab
            else:
                hm = ab
        if aw and hm:
            out[(aw, hm)] = ev["id"]
    with open(p, "w") as f:
        json.dump({f"{a}@{h}": eid for (a, h), eid in out.items()}, f)
    return out


def espn_event_total(eid):
    """stored PREGAME odds for a finished espn event → (median_total,
    n_books, span). span = max-min across books; a wide span means the books
    disagreed and the median is a knife-edge number.

    live-odds contamination (jul 2026 audit): since 2024-25 espn stores only
    two providers per event · "ESPN BET" (the pregame closer) and "ESPN Bet -
    Live Odds" (an IN-GAME snapshot, e.g. total 4.5 at a -3000 moneyline). a
    naive median across both produced impossible pregame totals (4.0-4.5)
    that graded 97-100% u2.5 · pure leakage of the in-game state. providers
    whose name contains "live" are excluded, and any surviving total outside
    the plausible pregame range [5.0, 8.5] is dropped, loudly countable via
    books=0. the raw per-provider list is cached so future filter changes
    never refetch."""
    p = cache_path("espn_odds_raw", str(eid))
    if os.path.exists(p):
        with open(p) as f:
            items = json.load(f)
    else:
        items = []
        try:
            data = api_get(ESPN_ODDS_URL.format(eid=eid), timeout=15)
            for item in data.get("items", []):
                prov = item.get("provider", {}) or {}
                items.append({"name": prov.get("name", ""),
                              "id": prov.get("id"),
                              "ou": item.get("overUnder")})
        except Exception:
            items = None
        if items is not None:
            with open(p, "w") as f:
                json.dump(items, f)
        else:
            items = []
    totals = sorted(float(it["ou"]) for it in items
                    if it.get("ou") is not None
                    and "live" not in (it.get("name") or "").lower())
    if totals:
        n = len(totals)
        med = totals[n // 2] if n % 2 else (totals[n // 2 - 1] + totals[n // 2]) / 2
        # snap to the nearest 0.5 (an even-count median can land on .25/.75)
        med = round(med * 2) / 2
        span = round(totals[-1] - totals[0], 1)
        if 5.0 <= med <= 8.5:
            return med, n, span
    return None, 0, None


def extract_team_abbrev(val):
    if isinstance(val, dict):
        return val.get("default", "")
    return str(val)


# ── moneypuck: per-game 1p starters, sog, xg ──

def load_moneypuck(season):
    """parse the moneypuck shots zip for a season (download + cache if
    missing). returns:
      starters: {gid: {"away": lastname, "home": lastname}}
      p1: {gid: {"away_sog","home_sog","away_xg","home_xg"}}
    gid = full NHL game id ({season}xxxxxx)."""
    mp_dir = os.path.join(CACHE_DIR, "moneypuck")
    os.makedirs(mp_dir, exist_ok=True)
    zpath = os.path.join(mp_dir, f"shots_{season}.zip")
    if not os.path.exists(zpath):
        progress(f"  downloading moneypuck shots_{season}.zip ...")
        try:
            req = urllib.request.Request(MP_ZIP_URL.format(season), headers=HDR)
            with urllib.request.urlopen(req, timeout=180) as r:
                zb = r.read()
            with open(zpath, "wb") as f:
                f.write(zb)
            progress(f"  downloaded {len(zb) / 1024 / 1024:.1f}MB")
        except Exception as exc:
            progress(f"  moneypuck download failed ({exc}) · goalie/sog/xg blank")
            return {}, {}
    with open(zpath, "rb") as f:
        zb = f.read()
    starters, p1 = {}, {}
    first_shot_time = {}
    with zipfile.ZipFile(io.BytesIO(zb)) as zf:
        cn = zf.namelist()[0]
        with zf.open(cn) as cf:
            reader = csv.DictReader(io.TextIOWrapper(cf))
            cols = reader.fieldnames or []
            need = ["game_id", "period", "teamCode", "homeTeamCode",
                    "awayTeamCode", "goalieNameForShot", "xGoal", "event", "time"]
            missing = [c for c in need if c not in cols]
            if missing:
                progress(f"  moneypuck columns missing {missing} · have {cols[:25]}")
                return {}, {}
            offset = season * 1000000
            for row in reader:
                try:
                    gid = offset + int(row["game_id"])
                except ValueError:
                    continue
                if row.get("period") != "1":
                    continue
                home = norm(row.get("homeTeamCode"))
                shooter = norm(row.get("teamCode"))
                side_def = "home" if shooter != home else "away"  # defender
                rec = p1.setdefault(gid, {"away_sog": 0, "home_sog": 0,
                                          "away_xg": 0.0, "home_xg": 0.0})
                shooter_side = "home" if shooter == home else "away"
                try:
                    rec[f"{shooter_side}_xg"] += float(row.get("xGoal") or 0)
                except ValueError:
                    pass
                if row.get("event") in ("SHOT", "GOAL"):
                    rec[f"{shooter_side}_sog"] += 1
                goalie = (row.get("goalieNameForShot") or "").strip()
                if goalie:
                    try:
                        t = float(row.get("time") or 1e9)
                    except ValueError:
                        t = 1e9
                    key = (gid, side_def)
                    if key not in first_shot_time or t < first_shot_time[key]:
                        first_shot_time[key] = t
                        starters.setdefault(gid, {})[side_def] = goalie.split()[-1].lower()
    progress(f"  moneypuck: {len(p1)} games with 1p data, {len(starters)} with starters")
    return starters, p1


# ── boxscore cache fallback for starters (engine's games bucket) ──

def boxscore_starter(gid):
    p = cache_path("games", str(gid))
    if not os.path.exists(p):
        return {}
    with open(p) as f:
        d = json.load(f)
    out = {}
    for side, key in (("awayTeam_goalie", "away"), ("homeTeam_goalie", "home")):
        nm = d.get(side, "?")
        if nm and nm != "?":
            out[key] = nm.lower().split()[-1]
    return out


def current_season():
    """season start-year for today: sep+ = this year, jan-aug = last year
    (2026-27 opens in late september under the new cba)."""
    now = datetime.now()
    return now.year if now.month >= 9 else now.year - 1


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--season", type=int, default=None,
                        help="season start year (e.g. 2023 = the 2023-24 season)")
    parser.add_argument("--end", default=None, help="last date to include (YYYY-MM-DD)")
    parser.add_argument("--validate", action="store_true",
                        help="rebuild + diff core columns against the existing csv; no write")
    args = parser.parse_args()

    season = args.season if args.season is not None else current_season()
    out_csv = os.path.join(ROOT, "research", f"season_dataset_{season}.csv")

    today = datetime.now().strftime("%Y-%m-%d")
    season_end_default = f"{season + 1}-07-05"
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    end = args.end or min(season_end_default, yesterday)

    progress(f"season {season}-{str(season + 1)[2:]} → {out_csv}")
    progress("loading moneypuck shots...")
    mp_starters, mp_p1 = load_moneypuck(season)

    # lines from picks_log: (date, "aw @ hm") -> total_line
    line_lookup = {}
    for e in read_log():
        if e.get("total_line") is not None:
            line_lookup[(e["date"], e["game"])] = e["total_line"]
    progress(f"  lines from picks_log: {len(line_lookup)}")

    # ── pass 1: collect all final games chronologically ──
    progress("walking season scores...")
    games = []
    breaks = SEASON_BREAKS.get(season, [])
    start = SEASON_STARTS.get(season, f"{season}{SEASON_START_FALLBACK_MMDD}")
    cur = datetime.strptime(start, "%Y-%m-%d")
    end_dt = datetime.strptime(end, "%Y-%m-%d")
    n_dates = 0
    while cur <= end_dt:
        ds = cur.strftime("%Y-%m-%d")
        if any(b_s <= ds <= b_e for b_s, b_e in breaks):
            cur += timedelta(days=1)
            continue
        try:
            data = get_scores_for_date(ds, today)
            n_dates += 1
        except Exception as exc:
            progress(f"  {ds}: fetch failed ({exc}) · skipping")
            cur += timedelta(days=1)
            continue
        for g in data.get("games", []):
            if g.get("gameState") not in ("OFF", "FINAL"):
                continue
            gtype = g.get("gameType", 2)
            if gtype not in (2, 3):  # skip preseason/all-star/special events
                continue
            gid = g.get("id", 0)
            if gid and gid // 1000000 != season:
                raise RuntimeError(f"game id {gid} on {ds} is not a season-"
                                   f"{season} id · refusing the slate")
            aw = norm(g["awayTeam"]["abbrev"])
            hm = norm(g["homeTeam"]["abbrev"])
            a1 = h1 = 0
            for gl in g.get("goals", []):
                if gl.get("period") != 1:
                    continue
                ta = norm(extract_team_abbrev(gl.get("teamAbbrev", "")))
                if ta == aw:
                    a1 += 1
                elif ta == hm:
                    h1 += 1
            games.append({
                "date": ds, "gid": g.get("id", 0), "type": gtype,
                "away": aw, "home": hm,
                "away_1p": a1, "home_1p": h1, "total_1p": a1 + h1,
                "u25": 1 if a1 + h1 <= 2 else 0,
                "ft": g["awayTeam"].get("score", 0) + g["homeTeam"].get("score", 0),
                "start_utc": g.get("startTimeUTC", ""),
            })
        if n_dates % 40 == 0:
            progress(f"  ...{ds} ({len(games)} games)")
        time.sleep(0.02)
        cur += timedelta(days=1)
    games.sort(key=lambda x: (x["date"], x["gid"]))
    progress(f"  {len(games)} final games over {n_dates} dates")

    # ── pass 1b: espn stored totals (historical closing consensus) ──
    progress("fetching espn stored totals...")
    from concurrent.futures import ThreadPoolExecutor
    espn_ids = {}          # (date, away, home) -> event id
    game_dates = sorted({g["date"] for g in games})
    with ThreadPoolExecutor(max_workers=12) as pool:
        for ds, sb in zip(game_dates, pool.map(espn_scoreboard, game_dates)):
            for (aw, hm), eid in sb.items():
                espn_ids[(ds, aw, hm)] = eid
    matched = [g for g in games if (g["date"], g["away"], g["home"]) in espn_ids]
    progress(f"  espn events matched: {len(matched)}/{len(games)}")
    espn_totals = {}       # (date, away, home) -> (total, books, span)
    with ThreadPoolExecutor(max_workers=12) as pool:
        keys = [(g["date"], g["away"], g["home"]) for g in matched]
        for key, res in zip(keys, pool.map(lambda k: espn_event_total(espn_ids[k]), keys)):
            espn_totals[key] = res
    with_tot = sum(1 for v in espn_totals.values() if v[0] is not None)
    progress(f"  espn totals found: {with_tot}/{len(matched)}")

    # ── pass 2: point-in-time features ──
    progress("computing point-in-time features...")
    hist = defaultdict(list)        # team -> [{date,gid,u25,gf,ga,ha}]
    h2h_last = {}                   # frozenset({a,b}) -> u25 of last meeting
    starts_count = defaultdict(lambda: defaultdict(int))  # team -> goalie -> starts
    team_gp = defaultdict(int)      # team -> games with known starter
    rows = []

    def venue_r10(team, ha):
        sub = [g for g in hist[team] if g["ha"] == ha][-10:]
        return (sum(g["u25"] for g in sub), len(sub))

    def comb_dedup(a_games, b_games):
        seen = {}
        for g in a_games:
            seen[g["gid"]] = g["u25"]
        shared = 0
        for g in b_games:
            if g["gid"] in seen:
                shared += 1
            else:
                seen[g["gid"]] = g["u25"]
        return sum(seen.values()), len(seen), shared

    for g in games:
        aw, hm, gid = g["away"], g["home"], g["gid"]
        ah, hh = hist[aw], hist[hm]

        # start time → ET
        et_hour = dow = None
        is_weekend = ""
        if g["start_utc"]:
            try:
                dt_utc = datetime.fromisoformat(g["start_utc"].replace("Z", "+00:00"))
                dt_et = dt_utc.astimezone(ET)
                et_hour = dt_et.hour + dt_et.minute / 60
                dow = dt_et.weekday()
                is_weekend = 1 if dow >= 5 else 0
            except ValueError:
                pass

        # rest
        def rest(team):
            if not hist[team]:
                return ""
            last = datetime.strptime(hist[team][-1]["date"], "%Y-%m-%d")
            return (datetime.strptime(g["date"], "%Y-%m-%d") - last).days

        a_r5 = sum(x["u25"] for x in ah[-5:])
        h_r5 = sum(x["u25"] for x in hh[-5:])
        a_r15 = sum(x["u25"] for x in ah[-15:])
        h_r15 = sum(x["u25"] for x in hh[-15:])
        c5_hits, c5_n, c5_shared = comb_dedup(ah[-5:], hh[-5:])
        c15_hits, c15_n, c15_shared = comb_dedup(ah[-15:], hh[-15:])

        # rolling 1p environment (r15): goals for+against per game, both teams
        def env(team):
            sub = hist[team][-15:]
            if not sub:
                return ("", "", "")
            gpg = sum(x["gf"] + x["ga"] for x in sub) / len(sub)
            sog = [x["sog"] for x in sub if x["sog"] is not None]
            xg = [x["xg"] for x in sub if x["xg"] is not None]
            return (round(gpg, 3),
                    round(sum(sog) / len(sog), 2) if sog else "",
                    round(sum(xg) / len(xg), 4) if xg else "")
        a_env_g, a_env_sog, a_env_xg = env(aw)
        h_env_g, h_env_sog, h_env_xg = env(hm)

        # goalies: actual starter this game (mp first; boxscore cache fallback)
        st = dict(mp_starters.get(gid, {}))
        if "away" not in st or "home" not in st:
            st = {**boxscore_starter(gid), **st}
        a_goalie = st.get("away", "")
        h_goalie = st.get("home", "")

        def cls_of(team, goalie):
            if not goalie or team_gp[team] < 10:
                return ""
            share = starts_count[team].get(goalie, 0) / team_gp[team]
            return "starter" if share >= 0.60 else ("tandem" if share >= 0.40 else "backup")
        a_cls = cls_of(aw, a_goalie)
        h_cls = cls_of(hm, h_goalie)
        pair = "+".join(sorted([a_cls, h_cls])) if a_cls and h_cls else ""

        hv_hits, hv_n = venue_r10(hm, "h")
        av_hits, av_n = venue_r10(aw, "a")

        key_h2h = frozenset([aw, hm])
        line = line_lookup.get((g["date"], f"{aw.lower()} @ {hm.lower()}"))
        e_tot, e_books, e_span = espn_totals.get((g["date"], aw, hm), (None, 0, None))

        rows.append({
            "season": season,
            "date": g["date"], "gid": gid, "phase": "po" if g["type"] == 3 else "reg",
            "away": aw, "home": hm,
            "away_1p": g["away_1p"], "home_1p": g["home_1p"],
            "total_1p": g["total_1p"], "u25": g["u25"], "ft": g["ft"],
            "et_hour": round(et_hour, 2) if et_hour is not None else "",
            "dow": dow if dow is not None else "", "weekend": is_weekend,
            "away_rest": rest(aw), "home_rest": rest(hm),
            "away_r5": a_r5 if len(ah) >= 5 else "", "home_r5": h_r5 if len(hh) >= 5 else "",
            "away_r15_n": len(ah[-15:]), "home_r15_n": len(hh[-15:]),
            "away_r15": a_r15, "home_r15": h_r15,
            "comb_r5_pct": round(100 * c5_hits / c5_n, 1) if c5_n >= 10 - c5_shared and len(ah) >= 5 and len(hh) >= 5 else "",
            "comb_r15_pct": round(100 * c15_hits / c15_n, 1) if len(ah) >= 15 and len(hh) >= 15 else "",
            "home_venue_r10": round(100 * hv_hits / hv_n, 1) if hv_n >= 5 else "",
            "away_road_r10": round(100 * av_hits / av_n, 1) if av_n >= 5 else "",
            "env_1p_goals": round((a_env_g + h_env_g) / 2, 3) if a_env_g != "" and h_env_g != "" else "",
            "env_1p_sog": round((a_env_sog + h_env_sog) / 2, 2) if a_env_sog != "" and h_env_sog != "" else "",
            "env_1p_xg": round((a_env_xg + h_env_xg) / 2, 4) if a_env_xg != "" and h_env_xg != "" else "",
            "h2h_last_u25": h2h_last.get(key_h2h, ""),
            "away_goalie": a_goalie, "home_goalie": h_goalie,
            "away_goalie_cls": a_cls, "home_goalie_cls": h_cls, "goalie_pair": pair,
            "total_line": line if line is not None else "",
            "espn_total": e_tot if e_tot is not None else "",
            "espn_books": e_books or "",
            "espn_span": e_span if e_span is not None else "",
        })

        # ── update state AFTER emitting features ──
        mp = mp_p1.get(gid)
        for team, ha, gf, ga, side in ((aw, "a", g["away_1p"], g["home_1p"], "away"),
                                       (hm, "h", g["home_1p"], g["away_1p"], "home")):
            sog = xg = None
            if mp:
                sog = mp["away_sog"] + mp["home_sog"]
                xg = mp["away_xg"] + mp["home_xg"]
            hist[team].append({"date": g["date"], "gid": gid, "u25": g["u25"],
                               "gf": gf, "ga": ga, "ha": ha,
                               "sog": sog, "xg": xg})
        h2h_last[key_h2h] = g["u25"]
        if a_goalie:
            starts_count[aw][a_goalie] += 1
        if h_goalie:
            starts_count[hm][h_goalie] += 1
        if a_goalie:
            team_gp[aw] += 1
        if h_goalie:
            team_gp[hm] += 1

    # ── validate mode: diff core columns against the existing csv, no write ──
    if args.validate:
        if not os.path.exists(out_csv):
            sys.exit(f"--validate: {out_csv} does not exist · nothing to diff against")
        with open(out_csv) as f:
            old = {r["gid"]: r for r in csv.DictReader(f)}
        new = {str(r["gid"]): r for r in rows}
        core = ("date", "away", "home", "away_1p", "home_1p", "total_1p", "u25", "ft")
        mismatches, only_new, only_old = [], [], []
        for gid_, r in new.items():
            o = old.get(gid_)
            if o is None:
                only_new.append(gid_)
                continue
            for c in core:
                if str(r[c]) != str(o.get(c, "")):
                    mismatches.append(f"gid {gid_} {c}: rebuilt {r[c]!r} vs csv {o.get(c)!r}")
        only_old = [g for g in old if g not in new]
        print(f"validate: {len(new)} rebuilt rows vs {len(old)} existing")
        print(f"  core-column mismatches: {len(mismatches)} (must be 0)")
        for m in mismatches[:10]:
            print(f"    {m}")
        if only_new or only_old:
            print(f"  rows only in rebuild: {len(only_new)} · only in csv: {len(only_old)}")
        sys.exit(1 if mismatches else 0)

    # ── write ──
    cols = list(rows[0].keys())
    with open(out_csv, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)
    progress(f"wrote {len(rows)} rows -> {out_csv}")

    u25 = sum(r["u25"] for r in rows)
    progress(f"season 1p u2.5 base rate: {u25}/{len(rows)} = {100*u25/len(rows):.1f}%")
    with_goalies = sum(1 for r in rows if r["goalie_pair"])
    with_lines = sum(1 for r in rows if r["total_line"] != "")
    progress(f"rows with goalie pair: {with_goalies} | with lines: {with_lines}")


if __name__ == "__main__":
    main()
