#!/usr/bin/env python3
"""build the full-season point-in-time dataset for 1p u2.5 factor research.

one row per final game, oct 2025 → today. every feature is computed from
information available BEFORE that game (point-in-time correctness):

  - rolling r5/r15 u2.5 per team + de-duped combined (engine semantics)
  - venue splits (home team's last-10 home games, away team's last-10 road)
  - rolling 1p goal/sog/xg environment (r15, both teams combined)
  - rest days / b2b per team
  - h2h last-meeting 1p result
  - start time (ET hour via America/New_York), day of week, weekend flag
  - goalie starters per game derived from the moneypuck shot file (the
    goalie facing each side's first 1p shot), classified by STARTS SHARE
    TO DATE (≥60% starter / 40-59 tandem / <40 backup, ≥10 team games) —
    no end-of-season leakage
  - total_line where a logged run recorded one (feb 26+ subset)

output: research/season_dataset.csv + a stderr progress log.
score fetches reuse the engine's .cache/scores bucket (read + populate).

usage:
    python3 research/build_dataset.py                 # through yesterday
    python3 research/build_dataset.py --end 2026-06-11
"""

import json, sys, os, csv, io, zipfile, argparse, time, urllib.request
from datetime import datetime, timedelta, date as date_cls
from zoneinfo import ZoneInfo
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from record import read_log  # noqa: E402

CACHE_DIR = os.path.join(ROOT, ".cache")
OUT_CSV = os.path.join(ROOT, "research", "season_dataset.csv")
SCORE_URL = "https://api-web.nhle.com/v1/score/{}"
HDR = {"User-Agent": "Mozilla/5.0"}
SEASON_START = "2025-10-07"
OLYMPIC_BREAK = ("2026-02-07", "2026-02-22")
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
    only dates < today-1 are cached (matches engine policy)."""
    p = cache_path("scores", ds)
    if os.path.exists(p):
        with open(p) as f:
            return json.load(f)
    data = api_get(SCORE_URL.format(ds))
    if ds < (datetime.strptime(today_str, "%Y-%m-%d") - timedelta(days=1)).strftime("%Y-%m-%d"):
        with open(p, "w") as f:
            json.dump(data, f)
    return data


def extract_team_abbrev(val):
    if isinstance(val, dict):
        return val.get("default", "")
    return str(val)


# ── moneypuck: per-game 1p starters, sog, xg ──

def load_moneypuck():
    """parse the cached moneypuck shots zip. returns:
      starters: {gid: {"away": lastname, "home": lastname}}
      p1: {gid: {"away_sog","home_sog","away_xg","home_xg"}}
    gid = full NHL game id (2025xxxxxx)."""
    zpath = os.path.join(CACHE_DIR, "moneypuck", "shots_2025.zip")
    if not os.path.exists(zpath):
        progress("  no moneypuck cache — goalie/sog/xg features will be blank")
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
                progress(f"  moneypuck columns missing {missing} — have {cols[:25]}")
                return {}, {}
            for row in reader:
                try:
                    gid = 2025000000 + int(row["game_id"])
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


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--end", default=None, help="last date to include (YYYY-MM-DD)")
    args = parser.parse_args()

    today = datetime.now().strftime("%Y-%m-%d")
    end = args.end or (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

    progress("loading moneypuck shots...")
    mp_starters, mp_p1 = load_moneypuck()

    # lines from picks_log: (date, "aw @ hm") -> total_line
    line_lookup = {}
    for e in read_log():
        if e.get("total_line") is not None:
            line_lookup[(e["date"], e["game"])] = e["total_line"]
    progress(f"  lines from picks_log: {len(line_lookup)}")

    # ── pass 1: collect all final games chronologically ──
    progress("walking season scores...")
    games = []
    ob_s, ob_e = OLYMPIC_BREAK
    cur = datetime.strptime(SEASON_START, "%Y-%m-%d")
    end_dt = datetime.strptime(end, "%Y-%m-%d")
    n_dates = 0
    while cur <= end_dt:
        ds = cur.strftime("%Y-%m-%d")
        if ob_s <= ds <= ob_e:
            cur += timedelta(days=1)
            continue
        try:
            data = get_scores_for_date(ds, today)
            n_dates += 1
        except Exception as exc:
            progress(f"  {ds}: fetch failed ({exc}) — skipping")
            cur += timedelta(days=1)
            continue
        for g in data.get("games", []):
            if g.get("gameState") not in ("OFF", "FINAL"):
                continue
            gtype = g.get("gameType", 2)
            if gtype not in (2, 3):  # skip preseason/all-star
                continue
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

        rows.append({
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

    # ── write ──
    cols = list(rows[0].keys())
    with open(OUT_CSV, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)
    progress(f"wrote {len(rows)} rows -> {OUT_CSV}")

    u25 = sum(r["u25"] for r in rows)
    progress(f"season 1p u2.5 base rate: {u25}/{len(rows)} = {100*u25/len(rows):.1f}%")
    with_goalies = sum(1 for r in rows if r["goalie_pair"])
    with_lines = sum(1 for r in rows if r["total_line"] != "")
    progress(f"rows with goalie pair: {with_goalies} | with lines: {with_lines}")


if __name__ == "__main__":
    main()
