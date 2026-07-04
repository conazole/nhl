#!/usr/bin/env python3
"""stamp structured bust-reason tags onto resolved picks_log.jsonl entries.

usage:
    python3 tag_results.py --date 2026-04-22 --tags /tmp/bust_tags.json

tags JSON, keyed by the log's game string ("away @ home", lowercase):
{
  "stl @ lak": {"bust_reason": "pp_goals", "bust_note": "3 first-period penalties, 2 pp goals"},
  "buf @ mia": {"bust_reason": "plain_variance", "bust_note": "two deflections in 90 seconds"}
}

why this exists: the postmortem used to be prose only · nothing accumulated.
tags turn each bust into a queryable data point so season_review.py can
answer "what actually beats this model" and reweight the research checklist
annually from the model's own results. claude assigns the tag while writing
the step-2 postmortem; tag every resolved loss that day · picks, honorable
mentions, AND avoids (a tagged avoid bust is direct evidence a fail-closed
cap or low score earned its keep).

taxonomy (fixed on purpose · free-form tags can't be aggregated):
    backup_surprise   an unexpected goalie started (prediction missed)
    pp_goals          power-play goals drove the over · penalty parade
    track_meet        open run-and-gun period, chances both ways
    soft_goals        a goalie leaked weak ones early
    late_1p_flurry    2+ goals inside the final ~5 minutes of the period
    late_news         lineup/goalie news broke after the pick was logged
    plain_variance    nothing to learn · hockey happened
    other             explain in bust_note
"""

import json, sys, argparse

from record import read_log, write_log

TAXONOMY = {
    "backup_surprise", "pp_goals", "track_meet", "soft_goals",
    "late_1p_flurry", "late_news", "plain_variance", "other",
}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", required=True, help="YYYY-MM-DD of the resolved slate")
    parser.add_argument("--tags", required=True,
                        help="JSON file: game -> {bust_reason, bust_note}")
    args = parser.parse_args()

    with open(args.tags) as f:
        tags = json.load(f)

    bad = {g: t.get("bust_reason") for g, t in tags.items()
           if t.get("bust_reason") not in TAXONOMY}
    if bad:
        sys.exit(f"unknown bust_reason(s) {bad} · taxonomy: {', '.join(sorted(TAXONOMY))}")

    entries = read_log()
    tagged, unmatched = 0, set(tags)
    for e in entries:
        if e.get("date") != args.date:
            continue
        t = tags.get(e.get("game", ""))
        if not t:
            continue
        if e.get("result") != "loss":
            print(f"warning: {e['game']} has result={e.get('result')!r} · bust "
                  f"tags belong on losses, skipping", file=sys.stderr)
            unmatched.discard(e["game"])
            continue
        e["bust_reason"] = t["bust_reason"]
        if t.get("bust_note"):
            e["bust_note"] = t["bust_note"]
        tagged += 1
        unmatched.discard(e["game"])

    if unmatched:
        # never let a tag silently vanish · same discipline as invariants
        sys.exit(f"FATAL: tag key(s) matched no resolved entry on {args.date}: "
                 f"{', '.join(sorted(unmatched))} · keys are the log's game "
                 f"strings ('away @ home', lowercase)")

    write_log(entries)
    print(f"tagged {tagged} entries for {args.date}", file=sys.stderr)


if __name__ == "__main__":
    main()
