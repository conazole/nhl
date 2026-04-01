#!/usr/bin/env python3
"""format engine JSON into styled analysis file.

usage:
    python3 format_output.py 2026-04-01 /tmp/engine.json --extras '{"postmortem":"...","injuries":{...},"context":{...}}'

reads engine JSON + picks_log, outputs styled analysis to stdout and
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

# ── visual constants ──
DOUBLE_LINE = "═" * 60
SINGLE_LINE = "─" * 60
U25_YES = "✅"
U25_NO  = "❌"
CONF_ON  = "🟢"
CONF_OFF = "⚫"
PICK_ICON = "🔒"
HM_ICON = "👀"
SLW_ICON = "👁️"
AVOID_ICON = "🛑"
NO_PLAY_ICON = "🚫"
ELITE_ICON = "🌟"

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
    return CONF_ON * conf + CONF_OFF * (scale - conf)

def start_time_et(utc_str):
    dt = datetime.fromisoformat(utc_str.replace("Z", "+00:00"))
    et = dt - timedelta(hours=4)  # EDT
    return et.strftime("%-I:%M %p").lower() + " et"

def tier_icon(conf):
    if conf >= 4:
        return PICK_ICON
    elif conf >= 2:
        return HM_ICON
    else:
        return AVOID_ICON

def tier_label(conf):
    if conf >= 4:
        return f"PICK {conf}/6"
    elif conf >= 2:
        return f"honorable mention {conf}/6"
    else:
        return f"avoid {conf}/6"


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

    # format yesterday date for display
    dt = datetime.strptime(yesterday, "%Y-%m-%d")
    date_label = dt.strftime("%b %-d").lower()

    out = []
    out.append(DOUBLE_LINE)
    out.append(f"📋  yesterday's postmortem — {date_label}, {dt.year}")
    out.append(DOUBLE_LINE)
    out.append("")

    if not yest:
        out.append("no entries to resolve.")
        out.append("")
        return out

    # parlay result
    if len(picks_y) >= 2:
        parlay_hit = all(e["result"] == "win" for e in picks_y)
        icon = "✅" if parlay_hit else "❌"
        word = "win" if parlay_hit else "loss"
        out.append(f"{icon} parlay {word} ({len(picks_y)}-0 legs)" if parlay_hit
                   else f"{icon} parlay {word}")
    elif len(picks_y) == 0:
        out.append(f"{NO_PLAY_ICON} no parlay — no games hit ≥4/6")
    else:
        out.append(f"{NO_PLAY_ICON} no parlay — only {len(picks_y)} leg")
    out.append("")

    if picks_y:
        out.append(f"{PICK_ICON} picks:")
        for e in picks_y:
            icon = "✅" if e["result"] == "win" else "❌"
            out.append(f"  {icon} {e['game']} ({e['confidence']}/6) — 1p total: {e['actual_1p_total']}")
    if hm_y:
        out.append(f"{HM_ICON} honorable mentions:")
        for e in hm_y:
            icon = "✅" if e["result"] == "win" else "❌"
            out.append(f"  {icon} {e['game']} ({e['confidence']}/6) — 1p total: {e['actual_1p_total']}")
    if avoid_y:
        out.append(f"{AVOID_ICON} avoids:")
        for e in avoid_y:
            icon = "✅" if e["result"] == "win" else "❌"
            out.append(f"  {icon} {e['game']} ({e['confidence']}/6) — 1p total: {e['actual_1p_total']}")
    out.append("")

    if postmortem_text:
        out.append("💡 what we got right / wrong:")
        for line in postmortem_text.strip().split("\n"):
            out.append(f"  {line}")
        out.append("")

    return out


# ── 15-game table ──

def format_table(team_abbr, team_data, line_lookup):
    header = "  #   date   opp  h/a  score  total  u2.5  w/l  line  ft   g"
    sep    = "  ─── ─────  ───  ───  ─────  ─────  ────  ───  ────  ───  ─"
    rows = [header, sep]
    for i, g in enumerate(team_data["games"]):
        num = i + 1
        date = g["date"][5:]  # strip year: "2026-03-31" → "03-31"
        opp = g["opp"].lower()
        ha = g["h_a"]
        score = g["score"]
        total = g["total_1p"]
        u25 = U25_YES if g["u25"] else U25_NO
        wl = g["wl"]
        line_val = get_line_for_game(line_lookup, team_abbr, g)
        line_str = format_line(line_val)
        ft = g["full_total"]
        gl = team_data["goalie_labels"][i]
        rows.append(f"  {num:<3} {date}  {opp:<3}  {ha:<3}  {score:<5}  {total:<5}  {u25:<4}  {wl:<3}  {line_str:<4}  {ft:<3}  {gl}")
    return "\n".join(rows)


# ── per-game analysis ──

def format_game(m, teams, line_lookup, injuries, context_map):
    away = m["away"]
    home = m["home"]
    away_l = away.lower()
    home_l = home.lower()
    conf = m["confidence"]

    icon = tier_icon(conf)
    # single-leg watch uses special icon
    label = tier_label(conf)

    out = []
    out.append(SINGLE_LINE)
    out.append(f"{icon}  {away_l} @ {home_l} — {label}")
    out.append(f"⏰ {start_time_et(m['start_utc'])} | 📏 total line: {format_line(m['total_line'])}")
    out.append(SINGLE_LINE)
    out.append("")

    # ── away team ──
    at = teams[away]
    out.append(f"🏒 {away_l} last 15 1p ({m['aw_goalie']} tonight):")
    out.append(format_table(away, at, line_lookup))
    out.append("")
    out.append(f"  📊 recent 5: {at['r5_u25']}/5 ({at['r5_u25']*20}%) | last 15: {at['r15_u25']}/15 ({at['r15_u25']/15*100:.1f}%)")
    venue = "road" if at["tonight_ha"] == "a" else "home"
    out.append(f"  🏟️  on {venue}: {at['venue_u25']}/{at['venue_total']} u2.5 ({at['venue_u25']/at['venue_total']*100:.1f}%)")
    out.append(f"  ⚡ wavg 1p gf: {at['wavg_gf']:.3f} | xgf: {at['wavg_xgf']:.3f} | xga: {at['wavg_xga']:.3f}")
    out.append(f"  🔧 system: {at['sys_class']} | avg 1p total: {at['avg_1p_total']:.2f} | blowups: {at['blowups']}/15")
    out.append("")

    # ── home team ──
    ht = teams[home]
    out.append(f"🏒 {home_l} last 15 1p ({m['hm_goalie']} tonight):")
    out.append(format_table(home, ht, line_lookup))
    out.append("")
    out.append(f"  📊 recent 5: {ht['r5_u25']}/5 ({ht['r5_u25']*20}%) | last 15: {ht['r15_u25']}/15 ({ht['r15_u25']/15*100:.1f}%)")
    venue_h = "home" if ht["tonight_ha"] == "h" else "road"
    out.append(f"  🏟️  on {venue_h}: {ht['venue_u25']}/{ht['venue_total']} u2.5 ({ht['venue_u25']/ht['venue_total']*100:.1f}%)")
    out.append(f"  ⚡ wavg 1p gf: {ht['wavg_gf']:.3f} | xgf: {ht['wavg_xgf']:.3f} | xga: {ht['wavg_xga']:.3f}")
    out.append(f"  🔧 system: {ht['sys_class']} | avg 1p total: {ht['avg_1p_total']:.2f} | blowups: {ht['blowups']}/15")
    out.append("")

    # ── combined stats ──
    h2h_str = ", ".join(m["h2h"]) if m["h2h"] else "none in window"
    b2b_str = ", ".join(m["b2b_teams"]) if m["b2b_teams"] else "none"
    out.append(f"  🔗 combined r5: {m['comb_r5']}/10 ({m['comb_r5_pct']:.0f}%) | r15: {m['comb_r15']}/30 ({m['comb_r15_pct']:.1f}%)")
    out.append(f"  🤝 h2h: {h2h_str}")
    out.append(f"  📅 b2b: {b2b_str}")
    out.append("")

    # ── goalies ──
    conf_a = "✅" if m["aw_confirmed"] else "⚠️"
    conf_h = "✅" if m["hm_confirmed"] else "⚠️"
    elite_a = f" {ELITE_ICON}" if m.get("aw_elite") else ""
    elite_h = f" {ELITE_ICON}" if m.get("hm_elite") else ""
    out.append("  🥅 goalies:")
    out.append(f"     {conf_a} {away_l}: {m['aw_goalie']} ({m['aw_goalie_cls']}, {m['aw_goalie_share']:.0f}%, {m['aw_season_gs']}gs, sv% {m['aw_sv_pct']:.4f}){elite_a}")
    out.append(f"     {conf_h} {home_l}: {m['hm_goalie']} ({m['hm_goalie_cls']}, {m['hm_goalie_share']:.0f}%, {m['hm_season_gs']}gs, sv% {m['hm_sv_pct']:.4f}){elite_h}")
    out.append(f"     🤝 matchup: {m['factors']['goalie_pair']}")
    out.append("")

    # ── injuries ──
    inj_a = injuries.get(away, "none")
    inj_h = injuries.get(home, "none")
    out.append(f"  🏥 injuries: {away_l}: {inj_a} | {home_l}: {inj_h}")

    # ── context ──
    ctx = context_map.get(f"{away}@{home}", "none notable")
    out.append(f"  📝 context: {ctx}")
    out.append("")

    # ── confidence ──
    f = m["factors"]
    sign = lambda v: f"+{v}" if v >= 0 else str(v)
    out.append(f"  🎯 confidence: {conf}/6  {conf_dots(conf)}")
    out.append(f"     r5: {sign(f['r5'])} | r15: {sign(f['r15'])} | goalie: {sign(f['goalie'])} ({f['goalie_pair']}) | line: {sign(f['line'])} ({format_line(m['total_line'])})")
    out.append("")
    out.append("")
    return out


# ── final recommendation ──

def format_recommendation(matchups):
    picks = [m for m in matchups if m["confidence"] >= 4]
    hms = [m for m in matchups if 2 <= m["confidence"] <= 3]
    avoids = [m for m in matchups if m["confidence"] < 2]

    out = []
    out.append(DOUBLE_LINE)

    if len(picks) >= 2:
        parlay_legs = sorted(picks, key=lambda x: (-x["confidence"], -x["comb_r5_pct"]))[:2]
        out.append(f"{PICK_ICON}  final 2-leg parlay")
        out.append(DOUBLE_LINE)
        out.append("")
        for p in parlay_legs:
            a, h = p["away"].lower(), p["home"].lower()
            c = p["confidence"]
            out.append(f"  {PICK_ICON} {a} @ {h} 1p u2.5 — {c}/6 {conf_dots(c)}")
            out.append(f"     goalie: {p['factors']['goalie_pair']} | line: {format_line(p['total_line'])}")
            out.append(f"     why: {p['comb_r5']}/10 combined r5 · {p['factors']['goalie_pair']} · {format_line(p['total_line'])} line")
            out.append("")
        # extra picks beyond top 2 become HMs
        extra = [p for p in picks if p not in parlay_legs]
        hms = extra + hms

    elif len(picks) == 1:
        out.append(f"{NO_PLAY_ICON}  no parlay tonight — only 1 game qualifies")
        out.append(DOUBLE_LINE)
        out.append("")
        p = picks[0]
        a, h = p["away"].lower(), p["home"].lower()
        c = p["confidence"]
        out.append(f"  {SLW_ICON} single-leg watch: {a} @ {h} 1p u2.5 — {c}/6 {conf_dots(c)}")
        out.append(f"     goalie: {p['factors']['goalie_pair']} | line: {format_line(p['total_line'])}")
        why_parts = []
        if p["factors"]["r5"] > 0:
            why_parts.append(f"{p['comb_r5']}/10 combined r5")
        if p["factors"]["goalie"] > 0:
            why_parts.append(p["factors"]["goalie_pair"])
        if p["factors"]["line"] > 0:
            why_parts.append(f"{format_line(p['total_line'])} line")
        if p["factors"]["r15"] > 0:
            why_parts.append(f"r15 {p['comb_r15_pct']:.0f}%")
        out.append(f"     why: {' · '.join(why_parts)}")
        others = ", ".join(f"{x['away'].lower()}@{x['home'].lower()} {x['confidence']}/6" for x in matchups if x != p)
        out.append(f"     can't pair it — {others}")
        out.append("")

    else:
        out.append(f"{NO_PLAY_ICON}  no play tonight")
        out.append(DOUBLE_LINE)
        out.append("")

    if hms:
        out.append(f"{HM_ICON} honorable mentions:")
        for m in hms:
            a, h = m["away"].lower(), m["home"].lower()
            out.append(f"  • {a} @ {h} — {m['confidence']}/6 ({m['factors']['goalie_pair']}, line {format_line(m['total_line'])})")
    if avoids:
        out.append(f"{AVOID_ICON} avoids:")
        for m in avoids:
            a, h = m["away"].lower(), m["home"].lower()
            reasons = []
            if m["factors"]["line"] == -1:
                reasons.append("6.5 line")
            if m["factors"]["r5"] == 0:
                reasons.append(f"r5 {m['comb_r5_pct']:.0f}%")
            if m["factors"]["r15"] == 0:
                reasons.append(f"r15 {m['comb_r15_pct']:.1f}%")
            if m["factors"]["goalie"] < 0:
                reasons.append("backup goalie")
            reason_str = ", ".join(reasons) if reasons else "low overall"
            out.append(f"  • {a} @ {h} — {m['confidence']}/6 ({reason_str})")

    out.append("")
    out.append(DOUBLE_LINE)
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

    with open(LOG_PATH, "r") as f:
        all_entries = [json.loads(l) for l in f if l.strip()]

    line_lookup = build_line_lookup(all_entries)
    record = compute_season_record(all_entries)

    # format date for header
    dt = datetime.strptime(target_date, "%Y-%m-%d")
    date_label = dt.strftime("%b %-d").lower()

    out = []

    # ── postmortem ──
    out.extend(format_postmortem(all_entries, yesterday, postmortem_text))

    # ── season record ──
    out.append(DOUBLE_LINE)
    out.append("📊  season record (v4 — since mar 28)")
    out.append(DOUBLE_LINE)
    out.append("")
    out.append(f"  🏆 parlays:        {record['parlay_w']}-{record['parlay_l']} ({pct(record['parlay_w'], record['parlay_l'])}%)")
    out.append(f"  📈 all legs:       {record['leg_w']}-{record['leg_l']} ({pct(record['leg_w'], record['leg_l'])}%)")
    out.append(f"     confidence 4+:  {record['c4_w']}-{record['c4_l']} ({pct(record['c4_w'], record['c4_l'])}%)")
    out.append(f"     confidence 5+:  {record['c5_w']}-{record['c5_l']} ({pct(record['c5_w'], record['c5_l'])}%)")
    out.append(f"  🔍 hms:           {record['hm_w']}-{record['hm_l']} would-have-won ({pct(record['hm_w'], record['hm_l'])}%)")
    out.append(f"  🛑 avoids:        {record['av_w']}-{record['av_l']} would-have-won ({pct(record['av_w'], record['av_l'])}%)")
    out.append("")

    # ── main analysis header ──
    n_games = len(data["matchups"])
    out.append(DOUBLE_LINE)
    out.append(f"🏒  nhl 1p u2.5 analysis — {date_label}, {dt.year}")
    out.append(DOUBLE_LINE)
    out.append(f"📊 league 1p u2.5 base rate: {data['base_rate']:.1f}% (from {data['league_total']} games)")
    out.append(f"🎯 {n_games} game{'s' if n_games != 1 else ''} tonight")
    out.append("")

    # ── per-game analysis ──
    for m in data["matchups"]:
        out.extend(format_game(m, data["teams"], line_lookup, injuries, context_map))

    # ── final recommendation ──
    out.extend(format_recommendation(data["matchups"]))

    full_output = "\n".join(out)
    print(full_output)

    # save analysis file
    analysis_path = f"/Users/raz/claude/nhl/analysis_{target_date}.md"
    with open(analysis_path, "w") as f:
        f.write(full_output)
    print(f"\n[saved to {analysis_path}]", file=sys.stderr)


if __name__ == "__main__":
    main()
