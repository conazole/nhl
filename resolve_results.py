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

import json, sys, urllib.request, argparse
from datetime import datetime, timedelta

from record import (read_log, write_log, compute_season_record,
                    parlay_outcome_for_date, tier_of, check_invariants)

SCORE_URL = "https://api-web.nhle.com/v1/score/{}"
BOXSCORE_URL = "https://api-web.nhle.com/v1/gamecenter/{}/boxscore"
RIGHTRAIL_URL = "https://api-web.nhle.com/v1/gamecenter/{}/right-rail"
HDR = {"User-Agent": "Mozilla/5.0"}


def api_get(url, timeout=20):
    req = urllib.request.Request(url, headers=HDR)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


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
    name.default on this endpoint is formatted "J. Oettinger" · we split on
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


def resolve_date(entries, date_str):
    """resolve all unresolved entries for one date against actual scores.
    mutates entries in place. returns list of per-entry resolution summaries.
    postponed/missing games are marked result="void" (never deleted · the log
    is a real-money audit trail)."""
    actuals = get_game_actuals(date_str)
    resolved = []
    for e in entries:
        if e["date"] != date_str or "result" in e:
            continue
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
            # only set if we recorded a prediction · legacy entries skip this.
            pred_a = (e.get("aw_goalie") or "").lower()
            pred_h = (e.get("hm_goalie") or "").lower()
            act_a = (act.get("actual_goalie_away") or "").lower()
            act_h = (act.get("actual_goalie_home") or "").lower()
            if pred_a and pred_h and act_a and act_h:
                e["goalie_prediction_hit"] = (pred_a == act_a and pred_h == act_h)
        else:
            # game not found on this date · postponed/rescheduled/bad key.
            # void it rather than delete: w/l counts skip voids, but the
            # entry (and why it produced no result) stays auditable.
            print(f"warning: {game} not found on {date_str}, marking void", file=sys.stderr)
            e["result"] = "void"
            e["void_reason"] = f"game not found on {date_str}"
        resolved.append({
            "date": date_str,
            "game": game,
            "result": e["result"],
            "actual_1p_total": e.get("actual_1p_total"),
            "confidence": e.get("confidence"),
            "tier": e.get("tier"),
        })
    return resolved


def main():
    parser = argparse.ArgumentParser(description="resolve unresolved past results")
    parser.add_argument("target_date", help="YYYY-MM-DD (resolves all unresolved dates < target)")
    args = parser.parse_args()

    target = datetime.strptime(args.target_date, "%Y-%m-%d")
    yesterday = (target - timedelta(days=1)).strftime("%Y-%m-%d")

    # load log
    entries = read_log()

    # sweep ALL unresolved dates strictly before target · not just yesterday.
    # gap days (no run the morning after) used to leave entries dangling
    # forever; the apr 9 2026 slate sat unresolved for 2 months and the
    # season record was missing a winning parlay because of it.
    unresolved_dates = sorted({
        e["date"] for e in entries
        if e["date"] < args.target_date and "result" not in e
    })

    if not unresolved_dates:
        record = compute_season_record(entries)
        warnings = check_invariants(entries, before_date=args.target_date)
        result = {
            "yesterday": yesterday,
            "resolved_dates": [],
            "resolved": [],
            "parlay_result": "no_games",
            "record": record,
            "invariant_warnings": warnings,
        }
        print(json.dumps(result))
        return

    resolved = []
    failed_dates = []
    for d in unresolved_dates:
        try:
            resolved.extend(resolve_date(entries, d))
        except Exception as exc:
            # a single bad date (api hiccup) must not block the others ·
            # it stays unresolved and the invariant check keeps flagging it.
            print(f"warning: failed to resolve {d}: {exc}", file=sys.stderr)
            failed_dates.append(d)

    # write updated log (atomic)
    write_log(entries)

    # parlay result for yesterday specifically (the postmortem subject) ·
    # graded by the shared rule over ALL of yesterday's picks: a lost top-2
    # leg is a loss even if the other leg voided or is still pending.
    picks_y = [e for e in entries
               if e["date"] == yesterday and tier_of(e) == "pick"
               and e.get("model") == "v4"]
    parlay_result, _top2 = parlay_outcome_for_date(picks_y)

    record = compute_season_record(entries)
    warnings = check_invariants(entries, before_date=args.target_date)

    result = {
        "yesterday": yesterday,
        "resolved_dates": [d for d in unresolved_dates if d not in failed_dates],
        "failed_dates": failed_dates,
        "resolved": resolved,
        "parlay_result": parlay_result,
        "record": record,
        "invariant_warnings": warnings,
    }
    print(json.dumps(result))


if __name__ == "__main__":
    main()
