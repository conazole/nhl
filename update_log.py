#!/usr/bin/env python3
"""add or replace entries in picks_log.jsonl for a given date.

usage:
    python3 update_log.py 2026-04-01 /tmp/engine_output.json
    python3 update_log.py 2026-04-01 '[{"game":"stl @ lak","confidence":4,...}]'

accepts either a file path (engine JSON with "matchups" array) or a raw
JSON string. removes all existing entries for TARGET_DATE (re-runs replace,
never duplicate). entries with a "result" field are never touched.

each entry must have at minimum: game, confidence.
the script adds: date, pick ("1p u2.5"), model ("v4" default).
"""

import json, sys, os, argparse, tempfile, shutil

LOG_PATH = "/Users/raz/claude/nhl/picks_log.jsonl"


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


def entries_from_engine(data):
    """extract log entries from engine JSON output."""
    entries = []
    for m in data["matchups"]:
        away = m["away"].lower()
        home = m["home"].lower()
        conf = m["confidence"]

        entry = {
            "game": f"{away} @ {home}",
            "confidence": conf,
            "total_line": m.get("total_line"),
            "combined_recent5_pct": m.get("comb_r5_pct", 0),
            "combined_last15_pct": m.get("comb_r15_pct", 0),
            "poisson_pct": m.get("poisson_pct", 0),
        }
        if conf < 2:
            entry["tier"] = "avoid"
        elif conf < 4:
            entry["tier"] = "honorable_mention"
        entries.append(entry)
    return entries


def load_entries(arg):
    """load entries from a file path or raw JSON string."""
    # try as file path first
    if os.path.isfile(arg):
        with open(arg) as f:
            content = f.read().strip()
        # engine output may have stderr before JSON — find the JSON
        for start_key in ['{"target_date"', '[{']:
            idx = content.find(start_key)
            if idx >= 0:
                content = content[idx:]
                break
        data = json.loads(content)
        # if it's engine output (has "matchups"), convert
        if isinstance(data, dict) and "matchups" in data:
            return entries_from_engine(data)
        # otherwise treat as raw entries array
        return data
    # raw JSON string
    return json.loads(arg)


def main():
    parser = argparse.ArgumentParser(description="update picks_log.jsonl")
    parser.add_argument("target_date", help="YYYY-MM-DD")
    parser.add_argument("entries", help="engine JSON file path or JSON array string")
    args = parser.parse_args()

    target_date = args.target_date
    new_entries = load_entries(args.entries)

    # load existing log
    entries = read_log()

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

    # write back (atomic)
    write_log(kept)

    result = {"removed": removed, "added": added, "total": len(kept)}
    print(json.dumps(result))


if __name__ == "__main__":
    main()
