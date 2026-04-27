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
    """extract log entries from engine JSON output.
    persists everything we'll want for later backtesting:
      - factors dict (r5/r15/goalie/line individual scores)
      - goalie_pair + per-team classification + predicted goalies + confirmed flags
      - is_playoff + series_info (round, game_num, seeds, series score)
    old log entries simply lack these fields — consumers must use .get() with defaults."""
    entries = []
    for m in data["matchups"]:
        away = m["away"].lower()
        home = m["home"].lower()
        conf = m["confidence"]

        factors = m.get("factors") or {}
        entry = {
            "game": f"{away} @ {home}",
            "confidence": conf,
            "total_line": m.get("total_line"),
            "combined_recent5_pct": m.get("comb_r5_pct", 0),
            "combined_last15_pct": m.get("comb_r15_pct", 0),
            "poisson_pct": m.get("poisson_pct", 0),

            # factor breakdown (v4.2+): individual contributions so we can backtest weights
            "factors": {
                "r5": factors.get("r5"),
                "r15": factors.get("r15"),
                "goalie": factors.get("goalie"),
                "line": factors.get("line"),
            },

            # goalie prediction state (what we believed when the pick was made)
            "goalie_pair": factors.get("goalie_pair"),
            "aw_goalie": m.get("aw_goalie"),
            "hm_goalie": m.get("hm_goalie"),
            "aw_goalie_cls": m.get("aw_goalie_cls"),
            "hm_goalie_cls": m.get("hm_goalie_cls"),
            "aw_confirmed": m.get("aw_confirmed", False),
            "hm_confirmed": m.get("hm_confirmed", False),

            # playoff / series state
            "is_playoff": bool(m.get("is_playoff")),
        }
        if m.get("is_playoff") and m.get("series_info"):
            entry["series_info"] = m.get("series_info")

        if conf < 2:
            entry["tier"] = "avoid"
        elif conf < 4:
            entry["tier"] = "honorable_mention"
        entries.append(entry)

    # parlay is always 2-leg, top 2 by (confidence, r5%).
    # n==1: solo qualifier becomes HM (no parlay).
    # n>=3: only top 2 stay as picks (tier=null); the rest become HMs.
    qualifiers = [e for e in entries if e["confidence"] >= 4]
    if len(qualifiers) == 1:
        qualifiers[0]["tier"] = "honorable_mention"
    elif len(qualifiers) >= 3:
        qualifiers.sort(
            key=lambda e: (e["confidence"], e.get("combined_recent5_pct", 0)),
            reverse=True,
        )
        for q in qualifiers[2:]:
            q["tier"] = "honorable_mention"

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

    # preserve closing-line fields across re-runs: if we already captured
    # closing_line (e.g., from close_line.py running earlier today) for a given
    # (date, game), stash it so we can re-attach after the pick refresh.
    CLOSING_FIELDS = ("closing_line", "line_delta", "line_direction", "closing_ts")
    preserved = {}
    # opening-line capture: the FIRST /nhl run of the day stores total_line as
    # the opening. subsequent runs preserve that original total_line and treat
    # the newly-fetched line as the closing line. lets clv accumulate just by
    # running /nhl again near puck drop — no separate cron required.
    prior_opening = {}
    for e in entries:
        if e.get("date") == target_date and "result" not in e:
            carry = {k: e[k] for k in CLOSING_FIELDS if k in e}
            if carry:
                preserved[e["game"]] = carry
            if e.get("total_line") is not None:
                prior_opening[e["game"]] = e["total_line"]

    # remove existing entries for target_date that DON'T have results
    # (resolved entries are sacred — never touch them)
    kept = [e for e in entries if not (e["date"] == target_date and "result" not in e)]
    removed = len(entries) - len(kept)

    # fields we pass through transparently (present in engine-derived entries,
    # absent in hand-crafted legacy entries — both cases work).
    PASSTHROUGH = (
        "tier", "reason", "factors", "goalie_pair",
        "aw_goalie", "hm_goalie", "aw_goalie_cls", "hm_goalie_cls",
        "aw_confirmed", "hm_confirmed", "is_playoff", "series_info",
    )

    from datetime import datetime, timezone
    now_iso = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")

    added = 0
    for ne in new_entries:
        current_line = ne.get("total_line")
        game = ne["game"]
        # opening-line preservation: first run of the day stores current line as
        # total_line. subsequent runs keep that original opening and treat the
        # newly-fetched line as closing_line with computed delta/direction.
        opening = prior_opening.get(game, current_line)

        entry = {
            "date": target_date,
            "game": game,
            "pick": "1p u2.5",
            "confidence": ne["confidence"],
            "poisson_pct": ne.get("poisson_pct", 0),
            "base_rate_pct": ne.get("base_rate_pct", 0),
            "combined_recent5_pct": ne.get("combined_recent5_pct", 0),
            "combined_last15_pct": ne.get("combined_last15_pct", 0),
            "total_line": opening,
            "model": ne.get("model", "v4"),
        }
        for field in PASSTHROUGH:
            if field in ne and ne[field] is not None:
                entry[field] = ne[field]
        # re-attach any closing-line fields captured earlier (e.g., close_line.py)
        if game in preserved:
            entry.update(preserved[game])
        # if this is a re-run and the line has moved, record clv here without
        # needing a separate close_line.py invocation
        if current_line is not None and opening is not None and current_line != opening:
            delta = round(float(current_line) - float(opening), 2)
            entry["closing_line"] = float(current_line)
            entry["line_delta"] = delta
            entry["line_direction"] = "toward_over" if delta > 0 else ("toward_under" if delta < 0 else "flat")
            entry["closing_ts"] = now_iso
        kept.append(entry)
        added += 1

    # write back (atomic)
    write_log(kept)

    result = {"removed": removed, "added": added, "total": len(kept)}
    print(json.dumps(result))


if __name__ == "__main__":
    main()
