#!/usr/bin/env python3
"""nhl 1p u2.5 analysis engine — reusable, all computation in one script.

usage:
    python3 run_analysis.py 2026-03-12
    python3 run_analysis.py 2026-03-12 --goalies '{"BOS":"swayman","SJS":"nedeljkovic",...}'

outputs JSON to stdout. progress to stderr.
"""

import json, sys, urllib.request, time, zipfile, csv, io, argparse
from datetime import datetime, timedelta
from math import exp, factorial
from concurrent.futures import ThreadPoolExecutor, as_completed

# ============================================================
# constants
# ============================================================

HDR = {"User-Agent": "Mozilla/5.0"}
SCORE_URL = "https://api-web.nhle.com/v1/score/{}"
SCHED_URL = "https://api-web.nhle.com/v1/schedule/now"
BOX_URL = "https://api-web.nhle.com/v1/gamecenter/{}/boxscore"
PBP_URL = "https://api-web.nhle.com/v1/gamecenter/{}/play-by-play"
MP_URL = "https://peter-tanner.com/moneypuck/downloads/shots_2025.zip"

OLYMPIC_BREAK = ("2026-02-07", "2026-02-22")
MAX_LOOKBACK_DAYS = 60
GAMES_PER_TEAM = 15
BATCH_SIZE = 30
MAX_WORKERS = 25

ELITE_GOALIES = frozenset({
    "shesterkin", "vasilevskiy", "hellebuyck", "oettinger", "demko",
    "sorokin", "saros", "swayman", "bobrovsky", "hill",
})


# ============================================================
# utilities
# ============================================================

def progress(msg):
    print(msg, file=sys.stderr, flush=True)


def api_get(url, timeout=20):
    req = urllib.request.Request(url, headers=HDR)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def parse_toi(toi_str):
    """parse 'MM:SS' to total seconds for proper comparison."""
    try:
        parts = toi_str.split(":")
        return int(parts[0]) * 60 + int(parts[1])
    except Exception:
        return 0


def poisson_pmf(k, lam):
    if lam <= 0:
        return 1.0 if k == 0 else 0.0
    return exp(-lam) * (lam ** k) / factorial(k)


def p_u25(la, lb):
    """P(total 1p goals <= 2) via poisson."""
    total = 0.0
    for a in range(3):
        for b in range(3 - a):
            total += poisson_pmf(a, la) * poisson_pmf(b, lb)
    return total


def normalize_abbrev(abbrev):
    """normalize team abbreviation to NHL standard."""
    s = abbrev.strip().upper()
    return {"WAS": "WSH", "VGS": "VGK", "UTAH": "UTA", "MON": "MTL",
            "TB": "TBL", "NJ": "NJD", "SJ": "SJS", "LA": "LAK",
            "CLS": "CBJ"}.get(s, s)


def extract_team_abbrev(val):
    """handle teamAbbrev as either string or {'default': 'XYZ'}."""
    if isinstance(val, dict):
        return val.get("default", "").upper()
    return str(val).upper()


# ============================================================
# phase 1: fetch tonight's games + walk dates for 1p scores
# ============================================================

def fetch_todays_games(target_date):
    """return list of (away, home) tuples for the target date."""
    progress(f"fetching games for {target_date}...")
    try:
        data = api_get(SCORE_URL.format(target_date))
    except Exception:
        progress("  score endpoint failed, trying schedule...")
        data = api_get(SCHED_URL)

    games = []
    for g in data.get("games", []):
        gdate = g.get("gameDate", "")[:10]
        # schedule endpoint returns multiple days — filter to target
        if "gameDate" in g and gdate != target_date:
            continue
        aw = normalize_abbrev(g.get("awayTeam", {}).get("abbrev", ""))
        hm = normalize_abbrev(g.get("homeTeam", {}).get("abbrev", ""))
        if aw and hm:
            games.append((aw, hm))
    progress(f"  {len(games)} games found")
    return games


def walk_scores(target_date, teams_needed, games_tonight):
    """walk backward from target_date-1, collecting 15 games per team."""
    progress("phase 1: walking scores...")
    team_games = {t: [] for t in teams_needed}
    league_total = league_u25 = 0
    h2h = {}
    gids = set()

    ob_start = datetime.strptime(OLYMPIC_BREAK[0], "%Y-%m-%d")
    ob_end = datetime.strptime(OLYMPIC_BREAK[1], "%Y-%m-%d")
    cur = datetime.strptime(target_date, "%Y-%m-%d") - timedelta(days=1)
    min_dt = cur - timedelta(days=MAX_LOOKBACK_DAYS)
    n_fetched = 0

    while cur >= min_dt:
        ds = cur.strftime("%Y-%m-%d")
        if ob_start <= cur <= ob_end:
            cur -= timedelta(days=1)
            continue
        try:
            data = api_get(SCORE_URL.format(ds))
            n_fetched += 1
        except Exception:
            cur -= timedelta(days=1)
            continue

        for g in data.get("games", []):
            if g.get("gameState") not in ("OFF", "FINAL"):
                continue
            aw = normalize_abbrev(g["awayTeam"]["abbrev"])
            hm = normalize_abbrev(g["homeTeam"]["abbrev"])
            gid = g.get("id", 0)

            a1p = h1p = 0
            for gl in g.get("goals", []):
                if gl.get("period") == 1:
                    ta = extract_team_abbrev(gl.get("teamAbbrev", ""))
                    if ta == aw:
                        a1p += 1
                    elif ta == hm:
                        h1p += 1
            t1p = a1p + h1p
            u = t1p <= 2
            asc = g["awayTeam"].get("score", 0)
            hsc = g["homeTeam"].get("score", 0)
            league_total += 1
            if u:
                league_u25 += 1

            for team in (aw, hm):
                if team in teams_needed and len(team_games[team]) < GAMES_PER_TEAM:
                    ih = team == hm
                    opp = hm if team == aw else aw
                    gf = h1p if ih else a1p
                    ga = a1p if ih else h1p
                    ts = hsc if ih else asc
                    os_ = asc if ih else hsc
                    wl = "w" if ts > os_ else ("l" if ts < os_ else "otl")
                    team_games[team].append({
                        "date": ds, "game_id": gid, "opp": opp,
                        "h_a": "h" if ih else "a",
                        "gf": gf, "ga": ga, "total_1p": t1p,
                        "u25": u, "score": f"{ts}-{os_}", "wl": wl,
                        "full_total": asc + hsc,
                    })
                    gids.add(gid)

            # h2h tracking
            for a2, h2 in games_tonight:
                if (aw == a2 and hm == h2) or (aw == h2 and hm == a2):
                    key = f"{a2}@{h2}"
                    h2h.setdefault(key, []).append({
                        "date": ds, "away": aw, "home": hm,
                        "away_1p": a1p, "home_1p": h1p, "total_1p": t1p,
                    })

        if all(len(team_games[t]) >= GAMES_PER_TEAM for t in teams_needed):
            break
        cur -= timedelta(days=1)
        time.sleep(0.03)

    progress(f"  {n_fetched} dates, {league_total} games, "
             f"base rate: {league_u25}/{league_total}")
    short = [t for t in teams_needed if len(team_games[t]) < GAMES_PER_TEAM]
    if short:
        progress(f"  WARNING short: {[(t, len(team_games[t])) for t in short]}")

    return team_games, league_total, league_u25, h2h, gids


# ============================================================
# phase 2+3: boxscores + play-by-play (combined fetch)
# ============================================================

def fetch_game_details(gid):
    """fetch boxscore + play-by-play for one game."""
    result = {"game_id": gid}

    # --- boxscore ---
    try:
        d = api_get(BOX_URL.format(gid))
        for side in ("awayTeam", "homeTeam"):
            goalies = d.get("playerByGameStats", {}).get(side, {}).get("goalies", [])
            best_name, best_toi = "?", 0
            for gl in goalies:
                nm = gl.get("name", {}).get("default", "?")
                toi_sec = parse_toi(gl.get("toi", "0:00"))
                if toi_sec > best_toi:
                    best_name, best_toi = nm, toi_sec
            result[f"{side}_goalie"] = best_name
    except Exception:
        result["awayTeam_goalie"] = "?"
        result["homeTeam_goalie"] = "?"

    # --- play-by-play ---
    try:
        d = api_get(PBP_URL.format(gid))
        aw = normalize_abbrev(d.get("awayTeam", {}).get("abbrev", ""))
        hm = normalize_abbrev(d.get("homeTeam", {}).get("abbrev", ""))
        aid = d.get("awayTeam", {}).get("id")
        hid = d.get("homeTeam", {}).get("id")
        as_ = hs = ap = hp = 0
        for p in d.get("plays", []):
            if p.get("periodDescriptor", {}).get("number") != 1:
                continue
            et = p.get("typeDescKey", "")
            oid = p.get("details", {}).get("eventOwnerTeamId")
            if et in ("shot-on-goal", "goal"):
                if oid == aid:
                    as_ += 1
                elif oid == hid:
                    hs += 1
            elif et == "penalty":
                if oid == aid:
                    ap += 1
                elif oid == hid:
                    hp += 1
        result.update({"pbp_away": aw, "pbp_home": hm,
                       "away_shots": as_, "home_shots": hs,
                       "away_pen": ap, "home_pen": hp})
    except Exception:
        result.update({"pbp_away": "", "pbp_home": "",
                       "away_shots": 0, "home_shots": 0,
                       "away_pen": 0, "home_pen": 0})
    return result


def fetch_all_game_details(gids):
    """fetch boxscore + pbp for all games using threading."""
    gid_list = list(gids)
    progress(f"phase 2+3: fetching {len(gid_list)} boxscores + play-by-play...")
    results = {}
    for i in range(0, len(gid_list), BATCH_SIZE):
        batch = gid_list[i:i + BATCH_SIZE]
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
            futs = {ex.submit(fetch_game_details, g): g for g in batch}
            for f in as_completed(futs):
                r = f.result()
                results[r["game_id"]] = r
        if i + BATCH_SIZE < len(gid_list):
            time.sleep(0.5)
    progress(f"  done: {len(results)}")
    return results


# ============================================================
# phase 4: moneypuck xG
# ============================================================

def fetch_moneypuck(gids):
    """download moneypuck CSV, extract period-1 xG data."""
    progress("phase 4: downloading moneypuck xG...")
    xg = {}
    all_game_team_xgf = {}  # ALL game-teams for league avg (not just ours)
    mpok = False

    try:
        req = urllib.request.Request(MP_URL, headers=HDR)
        with urllib.request.urlopen(req, timeout=120) as r:
            zb = r.read()
        progress(f"  downloaded {len(zb) / 1024 / 1024:.1f}MB")

        # build lookup: try both full ID and offset ID
        id_set_full = set(gids)
        id_set_offset = {g - 2025000000 for g in gids}
        offset_map = {g - 2025000000: g for g in gids}

        with zipfile.ZipFile(io.BytesIO(zb)) as zf:
            cn = zf.namelist()[0]
            with zf.open(cn) as cf:
                reader = csv.DictReader(io.TextIOWrapper(cf))
                for row in reader:
                    if row.get("period", "") != "1":
                        continue

                    raw_gid = int(row.get("game_id", 0))
                    tm = row.get("teamCode", "").upper()
                    xv = float(row.get("xGoal", 0))
                    ev = row.get("event", "")

                    # track ALL game-team xGF totals for league average
                    lk = f"{raw_gid}_{tm}"
                    all_game_team_xgf[lk] = all_game_team_xgf.get(lk, 0.0) + xv

                    # map to NHL game ID (only our games)
                    if raw_gid in id_set_full:
                        nhl_gid = raw_gid
                    elif raw_gid in id_set_offset:
                        nhl_gid = offset_map[raw_gid]
                    else:
                        continue

                    k = f"{nhl_gid}_{tm}"
                    if k not in xg:
                        xg[k] = {"xgf": 0.0, "sog": 0, "hdc": 0, "goals": 0}
                    xg[k]["xgf"] += xv
                    if ev in ("SHOT", "GOAL"):
                        xg[k]["sog"] += 1
                    if ev == "GOAL":
                        xg[k]["goals"] += 1
                    if xv >= 0.20:
                        xg[k]["hdc"] += 1

        mpok = True
        progress(f"  loaded {len(xg)} game-team entries")
    except Exception as e:
        progress(f"  moneypuck failed: {e}")

    # league avg xGA = avg per-game-team xGF across ALL games in the CSV
    if all_game_team_xgf:
        league_avg_xga = sum(all_game_team_xgf.values()) / len(all_game_team_xgf)
        progress(f"  league avg xga: {league_avg_xga:.3f} "
                 f"(from {len(all_game_team_xgf)} game-team entries)")
    else:
        league_avg_xga = 0.8
    return xg, mpok, league_avg_xga


# ============================================================
# compute: per-team metrics
# ============================================================

def compute_team_metrics(teams_needed, games_tonight, team_games,
                         game_details, xg_data, mpok):
    """compute all per-team stats."""
    progress("computing per-team metrics...")
    metrics = {}

    for team in teams_needed:
        games = team_games.get(team, [])
        n = len(games)
        if n == 0:
            continue

        # tonight's role
        tonight_ha = None
        for aw, hm in games_tonight:
            if team == aw:
                tonight_ha = "a"
                break
            if team == hm:
                tonight_ha = "h"
                break

        # goalie identification from boxscores
        goalie_starts = {}
        goalie_per_game = []
        for g in games:
            gid = g["game_id"]
            gd = game_details.get(gid, {})
            if g["h_a"] == "h":
                raw = gd.get("homeTeam_goalie", "?")
            else:
                raw = gd.get("awayTeam_goalie", "?")
            # use last name
            gname = raw.lower().split()[-1] if raw and raw != "?" else "?"
            goalie_starts[gname] = goalie_starts.get(gname, 0) + 1
            goalie_per_game.append(gname)

        starter_name = max(goalie_starts, key=goalie_starts.get) if goalie_starts else "?"
        goalie_labels = ["s" if gn == starter_name else "b" for gn in goalie_per_game]

        # shots + penalties from pbp
        shots_per_game = []
        pen_per_game = []
        for g in games:
            gid = g["game_id"]
            gd = game_details.get(gid, {})
            if g["h_a"] == "h":
                sf, sa, pf = gd.get("home_shots", 0), gd.get("away_shots", 0), gd.get("home_pen", 0)
            else:
                sf, sa, pf = gd.get("away_shots", 0), gd.get("home_shots", 0), gd.get("away_pen", 0)
            shots_per_game.append(sf + sa)
            pen_per_game.append(pf)

        # xG data
        xgf_list, xga_list, hdc_list = [], [], []
        for g in games:
            gid = g["game_id"]
            xk = f"{gid}_{team}"
            xk_opp = f"{gid}_{g['opp']}"
            if xk in xg_data:
                xgf_list.append(xg_data[xk]["xgf"])
                hdc_list.append(xg_data[xk]["hdc"])
            else:
                xgf_list.append(float(g["gf"]))
                hdc_list.append(0)
            if xk_opp in xg_data:
                xga_list.append(xg_data[xk_opp]["xgf"])
            else:
                xga_list.append(float(g["ga"]))

        # weighted averages (i=0 most recent = weight 1.0, i=n-1 oldest = 0.4)
        weights = [1.0 - 0.6 * (i / max(n - 1, 1)) for i in range(n)]
        wsum = sum(weights)
        wavg_gf = sum(g["gf"] * w for g, w in zip(games, weights)) / wsum
        wavg_xgf = sum(x * w for x, w in zip(xgf_list, weights)) / wsum
        wavg_xga = sum(x * w for x, w in zip(xga_list, weights)) / wsum

        # basic stats
        r5_u25 = sum(1 for g in games[:5] if g["u25"])
        r15_u25 = sum(1 for g in games if g["u25"])
        venue_games = [g for g in games if g["h_a"] == tonight_ha]
        venue_u25 = sum(1 for g in venue_games if g["u25"])

        # system profile
        avg_1p_total = sum(g["total_1p"] for g in games) / n
        blowups = sum(1 for g in games if g["total_1p"] >= 3)
        avg_shots = sum(shots_per_game) / n if shots_per_game else 20.0
        avg_hdc = sum(hdc_list) / n

        if avg_1p_total < 1.8 and blowups <= 3:
            sys_class = "structured"
        elif avg_1p_total >= 2.5 or blowups >= 6:
            sys_class = "volatile"
        else:
            sys_class = "moderate"
        # shot validation
        if sys_class == "structured" and avg_shots > 22:
            sys_class = "moderate"
        elif sys_class == "moderate" and avg_shots <= 18 and blowups <= 3:
            sys_class = "structured"
        elif sys_class == "moderate" and avg_shots > 28:
            sys_class = "volatile"

        # discipline + rest
        avg_pen = sum(pen_per_game) / n if pen_per_game else 1.0
        last_game = datetime.strptime(games[0]["date"], "%Y-%m-%d")
        rest_days = (datetime.strptime(games_tonight[0][0], "%Y-%m-%d")
                     if False else  # placeholder
                     0)
        # compute rest from target date
        # (target_date is not directly available here, derive from context)

        metrics[team] = {
            "games": games,
            "goalie_per_game": goalie_per_game,
            "goalie_labels": goalie_labels,
            "starter_name": starter_name,
            "goalie_starts": goalie_starts,
            "shots_per_game": shots_per_game,
            "pen_per_game": pen_per_game,
            "xgf_list": [round(x, 4) for x in xgf_list],
            "xga_list": [round(x, 4) for x in xga_list],
            "hdc_list": hdc_list,
            "wavg_gf": round(wavg_gf, 3),
            "wavg_xgf": round(wavg_xgf, 3),
            "wavg_xga": round(wavg_xga, 3),
            "r5_u25": r5_u25,
            "r15_u25": r15_u25,
            "venue_u25": venue_u25,
            "venue_total": len(venue_games),
            "avg_1p_total": round(avg_1p_total, 2),
            "blowups": blowups,
            "avg_shots": round(avg_shots, 1),
            "avg_hdc": round(avg_hdc, 1),
            "sys_class": sys_class,
            "avg_pen": round(avg_pen, 2),
            "rest_days": 0,  # filled in by caller
            "tonight_ha": tonight_ha,
        }

    return metrics


# ============================================================
# compute: per-matchup analysis + confidence
# ============================================================

def compute_matchups(games_tonight, team_metrics, h2h_data,
                     league_avg_xga, base_rate, tonight_goalies):
    """compute matchup analysis and confidence scores."""
    progress("computing matchups...")
    matchups = []

    for away, home in games_tonight:
        am = team_metrics.get(away)
        hm = team_metrics.get(home)
        if not am or not hm:
            continue

        # combined stats
        comb_r5 = am["r5_u25"] + hm["r5_u25"]
        comb_r5_pct = comb_r5 / 10 * 100
        comb_r15 = am["r15_u25"] + hm["r15_u25"]
        comb_r15_n = len(am["games"]) + len(hm["games"])
        comb_r15_pct = comb_r15 / comb_r15_n * 100 if comb_r15_n > 0 else 0

        # h2h
        h2h_key = f"{away}@{home}"
        h2h_games = h2h_data.get(h2h_key, [])

        # poisson (xG-based, opponent-adjusted)
        la_raw = am["wavg_xgf"]
        lb_raw = hm["wavg_xgf"]
        la_adj = la_raw * (hm["wavg_xga"] / league_avg_xga) if league_avg_xga > 0 else la_raw
        lb_adj = lb_raw * (am["wavg_xga"] / league_avg_xga) if league_avg_xga > 0 else lb_raw
        poisson_pct = p_u25(la_adj, lb_adj) * 100
        poisson_edge = poisson_pct - base_rate

        # b2b
        b2b_teams = []
        if am["rest_days"] == 1:
            b2b_teams.append(away)
        if hm["rest_days"] == 1:
            b2b_teams.append(home)

        # ----- confidence scoring -----
        # factor 1: combined recent 5 (0-3)
        if comb_r5_pct >= 90:    f_r5 = 3
        elif comb_r5_pct >= 70:  f_r5 = 2
        elif comb_r5_pct >= 50:  f_r5 = 1
        else:                    f_r5 = 0

        # factor 2: combined last 15 (0-3)
        if comb_r15_pct >= 80:   f_r15 = 3
        elif comb_r15_pct >= 70: f_r15 = 2
        elif comb_r15_pct >= 60: f_r15 = 1
        else:                    f_r15 = 0

        # factor 3: poisson (-1 to +2), edge-based
        if poisson_edge >= 8:    f_poi = 2
        elif poisson_edge >= 2:  f_poi = 1
        elif poisson_edge >= -3: f_poi = 0
        else:                    f_poi = -1

        # factor 4: system profile (-1 to +1)
        sys_map = {"structured": 1, "moderate": 0, "volatile": -1}
        sys_sum = sys_map.get(am["sys_class"], 0) + sys_map.get(hm["sys_class"], 0)
        f_sys = 1 if sys_sum >= 1 else (-1 if sys_sum <= -1 else 0)

        # factor 5: goalie matchup (-1 to +1)
        aw_goalie = tonight_goalies.get(away, am["starter_name"])
        hm_goalie = tonight_goalies.get(home, hm["starter_name"])
        aw_goalie_ln = aw_goalie.lower().split()[-1] if aw_goalie else "?"
        hm_goalie_ln = hm_goalie.lower().split()[-1] if hm_goalie else "?"
        aw_elite = aw_goalie_ln in ELITE_GOALIES
        hm_elite = hm_goalie_ln in ELITE_GOALIES
        aw_starts = am["goalie_starts"].get(aw_goalie_ln, 0)
        hm_starts = hm["goalie_starts"].get(hm_goalie_ln, 0)
        aw_backup = aw_starts <= 2  # ≤2 starts in 15-game window = true backup
        hm_backup = hm_starts <= 2

        if (aw_elite or hm_elite) and not aw_backup and not hm_backup:
            f_goalie = 1
        elif (aw_elite and hm_backup) or (hm_elite and aw_backup):
            f_goalie = 0
        elif not aw_backup and not hm_backup:
            f_goalie = 0
        else:
            f_goalie = -1

        # factor 6: rest (-1 to 0)
        f_rest = -1 if (am["rest_days"] >= 3 or hm["rest_days"] >= 3) else 0

        # factor 7: discipline (-1 to +1)
        comb_pen = am["avg_pen"] + hm["avg_pen"]
        if comb_pen <= 1.5:    f_disc = 1
        elif comb_pen > 2.5:   f_disc = -1
        else:                  f_disc = 0

        # factor 8: context (always 0 — claude applies manually)
        f_ctx = 0

        total_conf = max(0, min(12,
            f_r5 + f_r15 + f_poi + f_sys + f_goalie + f_rest + f_disc + f_ctx))

        matchups.append({
            "away": away, "home": home,
            "comb_r5": comb_r5, "comb_r5_pct": round(comb_r5_pct, 1),
            "comb_r15": comb_r15, "comb_r15_pct": round(comb_r15_pct, 1),
            "h2h": h2h_games[:3],
            "lambda_a": round(la_adj, 4), "lambda_a_raw": round(la_raw, 4),
            "lambda_b": round(lb_adj, 4), "lambda_b_raw": round(lb_raw, 4),
            "opp_xga_factor_a": round(hm["wavg_xga"] / league_avg_xga, 2) if league_avg_xga > 0 else 1.0,
            "opp_xga_factor_b": round(am["wavg_xga"] / league_avg_xga, 2) if league_avg_xga > 0 else 1.0,
            "poisson_pct": round(poisson_pct, 1),
            "poisson_edge": round(poisson_edge, 1),
            "b2b_teams": b2b_teams,
            "aw_goalie": aw_goalie_ln, "hm_goalie": hm_goalie_ln,
            "aw_backup": aw_backup, "hm_backup": hm_backup,
            "aw_goalie_starts": aw_starts, "hm_goalie_starts": hm_starts,
            "confidence": total_conf,
            "factors": {
                "r5": f_r5, "r15": f_r15, "poi": f_poi, "sys": f_sys,
                "goalie": f_goalie, "rest": f_rest, "disc": f_disc, "ctx": f_ctx,
            },
        })

    matchups.sort(key=lambda x: x["confidence"], reverse=True)
    return matchups


# ============================================================
# main
# ============================================================

def main():
    parser = argparse.ArgumentParser(description="NHL 1P U2.5 analysis engine")
    parser.add_argument("date", help="target date YYYY-MM-DD")
    parser.add_argument("--goalies", default="{}", help='JSON: {"TEAM":"goalie_lastname",...}')
    args = parser.parse_args()

    target_date = args.date
    tonight_goalies = json.loads(args.goalies)
    # normalize goalie keys
    tonight_goalies = {normalize_abbrev(k): v for k, v in tonight_goalies.items()}

    t0 = time.time()

    # fetch tonight's games
    games_tonight = fetch_todays_games(target_date)
    if not games_tonight:
        json.dump({"error": "no games found", "target_date": target_date}, sys.stdout)
        sys.exit(1)

    teams_needed = set()
    for a, h in games_tonight:
        teams_needed.add(a)
        teams_needed.add(h)

    # phase 1: score walking
    team_games, league_total, league_u25, h2h, gids = walk_scores(
        target_date, teams_needed, games_tonight)
    base_rate = league_u25 / league_total * 100 if league_total > 0 else 70.0

    # phase 2+3: boxscores + play-by-play
    game_details = fetch_all_game_details(gids)

    # phase 4: moneypuck xG
    xg_data, mpok, league_avg_xga = fetch_moneypuck(gids)

    # compute per-team metrics
    target_dt = datetime.strptime(target_date, "%Y-%m-%d")
    metrics = compute_team_metrics(
        teams_needed, games_tonight, team_games, game_details, xg_data, mpok)
    # fill in rest_days
    for team, m in metrics.items():
        if m["games"]:
            last = datetime.strptime(m["games"][0]["date"], "%Y-%m-%d")
            m["rest_days"] = (target_dt - last).days

    # compute matchups
    matchups = compute_matchups(
        games_tonight, metrics, h2h, league_avg_xga, base_rate, tonight_goalies)

    elapsed = time.time() - t0
    progress(f"\ndone in {elapsed:.1f}s")

    # assemble output
    # strip non-serializable data and trim games for output
    teams_out = {}
    for team, m in metrics.items():
        teams_out[team] = {
            "games": m["games"],
            "goalie_labels": m["goalie_labels"],
            "starter_name": m["starter_name"],
            "goalie_starts": m["goalie_starts"],
            "r5_u25": m["r5_u25"],
            "r15_u25": m["r15_u25"],
            "venue_u25": m["venue_u25"],
            "venue_total": m["venue_total"],
            "wavg_gf": m["wavg_gf"],
            "wavg_xgf": m["wavg_xgf"],
            "wavg_xga": m["wavg_xga"],
            "avg_1p_total": m["avg_1p_total"],
            "blowups": m["blowups"],
            "avg_shots": m["avg_shots"],
            "avg_hdc": m["avg_hdc"],
            "sys_class": m["sys_class"],
            "avg_pen": m["avg_pen"],
            "rest_days": m["rest_days"],
            "tonight_ha": m["tonight_ha"],
        }

    output = {
        "target_date": target_date,
        "games_tonight": games_tonight,
        "league_total": league_total,
        "league_u25": league_u25,
        "base_rate": round(base_rate, 1),
        "league_avg_xga": round(league_avg_xga, 4),
        "moneypuck_ok": mpok,
        "teams": teams_out,
        "matchups": matchups,
        "elapsed_seconds": round(elapsed, 1),
    }

    json.dump(output, sys.stdout)


if __name__ == "__main__":
    main()
