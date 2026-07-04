#!/usr/bin/env python3
"""capture closing lines ~30 min before first puck drop.

usage:
    python3 close_line.py 2026-04-19            # normal run
    python3 close_line.py 2026-04-19 --dry-run  # show what would change, no write

reads picks_log.jsonl, finds all entries for TARGET_DATE that still lack a
closing_line, re-fetches current totals via the same pinnacle/espn pipeline
prefetch.py uses, and writes per-entry:

    "closing_line":   6.5,        # current market line
    "line_delta":     0.5,        # closing - opening (+ = toward over, against u2.5)
    "line_direction": "toward_over" | "toward_under" | "flat",
    "closing_ts":     "2026-04-19T23:30:00Z"   # iso utc when we captured

skipped if: entry has a result (game already played), or entry already has a
closing_line. closing_line only makes sense pre-puck-drop.

CLV interpretation (for u2.5 1p bet, using full-game total as proxy):
  - line went UP (toward_over):  market priced more goals → our u2.5 got harder
  - line went DOWN (toward_under): market priced fewer goals → our u2.5 got easier
  - net: (average line_delta) × (-1) = our implied CLV against the market.
    sustained negative CLV = we're reading the market well; sustained positive = we're late.

intended cron (ET, first puck drop usually 7pm → fire 6:30pm):
    30 18 * * *  python3 /Users/raz/claude/nhl/close_line.py $(date +\\%Y-\\%m-\\%d)
"""

import json, sys, argparse
from datetime import datetime, timezone

# reuse prefetch's line fetchers · single source of truth for scraping logic
sys.path.insert(0, "/Users/raz/claude/nhl")
from prefetch import fetch_espn_lines, fetch_pinnacle_lines, reconcile_lines  # noqa: E402
from record import read_log, write_log  # noqa: E402


def game_key_from_entry(game_str):
    """"ott @ car" -> "OTT@CAR" (the key prefetch/engine use for lines dict)."""
    left, right = [p.strip() for p in game_str.split("@")]
    return f"{left.upper()}@{right.upper()}"


def line_direction(delta):
    if delta > 0:
        return "toward_over"
    if delta < 0:
        return "toward_under"
    return "flat"


def main():
    parser = argparse.ArgumentParser(description="capture closing lines for a date")
    parser.add_argument("target_date", help="YYYY-MM-DD")
    parser.add_argument("--dry-run", action="store_true", help="show updates without writing")
    args = parser.parse_args()

    entries = read_log()
    targets = [
        e for e in entries
        if e.get("date") == args.target_date
        and "result" not in e
        and "closing_line" not in e
        and e.get("total_line") is not None
    ]

    if not targets:
        print(json.dumps({"target_date": args.target_date, "updated": 0, "reason": "no eligible entries"}))
        return

    # fetch current lines (sharp source first · prefer pinnacle consensus per CLAUDE.md rules)
    print(f"fetching closing lines for {len(targets)} entries...", file=sys.stderr)
    espn = fetch_espn_lines(args.target_date)
    pin = fetch_pinnacle_lines(args.target_date)
    if "_error" in espn:
        espn = {}
    if "_error" in pin:
        pin = {}
    lines = reconcile_lines(espn, pin)

    now_iso = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")

    updates = []
    for e in targets:
        key = game_key_from_entry(e["game"])
        line_info = lines.get(key)
        if line_info is None:
            updates.append({"game": e["game"], "status": "no_line_available"})
            continue
        close = line_info if isinstance(line_info, (int, float)) else line_info.get("using") or line_info.get("line")
        if close is None:
            updates.append({"game": e["game"], "status": "no_line_available"})
            continue
        open_ = e["total_line"]
        delta = round(float(close) - float(open_), 2)
        e["closing_line"] = float(close)
        e["line_delta"] = delta
        e["line_direction"] = line_direction(delta)
        e["closing_ts"] = now_iso
        updates.append({
            "game": e["game"], "status": "updated",
            "open": open_, "close": float(close), "delta": delta,
            "direction": e["line_direction"],
        })

    if not args.dry_run:
        write_log(entries)

    result = {
        "target_date": args.target_date,
        "dry_run": args.dry_run,
        "eligible": len(targets),
        "updated": sum(1 for u in updates if u["status"] == "updated"),
        "missing": sum(1 for u in updates if u["status"] == "no_line_available"),
        "detail": updates,
    }
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
