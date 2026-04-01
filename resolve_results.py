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


def get_1p_totals(date_str):
    """fetch 1p goal totals for all games on a date. returns {game_key: 1p_total}."""
    data = api_get(SCORE_URL.format(date_str))
    totals = {}
    for g in data.get("games", []):
        state = g.get("gameState", "")
        if state not in ("OFF", "FINAL"):
            continue
        away = normalize_abbrev(g["awayTeam"]["abbrev"]).lower()
        home = normalize_abbrev(g["homeTeam"]["abbrev"]).lower()
        goals_1p = sum(1 for goal in g.get("goals", []) if goal.get("period") == 1)
        game_key = f"{away} @ {home}"
        totals[game_key] = goals_1p
    return totals


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

    # fetch actual scores
    try:
        actuals = get_1p_totals(yesterday)
    except Exception as e:
        print(json.dumps({"error": f"failed to fetch scores for {yesterday}: {e}"}), file=sys.stderr)
        sys.exit(1)

    # resolve each entry
    resolved = []
    for e in entries:
        if e["date"] == yesterday and "result" not in e:
            game = e["game"]
            if game in actuals:
                total = actuals[game]
                e["actual_1p_total"] = total
                e["result"] = "win" if total <= 2 else "loss"
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
