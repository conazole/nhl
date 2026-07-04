#!/usr/bin/env python3
"""replay past seasons through the LIVE selection code · the dress rehearsal.

usage:
    python3 replay_season.py 2024                 # one season, night by night
    python3 replay_season.py 2021 2022 2023 2024  # several
    python3 replay_season.py 2025 --tickets       # print every parlay night

what this is: research/emit_params.py and drift_lab.py validate the RULES on
preprocessed csv rows, but they re-implement the scoring · they are not the
engine. this script instead rebuilds each historical slate from the cached
nhl score payloads (the same payload the live fetch_todays_games consumes)
and pushes it through the real code path:

    run_analysis.walk_scores          (15-game windows, de-duped combined)
    run_analysis.compute_team_metrics
    run_analysis.compute_matchups     (all four factors + every cap)
    update_log.entries_from_engine    (tiering, 2-leg demotion)
    record.parlay_legs_for_date       (the ticket)

then grades the generated tickets against real 1p finals and reconciles
every night against the vectorized scorer. a material disagreement between
replay and backtest is a bug in one of them · investigate before betting.

known, honest gaps vs the deployed model (all documented, none scored):
- tonight's goalies are the ACTUAL starters (from the dataset), confirmed.
  live uses dfo predictions (93.2% accurate last season) · replay is the
  ceiling on goalie knowledge, live sits just below it.
- goalie classification is starts-share TO DATE rebuilt from the dataset.
  live reads club-stats on game day, which serves exactly the same
  to-date numbers · equivalent by construction, not by luck.
- lines are the logged line of record where a run recorded one, else the
  espn stored median. espn is a closing consensus · same caveat as the
  backtest.
- boxscore/pbp details are not fetched (shots/pens/xg are informational,
  never scored) · goalie display labels degrade, scoring path unaffected.
- no injuries, no postmortem context, no manual verification · this is the
  mechanical floor.
"""

import csv, json, os, sys, argparse
from collections import defaultdict
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import run_analysis as eng                    # noqa: E402
from update_log import entries_from_engine    # noqa: E402
from record import parlay_legs_for_date       # noqa: E402

# replay reads the local score cache built by build_dataset; the engine's
# polite api pacing (0.03s per walked date) would add ~5 min per season of
# pure sleep for zero benefit. real cache misses are rare one-time fetches.
eng.time.sleep = lambda *_: None

CACHE_SCORES = os.path.join(HERE, ".cache", "scores")


def load_season_csv(season):
    path = os.path.join(HERE, "research", f"season_dataset_{season}.csv")
    if not os.path.exists(path):
        sys.exit(f"missing {path} · run research/build_dataset.py --season {season} first")
    rows = []
    with open(path) as f:
        for r in csv.DictReader(f):
            r["u25"] = int(r["u25"])
            rows.append(r)
    # playoff game number within each series (for the g1 cap fallback)
    series = defaultdict(list)
    for r in rows:
        if r["phase"] == "po":
            series[tuple(sorted([r["away"], r["home"]]))].append(r)
    for games in series.values():
        games.sort(key=lambda x: x["date"])
        for i, g in enumerate(games, 1):
            g["game_num"] = i
    return rows


def fnum(v):
    try:
        return float(v)
    except (ValueError, TypeError):
        return None


def cached_score_payload(ds):
    p = os.path.join(CACHE_SCORES, f"{ds}.json")
    if not os.path.exists(p):
        return None
    with open(p) as f:
        return json.load(f)


def slate_from_cache(ds, csv_by_key):
    """rebuild games_tonight exactly as fetch_todays_games would see it,
    from the cached score payload. csv rows supply the g1-cap fallback when
    the payload lacks seriesStatus."""
    payload = cached_score_payload(ds)
    if payload is None:
        return None
    games = []
    for g in payload.get("games", []):
        if g.get("gameType", 2) not in (2, 3):
            continue
        aw = eng.normalize_abbrev(g.get("awayTeam", {}).get("abbrev", ""))
        hm = eng.normalize_abbrev(g.get("homeTeam", {}).get("abbrev", ""))
        if (ds, aw, hm) not in csv_by_key:
            continue                       # not a final in the dataset
        start_utc = g.get("startTimeUTC", "")
        game_type = g.get("gameType", 2)
        series_info = None
        if game_type == 3:
            ss = g.get("seriesStatus") or {}
            gn = ss.get("gameNumberOfSeries") or csv_by_key[(ds, aw, hm)].get("game_num")
            series_info = {
                "game_num": gn,
                "round": ss.get("round"),
                "round_label": ss.get("seriesTitle"),
                "top_seed": ss.get("topSeedTeamAbbrev"),
                "top_wins": ss.get("topSeedWins", 0),
                "bottom_seed": ss.get("bottomSeedTeamAbbrev"),
                "bottom_wins": ss.get("bottomSeedWins", 0),
            }
        games.append((aw, hm, start_utc, game_type, series_info))
    return games


def replay_season(season, show_tickets=False):
    rows = load_season_csv(season)
    csv_by_key = {(r["date"], r["away"], r["home"]): r for r in rows}
    dates = sorted({r["date"] for r in rows})

    # point-in-time goalie starts-share state, updated after each date
    starts_count = defaultdict(lambda: defaultdict(int))
    team_gp = defaultdict(int)

    stats = {"nights": 0, "parlay_w": 0, "parlay_l": 0, "leg_w": 0, "leg_l": 0,
             "no_slate": 0, "diverge": []}
    picks_by_conf = defaultdict(lambda: [0, 0])
    busts = []

    def update_goalie_state(ds):
        """count the date's starts from the CSV ROWS, not the scored slate ·
        a date with a missing payload must still advance the to-date shares,
        or every later classification drifts off the point-in-time truth
        (found via a 40-game replay-vs-backtest divergence hunt, jul 2026)."""
        for r in rows:
            if r["date"] != ds:
                continue
            for team, gl in ((r["away"], r["away_goalie"]),
                             (r["home"], r["home_goalie"])):
                if gl:
                    starts_count[team][gl] += 1
                    team_gp[team] += 1

    for ds in dates:
        eng._TARGET_DATE = ds
        slate = slate_from_cache(ds, csv_by_key)
        if not slate:
            stats["no_slate"] += 1
            update_goalie_state(ds)
            continue

        teams_needed = set()
        for a, h, *_ in slate:
            teams_needed.update((a, h))

        # the real 15-game window walk (fully cache-backed after build_dataset)
        team_games, league_total, league_u25, h2h, gids = eng.walk_scores(
            ds, teams_needed, slate)
        base_rate = league_u25 / league_total * 100 if league_total else 70.0

        metrics = eng.compute_team_metrics(teams_needed, slate, team_games,
                                           {}, {}, False)
        target_dt = datetime.strptime(ds, "%Y-%m-%d")
        for team, m in metrics.items():
            if m["games"]:
                last = datetime.strptime(m["games"][0]["date"], "%Y-%m-%d")
                m["rest_days"] = (target_dt - last).days

        # tonight's inputs from the dataset: actual starters + to-date shares
        tonight_goalies, season_stats, tonight_lines = {}, {}, {}
        for a, h, *_ in slate:
            r = csv_by_key[(ds, a, h)]
            for team, gl in ((a, r["away_goalie"]), (h, r["home_goalie"])):
                if gl:
                    tonight_goalies[team] = {"name": gl, "confirmed": True}
                    gp = team_gp[team]
                    if gp >= 1:
                        # mirror what club-stats would serve on this date:
                        # starts share to date, however small the sample
                        season_stats[team] = {gl: {
                            "gp": gp, "gs": starts_count[team].get(gl, 0),
                            "share": starts_count[team].get(gl, 0) / gp,
                            "total_team_gs": gp, "sv_pct": 0.0, "gaa": 0.0}}
            line = fnum(r["total_line"]) or fnum(r["espn_total"])
            if line is not None:
                tonight_lines[f"{a}@{h}"] = line

        matchups = eng.compute_matchups(slate, metrics, h2h, 0.8, base_rate,
                                        tonight_goalies, season_stats,
                                        frozenset(), tonight_lines, {})

        # the real tiering + demotion + ticket selection
        entries = entries_from_engine({"matchups": matchups,
                                       "model_version": eng.MODEL_VERSION})
        picks = [e for e in entries if "tier" not in e]
        stats["nights"] += 1

        # grade
        night_line = None
        if len(picks) >= 2:
            legs = parlay_legs_for_date(picks)
            results = []
            for leg in legs:
                a, h = leg["game"].split(" @ ")
                r = csv_by_key[(ds, a.upper(), h.upper())]
                won = bool(r["u25"])
                results.append((leg, won))
                stats["leg_w" if won else "leg_l"] += 1
                picks_by_conf[leg["confidence"]][0 if won else 1] += 1
                if not won:
                    busts.append((ds, leg["game"], leg["confidence"],
                                  r["total_1p"]))
            hit = all(w for _, w in results)
            stats["parlay_w" if hit else "parlay_l"] += 1
            night_line = " · ".join(
                f"{leg['game']} {leg['confidence']}/6" + ("" if w else " ✗")
                for leg, w in results)
            if show_tickets or not hit:
                print(f"  {ds}: {'WIN ' if hit else 'loss'} | {night_line}")

        # reconcile every matchup against the vectorized scorer
        for m in matchups:
            r = csv_by_key[(ds, m["away"], m["home"])]
            vec = vec_score(r)
            if vec is not None and vec != m["confidence"]:
                stats["diverge"].append(
                    (ds, f"{m['away']}@{m['home']}", m["confidence"], vec,
                     m.get("caps"), r))

        # update to-date goalie state AFTER the slate is scored, from the
        # csv rows (every final on the date, scored or not)
        update_goalie_state(ds)

    return stats, picks_by_conf, busts


GOALIE_43 = {"starter+starter": 2, "starter+tandem": 1, "backup+starter": 1,
             "tandem+tandem": 0, "backup+tandem": -1, "backup+backup": -1}


def vec_score(r):
    """the vectorized backtest scorer (emit_params policy) for reconciliation."""
    v5 = fnum(r["comb_r5_pct"])
    pair = r["goalie_pair"]
    if v5 is None or (not pair and r["phase"] != "po"):
        return None
    f5 = 2 if v5 >= 80 else (1 if v5 >= 70 else 0)
    eh = fnum(r["et_hour"])
    day = 1 if (eh is not None and eh < 17) else 0
    fg = 2 if r["phase"] == "po" else GOALIE_43.get(pair)
    if fg is None:
        return None
    ln = fnum(r["total_line"]) or fnum(r["espn_total"])
    fl = 0 if ln is None else (1 if ln <= 5.5 else (0 if ln <= 6.0 else -1))
    total = max(0, f5 + day + fg + fl)
    if r["phase"] == "po" and r.get("game_num") == 1:
        total = min(total, 3)
    return total


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("seasons", nargs="+", type=int)
    parser.add_argument("--tickets", action="store_true",
                        help="print every parlay night, not just the losses")
    parser.add_argument("--divergences", action="store_true",
                        help="print every replay-vs-backtest score disagreement")
    args = parser.parse_args()

    print(f"live-engine replay ({eng.MODEL_VERSION} · actual starters, "
          f"line of record else espn median · mechanical floor)")

    tw = tl = lw = ll = 0
    all_div = []
    for season in args.seasons:
        print(f"\n─── {season}-{str(season + 1)[2:]} " + "─" * 44)
        stats, by_conf, busts = replay_season(season, args.tickets)
        pn = stats["parlay_w"] + stats["parlay_l"]
        ln = stats["leg_w"] + stats["leg_l"]
        print(f"  parlays {stats['parlay_w']}-{stats['parlay_l']}"
              f" ({100*stats['parlay_w']/pn:.1f}%)" if pn else "  no parlay nights",
              end="")
        if ln:
            print(f" · legs {stats['leg_w']}-{stats['leg_l']} "
                  f"({100*stats['leg_w']/ln:.1f}%) · "
                  f"{pn}/{stats['nights']} slates played")
        else:
            print()
        for c in sorted(by_conf, reverse=True):
            w, l = by_conf[c]
            print(f"    conf {c}: {w}-{l}")
        if stats["no_slate"]:
            print(f"  ({stats['no_slate']} dates had no cached score payload)")
        n_div = len(stats["diverge"])
        print(f"  replay-vs-backtest score disagreements: {n_div}")
        all_div.extend(stats["diverge"])
        tw += stats["parlay_w"]; tl += stats["parlay_l"]
        lw += stats["leg_w"]; ll += stats["leg_l"]

    if len(args.seasons) > 1 and tw + tl:
        print(f"\n═══ combined: parlays {tw}-{tl} ({100*tw/(tw+tl):.1f}%) · "
              f"legs {lw}-{ll} ({100*lw/(lw+ll):.1f}%)")

    if all_div and args.divergences:
        print(f"\n─── divergences ({len(all_div)}) · replay conf vs backtest conf")
        for ds, game, live_c, vec_c, caps, r in all_div[:60]:
            print(f"  {ds} {game}: replay {live_c} vs backtest {vec_c} "
                  f"(caps {caps} · csv r5 {r['comb_r5_pct']} pair {r['goalie_pair']})")
    elif all_div:
        # summarize the reasons without dumping everything
        higher = sum(1 for d in all_div if d[2] > d[3])
        print(f"\n{len(all_div)} score disagreements across all seasons "
              f"({higher} replay-higher, {len(all_div)-higher} backtest-higher) "
              f"· rerun with --divergences to list them")


if __name__ == "__main__":
    main()
