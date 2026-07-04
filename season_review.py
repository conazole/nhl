#!/usr/bin/env python3
"""season-end (or any-time) calibration review of the model against its OWN
logged results · the judgment loop. the historical backtest validates the
mechanical rules; only this file can validate the operational layer · the
fail-closed caps, the goalie predictions, the tier boundaries, the bust
pattern · because none of that exists in historical data.

usage:
    python3 season_review.py                     # everything in the log
    python3 season_review.py --since 2026-10-01  # one season

reads picks_log.jsonl + model_params.json. every section degrades gracefully
on thin data · run it mid-season for a pulse check, run it in the offseason
before deciding what the next version's evidence actually supports.
"""

import json, os, math, argparse
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
LOG_PATH = os.path.join(HERE, "picks_log.jsonl")
PARAMS_PATH = os.path.join(HERE, "model_params.json")

try:
    with open(PARAMS_PATH) as _f:
        PARAMS = json.load(_f)
except (OSError, json.JSONDecodeError):
    PARAMS = {}
BASE = PARAMS.get("baselines", {})
PICK_THRESHOLD = PARAMS.get("pick_threshold", 4)


def wilson(w, n, z=1.96):
    if n == 0:
        return (0.0, 0.0)
    p = w / n
    den = 1 + z * z / n
    c = (p + z * z / (2 * n)) / den
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return (100 * (c - half), 100 * (c + half))


def read_log():
    entries = []
    if not os.path.exists(LOG_PATH):
        return entries
    with open(LOG_PATH) as f:
        for line in f:
            if line.strip():
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return entries


def tier_of(e):
    t = e.get("tier")
    if t == "honorable_mention":
        return "hm"
    if t == "avoid":
        return "avoid"
    return "pick"


def line(label, pool, baseline=None):
    w = sum(1 for e in pool if e["result"] == "win")
    n = len(pool)
    if not n:
        return f"  {label:<30} no data"
    lo, hi = wilson(w, n)
    s = f"  {label:<30} {w}-{n-w}  {100*w/n:5.1f}% [{lo:4.1f},{hi:5.1f}]"
    if baseline is not None:
        s += f"  vs {baseline:.1f}% expected"
    return s


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--since", default=None, help="only entries on/after this date")
    parser.add_argument("--model", default=PARAMS.get("model", "v4"),
                        help="model line to review (default from params)")
    args = parser.parse_args()

    entries = read_log()
    entries = [e for e in entries if e.get("model") == args.model]
    if args.since:
        entries = [e for e in entries if e.get("date", "") >= args.since]
    resolved = [e for e in entries if e.get("result") in ("win", "loss")]
    scope = f"model {args.model} · since {args.since}" if args.since else f"model {args.model}"

    if not resolved:
        print(f"no resolved entries for {scope} · nothing to review yet")
        return

    vt = PARAMS.get("validated_through", "n/a")
    print(f"season review · {scope} · {len(resolved)} graded games")
    print(f"params: {PARAMS.get('model_version', 'no model_params.json')} · "
          f"validated through {vt}")

    # ── 1. cover by tier ──
    print("\n── 1. cover by tier ──")
    picks = [e for e in resolved if tier_of(e) == "pick"]
    hm = [e for e in resolved if tier_of(e) == "hm"]
    avoid = [e for e in resolved if tier_of(e) == "avoid"]
    print(line("picks (the bet)", picks, BASE.get("pick_tier")))
    print(line("honorable mentions", hm, BASE.get("hm")))
    print(line("avoids", avoid, BASE.get("avoid")))
    print(line("whole slate (base rate)", resolved, BASE.get("base_rate")))

    # parlay record (top-2 per date, the actual bet)
    from record import parlay_legs_for_date
    by_date = defaultdict(list)
    for e in picks:
        by_date[e["date"]].append(e)
    pw = pl = 0
    for d, legs in by_date.items():
        if len(legs) < 2:
            continue
        top2 = parlay_legs_for_date(legs)
        if all(e["result"] == "win" for e in top2):
            pw += 1
        else:
            pl += 1
    if pw + pl:
        exp = PARAMS.get("parlay_sim", {}).get("rate")
        exp_s = f"  vs {100*exp:.1f}% simulated" if exp else ""
        print(f"  parlays (top-2 per date): {pw}-{pl} "
              f"({100*pw/(pw+pl):.1f}%){exp_s}")

    # ── 2. confidence calibration ──
    print("\n── 2. confidence calibration ──")
    by_conf = defaultdict(list)
    for e in resolved:
        by_conf[e.get("confidence", 0)].append(e)
    for c in sorted(by_conf, reverse=True):
        print(line(f"conf {c}", by_conf[c]))

    # ── 3. cap decisions graded · the fail-closed layer, measured ──
    # a cap "earned its keep" when the game it blocked from pick range went
    # OVER. a capped game that went under cost nothing certain (the pick was
    # never bet) but a pattern of >base-rate capped unders means the cap is
    # discarding real edge.
    print("\n── 3. fail-closed caps (would-be picks only) ──")
    capped = [e for e in resolved
              if e.get("caps") and e.get("confidence_uncapped", 0) >= PICK_THRESHOLD]
    if capped:
        by_cap = defaultdict(list)
        for e in capped:
            for c in e["caps"]:
                by_cap[c].append(e)
        for c, pool in sorted(by_cap.items()):
            w = sum(1 for e in pool if e["result"] == "win")
            n = len(pool)
            print(f"  {c:<16} blocked {n} would-be picks · they went "
                  f"{w}-{n-w} ({100*w/n:.0f}% u2.5)")
        base = BASE.get("pick_tier")
        if base:
            print(f"  (a blocked pool hitting near {base:.0f}% means the cap is "
                  f"discarding pick-grade games · investigate before next season)")
    else:
        print("  no capped would-be picks graded yet (telemetry ships jul 2026)")

    # ── 4. bust taxonomy ──
    print("\n── 4. bust reasons (tag_results.py taxonomy) ──")
    tagged = Counter(e["bust_reason"] for e in resolved if e.get("bust_reason"))
    untagged = sum(1 for e in resolved
                   if e.get("result") == "loss" and not e.get("bust_reason"))
    if tagged:
        for reason, n in tagged.most_common():
            print(f"  {reason:<18} {n}")
    if untagged:
        print(f"  untagged losses: {untagged} · tag them for a complete picture")
    if not tagged and not untagged:
        print("  no losses · nothing to tag")

    # ── 5. goalie layer ──
    print("\n── 5. goalie layer ──")
    gp = [e for e in resolved if e.get("goalie_prediction_hit") is not None]
    if gp:
        hits = sum(1 for e in gp if e["goalie_prediction_hit"])
        print(f"  predicted starters correct: {hits}/{len(gp)} "
              f"({100*hits/len(gp):.1f}%)")
        missed = [e for e in gp if not e["goalie_prediction_hit"]]
        if missed:
            mw = sum(1 for e in missed if e["result"] == "win")
            print(f"  games where prediction missed: went {mw}-{len(missed)-mw} "
                  f"({100*mw/len(missed):.0f}% u2.5)")
    both_conf = [e for e in picks
                 if e.get("aw_confirmed") is not None and e.get("hm_confirmed") is not None]
    if both_conf:
        conf_p = [e for e in both_conf if e.get("aw_confirmed") and e.get("hm_confirmed")]
        unconf_p = [e for e in both_conf if not (e.get("aw_confirmed") and e.get("hm_confirmed"))]
        print(line("picks · both goalies confirmed", conf_p))
        print(line("picks · not fully confirmed", unconf_p))

    # ── 6. day factor · live check of the v4.3 swap ──
    print("\n── 6. day-game factor (live) ──")
    day = [e for e in resolved if e.get("is_day_game") is True]
    night = [e for e in resolved if e.get("is_day_game") is False]
    if day or night:
        print(line("day games (<5pm et)", day, BASE.get("day_rate")))
        print(line("night games", night, BASE.get("night_rate")))
    else:
        print("  no entries carry is_day_game yet (field ships with v4.3 logging)")

    # ── 7. closing line value ──
    print("\n── 7. closing line value ──")
    clv = [e for e in resolved if e.get("line_delta") is not None]
    if clv:
        avg = sum(e["line_delta"] for e in clv) / len(clv)
        print(f"  {len(clv)} games with closing lines · avg delta {avg:+.2f} "
              f"(u2.5-aligned clv {-avg:+.2f} · positive = market moved our way)")
    else:
        print("  no closing lines captured")

    # ── 8. line-source health ──
    print("\n── 8. line-source health ──")
    missing = [e for e in resolved if "line_missing" in (e.get("caps") or [])]
    print(f"  games logged without a sourced line: {len(missing)}")
    picks_no_line = [e for e in picks if e.get("total_line") is None]
    if picks_no_line:
        print(f"  PICKS with no line: {len(picks_no_line)} · should be 0 "
              f"(fail-closed gate breached · investigate)")


if __name__ == "__main__":
    main()
