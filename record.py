#!/usr/bin/env python3
"""shared picks_log helpers · single source of truth for record math.

used by resolve_results.py, format_output.py, update_log.py, close_line.py.
keeping read/write/record/parlay logic in one module ends the drift risk of
the duplicated compute_season_record copies (audit, jun 12 2026).

parlay scoring rule: a date's parlay = the top 2 picks by the deterministic
sort key (confidence desc, r5% desc, r15% desc, game asc) · the same key
format_output.py uses to display the parlay and update_log.py uses to demote
3rd+ qualifiers. legacy dates that still carry 3+ untiered picks (pre apr-27
demotion fix) are thereby scored on what was actually bet, not on every
logged qualifier.

"void" results (postponed/rescheduled games) are excluded from all counts.
"""

import json, os, sys, tempfile, shutil
from collections import defaultdict

LOG_PATH = "/Users/raz/claude/nhl/picks_log.jsonl"


def read_log(path=LOG_PATH):
    """read picks_log.jsonl with error handling for malformed lines."""
    entries = []
    with open(path, "r") as f:
        for line_no, line in enumerate(f, 1):
            if not line.strip():
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError as e:
                print(f"warning: line {line_no} is invalid JSON, skipping: {e}",
                      file=sys.stderr)
    return entries


def write_log(entries, path=LOG_PATH):
    """write picks_log.jsonl atomically (temp file + rename)."""
    fd, tmp_path = tempfile.mkstemp(dir=os.path.dirname(path), suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            for e in entries:
                f.write(json.dumps(e) + "\n")
        shutil.move(tmp_path, path)
    except Exception:
        os.unlink(tmp_path)
        raise


def _r5_of(e):
    """combined r5 % · accepts log-entry or engine-matchup field names."""
    v = e.get("combined_recent5_pct")
    if v is None:
        v = e.get("comb_r5_pct", 0)
    return v or 0


def _r15_of(e):
    v = e.get("combined_last15_pct")
    if v is None:
        v = e.get("comb_r15_pct", 0)
    return v or 0


def pick_sort_key(e):
    """deterministic descending-priority sort key for pick ordering.
    (confidence, r5%, r15%) descending, then game string ascending so that
    full ties still order identically between runs (same data = same picks)."""
    return (-(e.get("confidence", 0)), -_r5_of(e), -_r15_of(e),
            (e.get("game") or f"{e.get('away','')} @ {e.get('home','')}").lower())


def parlay_legs_for_date(picks):
    """the 2 legs actually bet on a date: top 2 picks by pick_sort_key."""
    return sorted(picks, key=pick_sort_key)[:2]


def parlay_outcome_for_date(picks):
    """grade a date's parlay from ALL of that date's untiered picks, whatever
    their result status. top-2 selection happens BEFORE any result filtering ·
    a void or still-pending leg must never promote the 3rd qualifier into the
    graded ticket or silently drop the night from the record (the mlb repo
    shipped three copies of a "skip unsettled days" rule that flattered its
    record until a 7-3 vs 6-4 mismatch surfaced · jul 2026).

    returns (outcome, top2):
      "no_parlay"  fewer than 2 picks logged
      "loss"       any top-2 leg lost · a lost leg kills the ticket no matter
                   what the other leg did (void and pending included)
      "win"        both top-2 legs won
      "pending"    no loss yet, at least one leg unresolved
      "void"       no loss, nothing pending, at least one void · reduced
                   ticket, excluded from counts like all voids
    """
    if len(picks) < 2:
        return "no_parlay", sorted(picks, key=pick_sort_key)
    top2 = parlay_legs_for_date(picks)
    res = [e.get("result") for e in top2]
    if "loss" in res:
        return "loss", top2
    if all(r == "win" for r in res):
        return "win", top2
    if any(r not in ("win", "void") for r in res):
        return "pending", top2
    return "void", top2


def tier_of(e):
    t = e.get("tier")
    if t == "honorable_mention":
        return "hm"
    if t == "avoid":
        return "avoid"
    return "pick"


def is_resolved(e):
    return e.get("result") in ("win", "loss")


def compute_season_record(entries, model="v4"):
    """compute season record for a model from log entries.
    parlays are scored on the top-2 legs per date (what was actually bet)."""
    mine = [e for e in entries if e.get("model") == model]
    res = [e for e in mine if is_resolved(e)]
    picks = [e for e in res if tier_of(e) == "pick"]
    hm = [e for e in res if tier_of(e) == "hm"]
    avoid = [e for e in res if tier_of(e) == "avoid"]

    # parlay grading sees EVERY pick of a date (resolved or not) so top-2
    # selection can't drift when a leg is void/pending · see parlay_outcome_for_date
    parlay_dates = defaultdict(list)
    for e in mine:
        if tier_of(e) == "pick":
            parlay_dates[e["date"]].append(e)
    parlay_w = parlay_l = 0
    for legs in parlay_dates.values():
        outcome, _ = parlay_outcome_for_date(legs)
        if outcome == "win":
            parlay_w += 1
        elif outcome == "loss":
            parlay_l += 1

    return {
        "parlay_w": parlay_w,
        "parlay_l": parlay_l,
        "leg_w": sum(1 for e in picks if e["result"] == "win"),
        "leg_l": sum(1 for e in picks if e["result"] == "loss"),
        "c4_w": sum(1 for e in picks if e["result"] == "win" and e.get("confidence", 0) >= 4),
        "c4_l": sum(1 for e in picks if e["result"] == "loss" and e.get("confidence", 0) >= 4),
        "c5_w": sum(1 for e in picks if e["result"] == "win" and e.get("confidence", 0) >= 5),
        "c5_l": sum(1 for e in picks if e["result"] == "loss" and e.get("confidence", 0) >= 5),
        "hm_w": sum(1 for e in hm if e["result"] == "win"),
        "hm_l": sum(1 for e in hm if e["result"] == "loss"),
        "av_w": sum(1 for e in avoid if e["result"] == "win"),
        "av_l": sum(1 for e in avoid if e["result"] == "loss"),
    }


def check_invariants(entries, before_date=None, model="v4"):
    """log-health checks. returns list of warning strings (empty = healthy).

    catches the failure modes that corrupted the record between mar-jun 2026:
      - >2 untiered picks on one date (2-leg rule violation → wrong parlay math)
      - unresolved entries older than `before_date` (dangling days never resolved)
      - duplicate (date, game) rows
      - picks missing total_line (line gate unverifiable)
    """
    warnings = []
    by_date_picks = defaultdict(list)
    seen = defaultdict(int)
    for e in entries:
        if e.get("model") != model:
            continue
        seen[(e.get("date"), e.get("game"))] += 1
        if tier_of(e) == "pick":
            by_date_picks[e.get("date")].append(e)

    for (d, g), n in sorted(seen.items()):
        if n > 1:
            warnings.append(f"duplicate entries: {g} on {d} appears {n}x")

    for d, picks in sorted(by_date_picks.items()):
        if len(picks) > 2:
            games = ", ".join(p.get("game", "?") for p in picks)
            warnings.append(f"{d}: {len(picks)} untiered picks ({games}) · "
                            f"2-leg rule violated, demote extras to honorable_mention")

    if before_date:
        stale = [e for e in entries
                 if e.get("model") == model and e.get("date", "") < before_date
                 and "result" not in e]
        for e in sorted(stale, key=lambda x: (x.get("date", ""), x.get("game", ""))):
            warnings.append(f"unresolved past entry: {e.get('game')} on {e.get('date')} "
                            f"(conf {e.get('confidence')}, tier {e.get('tier', 'pick')})")

    for e in entries:
        if e.get("model") != model or "result" in e:
            continue
        if tier_of(e) == "pick" and e.get("total_line") is None:
            warnings.append(f"pick missing total_line: {e.get('game')} on {e.get('date')}")

    return warnings
