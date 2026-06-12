#!/usr/bin/env python3
"""one-time migration (jun 12 2026): restore 2-leg parlay integrity to picks_log.

context (full audit jun 12 2026, see README changelog):
  - update_log.py only gained the "demote 3rd+ qualifiers to honorable_mention"
    rule on apr 27 (commit 68002a5). six earlier dates wrote 3-6 untiered picks.
  - compute_season_record scored those days as "all logged picks must win", so
    apr 26 (bet: col@lak + tbl@mtl, both won — commit 64681cc) counted as a
    parlay LOSS because never-bet buf@bos lost.
  - the apr 9 re-run (commit d2a0fee) wiped min@dal's honorable_mention tier
    from the original run (commit a2d1f5e: "phi@det + wpg@stl parlay (both
    5/6, min@dal hm)"), and the date was never resolved at all.

what this does:
  1. demote never-bet extra qualifiers to honorable_mention on the six dates,
     keeping exactly the 2 legs per date that the run commits document as bet.
  2. tag each demoted entry with a "migration" marker for auditability.
  3. verify against the commit-documented bets EXACTLY — abort without
     writing if the log doesn't match expectations.

resolution of the dangling dates is NOT done here — run
`python3 resolve_results.py 2026-06-12` afterwards (sweep-resolve).

idempotent: re-running after success is a no-op.
"""

import sys, os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from record import read_log, write_log, compute_season_record, check_invariants  # noqa: E402

MIGRATION_TAG = "2026-06-12 parlay-integrity tier backfill"

# the 2 legs actually bet per date, straight from the run commits:
#   2026-04-09: a2d1f5e / d2a0fee   2026-04-21: 648a855
#   2026-04-11: 83845e5             2026-04-23: 0a3f5b8
#   2026-04-20: 99e2e64 / 1a1cc0d   2026-04-26: 64681cc
BET_LEGS = {
    "2026-04-09": {"phi @ det", "wpg @ stl"},
    "2026-04-11": {"nyr @ dal", "phi @ wpg"},
    "2026-04-20": {"ott @ car", "phi @ pit"},
    "2026-04-21": {"lak @ col", "mtl @ tbl"},
    "2026-04-23": {"car @ ott", "col @ lak"},
    "2026-04-26": {"col @ lak", "tbl @ mtl"},
}


def main():
    entries = read_log()
    demoted = []

    for date, legs in sorted(BET_LEGS.items()):
        day_picks = [e for e in entries
                     if e.get("date") == date and e.get("model") == "v4"
                     and "tier" not in e]
        day_games = {e["game"] for e in day_picks}

        if day_games == legs:
            print(f"{date}: already clean (exactly the 2 bet legs) — skipping")
            continue
        if not legs.issubset(day_games):
            print(f"ABORT: {date} untiered picks {sorted(day_games)} do not "
                  f"contain documented bet legs {sorted(legs)} — log does not "
                  f"match expectations, nothing written", file=sys.stderr)
            sys.exit(1)

        for e in day_picks:
            if e["game"] not in legs:
                e["tier"] = "honorable_mention"
                e["migration"] = MIGRATION_TAG
                demoted.append(f"{date} {e['game']} (conf {e.get('confidence')})")

    if not demoted:
        print("nothing to migrate — log already clean")
        return

    write_log(entries)

    print(f"\ndemoted {len(demoted)} never-bet entries to honorable_mention:")
    for d in demoted:
        print(f"  - {d}")

    rec = compute_season_record(entries)
    print(f"\nrecord after tier backfill (dangling dates still unresolved):")
    print(f"  parlays {rec['parlay_w']}-{rec['parlay_l']} | "
          f"legs {rec['leg_w']}-{rec['leg_l']} | 5+: {rec['c5_w']}-{rec['c5_l']}")

    leftover = [w for w in check_invariants(entries, before_date="2026-06-12")
                if "untiered" in w]
    if leftover:
        print("\nWARNING — still-violated 2-leg invariants:", file=sys.stderr)
        for w in leftover:
            print(f"  - {w}", file=sys.stderr)
    else:
        print("\n2-leg invariant clean on all dates ✓")


if __name__ == "__main__":
    main()
