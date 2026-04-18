#!/usr/bin/env python3
"""resolve yesterday's picks against actual scores + compute season record.

usage:
    python3 resolve_results.py 2026-04-01

resolves entries for TARGET_DATE - 1. fetches actual 1p scores from
nhl api, updates picks_log.jsonl with result + actual_1p_total, and
prints a JSON summary of yesterday's results + season record to stdout.

output JSON schema:
{
    "yesterday": "2026-03-31",
    "resolved": [{"game":"...","result":"win","actual_1p_total":2,"confidence":5,"tier":null}, ...],
    "parlay_result": "win" | "loss" | "no_parlay",
    "record": {
        "parlay_w": 2, "parlay_l": 0,
        "leg_w": 4, "leg_l": 0,
        "c4_w": 4, "c4_l": 0,
        "c5_w": 4, "c5_l": 0,
        "hm_w": 7, "hm_l": 9,
        "av_w": 16, "av_l": 1
    }
}
"""

import json, sys, os, urllib.request, argparse, tempfile, shutil
from datetime import datetime, timedelta
from collections import defaultdict

LOG_PATH = "/Users/raz/claude/nhl/picks_log.jsonl"
SCORE_URL = "https://api-web.nhle.com/v1/score/{}"
BOXSCORE_URL = "https://api-web.nhle.com/v1/gamecenter/{}/boxscore"
RIGHTRAIL_URL = "https://api-web.nhle.com/v1/gamecenter/{}/right-rail"
HDR = {"User-Agent": "Mozilla/5.0"}


def api_get(url, timeout=20):
    req = urllib.request.Request(url, headers=HDR)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def read_log():
    """read picks_log.jsonl with error handling for malformed lines."""
    entries = []
    with open(LOG_PATH, "r") as f:
        for line_no, line in enumerate(f, 1):
            if not line.strip():
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError as e:
                print(f"warning: line {line_no} is invalid JSON, skipping: {e}", file=sys.stderr)
    return entries


def write_log(entries):
    """write picks_log.jsonl atomically (temp file + rename)."""
    fd, tmp_path = tempfile.mkstemp(dir=os.path.dirname(LOG_PATH), suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            for e in entries:
                f.write(json.dumps(e) + "\n")
        shutil.move(tmp_path, LOG_PATH)
    except Exception:
        os.unlink(tmp_path)
        raise


def normalize_abbrev(abbrev):
    """normalize team abbreviations to match log format."""
    mapping = {"ARI": "UTA", "PHX": "UTA"}
    return mapping.get(abbrev.upper(), abbrev.upper())


def get_officials(game_id):
    """fetch referee names from the right-rail endpoint. returns
    {"referees": [name, name], "linesmen": [name, name]} or {} on failure.
    tracking officials lets us later analyze whether specific crews produce
    higher/lower 1p scoring (some crews call 30%+ more penalties → more pp)."""
    try:
        data = api_get(RIGHTRAIL_URL.format(game_id), timeout=15)
    except Exception:
        return {}
    gi = data.get("gameInfo") or {}
    refs = [(r.get("default") or "").strip() for r in (gi.get("referees") or []) if r]
    lines = [(l.get("default") or "").strip() for l in (gi.get("linesmen") or []) if l]
    out = {}
    if any(refs):
        out["referees"] = [r for r in refs if r]
    if any(lines):
        out["linesmen"] = [l for l in lines if l]
    return out


def get_starting_goalies(game_id):
    """fetch starting goalies for a completed game via the boxscore endpoint.
    returns {"away": "lastname", "home": "lastname"} or {} on failure.
    name.default on this endpoint is formatted "J. Oettinger" — we split on
    whitespace and take the last token to get just the surname."""
    try:
        data = api_get(BOXSCORE_URL.format(game_id), timeout=15)
    except Exception:
        return {}
    pbs = data.get("playerByGameStats") or {}
    out = {}
    for side, key in (("awayTeam", "away"), ("homeTeam", "home")):
        for g in pbs.get(side, {}).get("goalies", []):
            if g.get("starter"):
                name = (g.get("name") or {}).get("default", "").strip()
                last = name.split()[-1] if name else ""
                if last:
                    out[key] = last.lower()
                break
    return out


def get_game_actuals(date_str):
    """fetch per-game actuals for a date: 1p total, away/home 1p split,
    game_id, and starting goalies. returns {game_key: {...}}."""
    data = api_get(SCORE_URL.format(date_str))
    out = {}
    for g in data.get("games", []):
        state = g.get("gameState", "")
        if state not in ("OFF", "FINAL"):
            continue
        away = normalize_abbrev(g["awayTeam"]["abbrev"]).lower()
        home = normalize_abbrev(g["homeTeam"]["abbrev"]).lower()
        away_abbr = g["awayTeam"]["abbrev"]
        home_abbr = g["homeTeam"]["abbrev"]
        away_1p = 0
        home_1p = 0
        for goal in g.get("goals", []):
            if goal.get("period") != 1:
                continue
            team = (goal.get("teamAbbrev") or "").upper()
            # teamAbbrev may be a dict in newer api versions
            if isinstance(goal.get("teamAbbrev"), dict):
                team = goal["teamAbbrev"].get("default", "").upper()
            if team == away_abbr.upper():
                away_1p += 1
            elif team == home_abbr.upper():
                home_1p += 1
        game_id = g.get("id")
        goalies = get_starting_goalies(game_id) if game_id else {}
        officials = get_officials(game_id) if game_id else {}
        game_key = f"{away} @ {home}"
        out[game_key] = {
            "total_1p": away_1p + home_1p,
            "away_1p": away_1p,
            "home_1p": home_1p,
            "game_id": game_id,
            "actual_goalie_away": goalies.get("away"),
            "actual_goalie_home": goalies.get("home"),
            "referees": officials.get("referees"),
            "linesmen": officials.get("linesmen"),
        }
    return out


def compute_season_record(entries):
    """compute v4 season record from all log entries."""
    v4_picks = [e for e in entries if e.get("model") == "v4" and "result" in e and "tier" not in e]
    v4_hm = [e for e in entries if e.get("model") == "v4" and "result" in e and e.get("tier") == "honorable_mention"]
    v4_avoid = [e for e in entries if e.get("model") == "v4" and "result" in e and e.get("tier") == "avoid"]

    parlay_dates = defaultdict(list)
    for e in v4_picks:
        parlay_dates[e["date"]].append(e["result"])
    parlay_w = sum(1 for legs in parlay_dates.values() if len(legs) >= 2 and all(r == "win" for r in legs))
    parlay_l = sum(1 for legs in parlay_dates.values() if len(legs) >= 2 and any(r == "loss" for r in legs))

    return {
        "parlay_w": parlay_w,
        "parlay_l": parlay_l,
        "leg_w": sum(1 for e in v4_picks if e["result"] == "win"),
        "leg_l": sum(1 for e in v4_picks if e["result"] == "loss"),
        "c4_w": sum(1 for e in v4_picks if e["result"] == "win" and e.get("confidence", 0) >= 4),
        "c4_l": sum(1 for e in v4_picks if e["result"] == "loss" and e.get("confidence", 0) >= 4),
        "c5_w": sum(1 for e in v4_picks if e["result"] == "win" and e.get("confidence", 0) >= 5),
        "c5_l": sum(1 for e in v4_picks if e["result"] == "loss" and e.get("confidence", 0) >= 5),
        "hm_w": sum(1 for e in v4_hm if e["result"] == "win"),
        "hm_l": sum(1 for e in v4_hm if e["result"] == "loss"),
        "av_w": sum(1 for e in v4_avoid if e["result"] == "win"),
        "av_l": sum(1 for e in v4_avoid if e["result"] == "loss"),
    }


def main():
    parser = argparse.ArgumentParser(description="resolve yesterday's results")
    parser.add_argument("target_date", help="YYYY-MM-DD (yesterday = target - 1)")
    args = parser.parse_args()

    target = datetime.strptime(args.target_date, "%Y-%m-%d")
    yesterday = (target - timedelta(days=1)).strftime("%Y-%m-%d")

    # load log
    entries = read_log()

    # find unresolved entries for yesterday
    unresolved = [e for e in entries if e["date"] == yesterday and "result" not in e]

    if not unresolved:
        # nothing to resolve — just compute record and output
        record = compute_season_record(entries)
        result = {
            "yesterday": yesterday,
            "resolved": [],
            "parlay_result": "no_games",
            "record": record,
        }
        print(json.dumps(result))
        return

    # fetch actual scores + starting goalies + home/away 1p splits
    try:
        actuals = get_game_actuals(yesterday)
    except Exception as e:
        print(json.dumps({"error": f"failed to fetch scores for {yesterday}: {e}"}), file=sys.stderr)
        sys.exit(1)

    # resolve each entry — we now record:
    #   actual_1p_total, away_1p_goals, home_1p_goals
    #   actual_goalie_away, actual_goalie_home (to detect dfo misses)
    #   goalie_prediction_hit (bool: did our predicted goalies match actuals on both sides?)
    resolved = []
    for e in entries:
        if e["date"] == yesterday and "result" not in e:
            game = e["game"]
            if game in actuals:
                act = actuals[game]
                total = act["total_1p"]
                e["actual_1p_total"] = total
                e["away_1p_goals"] = act["away_1p"]
                e["home_1p_goals"] = act["home_1p"]
                e["result"] = "win" if total <= 2 else "loss"
                if act.get("actual_goalie_away"):
                    e["actual_goalie_away"] = act["actual_goalie_away"]
                if act.get("actual_goalie_home"):
                    e["actual_goalie_home"] = act["actual_goalie_home"]
                if act.get("referees"):
                    e["referees"] = act["referees"]
                if act.get("linesmen"):
                    e["linesmen"] = act["linesmen"]
                if act.get("game_id"):
                    e["game_id"] = act["game_id"]
                # goalie-prediction-hit: compare predicted vs actual (last-name match).
                # only set if we recorded a prediction — legacy entries skip this.
                pred_a = (e.get("aw_goalie") or "").lower()
                pred_h = (e.get("hm_goalie") or "").lower()
                act_a = (act.get("actual_goalie_away") or "").lower()
                act_h = (act.get("actual_goalie_home") or "").lower()
                if pred_a and pred_h and act_a and act_h:
                    e["goalie_prediction_hit"] = (pred_a == act_a and pred_h == act_h)
                resolved.append({
                    "game": game,
                    "result": e["result"],
                    "actual_1p_total": total,
                    "confidence": e.get("confidence"),
                    "tier": e.get("tier"),
                })
            else:
                # phantom entry — game doesn't exist on this date
                print(f"warning: {game} not found on {yesterday}, removing from log", file=sys.stderr)
                e["_remove"] = True

    # remove phantom entries
    entries = [e for e in entries if not e.get("_remove")]

    # write updated log (atomic)
    write_log(entries)

    # compute parlay result for yesterday
    picks_y = [r for r in resolved if r["tier"] is None]
    if len(picks_y) >= 2:
        parlay_result = "win" if all(r["result"] == "win" for r in picks_y) else "loss"
    elif len(picks_y) == 1:
        parlay_result = "no_parlay"
    else:
        parlay_result = "no_parlay"

    record = compute_season_record(entries)

    result = {
        "yesterday": yesterday,
        "resolved": resolved,
        "parlay_result": parlay_result,
        "record": record,
    }
    print(json.dumps(result))


if __name__ == "__main__":
    main()
