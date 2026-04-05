#!/usr/bin/env python3
"""weekly review — find patterns the daily postmortem can't see.

reads picks_log.jsonl, analyzes all resolved v4 entries, and prints
a synthesis of systematic blind spots and model calibration.

usage:
    python3 review.py              # all v4 data
    python3 review.py --last 14    # last 14 days only
"""

import json, argparse, sys
from collections import defaultdict, Counter
from datetime import datetime, timedelta

LOG_PATH = "/Users/raz/claude/nhl/picks_log.jsonl"


def load_resolved(model="v4", last_days=None):
    entries = []
    cutoff = None
    if last_days:
        cutoff = (datetime.now() - timedelta(days=last_days)).strftime("%Y-%m-%d")
    with open(LOG_PATH) as f:
        for line in f:
            if not line.strip():
                continue
            e = json.loads(line)
            if e.get("model") != model:
                continue
            if not e.get("result"):
                continue
            if cutoff and e["date"] < cutoff:
                continue
            entries.append(e)
    return entries


def tier_of(e):
    t = e.get("tier")
    if t == "honorable_mention":
        return "hm"
    if t == "avoid":
        return "avoid"
    return "pick"


def print_section(title):
    print(f"\n{'═' * 44}")
    print(f"  {title}")
    print(f"{'═' * 44}")


def pct(w, total):
    return f"{100 * w / total:.1f}%" if total else "n/a"


def bar(w, total, width=20):
    if not total:
        return ""
    filled = round(width * w / total)
    return "█" * filled + "░" * (width - filled)


def analyze(entries):
    if not entries:
        print("no resolved v4 entries found.")
        return

    dates = sorted(set(e["date"] for e in entries))
    print(f"v4 review — {len(entries)} games over {len(dates)} days")
    print(f"({dates[0]} to {dates[-1]})")

    # ── confidence calibration ──────────────────────
    print_section("confidence calibration")
    by_conf = defaultdict(lambda: {"w": 0, "l": 0})
    for e in entries:
        c = e["confidence"]
        by_conf[c]["w" if e["result"] == "win" else "l"] += 1

    print(f"  {'conf':>4}  {'w':>3}  {'l':>3}  {'total':>5}  {'hit%':>6}  ")
    print(f"  {'─' * 4}  {'─' * 3}  {'─' * 3}  {'─' * 5}  {'─' * 6}  {'─' * 20}")
    for c in sorted(by_conf.keys(), reverse=True):
        d = by_conf[c]
        t = d["w"] + d["l"]
        print(f"  {c:>4}  {d['w']:>3}  {d['l']:>3}  {t:>5}  {pct(d['w'], t):>6}  {bar(d['w'], t)}")

    # ── tier accuracy ───────────────────────────────
    print_section("tier accuracy")
    by_tier = defaultdict(lambda: {"w": 0, "l": 0})
    for e in entries:
        by_tier[tier_of(e)]["w" if e["result"] == "win" else "l"] += 1

    for tier in ["pick", "hm", "avoid"]:
        d = by_tier[tier]
        t = d["w"] + d["l"]
        if t:
            print(f"  {tier:<6} {d['w']:>3}w {d['l']:>3}l  ({pct(d['w'], t):>6})  {bar(d['w'], t)}")

    # ── parlay tracking ─────────────────────────────
    print_section("parlay results by day")
    days = defaultdict(list)
    for e in entries:
        if tier_of(e) == "pick":
            days[e["date"]].append(e["result"] == "win")

    parlay_w, parlay_l = 0, 0
    streak, max_streak = 0, 0
    current_streak_type = None
    for d in sorted(days.keys()):
        legs = days[d]
        won = all(legs)
        if won:
            parlay_w += 1
        else:
            parlay_l += 1
        # streak tracking
        if current_streak_type == won:
            streak += 1
        else:
            streak = 1
            current_streak_type = won
        if won:
            max_streak = max(max_streak, streak)

    if parlay_w + parlay_l:
        print(f"  parlays: {parlay_w}-{parlay_l} ({pct(parlay_w, parlay_w + parlay_l)})")
        print(f"  best win streak: {max_streak}")

    # ── line factor impact ──────────────────────────
    print_section("line factor impact")
    by_line = defaultdict(lambda: {"w": 0, "l": 0})
    for e in entries:
        line = e.get("total_line")
        if line is None:
            continue
        # bucket: 5.5, 6.0, 6.5
        if line <= 5.5:
            k = "≤5.5"
        elif line <= 6.0:
            k = "6.0"
        else:
            k = "≥6.5"
        by_line[k]["w" if e["result"] == "win" else "l"] += 1

    for k in ["≤5.5", "6.0", "≥6.5"]:
        d = by_line.get(k, {"w": 0, "l": 0})
        t = d["w"] + d["l"]
        if t:
            print(f"  {k:<5}  {d['w']:>3}w {d['l']:>3}l  ({pct(d['w'], t):>6})  {bar(d['w'], t)}")

    # picks-only line analysis
    pick_by_line = defaultdict(lambda: {"w": 0, "l": 0})
    for e in entries:
        if tier_of(e) != "pick":
            continue
        line = e.get("total_line")
        if line is None:
            continue
        if line <= 5.5:
            k = "≤5.5"
        elif line <= 6.0:
            k = "6.0"
        else:
            k = "≥6.5"
        pick_by_line[k]["w" if e["result"] == "win" else "l"] += 1

    if pick_by_line:
        print(f"\n  picks only:")
        for k in ["≤5.5", "6.0", "≥6.5"]:
            d = pick_by_line.get(k, {"w": 0, "l": 0})
            t = d["w"] + d["l"]
            if t:
                print(f"  {k:<5}  {d['w']:>3}w {d['l']:>3}l  ({pct(d['w'], t):>6})")

    # ── margin analysis ─────────────────────────────
    print_section("1p total distribution")
    totals_w = Counter()
    totals_l = Counter()
    for e in entries:
        t = e.get("actual_1p_total")
        if t is None:
            continue
        if e["result"] == "win":
            totals_w[t] += 1
        else:
            totals_l[t] += 1

    all_totals = sorted(set(list(totals_w.keys()) + list(totals_l.keys())))
    print(f"  {'1p':>3}  {'wins':>5}  {'losses':>6}")
    print(f"  {'─' * 3}  {'─' * 5}  {'─' * 6}")
    for t in all_totals:
        w = totals_w.get(t, 0)
        l = totals_l.get(t, 0)
        marker = " ← under" if t <= 2 else " ← OVER"
        print(f"  {t:>3}  {w:>5}  {l:>6}{marker}")

    # losses by margin (how badly do we miss?)
    losses = [e for e in entries if e["result"] == "loss" and e.get("actual_1p_total")]
    if losses:
        barely = sum(1 for e in losses if e["actual_1p_total"] == 3)
        blowout = sum(1 for e in losses if e["actual_1p_total"] >= 4)
        print(f"\n  losses: {barely} barely over (3 goals), {blowout} blowout (4+)")

    # ── day-of-week ─────────────────────────────────
    print_section("day of week")
    by_dow = defaultdict(lambda: {"w": 0, "l": 0})
    dow_names = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
    for e in entries:
        dow = datetime.strptime(e["date"], "%Y-%m-%d").weekday()
        by_dow[dow]["w" if e["result"] == "win" else "l"] += 1

    for i, name in enumerate(dow_names):
        d = by_dow.get(i, {"w": 0, "l": 0})
        t = d["w"] + d["l"]
        if t:
            print(f"  {name}  {d['w']:>3}w {d['l']:>3}l  ({pct(d['w'], t):>6})  {bar(d['w'], t, 15)}")

    # ── team frequency in losses ────────────────────
    print_section("teams in losses (picks + hm)")
    team_losses = Counter()
    team_total = Counter()
    for e in entries:
        if tier_of(e) == "avoid":
            continue
        parts = e["game"].split(" @ ")
        if len(parts) != 2:
            continue
        away, home = parts[0].strip(), parts[1].strip()
        team_total[away] += 1
        team_total[home] += 1
        if e["result"] == "loss":
            team_losses[away] += 1
            team_losses[home] += 1

    # show teams with 2+ losses in picks/hm
    repeat_offenders = [(t, team_losses[t], team_total[t])
                        for t in team_losses if team_losses[t] >= 2]
    repeat_offenders.sort(key=lambda x: -x[1])
    if repeat_offenders:
        for t, l, tot in repeat_offenders:
            print(f"  {t:<5} {l} losses in {tot} appearances ({pct(tot - l, tot)} hit)")
    else:
        print("  no repeat offenders (2+ losses)")

    # ── weekly trend ────────────────────────────────
    print_section("weekly trend (picks only)")
    picks = [e for e in entries if tier_of(e) == "pick"]
    if picks:
        # group by week
        by_week = defaultdict(lambda: {"w": 0, "l": 0})
        for e in picks:
            dt = datetime.strptime(e["date"], "%Y-%m-%d")
            week_start = (dt - timedelta(days=dt.weekday())).strftime("%m-%d")
            by_week[week_start]["w" if e["result"] == "win" else "l"] += 1

        for wk in sorted(by_week.keys()):
            d = by_week[wk]
            t = d["w"] + d["l"]
            print(f"  wk {wk}  {d['w']:>2}w {d['l']:>2}l  ({pct(d['w'], t):>6})  {bar(d['w'], t, 12)}")

    # ── synthesis ───────────────────────────────────
    print_section("synthesis — blind spots & edges")

    findings = []

    # check if high-confidence still holds
    high = [e for e in entries if e["confidence"] >= 5]
    if high:
        hw = sum(1 for e in high if e["result"] == "win")
        hr = hw / len(high) * 100
        if hr >= 85:
            findings.append(f"✓ 5+/6 confidence is elite: {hw}/{len(high)} ({hr:.0f}%)")
        elif hr < 75:
            findings.append(f"⚠ 5+/6 confidence dropping: {hw}/{len(high)} ({hr:.0f}%) — investigate")

    # check avoid accuracy
    avoids = [e for e in entries if tier_of(e) == "avoid"]
    if avoids:
        av_w = sum(1 for e in avoids if e["result"] == "win")
        av_r = av_w / len(avoids) * 100
        if av_r < 65:
            findings.append(f"✓ avoids are correctly bad bets: {av_r:.0f}% u2.5 rate")
        else:
            findings.append(f"⚠ avoids hitting at {av_r:.0f}% — model may be too conservative")

    # check 6.5 line gate
    line65 = [e for e in entries if e.get("total_line") and e["total_line"] >= 6.5]
    if line65:
        l65w = sum(1 for e in line65 if e["result"] == "win")
        l65r = l65w / len(line65) * 100
        findings.append(f"{'✓' if l65r < 75 else '⚠'} 6.5 line: {l65r:.0f}% u2.5 ({l65w}/{len(line65)}) — gate {'holding' if l65r < 75 else 'may need revisit'}")

    # check barely-over rate
    if losses:
        barely_pct = barely / len(losses) * 100
        if barely_pct > 60:
            findings.append(f"⚠ {barely_pct:.0f}% of losses are barely over (3 goals) — edge cases, not model failures")
        else:
            findings.append(f"⚠ {100 - barely_pct:.0f}% of losses are blowouts (4+) — model missing high-scoring signals")

    # check if hm > pick rate (model too conservative?)
    hm = [e for e in entries if tier_of(e) == "hm"]
    pk = [e for e in entries if tier_of(e) == "pick"]
    if hm and pk:
        hm_r = sum(1 for e in hm if e["result"] == "win") / len(hm) * 100
        pk_r = sum(1 for e in pk if e["result"] == "win") / len(pk) * 100
        if hm_r > pk_r:
            findings.append(f"⚠ HMs hitting better than picks ({hm_r:.0f}% vs {pk_r:.0f}%) — threshold may be too high")
        else:
            findings.append(f"✓ picks > HMs ({pk_r:.0f}% vs {hm_r:.0f}%) — threshold calibrated well")

    if findings:
        for f in findings:
            print(f"  {f}")
    else:
        print("  not enough data for synthesis yet.")

    print()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--last", type=int, help="only look at last N days")
    parser.add_argument("--model", default="v4", help="model version (default: v4)")
    args = parser.parse_args()
    entries = load_resolved(model=args.model, last_days=args.last)
    analyze(entries)
