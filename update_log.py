#!/usr/bin/env python3
"""add or replace entries in picks_log.jsonl for a given date.

usage:
    python3 update_log.py 2026-04-01 '[{"game":"stl @ lak","confidence":4,...}, ...]'

removes all existing entries for TARGET_DATE (re-runs replace, never
duplicate). entries with a "result" field are never touched. appends
new entries from the JSON argument.

each entry must have at minimum: game, confidence, model.
the script adds: date, pick ("1p u2.5").
"""

import json, sys, argparse

LOG_PATH = "/Users/raz/claude/nhl/picks_log.jsonl"


def main():
    parser = argparse.ArgumentParser(description="update picks_log.jsonl")
    parser.add_argument("target_date", help="YYYY-MM-DD")
    parser.add_argument("entries_json", help="JSON array of new entries")
    args = parser.parse_args()

    target_date = args.target_date
    new_entries = json.loads(args.entries_json)

    # load existing log
    with open(LOG_PATH, "r") as f:
        entries = [json.loads(l) for l in f if l.strip()]

    # remove existing entries for target_date that DON'T have results
    # (resolved entries are sacred — never touch them)
    kept = [e for e in entries if not (e["date"] == target_date and "result" not in e)]
    removed = len(entries) - len(kept)

    # add new entries with standard fields
    added = 0
    for ne in new_entries:
        entry = {
            "date": target_date,
            "game": ne["game"],
            "pick": "1p u2.5",
            "confidence": ne["confidence"],
            "poisson_pct": ne.get("poisson_pct", 0),
            "base_rate_pct": ne.get("base_rate_pct", 0),
            "combined_recent5_pct": ne.get("combined_recent5_pct", 0),
            "combined_last15_pct": ne.get("combined_last15_pct", 0),
            "total_line": ne.get("total_line"),
            "model": ne.get("model", "v4"),
        }
        # optional fields
        if "tier" in ne:
            entry["tier"] = ne["tier"]
        if "reason" in ne:
            entry["reason"] = ne["reason"]
        kept.append(entry)
        added += 1

    # write back
    with open(LOG_PATH, "w") as f:
        for e in kept:
            f.write(json.dumps(e) + "\n")

    result = {"removed": removed, "added": added, "total": len(kept)}
    print(json.dumps(result))


if __name__ == "__main__":
    main()
