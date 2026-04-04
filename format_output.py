#!/usr/bin/env python3
"""format engine JSON into github-flavored markdown analysis file.

usage:
    python3 format_output.py 2026-04-01 /tmp/engine.json --extras '{"postmortem":"...","injuries":{...},"context":{...}}'

reads engine JSON + picks_log, outputs github markdown to stdout and
saves to analysis_{date}.md. the --extras JSON provides dynamic content
that changes each run (postmortem text, injuries, game context). everything
else (tables, stats, record, confidence) is computed deterministically.

extras JSON schema:
{
    "postmortem": "free-text postmortem analysis (right/wrong)",
    "injuries": {"TEAM": "player (pos, status), ..."},
    "context": {"AWAY@HOME": "context notes..."}
}
"""

import json, sys, argparse
from datetime import datetime, timedelta
from collections import defaultdict

# ── paths ──
LOG_PATH = "/Users/raz/claude/nhl/picks_log.jsonl"

# ── helpers ──

def pct(w, l):
    return f"{w/(w+l)*100:.1f}" if w + l > 0 else "n/a"

def format_line(val):
    if val is None:
        return "-"
    if val == int(val):
        return f"{val:.1f}"
    return f"{val}"

def conf_dots(conf, scale=6):
    return "●" * conf + "○" * (scale - conf)

def start_time_et(utc_str):
    dt = datetime.fromisoformat(utc_str.replace("Z", "+00:00"))
    et = dt - timedelta(hours=4)  # EDT
    return et.strftime("%-I:%M %p").lower() + " et"

def sign(v):
    return f"+{v}" if v >= 0 else str(v)

def tier_label(conf):
    if conf >= 4:
        return f"🔒 {conf}/6"
    elif conf >= 2:
        return f"💡 {conf}/6"
    else:
        return f"⛔ {conf}/6"


# ── line lookup from picks_log ──

def build_line_lookup(entries):
    lookup = {}
    for e in entries:
        if "total_line" in e and e["total_line"] is not None:
            lookup[(e["date"], e["game"])] = e["total_line"]
    return lookup

def get_line_for_game(lookup, team_abbr, game):
    opp = game["opp"].lower()
    ta = team_abbr.lower()
    if game["h_a"] == "h":
        game_str = f"{opp} @ {ta}"
    else:
        game_str = f"{ta} @ {opp}"
    return lookup.get((game["date"], game_str))


# ── season record (v4) ──

def compute_season_record(entries):
    v4_picks = [e for e in entries if e.get("model") == "v4" and "result" in e and "tier" not in e]
    v4_hm = [e for e in entries if e.get("model") == "v4" and "result" in e and e.get("tier") == "honorable_mention"]
    v4_avoid = [e for e in entries if e.get("model") == "v4" and "result" in e and e.get("tier") == "avoid"]

    parlay_dates = defaultdict(list)
    for e in v4_picks:
        parlay_dates[e["date"]].append(e["result"])
    parlay_w = sum(1 for legs in parlay_dates.values() if len(legs) >= 2 and all(r == "win" for r in legs))
    parlay_l = sum(1 for legs in parlay_dates.values() if len(legs) >= 2 and any(r == "loss" for r in legs))

    leg_w = sum(1 for e in v4_picks if e["result"] == "win")
    leg_l = sum(1 for e in v4_picks if e["result"] == "loss")
    c4_w = sum(1 for e in v4_picks if e["result"] == "win" and e.get("confidence", 0) >= 4)
    c4_l = sum(1 for e in v4_picks if e["result"] == "loss" and e.get("confidence", 0) >= 4)
    c5_w = sum(1 for e in v4_picks if e["result"] == "win" and e.get("confidence", 0) >= 5)
    c5_l = sum(1 for e in v4_picks if e["result"] == "loss" and e.get("confidence", 0) >= 5)
    hm_w = sum(1 for e in v4_hm if e["result"] == "win")
    hm_l = sum(1 for e in v4_hm if e["result"] == "loss")
    av_w = sum(1 for e in v4_avoid if e["result"] == "win")
    av_l = sum(1 for e in v4_avoid if e["result"] == "loss")

    return {
        "parlay_w": parlay_w, "parlay_l": parlay_l,
        "leg_w": leg_w, "leg_l": leg_l,
        "c4_w": c4_w, "c4_l": c4_l,
        "c5_w": c5_w, "c5_l": c5_l,
        "hm_w": hm_w, "hm_l": hm_l,
        "av_w": av_w, "av_l": av_l,
    }


# ── yesterday's results ──

def format_postmortem(entries, yesterday, postmortem_text):
    yest = [e for e in entries if e["date"] == yesterday and "result" in e]
    picks_y = [e for e in yest if "tier" not in e]
    hm_y = [e for e in yest if e.get("tier") == "honorable_mention"]
    avoid_y = [e for e in yest if e.get("tier") == "avoid"]

    dt = datetime.strptime(yesterday, "%Y-%m-%d")
    date_label = dt.strftime("%b %-d").lower()

    out = []
    out.append(f"## yesterday's results — {date_label}, {dt.year}")
    out.append("")

    if not yest:
        out.append("no entries to resolve.")
        out.append("")
        return out

    # picks
    if picks_y:
        for e in picks_y:
            icon = "✅" if e["result"] == "win" else "❌"
            out.append(f'{icon} {e["game"]} — {e["result"]} (1p: {e["actual_1p_total"]}, {e["confidence"]}/6)')
        out.append("")

    # parlay result
    if len(picks_y) >= 2:
        parlay_hit = all(e["result"] == "win" for e in picks_y)
        icon = "✅" if parlay_hit else "❌"
        word = "win" if parlay_hit else "loss"
        losers = [e["game"] for e in picks_y if e["result"] == "loss"]
        if parlay_hit:
            out.append(f"parlay: {icon} {word}")
        else:
            out.append(f"parlay: {icon} {word} ({', '.join(losers)} busted)")
    elif len(picks_y) == 0:
        out.append("no parlay — no games hit ≥4/6")
    else:
        out.append("no parlay — only 1 leg")
    out.append("")

    # postmortem text
    if postmortem_text:
        out.append("### post-mortem")
        out.append("")
        for line in postmortem_text.strip().split("\n"):
            out.append(line)
        out.append("")

    return out


# ── 15-game markdown table ──

def format_table(team_abbr, team_data, line_lookup):
    rows = []
    rows.append("| # | date | opp | h/a | score | total | u2.5 | w/l | line | ft | g |")
    rows.append("|---|------|-----|-----|-------|-------|------|-----|------|----|---|")
    for i, g in enumerate(team_data["games"]):
        date = g["date"][5:]
        u25 = "✅" if g["u25"] else "❌"
        line_val = get_line_for_game(line_lookup, team_abbr, g)
        line_str = format_line(line_val)
        gl = team_data["goalie_labels"][i]
        rows.append(f'| {i+1} | {date} | {g["opp"]} | {g["h_a"]} | {g["score"]} | {g["total_1p"]} | {u25} | {g["wl"]} | {line_str} | {g["full_total"]} | {gl} |')
    return "\n".join(rows)


# ── per-game analysis ──

def format_game(m, teams, line_lookup, injuries, context_map):
    away = m["away"]
    home = m["home"]
    away_l = away.lower()
    home_l = home.lower()
    conf = m["confidence"]
    f = m["factors"]

    out = []
    out.append(f"## {away_l} @ {home_l} — {tier_label(conf)}")
    out.append(f"> {start_time_et(m['start_utc'])} · {format_line(m['total_line'])}")
    out.append("")

    # ── away team ──
    at = teams[away]
    venue_a = "road" if at["tonight_ha"] == "a" else "home"
    va_pct = at['venue_u25']/at['venue_total']*100 if at['venue_total'] > 0 else 0.0
    out.append(f"### {away_l} ({m['aw_goalie']}, {m['aw_goalie_cls']})")
    out.append("")
    out.append(format_table(away, at, line_lookup))
    out.append("")
    out.append(f"> r5: {at['r5_u25']}/5 ({at['r5_u25']*20}%) · r15: {at['r15_u25']}/15 ({at['r15_u25']/15*100:.0f}%) · {venue_a}: {at['venue_u25']}/{at['venue_total']} ({va_pct:.0f}%) · wavg: {at['wavg_gf']:.3f} · {at['sys_class']}")
    out.append("")

    # ── home team ──
    ht = teams[home]
    venue_h = "home" if ht["tonight_ha"] == "h" else "road"
    vh_pct = ht['venue_u25']/ht['venue_total']*100 if ht['venue_total'] > 0 else 0.0
    out.append(f"### {home_l} ({m['hm_goalie']}, {m['hm_goalie_cls']})")
    out.append("")
    out.append(format_table(home, ht, line_lookup))
    out.append("")
    out.append(f"> r5: {ht['r5_u25']}/5 ({ht['r5_u25']*20}%) · r15: {ht['r15_u25']}/15 ({ht['r15_u25']/15*100:.0f}%) · {venue_h}: {ht['venue_u25']}/{ht['venue_total']} ({vh_pct:.0f}%) · wavg: {ht['wavg_gf']:.3f} · {ht['sys_class']}")
    out.append("")

    # ── combined stats ──
    if m["h2h"]:
        h2h_parts = [f"{h['total_1p']}g ({h['date'][5:]})" for h in m["h2h"][:3]]
        h2h_str = ", ".join(h2h_parts)
    else:
        h2h_str = "none in window"
    b2b_str = ", ".join(t.lower() for t in m["b2b_teams"]) if m["b2b_teams"] else "none"

    # goalie info
    ac = "✓" if m["aw_confirmed"] else "✗"
    hc = "✓" if m["hm_confirmed"] else "✗"
    elite_a = " ★" if m.get("aw_elite") else ""
    elite_h = " ★" if m.get("hm_elite") else ""

    out.append(f"combined r5: {m['comb_r5']}/10 ({m['comb_r5_pct']}%) · r15: {m['comb_r15']}/30 ({m['comb_r15_pct']}%)")
    parts = [f"h2h: {h2h_str}", f"b2b: {b2b_str}"]
    out.append(" · ".join(parts))
    out.append("")
    out.append(f"{away_l}: {m['aw_goalie']} ({m['aw_goalie_cls']}, {m['aw_goalie_share']:.0f}%, sv% {m['aw_sv_pct']:.4f}) [{ac}]{elite_a}")
    out.append(f"{home_l}: {m['hm_goalie']} ({m['hm_goalie_cls']}, {m['hm_goalie_share']:.0f}%, sv% {m['hm_sv_pct']:.4f}) [{hc}]{elite_h}")
    out.append(f"matchup: {f['goalie_pair']}")

    # injuries + context (only if present)
    inj_a = injuries.get(away, "")
    inj_h = injuries.get(home, "")
    inj_parts = []
    if inj_a: inj_parts.append(f"{away_l}: {inj_a}")
    if inj_h: inj_parts.append(f"{home_l}: {inj_h}")
    if inj_parts:
        out.append(f"injuries: {' · '.join(inj_parts)}")
    ctx = context_map.get(f"{away}@{home}", "")
    if ctx:
        out.append(f"context: {ctx}")
    out.append("")

    # ── confidence ──
    out.append(f"{conf}/6 {conf_dots(conf)}")
    out.append(f"r5:{sign(f['r5'])} · r15:{sign(f['r15'])} · goalie:{sign(f['goalie'])} ({f['goalie_pair']}) · line:{sign(f['line'])}")
    out.append("")
    out.append("---")
    out.append("")
    return out


# ── final recommendation ──

def format_recommendation(matchups, record):
    picks = [m for m in matchups if m["confidence"] >= 4]
    hms = [m for m in matchups if 2 <= m["confidence"] <= 3]
    avoids = [m for m in matchups if m["confidence"] < 2]

    out = []

    if len(picks) >= 2:
        parlay_legs = sorted(picks, key=lambda x: (-x["confidence"], -x["comb_r5_pct"]))[:2]
        out.append("## 🔒 today's 2-leg parlay")
        out.append("")
        for p in parlay_legs:
            a, h = p["away"].lower(), p["home"].lower()
            f = p["factors"]
            out.append(f"### {a} @ {h} ({p['confidence']}/6)")
            out.append(f"> {start_time_et(p['start_utc'])} · {format_line(p['total_line'])} · {f['goalie_pair']}")
            out.append(f">")
            out.append(f"> r5:{sign(f['r5'])} · r15:{sign(f['r15'])} · goalie:{sign(f['goalie'])} · line:{sign(f['line'])}")
            out.append("")
        extra = [p for p in picks if p not in parlay_legs]
        hms = extra + hms

    elif len(picks) == 1:
        out.append("## 🚫 no parlay tonight — only 1 game qualifies")
        out.append("")
        p = picks[0]
        a, h = p["away"].lower(), p["home"].lower()
        f = p["factors"]
        out.append(f"**single-leg watch:** {a} @ {h} — {p['confidence']}/6")
        out.append(f"> {f['goalie_pair']} · line: {format_line(p['total_line'])}")
        out.append("")

    else:
        out.append("## 🚫 no play tonight")
        out.append("")

    if hms:
        out.append("### honorable mentions")
        out.append("")
        for m in hms:
            out.append(f"- {m['away'].lower()} @ {m['home'].lower()} — {m['confidence']}/6")
        out.append("")

    if avoids:
        out.append("### avoid")
        out.append("")
        for m in avoids:
            f = m["factors"]
            reasons = []
            if f["goalie"] < 0: reasons.append(f["goalie_pair"])
            if f["line"] < 0: reasons.append(f"{format_line(m['total_line'])} line")
            if f["r5"] == 0: reasons.append(f"r5 {m['comb_r5_pct']:.0f}%")
            reason_str = ", ".join(reasons) if reasons else "low factors"
            out.append(f"- {m['away'].lower()} @ {m['home'].lower()} — {m['confidence']}/6 ({reason_str})")
        out.append("")

    out.append(f"season: {record['parlay_w']}-{record['parlay_l']} parlays · {record['leg_w']}-{record['leg_l']} legs")
    out.append("")
    return out


# ── main ──

def main():
    parser = argparse.ArgumentParser(description="format engine JSON into styled analysis")
    parser.add_argument("target_date", help="YYYY-MM-DD")
    parser.add_argument("engine_json", help="path to engine output JSON")
    parser.add_argument("--extras", default="{}", help="JSON with postmortem, injuries, context")
    args = parser.parse_args()

    target_date = args.target_date
    yesterday = (datetime.strptime(target_date, "%Y-%m-%d") - timedelta(days=1)).strftime("%Y-%m-%d")

    with open(args.engine_json, "r") as f:
        data = json.loads(f.read().strip())

    extras = json.loads(args.extras)
    postmortem_text = extras.get("postmortem", "")
    injuries = extras.get("injuries", {})
    context_map = extras.get("context", {})

    all_entries = []
    with open(LOG_PATH, "r") as f:
        for line_no, line in enumerate(f, 1):
            if not line.strip():
                continue
            try:
                all_entries.append(json.loads(line))
            except json.JSONDecodeError:
                print(f"warning: picks_log line {line_no} is invalid JSON, skipping", file=sys.stderr)

    line_lookup = build_line_lookup(all_entries)
    record = compute_season_record(all_entries)

    dt = datetime.strptime(target_date, "%Y-%m-%d")
    date_label = dt.strftime("%B %-d").lower()

    out = []

    # ── header ──
    out.append(f"# nhl 1p u2.5 analysis — {date_label}, {dt.year}")
    out.append("")

    # ── postmortem ──
    out.extend(format_postmortem(all_entries, yesterday, postmortem_text))

    # ── season record ──
    out.append("## season record (v4)")
    out.append("")
    out.append(f"parlays: {record['parlay_w']}-{record['parlay_l']} ({pct(record['parlay_w'], record['parlay_l'])}%) · legs: {record['leg_w']}-{record['leg_l']} ({pct(record['leg_w'], record['leg_l'])}%) · 5+: {record['c5_w']}-{record['c5_l']}")
    out.append("")
    out.append(f"base rate: {data['base_rate']:.1f}% ({data['league_total']} games)")
    out.append("")
    out.append("---")
    out.append("")

    # ── parlay recommendation (at the top for quick mobile reading) ──
    out.extend(format_recommendation(data["matchups"], record))
    out.append("---")
    out.append("")

    # ── per-game analysis ──
    for m in data["matchups"]:
        out.extend(format_game(m, data["teams"], line_lookup, injuries, context_map))

    # ── summary at bottom ──
    hms = [m for m in data["matchups"] if 2 <= m["confidence"] <= 3]
    avoids = [m for m in data["matchups"] if m["confidence"] < 2]

    out.append("## summary")
    out.append("")
    if hms:
        out.append("### honorable mentions")
        out.append("")
        for m in hms:
            out.append(f"- {m['away'].lower()} @ {m['home'].lower()} — {m['confidence']}/6")
        out.append("")
    if avoids:
        out.append("### avoid")
        out.append("")
        for m in avoids:
            f = m["factors"]
            reasons = []
            if f["goalie"] < 0: reasons.append(f["goalie_pair"])
            if f["line"] < 0: reasons.append(f"{format_line(m['total_line'])} line")
            if f["r5"] == 0: reasons.append(f"r5 {m['comb_r5_pct']:.0f}%")
            reason_str = ", ".join(reasons) if reasons else "low factors"
            out.append(f"- {m['away'].lower()} @ {m['home'].lower()} — {m['confidence']}/6 ({reason_str})")
        out.append("")

    full_output = "\n".join(out)
    print(full_output)

    # save analysis file + delete previous day's
    analysis_path = f"/Users/raz/claude/nhl/analysis_{target_date}.md"
    prev_date = (dt - timedelta(days=1)).strftime("%Y-%m-%d")
    prev_path = f"/Users/raz/claude/nhl/analysis_{prev_date}.md"

    import os
    if os.path.exists(prev_path):
        os.remove(prev_path)
        print(f"[deleted {prev_path}]", file=sys.stderr)

    with open(analysis_path, "w") as f:
        f.write(full_output)
    print(f"[saved to {analysis_path}]", file=sys.stderr)


if __name__ == "__main__":
    main()
