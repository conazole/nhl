#!/usr/bin/env python3
"""render analysis_{date}.html · the daily report as a clickable website
(user feature 2026-07-20, ported from the mlb repo's 2026-07-19/20 build).

a VIEW, never a second model path: consumes the SAME artifacts the md report
is assembled from (engine json + picks_log + model_params + maintenance
state + --extras), renders them as real components (ticket slip, game
accordion, real tables, colored streak cells). every number comes from the
artifacts · if something looks wrong, fix the generator, not the html.

the ticket lock: when picks_log already carries today's logged entries
(update_log ran), the displayed tiers come from the LOG, so rebuilding or
republishing the html can never disagree with the logged bets. engine-side
tiering (same shared sort key) is the fallback for mocks/replays.

free text (postmortem) and any structure the component layer doesn't
recognize fall back to a generic md renderer · content is never silently
lost.

artifact-host compatible on purpose: NO doctype/html/head/body (the
claude.ai artifact host wraps it), viewport meta injected into the real
head at runtime (a body-level meta is ignored → phones render
desktop-width), and ALL in-page anchors navigate programmatically (the
wrapper swallows hash navigation).

usage (after run_analysis, mirrors format_output):
    python3 build_html.py 2026-04-04 /tmp/engine_clean.json --extras '{...}'
    add --out {path} for mocks/replays · live archive untouched
"""

import argparse
import html
import json
import os
import re
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import format_output as FO
import record as R

REPO = "/Users/raz/claude/nhl"
esc = html.escape


# ---------------------------------------------------------------- generic md fallback
def md_to_html(text):
    """forgiving renderer for free text (postmortem) and anything the
    component layer doesn't recognize. fences → pre, '> ' → rail,
    '- ' → list, ━ rules → hr, plain lines → p."""
    out, mode, buf = [], None, []

    def flush():
        nonlocal mode, buf
        if mode == "fence":
            out.append('<pre class="tbl">' + esc("\n".join(buf)) + "</pre>")
        elif mode == "rail":
            out.append('<div class="rail">' + "<br>".join(esc(b) for b in buf) + "</div>")
        elif mode == "list":
            out.append("<ul>" + "".join(f"<li>{esc(b)}</li>" for b in buf) + "</ul>")
        mode, buf = None, []

    for ln in (text or "").splitlines():
        s = ln.strip()
        if mode == "fence":
            if s.startswith("```"):
                flush()
            else:
                buf.append(ln.rstrip())
            continue
        if s.startswith("```"):
            flush()
            mode = "fence"
            continue
        if not s:
            flush()
            continue
        if set(s) <= {"━"}:            # ━ masthead rule
            flush()
            out.append("<hr>")
            continue
        if s.startswith("> "):
            if mode != "rail":
                flush()
                mode = "rail"
            buf.append(s[2:].rstrip())
            continue
        if s.startswith("- "):
            if mode != "list":
                flush()
                mode = "list"
            buf.append(s[2:].rstrip())
            continue
        flush()
        cls = ' class="lbl"' if s.endswith(":") else ""
        out.append(f"<p{cls}>{esc(s)}</p>")
    flush()
    return "\n".join(out)


# ---------------------------------------------------------------- atoms
def game_anchor(game):
    """stable per-game element id shared by slip legs, slate rows, and the
    accordion ('det @ nyr' → 'game-det-nyr')."""
    return "game-" + re.sub(r"[^a-z0-9]+", "-", (game or "").lower()).strip("-")


def game_str(m):
    return f"{m['away'].lower()} @ {m['home'].lower()}"


def chip(text, kind=""):
    return f'<span class="chip {kind}">{esc(str(text))}</span>'


def short_time(utc_str):
    """'7:00 pm et' → '7:00p' · every time on the page is eastern by
    convention, so the tag is noise (display shorthand, page-wide)."""
    t = FO.start_time_et(utc_str)
    return t.replace(" pm et", "p").replace(" am et", "a")


def mark_span(marks, indexed=False):
    """✓/✗ streak marks as colored text (groups of 5 keep their gaps).
    indexed=True stamps each mark with data-row=n so a tap can jump to the
    matching 15-game table row (the strip as an index, user 2026-07-20)."""
    out, i = [], 0
    for ch in marks:
        if ch in "✓✗":
            k = "w" if ch == "✓" else "l"
            idx = f' data-row="{i}" role="button" tabindex="0"' if indexed else ""
            out.append(f'<span class="mk-{k}"{idx}>{ch}</span>')
            i += 1
        else:
            out.append(esc(ch))
    return "".join(out)


def conf_meter(conf, uncapped=None):
    """confidence as a 6-segment meter. capped-away points render as ghost
    segments so a fail-closed cap is visible at a glance."""
    up = uncapped if uncapped is not None else conf
    segs = []
    for i in range(6):
        k = "on" if i < conf else ("cap" if i < up else "")
        segs.append(f'<i class="seg {k}"></i>')
    return (f'<span class="meter" role="img" '
            f'aria-label="confidence {conf} of 6">{"".join(segs)}</span>')


_LINE_F = (FO.PARAMS.get("factors") or {}).get("line") or {}
_LINE_PLUS = _LINE_F.get("plus", 5.5)
_LINE_ZERO = _LINE_F.get("zero", 6.0)


def line_factor(v):
    """the line factor the model would score at total v · thresholds from
    model_params (same policy the engine reads)."""
    return 1 if v <= _LINE_PLUS else (0 if v <= _LINE_ZERO else -1)


def line_drift(entry):
    """opening→closing line drift arrow for a slip leg · clv made visible
    pre-bet (user feature 2026-07-20, iphone-first: tap shows the detail).
    reads the log entry's clv fields (update_log writes closing_line when a
    later run sees a moved line). for u2.5, line UP = market pricing more
    goals = against us. flags when the move crossed a line-factor boundary ·
    a half point can flip the pick (the gate-straddle trap)."""
    if not entry:
        return ""
    o, c = entry.get("total_line"), entry.get("closing_line")
    if o is None or c is None or c == o:
        return ""
    against = c > o
    arrow = "↗" if against else "↘"
    word = "market against" if against else "market toward us"
    tip = f"open {FO.format_line(o)} → {FO.format_line(c)} · {word}"
    if line_factor(o) != line_factor(c):
        tip += " · line factor flips at this number · re-check before betting"
    k = "against" if against else "toward"
    return (f' <span class="drift {k}" data-tip="{esc(tip)}" tabindex="0" '
            f'role="button" aria-label="line drift · {esc(tip)}">{arrow}</span>')


def conf_num(conf):
    """bare confidence number · the /6 scale is known and the meter got too
    dominant outside the ticket slip (user 2026-07-20: 'too noisy'). the
    slip keeps the meter; every other surface shows just the number."""
    return f'<span class="confn" aria-label="confidence {conf} of 6">{conf}</span>'


def factor_chips(f):
    """the scored factor strip as data chips (r15 stays out · unscored)."""
    out = []
    for key in ("r5", "day", "goalie", "line"):
        v = f.get(key)
        if v is None:
            continue
        k = "pos" if v > 0 else ("neg" if v < 0 else "zero")
        out.append(f'<span class="fchip {k}">{esc(key)} {esc(FO.sign(v))}</span>')
    return f'<span class="fchips">{"".join(out)}</span>'


def _kv(key, val_html):
    return (f'<div class="kv"><span class="kv-k">{esc(key)}</span>'
            f'<span class="kv-v">{val_html}</span></div>')


OUTCOME_KIND = {"win": "win", "loss": "loss", "void": "push", "pending": "pend"}


def pill(outcome):
    k = OUTCOME_KIND.get(outcome, "pend")
    return f'<span class="pill {k}">{esc(outcome)}</span>'


# ---------------------------------------------------------------- tiering (the lock)
def logged_tiers(entries, date):
    """{game: tier} for the date's logged v4 entries · the ticket lock."""
    out = {}
    for e in entries:
        if e.get("date") == date and e.get("model") == "v4":
            out[e.get("game")] = R.tier_of(e)
    return out


def tier_map(matchups, entries, date, use_log=True):
    """display tier per game. picks_log wins when it covers the slate (the
    logged bet is the lock · a rebuild/republish can never disagree with the
    logged bet); engine-side tiering (same shared sort key as
    update_log/format_output) is used for mocks/replays and pre-log runs."""
    logged = logged_tiers(entries, date) if use_log else {}
    if logged and all(game_str(m) in logged for m in matchups):
        return {g: t for g, t in logged.items()}
    tiers = {}
    qualifiers = sorted([m for m in matchups if m["confidence"] >= 4],
                        key=R.pick_sort_key)
    legs = qualifiers[:2] if len(qualifiers) >= 2 else []
    for m in matchups:
        g = game_str(m)
        if m in legs:
            tiers[g] = "pick"
        elif m["confidence"] < 2:
            tiers[g] = "avoid"
        else:
            tiers[g] = "hm"          # 2-3/6, demoted 3rd+ qualifiers, solo watch
    return tiers


def split_tiers(matchups, tiers):
    legs = sorted([m for m in matchups if tiers[game_str(m)] == "pick"],
                  key=R.pick_sort_key)
    hms = sorted([m for m in matchups if tiers[game_str(m)] == "hm"],
                 key=R.pick_sort_key)
    avoids = sorted([m for m in matchups if tiers[game_str(m)] == "avoid"],
                    key=R.pick_sort_key)
    return legs, hms, avoids


# ---------------------------------------------------------------- masthead + health
def parlay_nights(entries, before=None):
    """[(date, outcome, top2)] for every logged v4 parlay night, oldest
    first · one shared grading rule (record.parlay_outcome_for_date): a
    lost leg plus a void/pending leg is a LOSS on every surface."""
    by_date = {}
    for e in entries:
        if e.get("model") == "v4" and R.tier_of(e) == "pick" and e.get("date"):
            if before and e["date"] > before:
                continue
            by_date.setdefault(e["date"], []).append(e)
    nights = []
    for d in sorted(by_date):
        outcome, top2 = R.parlay_outcome_for_date(by_date[d])
        if outcome == "no_parlay":
            continue
        nights.append((d, outcome, top2))
    return nights


def _lamps(outcomes):
    """parlay outcomes as goal lamps, newest first."""
    kinds = {"win": "w", "loss": "l", "void": "v", "pending": "p"}
    lit = "".join(f'<i class="lamp {kinds.get(o, "p")}"></i>' for o in outcomes)
    return f'<span class="lamps">{lit}</span>'


def build_masthead(n_games, record, nights):
    cells = [f'<a class="pcell" href="#games"><span class="pcell-v">{n_games}'
             f'</span><span class="pcell-l">games</span></a>',
             f'<a class="pcell" href="#ledger"><span class="pcell-v">'
             f'{record["parlay_w"]}-{record["parlay_l"]}</span>'
             f'<span class="pcell-l">parlays</span></a>',
             f'<a class="pcell" href="#ledger"><span class="pcell-v">'
             f'{record["leg_w"]}-{record["leg_l"]}</span>'
             f'<span class="pcell-l">legs</span></a>']
    strip = ""
    last = [o for _, o, _ in nights][-10:][::-1]     # newest first
    if last:
        graded = [o for o in last if o in ("win", "loss")]
        w = sum(1 for o in graded if o == "win")
        rec = f"{w}-{len(graded) - w} last {len(graded)}"
        strip = (f'<a class="pstrip" href="#ledger">'
                 f'<span class="pstrip-l">parlay</span>{_lamps(last)}'
                 f'<span class="pstrip-r">{esc(rec)}</span></a>')
    return (f'<header class="plate"><div class="plate-cells">{"".join(cells)}'
            f'</div>{strip}</header>')


def build_health(date):
    lines = [l for l in FO.health_lines(date) if l]
    if not lines:
        return ""
    items = "".join(f"<li>{esc(l[2:] if l.startswith('- ') else l)}</li>"
                    for l in lines)
    return (f'<section class="flags"><div class="flags-h">health</div>'
            f"<ul>{items}</ul></section>")


# ---------------------------------------------------------------- ticket
def leg_row(i, m, log_entry=None):
    g = game_str(m)
    f = m["factors"]
    return (f'<a class="leg" href="#{game_anchor(g)}">'
            f'<span class="leg-n">{i}</span>'
            f'<div class="leg-mid"><span class="leg-bet">{esc(g)}</span>'
            f'<span class="leg-game">{esc(short_time(m["start_utc"]))} · '
            f'{esc(FO.format_line(m["total_line"]))}'
            f"{line_drift(log_entry)} · "
            f'{esc(FO.pair_abbrev(f["goalie_pair"]))}</span></div>'
            f'<div class="leg-right">{conf_meter(m["confidence"], m.get("confidence_uncapped"))}'
            f"</div></a>")


def build_ticket(legs, hms, matchups, log_by_game=None):
    # title is just "u2.5" · less is more (user 2026-07-20); the n/6 text next
    # to any meter was cut the same day · the meter alone carries confidence.
    # no bet-window line, no focus button · shipped and removed the same day
    # (user: tacky) · do not re-add.
    if len(legs) >= 2:
        rows = "".join(
            leg_row(i, m, (log_by_game or {}).get(game_str(m)))
            for i, m in enumerate(legs, 1))
        return (f'<section id="ticket"><div class="slip">'
                f'<div class="slip-head"><span class="slip-title">u2.5</span>'
                f'</div><div class="legs">{rows}</div></div></section>')
    solo = [m for m in matchups if m["confidence"] >= 4]
    if not matchups:
        note = "no play tonight · 0 games scheduled"
    elif solo:
        m = solo[0]
        note = (f'no parlay tonight · only <a class="glink" '
                f'href="#{game_anchor(game_str(m))}">{esc(game_str(m))}</a> '
                f"qualifies · logged as hm (2-leg rule)")
    else:
        near = hms[0] if hms else None
        near_s = (f' · nearest: <a class="glink" href="#{game_anchor(game_str(near))}">'
                  f"{esc(game_str(near))}</a>") if near else ""
        note = f"no play tonight · nothing qualifies{near_s}"
    return (f'<section id="ticket"><div class="slip"><div class="slip-head">'
            f'<span class="slip-title">u2.5</span></div>'
            f'<p class="slip-note">{note}</p></div></section>')


# ---------------------------------------------------------------- slate + boards
def fold(fid, title, body_html):
    """collapsed-by-default table fold (user 2026-07-20: 'i want to look at
    them when i choose, not on my face'). slate/hm/avoid share one exclusive
    group (name=) · opening one closes whichever was open (user, same day).
    the generic hash handler opens it when a nav link targets its id."""
    fid_attr = f' id="{fid}"' if fid else ""
    return (f'<details class="fold"{fid_attr} name="board-acc">'
            f"<summary>{esc(title)}</summary>"
            f'<div class="fold-b">{body_html}</div></details>')


def build_glance(matchups, tiers):
    if not matchups:
        return ""
    # no notes column (user 2026-07-20: bet/avoid live in their own tables)
    rows = []
    for m in matchups:
        g = game_str(m)
        f = m["factors"]
        rows.append(
            f'<tr><td><a class="glink" href="#{game_anchor(g)}">{esc(g)}</a></td>'
            f'<td class="num">{conf_num(m["confidence"])}</td>'
            f'<td class="num">{esc(FO.format_line(m["total_line"]))}</td>'
            f'<td>{esc(FO.pair_abbrev(f["goalie_pair"]))}</td>'
            f'<td class="num">{esc(short_time(m["start_utc"]))}</td></tr>')
    table = (f'<div class="scroll"><table><thead><tr><th>game</th><th>conf</th>'
             f"<th>line</th><th>pair</th><th>start</th></tr>"
             f'</thead><tbody>{"".join(rows)}</tbody></table></div>')
    return f'<section>{fold("slate", f"slate · {len(matchups)}", table)}</section>'


def display_tags(m):
    """summary tags for the html surface · 'day' is dropped (the start time
    already says it · user 2026-07-20); playoff/no-line/short-window stay."""
    return [t for t in FO.game_tags(m).split(" · ") if t and t != "day"]


def why_text(m):
    """miss_reason for the html surface · the leading n/6 and 'capped from
    n/6' are stripped because the adjacent meter (with its cap ghosts)
    already carries both, and column-implied words go too: 'night start' →
    'night', 'line 6.5' → '6.5' (user 2026-07-20: start/line are known)."""
    why = FO.miss_reason(m) or FO.game_tags(m)
    why = re.sub(r"^capped from \d/6: ", "capped · ", why)
    why = re.sub(r"^\d/6 · ", "", why)
    why = why.replace("night start", "night")
    return re.sub(r"\bline (\d+\.\d)", r"\1", why)


def build_hm_avoid(hms, avoids):
    boards = []
    if hms:
        rows = "".join(
            f'<tr><td><a class="glink" href="#{game_anchor(game_str(m))}">'
            f"{esc(game_str(m))}</a></td>"
            f'<td class="num">{conf_num(m["confidence"])}</td>'
            f"<td>{esc(why_text(m))}</td></tr>"
            for m in hms)
        table = (f'<div class="scroll"><table><thead><tr><th>game</th><th>conf</th>'
                 f'<th>why it misses</th></tr></thead><tbody>{rows}</tbody>'
                 f"</table></div>")
        boards.append(fold("hm", f"hm · {len(hms)}", table))
    if avoids:
        rows = []
        for m in avoids:
            f = m["factors"]
            reasons = []
            if f.get("goalie", 0) < 0:
                reasons.append(FO.pair_abbrev(f.get("goalie_pair")))
            if f.get("line", 0) < 0:
                reasons.append(FO.format_line(m["total_line"]))
            if f.get("r5", 1) == 0:
                reasons.append(f"r5 {m['comb_r5_pct']:.0f}%")
            rows.append(
                f'<tr><td><a class="glink" href="#{game_anchor(game_str(m))}">'
                f"{esc(game_str(m))}</a></td>"
                f'<td class="num">{conf_num(m["confidence"])}</td>'
                f'<td>{esc(", ".join(reasons) if reasons else "low factors")}</td></tr>')
        table = (f'<div class="scroll"><table><thead><tr><th>game</th><th>conf</th>'
                 f'<th>reason</th></tr></thead><tbody>{"".join(rows)}</tbody>'
                 f"</table></div>")
        boards.append(fold("avoid", f"avoid · {len(avoids)}", table))
    if not boards:
        return ""
    return f'<section id="boards">{"".join(boards)}</section>'


# ---------------------------------------------------------------- game cards
def pick_panel(m, all_entries, leg_no):
    """pre-bet decision info for a parlay leg, templated from the same
    fields the md report's leg block uses · nothing invented."""
    rows = []
    ac = "confirmed" if m.get("aw_confirmed") else "unconfirmed"
    hc = "confirmed" if m.get("hm_confirmed") else "unconfirmed"
    rows.append(_kv("goalies", f"{esc(m.get('aw_goalie') or '?')} {esc(ac)} · "
                              f"{esc(m.get('hm_goalie') or '?')} {esc(hc)}"))
    rows.append(_kv("factors", factor_chips(m["factors"])))
    w, l = FO.conf_record(all_entries, m["confidence"])
    if w + l > 0:
        rows.append(_kv("tier", f"season {w}-{l} ({100 * w / (w + l):.1f}%)"))
    frag = FO.leg_fragility(m)
    if frag:
        rows.append(_kv("risk", esc(frag)))
    caution = FO.leg_caution(m)
    if caution:
        rows.append(_kv("note", esc(caution)))
    return (f'<div class="pickpanel"><div class="pickpanel-h">leg {leg_no} · '
            f'1p u2.5</div>{"".join(rows)}</div>')


def last15_table(team_abbr, tdata, line_lookup):
    head = ('<thead><tr><th class="stick">date</th><th>opp</th><th>h/a</th>'
            "<th>score</th><th>total</th><th>u2.5</th><th>w/l</th>"
            "<th>line</th><th>ft</th><th>g</th></tr></thead>")
    rows = []
    for i, g in enumerate(tdata["games"]):
        u = ('<span class="mk-w">✓</span>' if g["u25"]
             else '<span class="mk-l">✗</span>')
        line_str = FO.format_line(FO.get_line_for_game(line_lookup, team_abbr, g))
        gl = tdata["goalie_labels"][i]
        rows.append(f'<tr><td class="stick">{esc(g["date"][5:])}</td>'
                    f'<td>{esc(g["opp"])}</td><td>{esc(g["h_a"])}</td>'
                    f'<td class="num">{esc(g["score"])}</td>'
                    f'<td class="num">{g["total_1p"]}</td><td>{u}</td>'
                    f'<td>{esc(g["wl"])}</td><td class="num">{esc(line_str)}</td>'
                    f'<td class="num">{g["full_total"]}</td><td>{esc(gl)}</td></tr>')
    return (f'<div class="scroll"><table>{head}<tbody>{"".join(rows)}</tbody>'
            f"</table></div>")


def team_block(team, m, teams, line_lookup, side):
    """per-team fold: goalie row (with share/confirm detail folded in ·
    no separate goalies section), streak strip, real 15-game table, rail."""
    t = teams[team]
    team_l = team.lower()
    if side == "away":
        goalie, cls, sv = m["aw_goalie"], m["aw_goalie_cls"], m.get("aw_sv_pct")
        share, conf, elite = m.get("aw_goalie_share"), m.get("aw_confirmed"), m.get("aw_elite")
    else:
        goalie, cls, sv = m["hm_goalie"], m["hm_goalie_cls"], m.get("hm_sv_pct")
        share, conf, elite = m.get("hm_goalie_share"), m.get("hm_confirmed"), m.get("hm_elite")
    per_game = t.get("goalie_per_game") or []
    gas = [str(g["ga"]) for g, name in zip(t["games"], per_game) if name == goalie][:5]
    ga_s = f"last-{len(gas)} 1p ga {','.join(gas)}" if gas else "no starts in window"
    sv_s = f"sv% {sv:.3f}".replace("0.", ".") if sv else ""
    share_s = f"{share:.0f}% starts" if share is not None else ""
    bits = " · ".join(b for b in (ga_s, share_s, sv_s) if b)
    cchip = chip("confirmed", "ok") if conf else chip("unconfirmed")
    echip = chip("elite") if elite else ""
    strip = FO.streak_strip(t["games"])
    venue_lbl = "home" if t["tonight_ha"] == "h" else "road"
    v_pct = t["venue_u25"] / t["venue_total"] * 100 if t["venue_total"] > 0 else 0.0
    rail = (f"r5 {t['r5_u25']}/5 ({t['r5_u25'] * 20}%) · "
            f"r15 {t['r15_u25']}/15 ({t['r15_u25'] / 15 * 100:.0f}%) · "
            f"{venue_lbl} {t['venue_u25']}/{t['venue_total']} ({v_pct:.0f}%) · "
            f"wavg gf {t['wavg_gf']:.2f} · {t['sys_class']}")
    # per-team fold, closed by default (user 2026-07-20: both tables in one
    # view ran too long) · the goalie row + streak strip stay visible as the
    # summary; tapping a strip mark opens the fold and highlights its row
    return (f'<details class="tfold"><summary><span class="tfold-t">{esc(team_l)} · '
            f"{esc(goalie)} · {esc(FO.pair_abbrev(cls))}{cchip}{echip}</span>"
            f'<span class="mono strip15">{mark_span(strip, indexed=True)}</span>'
            f"</summary>"
            f'<div class="tfold-b"><div class="gsec-sub">{esc(bits)}</div>'
            f"{last15_table(team, t, line_lookup)}"
            f'<div class="gsec-rail">{esc(rail)}</div></div></details>')


def context_rows(m, injuries, context_map):
    away_l, home_l = m["away"].lower(), m["home"].lower()
    rows = []
    if m["h2h"]:
        h2h = ", ".join(f"{h['total_1p']}g ({h['date'][5:]})" for h in m["h2h"][:3])
    else:
        h2h = "none in window"
    rows.append(_kv("h2h", esc(h2h)))
    b2b = ", ".join(t.lower() for t in m["b2b_teams"]) if m["b2b_teams"] else "none"
    rows.append(_kv("b2b", esc(b2b)))
    if m.get("is_playoff"):
        si = m.get("series_info") or {}
        rd = (si.get("round_label") or f"round {si.get('round')}"
              if si.get("round") else "playoff round").lower()
        gn = si.get("game_num")
        top, bot = si.get("top_seed"), si.get("bottom_seed")
        tw, bw = si.get("top_wins", 0), si.get("bottom_wins", 0)
        if top and bot and (tw or bw):
            rows.append(_kv("series", esc(f"{rd}, game {gn} · {top.lower()} {tw}-{bw} {bot.lower()}")))
        else:
            rows.append(_kv("series", esc(f"{rd}, game {gn} (series tied 0-0)")))
    else:
        info = m.get("info", {})
        aw_po, hm_po = info.get("aw_playoff", {}), info.get("hm_playoff", {})
        po = " · ".join(
            f"{abbr} {p.get('pts', '?')}pts/{p.get('remaining', '?')}left ({p.get('status', '?')})"
            for abbr, p in ((away_l, aw_po), (home_l, hm_po)) if p)
        rows.append(_kv("race", esc(po or "n/a")))
        caution = FO.playoff_caution(aw_po, hm_po, away_l, home_l)
        if caution:
            rows.append(_kv("caution", esc(caution)))
    inj = " · ".join(f"{t.lower()}: {x}" for t, x in
                     ((m["away"], injuries.get(m["away"], "")),
                      (m["home"], injuries.get(m["home"], ""))) if x)
    if inj:
        rows.append(_kv("injuries", esc(inj)))
    ctx = context_map.get(f"{m['away']}@{m['home']}", "")
    if ctx:
        rows.append(_kv("notes", esc(ctx)))
    return f'<div class="gsec"><div class="gsec-h"><span>context</span></div>{"".join(rows)}</div>'


def rank_chip(rankings, team):
    """u2.5 form-rank chip for a summary title (user feature 2026-07-20:
    'buf #5 @ wsh #30') · rendered from the engine's team_rankings, the
    rolling last-15 u2.5-rate ordering with least-1p-ga-per-game tiebreak
    (current form beats a season-long running rank · user, same day).
    display context only, never scored. empty when the engine has no
    ranking for the team (old json, early season zero-gp)."""
    row = (rankings or {}).get(team) or {}
    r = row.get("rank")
    if not r:
        return ""
    tip = ""
    if row.get("gp"):
        ga = f"{row.get('ga_pg', 0):.2f}".rstrip("0").rstrip(".")
        tip_txt = f"u2.5 {row.get('u25')}/{row['gp']} · ga {ga}/gp"
        d = row.get("delta7")
        if d:                                  # rank movement vs a week ago
            tip_txt += f" · {'↑' if d > 0 else '↓'}{abs(d)} wk"
        tip = (f' data-tip="{esc(tip_txt)}" tabindex="0" role="button" '
               f'aria-label="rank {r} · {esc(tip_txt)}"')
    return f'<span class="rk"{tip}>#{r}</span>'


def title_html(m, rankings):
    """team, rank, @, team, rank each in a fixed sub-column so every element
    sits at the same x on every card (user 2026-07-20 · two rounds: first
    the @, then the residual whitespace)."""
    return (f'<span class="g-away">{esc(m["away"].lower())}</span>'
            f'<span class="g-rk">{rank_chip(rankings, m["away"])}</span>'
            f'<span class="g-at">@</span>'
            f'<span class="g-home">{esc(m["home"].lower())}</span>'
            f'<span class="g-rk">{rank_chip(rankings, m["home"])}</span>')


def game_card(m, teams, line_lookup, injuries, context_map, tiers, legs,
              all_entries, rankings=None):
    g = game_str(m)
    f = m["factors"]
    conf = m["confidence"]
    # no bet badge on the row (user 2026-07-20: hated it) · the ticket names
    # the legs and the pick panel inside the card marks them
    tag_chips = "".join(chip(t) for t in display_tags(m))
    tier = tiers[g]
    r5_n = m.get("comb_r5_n", 10)
    r15_n = m.get("comb_r15_n", 30)
    r5_dd = f", {m.get('r5_shared', 0)} shared" if m.get("r5_shared") else ""
    rail = (f"r5 {m['comb_r5']}/{r5_n} ({m['comb_r5_pct']}%{r5_dd}) · "
            f"r15 {m['comb_r15']}/{r15_n} ({m['comb_r15_pct']}%, unscored)")
    body = [f'<div class="grail">{factor_chips(f)}'
            f'<span class="grail-nums">{esc(rail)}</span></div>']
    if FO.miss_reason(m):
        body.append(f'<p class="miss">misses the ticket: {esc(why_text(m))}</p>')
    if tier == "pick":
        leg_no = next((i for i, lm in enumerate(legs, 1) if lm is m), 1)
        body.append(pick_panel(m, all_entries, leg_no))
    body.append(team_block(m["away"], m, teams, line_lookup, "away"))
    body.append(team_block(m["home"], m, teams, line_lookup, "home"))
    body.append(context_rows(m, injuries, context_map))
    return (f'<details class="game" id="{game_anchor(g)}" name="game-acc">'
            f'<summary>'
            f'<span class="g-title">{title_html(m, rankings)}</span>'
            f'<span class="g-sub">{esc(FO.format_line(m["total_line"]))} · '
            f'{esc(FO.pair_abbrev(f["goalie_pair"]))}</span>'
            f'<span class="g-conf">{conf_num(conf)}</span>'
            f'<span class="g-right">{tag_chips}<span class="g-time">'
            f'{esc(short_time(m["start_utc"]))}</span></span></summary>'
            f'<div class="g-body">{"".join(body)}</div></details>')


def build_games(matchups, teams, line_lookup, injuries, context_map, tiers,
                legs, all_entries, rankings=None):
    cards = "".join(game_card(m, teams, line_lookup, injuries, context_map,
                              tiers, legs, all_entries, rankings)
                    for m in matchups)
    return f'<section id="games"><div class="games">{cards}</div></section>'


# ---------------------------------------------------------------- yesterday + season
_RES_MK = {"win": ("✓", "w"), "loss": ("✗", "l"), "void": ("v", "p")}


def bust_chip(e):
    """the loss's bust-taxonomy tag as a chip (tag_results.py wrote it to
    the log) · months of postmortems become scannable. the bust_note rides
    in the tap tooltip when present."""
    reason = e.get("bust_reason")
    if not reason or e.get("result") != "loss":
        return ""
    label = reason.replace("_", " ")
    note = e.get("bust_note")
    tip = (f' data-tip="{esc(note)}" tabindex="0" role="button" '
           f'aria-label="{esc(label)} · {esc(note)}"') if note else ""
    return f'<span class="chip bust"{tip}>{esc(label)}</span>'


def build_yesterday(all_entries, yesterday, postmortem_text):
    yest = [e for e in all_entries
            if e.get("date") == yesterday and e.get("result") in ("win", "loss", "void")]
    picks_y = [e for e in yest if R.tier_of(e) == "pick"]
    hm_y = [e for e in yest if R.tier_of(e) == "hm"]
    avoid_y = [e for e in yest if R.tier_of(e) == "avoid"]
    parts = [f'<p class="lbl">yesterday · {esc(yesterday[5:])}</p>']
    if not yest:
        parts.append('<p class="muted">no entries to resolve.</p>')
    else:
        rows = []
        for e in picks_y:
            mk, k = _RES_MK.get(e["result"], ("·", "p"))
            if e["result"] == "void":
                det = "postponed · excluded"
            else:
                det = f'1p {e.get("actual_1p_total")} · conf {e.get("confidence")}'
            tag = bust_chip(e)
            rows.append(f'<div class="rleg"><span class="rmark {k}">{mk}</span>'
                        f'<div class="rleg-m"><div class="rleg-top">'
                        f'<span class="rleg-pick">{esc(e["game"])}{tag}</span>'
                        f'<span class="rleg-est">{det}</span></div></div></div>')
        outcome, top2 = R.parlay_outcome_for_date(
            [e for e in all_entries if e.get("date") == yesterday
             and R.tier_of(e) == "pick" and e.get("model") == "v4"])
        if outcome != "no_parlay":
            rows.append(f'<div class="res-h"><span>parlay</span>{pill(outcome)}</div>')
        elif not picks_y:
            rows.append('<p class="muted">no parlay · no games hit 4/6</p>')
        else:
            rows.append('<p class="muted">no parlay · only 1 leg</p>')
        for label, sub in (("hm", hm_y), ("avoid", avoid_y)):
            if sub:
                bits = " · ".join(
                    f'{esc(e["game"])} {mark_span("✓" if e["result"] == "win" else "✗")}'
                    f' (1p {e.get("actual_1p_total")})'
                    + (f' {bust_chip(e)}' if e.get("bust_reason") else "")
                    for e in sub if e["result"] != "void")
                rows.append(f'<p class="resline"><span class="kv-k">{label}</span> {bits}</p>')
        parts.append("".join(rows))
    if postmortem_text:
        parts.append('<p class="lbl">post-mortem</p>')
        parts.append(md_to_html(postmortem_text.strip()))
    return f'<section id="yesterday"><div class="card">{"".join(parts)}</div></section>'


def build_season(record, nights):
    line = (f"parlays {record['parlay_w']}-{record['parlay_l']} "
            f"({FO.pct(record['parlay_w'], record['parlay_l'])}%) · "
            f"legs {record['leg_w']}-{record['leg_l']} "
            f"({FO.pct(record['leg_w'], record['leg_l'])}%) · "
            f"5+/6: {record['c5_w']}-{record['c5_l']} · "
            f"hm {record['hm_w']}-{record['hm_l']} · "
            f"avoid {record['av_w']}-{record['av_l']}")
    rows = []
    for d, outcome, top2 in reversed(nights):     # newest first
        cells = []
        for e in top2:
            mk, k = _RES_MK.get(e.get("result"), ("·", "p"))
            cells.append(f'{esc(e["game"])} <span class="mk-{k}">{mk}</span>')
        rows.append(f'<tr><td class="num stick">{esc(d[5:])}</td>'
                    f'<td>{" · ".join(cells)}</td><td>{pill(outcome)}</td></tr>')
    ledger = ""
    if rows:
        ledger = (f'<div class="board-t" id="ledger"><div class="board-h">'
                  f'<span>parlays · night by night</span>'
                  f'<a class="backtop" href="#top">← top</a></div>'
                  f'<div class="scroll"><table><thead><tr><th>date</th><th>legs</th>'
                  f'<th></th></tr></thead><tbody>{"".join(rows)}</tbody></table>'
                  f"</div></div>")
    return (f'<section id="season"><div class="card"><p class="lbl">season · v4</p>'
            f"<p>{esc(line)}</p></div>{ledger}</section>")


# ---------------------------------------------------------------- page css
# design system: the rink. cold ice grounds with a blue bias (day-ice light /
# night-rink dark), steel-ice accent, a center-line red used ONLY as the
# slip's thin leg divider. NO bold anywhere · regular weight, hierarchy from
# size/letterspacing/color (user taste, ported from mlb 2026-07-20). status
# trio (win/loss/pend + void gray) validated per theme with the dataviz
# six-checks script; every status use carries a symbol or word, never color
# alone; all text roles >= 4.5:1.
CSS = """
:root {
  --bg:#e8edf2; --surface:#f6f9fb; --surface2:#dee6ed; --ink:#16222e;
  --muted:#4e6172; --line:#c8d4de; --accent:#20648f; --accent-soft:#20648f14;
  --redline:#b2433a; --win:#177347; --win-soft:#17734714; --loss:#b23a31;
  --loss-soft:#b23a3112; --void:#5d6b7a; --pend:#8a6410; --pend-soft:#8a641016;
  --mono:ui-monospace,"SF Mono",Menlo,Consolas,monospace;
  --sans:system-ui,-apple-system,"Segoe UI",sans-serif;
  --disp:"Avenir Next","Avenir",system-ui,sans-serif;
  --shadow:0 1px 2px rgb(22 34 46 / .05), 0 6px 18px -8px rgb(22 34 46 / .12);
}
@media (prefers-color-scheme: dark) { :root {
  --bg:#0a0f14; --surface:#101821; --surface2:#16202b; --ink:#e2e9ef;
  --muted:#8fa2b3; --line:#22303d; --accent:#5aabdc; --accent-soft:#5aabdc1f;
  --redline:#d05c50; --win:#3fb478; --win-soft:#3fb4781f; --loss:#e0685c;
  --loss-soft:#e0685c1c; --void:#7f909f; --pend:#c79a2e; --pend-soft:#c79a2e20;
  --shadow:0 1px 2px rgb(0 0 0 / .3), 0 8px 22px -10px rgb(0 0 0 / .5);
} }
:root[data-theme="dark"] {
  --bg:#0a0f14; --surface:#101821; --surface2:#16202b; --ink:#e2e9ef;
  --muted:#8fa2b3; --line:#22303d; --accent:#5aabdc; --accent-soft:#5aabdc1f;
  --redline:#d05c50; --win:#3fb478; --win-soft:#3fb4781f; --loss:#e0685c;
  --loss-soft:#e0685c1c; --void:#7f909f; --pend:#c79a2e; --pend-soft:#c79a2e20;
  --shadow:0 1px 2px rgb(0 0 0 / .3), 0 8px 22px -10px rgb(0 0 0 / .5);
}
:root[data-theme="light"] {
  --bg:#e8edf2; --surface:#f6f9fb; --surface2:#dee6ed; --ink:#16222e;
  --muted:#4e6172; --line:#c8d4de; --accent:#20648f; --accent-soft:#20648f14;
  --redline:#b2433a; --win:#177347; --win-soft:#17734714; --loss:#b23a31;
  --loss-soft:#b23a3112; --void:#5d6b7a; --pend:#8a6410; --pend-soft:#8a641016;
  --shadow:0 1px 2px rgb(22 34 46 / .05), 0 6px 18px -8px rgb(22 34 46 / .12);
}
* { box-sizing:border-box; font-weight:400; }
html { scroll-behavior:smooth; scroll-padding-top:64px; }
@media (prefers-reduced-motion:reduce){ html{scroll-behavior:auto;} }
body { margin:0; background:var(--bg); color:var(--ink);
  font:15.5px/1.6 var(--sans); -webkit-text-size-adjust:100%; }
.wrap { max-width:840px; margin:0 auto; padding:0 18px 90px; }
/* nav */
nav { position:sticky; top:0; z-index:10;
  background:color-mix(in srgb,var(--bg) 86%,transparent);
  backdrop-filter:blur(14px); -webkit-backdrop-filter:blur(14px);
  border-bottom:1px solid var(--line); }
nav .nav-in { max-width:840px; margin:0 auto; padding:12px 18px; display:flex;
  gap:17px; align-items:baseline; overflow-x:auto; white-space:nowrap;
  scrollbar-width:none; }
nav .nav-in::-webkit-scrollbar { display:none; }
nav .brand { font:15px var(--disp); color:var(--ink); margin-right:auto;
  letter-spacing:.02em; text-decoration:none; }
.brand-date { color:var(--accent); font:13px var(--mono); margin-left:4px; }
#pbar { position:absolute; left:0; bottom:-1px; height:2px; width:100%;
  background:var(--accent); transform:scaleX(0); transform-origin:0 50%; z-index:11; }
nav a { font:14px var(--sans); color:var(--muted); text-decoration:none;
  padding:2px 0; border-bottom:2px solid transparent; }
nav a:hover, nav a:focus-visible { color:var(--accent); }
nav a.on { color:var(--ink); border-bottom-color:var(--accent); }
.totop { position:fixed; right:14px; bottom:18px; width:38px; height:38px;
  border-radius:50%; background:var(--surface); border:1px solid var(--line);
  color:var(--accent); font:17px/36px var(--mono); text-align:center;
  text-decoration:none; box-shadow:var(--shadow); z-index:9; }
.totop:hover, .totop:focus-visible { border-color:var(--accent); }
.backtop { font:11.5px var(--mono); color:var(--accent); text-decoration:none;
  white-space:nowrap; }
/* rhythm */
section { margin:14px 0; }
.muted { color:var(--muted); }
.mono { font-family:var(--mono); }
.lbl { font:12px var(--mono); letter-spacing:.09em; color:var(--muted);
  margin:16px 0 6px; display:flex; align-items:center; gap:10px; }
.lbl::after { content:""; flex:1; border-top:1px solid var(--line); }
.card { background:var(--surface); border:1px solid var(--line);
  border-radius:12px; padding:13px 16px; box-shadow:var(--shadow); }
.card .lbl:first-child { margin-top:2px; }
/* masthead plate */
.plate { margin:14px 0; background:var(--surface); border:1px solid var(--line);
  border-radius:12px; padding:13px 15px 11px; box-shadow:var(--shadow); }
.plate-cells { display:flex; gap:8px; flex-wrap:wrap; }
.pcell { flex:1 1 90px; background:var(--surface2); border:1px solid var(--line);
  border-radius:9px; padding:8px 12px 7px; text-decoration:none;
  display:flex; flex-direction:column; min-width:0; }
.pcell:hover, .pcell:focus-visible { border-color:var(--accent); }
.pcell-v { font:19px var(--mono); color:var(--accent);
  font-variant-numeric:tabular-nums; white-space:nowrap; }
.pcell-l { font:10.5px var(--mono); letter-spacing:.14em; color:var(--muted); }
.pstrip { margin-top:10px; display:flex; align-items:center; gap:10px;
  text-decoration:none; font:12px var(--mono); color:var(--muted); }
.pstrip-l { color:var(--ink); }
.pstrip-r { margin-left:auto; color:var(--muted); font-variant-numeric:tabular-nums; }
.lamps { display:inline-flex; align-items:center; gap:5px; }
.lamp { width:11px; height:11px; border-radius:50%; background:var(--surface2);
  border:1px solid var(--line); }
.lamp.w { background:var(--win); border-color:transparent;
  box-shadow:0 0 6px 1px color-mix(in srgb,var(--win) 45%,transparent); }
.lamp.l { background:var(--loss); border-color:transparent; }
.lamp.v { background:var(--void); border-color:transparent; opacity:.55; }
.lamp.p { background:var(--pend); border-color:transparent; opacity:.75; }
/* health flags */
.flags { background:var(--pend-soft);
  border:1px solid color-mix(in srgb,var(--pend) 40%,transparent);
  border-radius:12px; padding:11px 16px; }
.flags-h { font:11.5px var(--mono); letter-spacing:.12em; color:var(--pend);
  margin-bottom:6px; }
.flags ul { margin:0; padding-left:18px; }
.flags li { margin:4px 0; font-size:14px; line-height:1.5; }
/* ticket slip · blue line top, center-line red between legs */
.slip { position:relative; overflow:hidden; background:var(--surface);
  border:1px solid var(--line); border-radius:12px; padding:12px 16px 13px;
  box-shadow:var(--shadow); }
.slip::before { content:""; position:absolute; inset:0 0 auto 0; height:3px;
  background:var(--accent); }
.slip-head { display:flex; align-items:center; gap:9px; padding:2px 0 8px; }
.slip-title { font:16px var(--disp); letter-spacing:.01em; }
.slip-note { margin:2px 0 4px; color:var(--muted); font-size:14.5px; }
.legs { display:flex; flex-direction:column; }
a.leg { text-decoration:none; color:inherit;
  -webkit-tap-highlight-color:transparent; }
a.leg:active .leg-bet, a.leg:hover .leg-bet { color:var(--accent); }
.leg { display:flex; gap:13px; align-items:center; padding:10px 0; }
.leg + .leg { border-top:1px solid
  color-mix(in srgb,var(--redline) 55%,transparent); }
.leg-n { flex:none; width:26px; height:26px; border-radius:50%;
  background:var(--accent-soft); color:var(--accent);
  font:13px/26px var(--mono); text-align:center; }
.leg-mid { flex:1; display:flex; flex-direction:column; gap:1px; min-width:0; }
.leg-bet { font:17px var(--mono); letter-spacing:-.01em; white-space:nowrap; }
.leg-game { font-size:13px; color:var(--muted); white-space:nowrap; }
.leg-right { display:flex; align-items:center; }
/* per-team folds inside a game card */
.tfold { border-top:1px solid var(--line); margin-top:16px; }
.tfold > summary { display:flex; justify-content:space-between;
  align-items:baseline; gap:10px; flex-wrap:wrap; cursor:pointer;
  list-style:none; padding:12px 0 8px; font:12px var(--mono);
  letter-spacing:.07em; }
.tfold > summary::-webkit-details-marker { display:none; }
.tfold > summary:focus-visible { outline:2px solid var(--accent);
  outline-offset:-2px; }
.tfold-t::before { content:"▸"; color:var(--accent); margin-right:8px;
  font-family:var(--mono); display:inline-block; transition:transform .15s; }
.tfold[open] > summary .tfold-t::before { transform:rotate(90deg); }
@media (prefers-reduced-motion:reduce){ .tfold-t::before { transition:none; } }
.tfold-b { overflow-x:auto; padding-bottom:4px; }
.strip15 [data-row] { cursor:pointer; }
tr.hl td { background:var(--accent-soft); }
.chip.bust { color:var(--loss); border-color:var(--loss);
  background:var(--loss-soft); }
/* chips + pills + meters */
.chip { display:inline-block; font:11.5px var(--mono); color:var(--muted);
  border:1px solid var(--line); border-radius:999px; padding:2px 9px;
  margin-left:6px; white-space:nowrap; background:var(--surface); }
.chip.bet { background:var(--accent); color:var(--bg); border-color:var(--accent); }
.chip.ok { color:var(--win); border-color:var(--win); background:var(--win-soft); }
.chip.no { color:var(--muted); background:var(--surface2); }
.pill { font:12.5px var(--mono); border-radius:999px; padding:3px 12px;
  white-space:nowrap; }
.pill.win { color:var(--win); background:var(--win-soft); }
.pill.loss { color:var(--loss); background:var(--loss-soft); }
.pill.pend { color:var(--pend); background:var(--pend-soft); }
.pill.push { color:var(--void); background:var(--surface2); }
.confn { font:15px var(--mono); color:var(--accent);
  font-variant-numeric:tabular-nums; }
.meter { display:inline-flex; gap:2.5px; align-items:center; }
.meter .seg { width:7px; height:12px; border-radius:2px;
  background:var(--surface2);
  box-shadow:inset 0 0 0 1px color-mix(in srgb,var(--muted) 30%,transparent); }
.meter .seg.on { background:var(--accent); box-shadow:none; }
.meter .seg.cap { background:transparent;
  box-shadow:inset 0 0 0 1px var(--pend); }
.fchips { display:inline-flex; gap:5px; flex-wrap:wrap; }
.fchip { font:11.5px var(--mono); border-radius:6px; padding:2.5px 8px;
  white-space:nowrap; background:var(--surface2); color:var(--muted); }
.fchip.pos { background:var(--accent-soft); color:var(--accent); }
.fchip.neg { background:var(--loss-soft); color:var(--loss); }
/* boards + tables */
.board { display:grid; gap:10px; grid-template-columns:1fr; }
@media (min-width:660px){ .board { grid-template-columns:1fr 1fr; } }
.board-t { background:var(--surface); border:1px solid var(--line);
  border-radius:12px; padding:11px 15px; box-shadow:var(--shadow); min-width:0;
  overflow-x:auto; }
.board-h { display:flex; justify-content:space-between; align-items:baseline;
  gap:8px; font:14.5px var(--disp); margin-bottom:6px; flex-wrap:wrap; }
.scroll { overflow-x:auto; }
table { border-collapse:collapse; width:100%; font:13px var(--mono);
  font-variant-numeric:tabular-nums; }
th { text-align:left; color:var(--muted); font-size:11px; letter-spacing:.08em;
  padding:5px 10px 5px 0; border-bottom:1px solid var(--line);
  white-space:nowrap; }
td { padding:6px 10px 6px 0; white-space:nowrap; border-bottom:1px solid
  color-mix(in srgb,var(--line) 55%,transparent); }
tr:last-child td { border-bottom:0; }
td.num { font-variant-numeric:tabular-nums; }
td.stick, th.stick { position:sticky; left:0; background:var(--surface);
  z-index:1; }
a.glink { color:inherit; text-decoration:underline dotted;
  text-underline-offset:3px; text-decoration-color:var(--muted);
  -webkit-tap-highlight-color:transparent; }
a.glink:active, a.glink:hover { color:var(--accent); }
.mk-w { color:var(--win); } .mk-l { color:var(--loss); }
.mk-p { color:var(--void); }
/* table folds · collapsed by default, tap to open */
.fold { background:var(--surface); border:1px solid var(--line);
  border-radius:12px; padding:0 15px; margin:8px 0;
  box-shadow:var(--shadow); }
.fold > summary { padding:13px 0; cursor:pointer; list-style:none;
  display:flex; align-items:center; font:14.5px var(--disp); }
.fold > summary::-webkit-details-marker { display:none; }
.fold > summary::before { content:"▸"; color:var(--accent); margin-right:9px;
  font-family:var(--mono); transition:transform .15s; }
.fold[open] > summary::before { transform:rotate(90deg); }
@media (prefers-reduced-motion:reduce){ .fold > summary::before { transition:none; } }
.fold > summary:focus-visible { outline:2px solid var(--accent);
  outline-offset:-2px; }
.fold-b { padding:2px 0 13px; }
/* game cards */
.games { display:flex; flex-direction:column; gap:8px; }
details.game { background:var(--surface); border:1px solid var(--line);
  border-radius:12px; overflow:hidden; box-shadow:var(--shadow);
  transition:border-color .18s, transform .18s; }
details.game:not([open]):hover {
  border-color:color-mix(in srgb,var(--accent) 40%,var(--line));
  transform:translateY(-1px); }
@media (prefers-reduced-motion:reduce){ details.game { transition:none; } }
details.game > summary { display:flex; align-items:center; gap:11px;
  padding:11px 15px; cursor:pointer; list-style:none; flex-wrap:wrap; }
details.game > summary::-webkit-details-marker { display:none; }
details.game > summary:focus-visible { outline:2px solid var(--accent);
  outline-offset:-2px; }
details.game[open] {
  border-color:color-mix(in srgb,var(--accent) 45%,var(--line)); }
.g-conf { display:flex; align-items:center; flex:none; }
/* fixed title column so every row's line·pair starts at the same x
   (user 2026-07-20: "some are crooked") · widest real title ("chi #32 @
   sea #31") fits inside 150px */
.g-title { font:16px var(--disp); letter-spacing:.01em; white-space:nowrap;
  flex:0 0 148px; display:flex; align-items:baseline; }
.g-away, .g-home { flex:0 0 36px; white-space:nowrap; }
.g-rk { flex:0 0 28px; white-space:nowrap; }
.g-at { flex:0 0 18px; text-align:center; margin-right:4px; }
.rk { font:11px var(--mono); color:var(--accent); white-space:nowrap; }
.rk[data-tip] { cursor:pointer; text-decoration:underline dotted;
  text-underline-offset:3px;
  text-decoration-color:color-mix(in srgb,var(--accent) 55%,transparent); }
/* iphone-first: thumb-size hit area without moving the visual (padding
   grown, margin pulls it back) · applies to every tappable tip source */
[data-tip] { padding:8px 6px; margin:-8px -6px;
  -webkit-tap-highlight-color:transparent; }
[data-tip]:focus-visible { outline:2px solid var(--accent);
  outline-offset:2px; }
.drift { font:13px var(--mono); cursor:pointer; }
.drift.against { color:var(--pend); }
.drift.toward { color:var(--win); }
.tip { position:fixed; z-index:30; background:var(--surface2);
  border:1px solid var(--line); border-radius:8px; padding:6px 11px;
  font:12px/1.5 var(--mono); color:var(--ink); box-shadow:var(--shadow);
  max-width:min(92vw, 340px); pointer-events:none; }
/* fixed slot so the conf column after it never drifts (user 2026-07-20) */
.g-sub { font-size:13px; color:var(--muted); white-space:nowrap;
  flex:0 0 56px; }
.g-right { margin-left:auto; display:flex; align-items:center; }
.g-time { font:13px var(--mono); color:var(--muted); margin-left:9px; }
.g-body { padding:4px 17px 16px; border-top:1px solid var(--line); }
.grail { display:flex; align-items:center; gap:12px; flex-wrap:wrap;
  margin:12px 0 4px; }
.grail-nums { font:12.5px var(--mono); color:var(--muted); }
.miss { font-size:13.5px; color:var(--pend); margin:8px 0 0; }
.gsec { margin:18px 0 0; overflow-x:auto; }
.gsec-h { display:flex; justify-content:space-between; align-items:baseline;
  gap:10px; font:12px var(--mono); letter-spacing:.07em; color:var(--ink);
  margin-bottom:4px; flex-wrap:wrap; position:sticky; left:0; }
.gsec-h .chip { margin-left:5px; }
.gsec-sub { font:12px var(--mono); color:var(--muted); margin-bottom:7px;
  white-space:nowrap; }
.gsec-rail { font:12px var(--mono); color:var(--muted); margin-top:7px;
  white-space:nowrap; }
.strip15 { font-size:12.5px; letter-spacing:1.5px; white-space:nowrap; }
.pickpanel { background:var(--accent-soft); border-left:3px solid var(--accent);
  border-radius:0 12px 12px 0; padding:12px 15px; margin:14px 0 0; }
.pickpanel-h { font:12.5px var(--mono); letter-spacing:.07em;
  color:var(--accent); margin-bottom:7px; }
.kv { display:flex; gap:10px; padding:3.5px 0; align-items:baseline; }
.kv-k { flex:0 0 72px; font:11px var(--mono); letter-spacing:.06em;
  color:var(--accent); }
.kv-v { font-size:13.5px; line-height:1.5; min-width:0; }
/* results */
.rleg { display:flex; gap:12px; align-items:center; padding:8px 0; }
.rmark { flex:none; width:26px; height:26px; border-radius:50%;
  text-align:center; font:13px/26px var(--mono); }
.rmark.w { background:var(--win-soft); color:var(--win); }
.rmark.l { background:var(--loss-soft); color:var(--loss); }
.rmark.p { background:var(--surface2); color:var(--void); }
.rleg-m { flex:1; min-width:0; }
.rleg-top { display:flex; justify-content:space-between; gap:10px;
  align-items:baseline; }
.rleg-pick { font:15px var(--mono); }
.rleg-est { font:12.5px var(--mono); color:var(--muted); }
.res-h { display:flex; justify-content:space-between; align-items:center;
  gap:10px; font:14.5px var(--disp); margin:8px 0 2px; }
.resline { font-size:13.5px; margin:6px 0; }
.resline .kv-k { margin-right:4px; }
/* md fallback bits */
ul { margin:7px 0; padding-left:21px; }
li { margin:4px 0; font-size:14px; }
.rail { border-left:2px solid var(--accent); padding:4px 0 4px 11px;
  font-size:13.5px; color:var(--muted); margin:9px 0; line-height:1.6; }
pre.tbl { background:var(--surface2); border:1px solid var(--line);
  border-radius:9px; padding:11px 13px; overflow-x:auto;
  font:12.5px/1.55 var(--mono); margin:9px 0; }
hr { border:0; border-top:1px solid var(--line); margin:18px 0; }
p { margin:8px 0; }
footer { margin-top:48px; border-top:1px solid var(--line); padding-top:14px;
  font:12px var(--mono); color:var(--muted); line-height:1.8; }
/* motion: one orchestrated load (plate → slip → slate), lamps flicker on ·
   all gated on reduced-motion */
@media (prefers-reduced-motion:no-preference){
  @keyframes rise { from { opacity:0; transform:translateY(12px); } }
  .plate { animation:rise .5s cubic-bezier(.2,.7,.3,1) backwards; }
  #ticket .slip { animation:rise .5s cubic-bezier(.2,.7,.3,1) .08s backwards; }
  details#slate { animation:rise .5s cubic-bezier(.2,.7,.3,1) .16s backwards; }
  @keyframes lampon { from { opacity:0; transform:scale(.4); } }
  .lamp { animation:lampon .4s ease .3s backwards; }
  @supports (interpolate-size: allow-keywords){
    :root { interpolate-size:allow-keywords; }
    details.game::details-content { height:0; overflow:clip;
      transition:height .26s cubic-bezier(.2,.7,.3,1),
        content-visibility .26s allow-discrete; }
    details.game[open]::details-content { height:auto; }
  }
}
"""

JS = (
    # the artifact host wraps this file in its own <head>; a meta sitting in
    # <body> is ignored, so phones would render desktop-width with tiny
    # fonts. inject the viewport into the real head at runtime; no-op when
    # the wrapper already has one.
    '<script>(function(){var h=document.head||document.documentElement;'
    'if(!h.querySelector(\'meta[name="viewport"]\')){var m=document.createElement("meta");'
    'm.name="viewport";m.content="width=device-width, initial-scale=1";'
    "h.appendChild(m);}})();"
    # the wrapper swallows in-page hash navigation · ALL internal anchors
    # (nav links, slip legs, slate rows, back-to-top) navigate
    # programmatically; a <details> target opens before scrolling.
    "(function(){"
    'var smooth=matchMedia("(prefers-reduced-motion: reduce)").matches?"auto":"smooth";'
    'document.addEventListener("click",function(e){'
    'var a=e.target.closest&&e.target.closest(\'a[href^="#"]\');'
    "if(!a)return;e.preventDefault();"
    'var id=a.getAttribute("href").slice(1);'
    'if(!id||id==="top"){(document.scrollingElement||document.documentElement)'
    ".scrollTo({top:0,behavior:smooth});return;}"
    "var t=document.getElementById(id);if(!t)return;"
    'if(t.tagName==="DETAILS")t.open=true;'
    "t.scrollIntoView({behavior:smooth,block:\"start\"});});})();"
    # reading-progress hairline under the nav
    "(function(){"
    'var pb=document.getElementById("pbar");if(!pb)return;'
    "function u(){var d=document.scrollingElement||document.documentElement;"
    "var m=d.scrollHeight-d.clientHeight;"
    'pb.style.transform="scaleX("+(m>0?d.scrollTop/m:0)+")";}'
    'addEventListener("scroll",u,{passive:true});u();})();'
    # streak strip as an index: tapping a mark opens the team fold and
    # flashes the matching table row (capture so the summary never toggles)
    'document.addEventListener("click",function(e){'
    'var mk=e.target.closest&&e.target.closest(".strip15 [data-row]");'
    "if(!mk)return;e.preventDefault();e.stopPropagation();"
    'var d=mk.closest("details.tfold");if(!d)return;d.open=true;'
    'var rows=d.querySelectorAll("tbody tr");'
    'var tr=rows[parseInt(mk.getAttribute("data-row"),10)];if(!tr)return;'
    'd.querySelectorAll("tr.hl").forEach(function(x){x.classList.remove("hl");});'
    'tr.classList.add("hl");'
    'tr.scrollIntoView({behavior:"smooth",block:"nearest"});'
    'setTimeout(function(){tr.classList.remove("hl");},2200);},true);'
    # rank-chip tooltip: the chip's u2.5 record on hover (desktop) or tap
    # (mobile). the tap is captured BEFORE the summary toggle so opening the
    # tip never opens/closes the accordion; any other tap or a scroll hides it.
    # hover previews, tap pins: mobile browsers fire a synthetic mouseover
    # right before the tap, so a naive click-toggle hides the tip the moment
    # it appears · the stuck flag separates the two.
    "(function(){"
    'var tip=document.createElement("div");tip.className="tip";tip.hidden=true;'
    "document.body.appendChild(tip);var cur=null,stuck=false;"
    "function show(el){tip.textContent=el.getAttribute(\"data-tip\");"
    "tip.hidden=false;var r=el.getBoundingClientRect();"
    "var x=Math.min(Math.max(8,r.left+r.width/2-tip.offsetWidth/2),"
    "innerWidth-tip.offsetWidth-8);"
    'tip.style.left=x+"px";tip.style.top=(r.bottom+7)+"px";cur=el;}'
    "function hide(){tip.hidden=true;cur=null;stuck=false;}"
    'document.addEventListener("click",function(e){'
    'var el=e.target.closest&&e.target.closest("[data-tip]");'
    "if(el){e.preventDefault();e.stopPropagation();"
    "if(cur===el&&stuck){hide();}else{show(el);stuck=true;}}"
    "else hide();},true);"
    'document.addEventListener("mouseover",function(e){'
    'var el=e.target.closest&&e.target.closest("[data-tip]");'
    "if(el&&!stuck)show(el);});"
    'document.addEventListener("mouseout",function(e){'
    'if(!stuck&&e.target.closest&&e.target.closest("[data-tip]"))hide();});'
    'addEventListener("scroll",hide,{passive:true});'
    "})();"
    # scrollspy: light the nav link for the section in view
    "(function(){"
    "if(!window.IntersectionObserver)return;"
    'var as=[].slice.call(document.querySelectorAll(".nav-in a[href^=\\"#\\"]"))'
    '.filter(function(a){return a.hash&&a.hash!=="#top";});'
    "var map={},cur=null;"
    "as.forEach(function(a){var el=document.querySelector(a.hash);"
    "if(el)map[el.id]=a;});"
    "var io=new IntersectionObserver(function(es){es.forEach(function(en){"
    "if(!en.isIntersecting)return;var a=map[en.target.id];if(!a||a===cur)return;"
    'if(cur)cur.classList.remove("on");cur=a;cur.classList.add("on");});},'
    '{rootMargin:"-15% 0px -75% 0px"});'
    "Object.keys(map).forEach(function(id){io.observe(document.getElementById(id));});"
    "})();"
    "</script>")


# ---------------------------------------------------------------- page
def build_page(date, data, extras, all_entries, mock=False):
    yesterday = (datetime.strptime(date, "%Y-%m-%d")
                 - timedelta(days=1)).strftime("%Y-%m-%d")
    record = R.compute_season_record(all_entries)
    nights = parlay_nights(all_entries, before=date)
    no_games = data.get("error") == "no games found"
    matchups = [] if no_games else sorted(data["matchups"], key=R.pick_sort_key)
    tiers = tier_map(matchups, all_entries, date, use_log=not mock)
    legs, hms, avoids = split_tiers(matchups, tiers)
    line_lookup = FO.build_line_lookup(all_entries)
    injuries = extras.get("injuries", {})
    context_map = extras.get("context", {})
    postmortem = extras.get("postmortem", "")
    model_v = data.get("model_version", "v4")

    nav_games = '<a href="#slate">slate</a><a href="#games">games</a>' if matchups else ""
    parts = [
        '<meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        # stable title on purpose: one artifact identity across daily
        # republishes (the date lives in the nav)
        "<title>nhl 1p board</title>",
        f"<style>{CSS}</style>",
        f'<nav id="top"><div class="nav-in"><a class="brand" href="#top">nhl 1p u2.5'
        f'<span class="brand-date">{esc(date[5:])}</span></a>'
        f'<a href="#ticket">ticket</a>{nav_games}'
        f'<a href="#yesterday">yesterday</a><a href="#season">season</a>'
        f'</div><div id="pbar"></div></nav>',
        '<div class="wrap">',
        build_masthead(len(matchups), record, nights),
        build_health(date),
        build_ticket(legs, hms, matchups,
                     {e.get("game"): e for e in all_entries
                      if e.get("date") == date and e.get("model") == "v4"}),
        build_glance(matchups, tiers),
        build_hm_avoid(hms, avoids),
        build_games(matchups, data.get("teams", {}), line_lookup, injuries,
                    context_map, tiers, legs, all_entries,
                    data.get("team_rankings") or data.get("season_rankings"))
        if matchups else "",
        build_yesterday(all_entries, yesterday, postmortem),
        build_season(record, nights),
        f"<footer>{esc(model_v)} · r5 + day + goalie + line · /6 scale · "
        f"pick ≥ 4 · hm 2-3 · avoid &lt; 2"
        + (f" · validated through {esc(FO.PARAMS['validated_through'])}"
           if FO.PARAMS.get("validated_through") else "")
        + f" · generated by /nhl · {esc(date)}</footer>",
        "</div>",
        '<a class="totop" href="#top" aria-label="back to top">↑</a>',
        JS,
    ]
    page = "\n".join(p for p in parts if p)
    # display shorthand, page-wide: no years in dates
    page = page.replace("2026-", "").replace("2025-", "")
    return page


def main():
    ap = argparse.ArgumentParser(description="render the daily report as html")
    ap.add_argument("target_date", help="YYYY-MM-DD")
    ap.add_argument("engine_json", help="path to engine output JSON (same file format_output consumed)")
    ap.add_argument("--extras", default="{}", help="same extras json as format_output")
    ap.add_argument("--out", default=None,
                    help="write here instead of the live archive (mock/replay)")
    args = ap.parse_args()
    date = args.target_date

    with open(args.engine_json) as f:
        content = f.read().strip()
    idx = content.find('{"target_date"')
    if idx > 0:
        content = content[idx:]
    data = json.loads(content)

    # freshness gate: the engine json must be THIS date's artifact. a stale
    # file from a previous run renders yesterday's slate as today's · refuse.
    if data.get("target_date") != date:
        sys.exit(f"build_html: engine json is for {data.get('target_date')!r}, "
                 f"not {date} · stale artifact, re-run the pipeline")

    extras = json.loads(args.extras)
    all_entries = R.read_log()
    page = build_page(date, data, extras, all_entries, mock=bool(args.out))

    if args.out:
        with open(args.out, "w") as f:
            f.write(page)
        print(f"wrote {args.out} ({len(page)} bytes) · mock mode, live archive untouched")
        return
    out_path = f"{REPO}/analysis_{date}.html"
    prev = (datetime.strptime(date, "%Y-%m-%d") - timedelta(days=1)).strftime("%Y-%m-%d")
    prev_path = f"{REPO}/analysis_{prev}.html"
    if os.path.exists(prev_path):
        os.remove(prev_path)
        print(f"[deleted {prev_path}]", file=sys.stderr)
    with open(out_path, "w") as f:
        f.write(page)
    print(f"wrote {out_path} ({len(page)} bytes)")


if __name__ == "__main__":
    main()
