#!/usr/bin/env python3
"""nhl 1p u2.5 model review — find patterns the daily postmortem can't see.

reads picks_log.jsonl, analyzes all resolved v4 entries, prints colored
output to terminal, and saves a clean markdown report to review_{date}.md.

usage:
    python3 review.py              # all v4 data
    python3 review.py --last 14    # last 14 days only
"""

import json, argparse, os, re
from collections import defaultdict, Counter
from datetime import datetime, timedelta

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_PATH = os.path.join(SCRIPT_DIR, "picks_log.jsonl")

# ── ansi colors (terminal only) ──
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
BOLD = "\033[1m"
DIM = "\033[2m"
RESET = "\033[0m"


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


def pct(w, total):
    return f"{100 * w / total:.1f}%" if total else "n/a"


def bar(w, total, width=20):
    if not total:
        return ""
    filled = round(width * w / total)
    empty = width - filled
    return f"{GREEN}{'█' * filled}{RESET}{RED}{'░' * empty}{RESET}"


def bar_plain(w, total, width=20):
    if not total:
        return ""
    filled = round(width * w / total)
    empty = width - filled
    return "█" * filled + "░" * empty


def strip_ansi(text):
    return re.sub(r'\033\[[0-9;]*m', '', text)


def analyze(entries, last_days=None):
    if not entries:
        return ["no resolved v4 entries found."]

    lines = []  # collect all output lines

    def out(text=""):
        lines.append(text)

    def section(title):
        out(f"\n{'═' * 50}")
        out(f"  {BOLD}{title}{RESET}")
        out(f"{'═' * 50}")

    dates = sorted(set(e["date"] for e in entries))
    scope = f"last {last_days} days" if last_days else "all time"
    out(f"{BOLD}nhl 1p u2.5 — model review{RESET}")
    out(f"{len(entries)} games · {len(dates)} days · {dates[0]} to {dates[-1]} · {scope}")

    # ── record summary ─────────────────────────────
    section("record")

    picks = [e for e in entries if tier_of(e) == "pick"]
    hm = [e for e in entries if tier_of(e) == "hm"]
    avoids = [e for e in entries if tier_of(e) == "avoid"]

    # parlay calc
    days = defaultdict(list)
    for e in picks:
        days[e["date"]].append(e["result"] == "win")
    parlay_w = sum(1 for legs in days.values() if all(legs))
    parlay_l = sum(1 for legs in days.values() if not all(legs))
    leg_w = sum(1 for e in picks if e["result"] == "win")
    leg_l = sum(1 for e in picks if e["result"] == "loss")

    # streak
    streak, max_streak, current_type = 0, 0, None
    for d in sorted(days.keys()):
        won = all(days[d])
        if current_type == won:
            streak += 1
        else:
            streak, current_type = 1, won
        if won:
            max_streak = max(max_streak, streak)

    out(f"  parlays: {BOLD}{parlay_w}-{parlay_l}{RESET} ({pct(parlay_w, parlay_w + parlay_l)}) · best streak: {max_streak}")
    out(f"  legs:    {BOLD}{leg_w}-{leg_l}{RESET} ({pct(leg_w, leg_w + leg_l)})")

    high = [e for e in entries if e["confidence"] >= 5]
    if high:
        hw = sum(1 for e in high if e["result"] == "win")
        out(f"  5+/6:   {BOLD}{hw}-{len(high)-hw}{RESET} ({pct(hw, len(high))})")

    # ── confidence calibration ─────────────────────
    section("confidence calibration")
    by_conf = defaultdict(lambda: {"w": 0, "l": 0})
    for e in entries:
        by_conf[e["confidence"]]["w" if e["result"] == "win" else "l"] += 1

    out(f"  {'conf':>4}  {'w':>3}  {'l':>3}  {'total':>5}  {'hit%':>6}")
    out(f"  {'─' * 4}  {'─' * 3}  {'─' * 3}  {'─' * 5}  {'─' * 6}  {'─' * 20}")
    for c in sorted(by_conf.keys(), reverse=True):
        d = by_conf[c]
        t = d["w"] + d["l"]
        rate = 100 * d["w"] / t if t else 0
        color = GREEN if rate >= 75 else (YELLOW if rate >= 60 else RED)
        out(f"  {c:>4}  {d['w']:>3}  {d['l']:>3}  {t:>5}  {color}{pct(d['w'], t):>6}{RESET}  {bar(d['w'], t)}")

    # interpretation
    conf4 = by_conf.get(4, {"w": 0, "l": 0})
    conf4_t = conf4["w"] + conf4["l"]
    if conf4_t >= 5:
        conf4_r = 100 * conf4["w"] / conf4_t
        if conf4_r < 65:
            out(f"\n  {YELLOW}⚠ 4/6 threshold tier at {conf4_r:.0f}% — weakest pick tier. monitor with v4.1 changes.{RESET}")
        else:
            out(f"\n  {GREEN}✓ 4/6 threshold tier at {conf4_r:.0f}% — holding well.{RESET}")

    # ── tier accuracy ──────────────────────────────
    section("tier accuracy")
    for tier_name, tier_entries in [("pick", picks), ("hm", hm), ("avoid", avoids)]:
        w = sum(1 for e in tier_entries if e["result"] == "win")
        t = len(tier_entries)
        if t:
            out(f"  {tier_name:<6} {w:>3}w {t-w:>3}l  ({pct(w, t):>6})  {bar(w, t)}")

    # picks vs hm comparison
    if picks and hm:
        pk_r = 100 * sum(1 for e in picks if e["result"] == "win") / len(picks)
        hm_r = 100 * sum(1 for e in hm if e["result"] == "win") / len(hm)
        if hm_r > pk_r:
            out(f"\n  {YELLOW}⚠ HMs ({hm_r:.0f}%) outperforming picks ({pk_r:.0f}%) — threshold may be too strict{RESET}")
        else:
            out(f"\n  {GREEN}✓ picks ({pk_r:.0f}%) > HMs ({hm_r:.0f}%) — threshold calibrated well{RESET}")

    # ── line factor ────────────────────────────────
    section("line factor")
    by_line = defaultdict(lambda: {"w": 0, "l": 0})
    for e in entries:
        line = e.get("total_line")
        if line is None:
            continue
        k = "≤5.5" if line <= 5.5 else ("6.0" if line <= 6.0 else "≥6.5")
        by_line[k]["w" if e["result"] == "win" else "l"] += 1

    out(f"  {'all games:'}")
    for k in ["≤5.5", "6.0", "≥6.5"]:
        d = by_line.get(k, {"w": 0, "l": 0})
        t = d["w"] + d["l"]
        if t:
            out(f"  {k:<5}  {d['w']:>3}w {d['l']:>3}l  ({pct(d['w'], t):>6})  {bar(d['w'], t)}")

    pick_by_line = defaultdict(lambda: {"w": 0, "l": 0})
    for e in picks:
        line = e.get("total_line")
        if line is None:
            continue
        k = "≤5.5" if line <= 5.5 else ("6.0" if line <= 6.0 else "≥6.5")
        pick_by_line[k]["w" if e["result"] == "win" else "l"] += 1

    if pick_by_line:
        out(f"\n  {'picks only:'}")
        for k in ["≤5.5", "6.0", "≥6.5"]:
            d = pick_by_line.get(k, {"w": 0, "l": 0})
            t = d["w"] + d["l"]
            if t:
                out(f"  {k:<5}  {d['w']:>3}w {d['l']:>3}l  ({pct(d['w'], t):>6})")

    # 6.5 gate check
    l65 = by_line.get("≥6.5", {"w": 0, "l": 0})
    l65_t = l65["w"] + l65["l"]
    if l65_t:
        l65_r = 100 * l65["w"] / l65_t
        sym = GREEN + "✓" if l65_r < 75 else YELLOW + "⚠"
        out(f"\n  {sym} 6.5 gate: {l65_r:.0f}% u2.5 — {'holding' if l65_r < 75 else 'may need revisit'}{RESET}")

    # ── loss profile ───────────────────────────────
    section("loss profile")
    totals_w = Counter()
    totals_l = Counter()
    for e in entries:
        t = e.get("actual_1p_total")
        if t is None:
            continue
        (totals_w if e["result"] == "win" else totals_l)[t] += 1

    all_totals = sorted(set(list(totals_w.keys()) + list(totals_l.keys())))
    out(f"  {'1p':>3}  {'wins':>5}  {'losses':>6}")
    out(f"  {'─' * 3}  {'─' * 5}  {'─' * 6}")
    for t in all_totals:
        w = totals_w.get(t, 0)
        l = totals_l.get(t, 0)
        marker = f" {DIM}← under{RESET}" if t <= 2 else f" {RED}← OVER{RESET}"
        out(f"  {t:>3}  {w:>5}  {l:>6}{marker}")

    losses = [e for e in entries if e["result"] == "loss" and e.get("actual_1p_total")]
    if losses:
        barely = sum(1 for e in losses if e["actual_1p_total"] == 3)
        blowout = sum(1 for e in losses if e["actual_1p_total"] >= 4)
        barely_pct = 100 * barely / len(losses)
        out(f"\n  {barely} barely over (3 goals, {barely_pct:.0f}%) · {blowout} blowout (4+, {100-barely_pct:.0f}%)")
        if barely_pct < 50:
            out(f"  {YELLOW}⚠ majority of losses are blowouts — model missing high-scoring signals{RESET}")

    # ── day of week ────────────────────────────────
    section("day of week")
    by_dow = defaultdict(lambda: {"w": 0, "l": 0})
    dow_names = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
    for e in entries:
        dow = datetime.strptime(e["date"], "%Y-%m-%d").weekday()
        by_dow[dow]["w" if e["result"] == "win" else "l"] += 1

    for i, name in enumerate(dow_names):
        d = by_dow.get(i, {"w": 0, "l": 0})
        t = d["w"] + d["l"]
        if t:
            rate = 100 * d["w"] / t
            color = GREEN if rate >= 70 else (YELLOW if rate >= 55 else RED)
            out(f"  {name}  {d['w']:>3}w {d['l']:>3}l  ({color}{pct(d['w'], t):>6}{RESET})  {bar(d['w'], t, 15)}")

    # ── repeat offenders ───────────────────────────
    section("repeat offenders")
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

    repeat = [(t, team_losses[t], team_total[t])
              for t in team_losses if team_losses[t] >= 2]
    repeat.sort(key=lambda x: -x[1])
    if repeat:
        for t, l, tot in repeat:
            hit = pct(tot - l, tot)
            color = RED if (tot - l) / tot < 0.4 else YELLOW
            out(f"  {color}{t:<5}{RESET} {l} losses in {tot} games ({hit} hit)")
    else:
        out(f"  {GREEN}no repeat offenders (2+ losses){RESET}")

    # ── weekly trend ───────────────────────────────
    section("trend (picks only)")
    if picks:
        by_week = defaultdict(lambda: {"w": 0, "l": 0})
        for e in picks:
            dt = datetime.strptime(e["date"], "%Y-%m-%d")
            week_start = (dt - timedelta(days=dt.weekday())).strftime("%m-%d")
            by_week[week_start]["w" if e["result"] == "win" else "l"] += 1

        for wk in sorted(by_week.keys()):
            d = by_week[wk]
            t = d["w"] + d["l"]
            out(f"  wk {wk}  {d['w']:>2}w {d['l']:>2}l  ({pct(d['w'], t):>6})  {bar(d['w'], t, 12)}")

    # ── synthesis ──────────────────────────────────
    section("what we've learned")

    findings = []

    # high confidence
    if high:
        hw = sum(1 for e in high if e["result"] == "win")
        hr = 100 * hw / len(high)
        if hr >= 85:
            findings.append(f"{GREEN}✓{RESET} 5+/6 is elite: {hw}/{len(high)} ({hr:.0f}%). high-confidence picks are the money maker.")
        elif hr >= 75:
            findings.append(f"{GREEN}✓{RESET} 5+/6 is solid: {hw}/{len(high)} ({hr:.0f}%). holding up well.")
        else:
            findings.append(f"{RED}⚠{RESET} 5+/6 dropping: {hw}/{len(high)} ({hr:.0f}%). investigate what changed.")

    # picks vs base rate
    base_entries = [e for e in entries if e.get("actual_1p_total") is not None]
    if base_entries:
        base_u25 = sum(1 for e in base_entries if e["actual_1p_total"] < 3)
        base_r = 100 * base_u25 / len(base_entries)
        if picks:
            pk_r = 100 * sum(1 for e in picks if e["result"] == "win") / len(picks)
            edge = pk_r - base_r
            findings.append(f"{'✓' if edge > 5 else '⚠'} pick edge over base rate: {pk_r:.0f}% vs {base_r:.0f}% ({'+' if edge > 0 else ''}{edge:.1f}pp)")

    # avoids
    if avoids:
        av_w = sum(1 for e in avoids if e["result"] == "win")
        av_r = 100 * av_w / len(avoids)
        if av_r >= 75:
            findings.append(f"{YELLOW}⚠{RESET} avoids hit at {av_r:.0f}% — looks conservative, but that's the base rate. the model's edge is in picks, not avoids.")
        else:
            findings.append(f"{GREEN}✓{RESET} avoids at {av_r:.0f}% — correctly filtering weaker games.")

    # the kill list: factors we've removed and why
    findings.append(f"{DIM}killed factors: poisson, elite bonus, b2b, penalties, system profile, context, early start — all noise on 1149 games{RESET}")

    # model evolution note
    findings.append(f"{DIM}v4.1 (apr 6): backup+starter split from backup+tandem. 77.4% vs 62.0% — the starter anchors the game.{RESET}")

    for f in findings:
        out(f"  {f}")

    out()
    return lines


def save_report(lines, last_days=None):
    """save github-friendly markdown version to review_{date}.md.

    simple approach: ## headers for sections, everything else in one big
    code block per section (perfect alignment), insights as bullet points.
    """
    today = datetime.now().strftime("%Y-%m-%d")
    filename = f"review_{today}.md"
    filepath = os.path.join(SCRIPT_DIR, filename)

    clean = [strip_ansi(line) for line in lines]

    md = []
    i = 0
    while i < len(clean):
        line = clean[i]
        stripped = line.strip()

        # title
        if i == 0:
            md.append(f"# {stripped}")
            md.append("")
            i += 1
            continue

        # section divider → ## header
        if stripped.startswith("═" * 10):
            if i + 2 < len(clean) and clean[i + 2].strip().startswith("═" * 10):
                title = clean[i + 1].strip()
                md.append(f"## {title}")
                md.append("")
                i += 3

                # collect section content
                code_buf = []
                while i < len(clean):
                    sl = clean[i].strip()
                    if sl.startswith("═" * 10):
                        break
                    is_insight = sl.startswith(("✓", "⚠", "killed", "v4."))
                    if is_insight:
                        if code_buf:
                            md.append("```")
                            md.extend(code_buf)
                            md.append("```")
                            md.append("")
                            code_buf = []
                        md.append(f"- {sl}")
                    elif sl:
                        code_buf.append(clean[i].rstrip())
                    else:
                        if code_buf:
                            md.append("```")
                            md.extend(code_buf)
                            md.append("```")
                            md.append("")
                            code_buf = []
                    i += 1

                if code_buf:
                    md.append("```")
                    md.extend(code_buf)
                    md.append("```")
                md.append("")
                continue
            i += 1
            continue

        # regular lines (subtitle etc)
        if stripped:
            md.append(stripped)
            md.append("")
        i += 1

    with open(filepath, "w") as f:
        f.write("\n".join(md))

    return filepath


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--last", type=int, help="only look at last N days")
    parser.add_argument("--model", default="v4", help="model version (default: v4)")
    parser.add_argument("--no-save", action="store_true", help="skip saving report file")
    args = parser.parse_args()

    entries = load_resolved(model=args.model, last_days=args.last)
    lines = analyze(entries, last_days=args.last)

    # print colored to terminal
    for line in lines:
        print(line)

    # save clean report
    if not args.no_save and lines:
        path = save_report(lines, last_days=args.last)
        print(f"{DIM}saved → {path}{RESET}")
