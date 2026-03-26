# nhl 1p u2.5 betting model

systematic model for betting nhl 1st period under 2.5 goals. data-driven, no gut feels. real money.

## v3 model (active since mar 24, 2026)

validated on 892 games (nov 7 - mar 22). 3-factor confidence score on a /5 scale:

| factor | criteria | points |
| --- | --- | --- |
| combined r5 u2.5% | <70%: 0, 70-79%: +1, ≥80%: +2 | 0-2 |
| combined r15 u2.5% | <70%: 0, ≥70%: +1 | 0-1 |
| goalie matchup type | starter+starter: +2, starter+tandem: +1, tandem+tandem: 0, any backup: -1 | -1 to +2 |

- **pick threshold: ≥4/5.** honorable mention: 2-3. avoid: <2.
- goalie classification: full-season starts share (≥60% starter, 40-59% tandem, <40% backup).
- goalie factor only scores when both goalies are confirmed — unconfirmed = 0.
- always a 2-leg parlay (top 2 picks). if <2 games qualify, no bet.

### backtest results (892 games)
- picks (≥4): 80.1% hit rate (+5.5pp over base rate)
- avoids (<2): 71.1% (-3.4pp) — correctly filtered
- starter vs starter: 81.0% on 247 games
- any backup: 66-69% on 252 games

### killed factors (not in scoring)
poisson edge, elite bonus, b2b/fatigue, context modifiers, system profile, penalty rate. computed for informational display only.

## how it works

1. fetch tonight's slate from the nhl api
2. confirm goalies from 3 sources (dailyfaceoff, nhl.com, web search)
3. run `run_analysis.py` — walks 15 games per team, fetches boxscores + play-by-play + moneypuck xG, computes all metrics and v3 confidence
4. output full analysis (terminal + saved file), send 2 emails (picks summary + mobile analysis)
5. log all games to `picks_log.jsonl`, commit and push

## key files

| file | purpose |
| --- | --- |
| `run_analysis.py` | analysis engine — all data collection and v3 scoring in one script |
| `picks_log.jsonl` | full pick history with results, avoids, honorable mentions |
| `analysis_{date}.md` | daily analysis file with 15-game tables, metrics, confidence breakdowns |
| `~/.claude/commands/nhl.md` | skill file — workflow, output format, email rules, goalie protocol |

## stack

- nhl api (`api-web.nhle.com`) — scores, boxscores, play-by-play, club stats. free, no auth.
- moneypuck (`peter-tanner.com`) — xG data for opponent-adjusted poisson (informational only)
- dailyfaceoff + nhl.com + web search — goalie confirmations (3-source protocol, mandatory)
- espn — game total lines (tracked for future validation, not in scoring)
- python — data collection, metric computation, v3 confidence scoring
- applescript — email delivery via macOS Mail

## model history

- **v1** (feb 2026): 8-factor /10 scale. killed — no predictive power.
- **v2** (mar 2026): goalie classification used 15-game window, elite list hardcoded, r5≥90% overvalued. killed — picks underperformed avoids.
- **v3** (mar 24, 2026): rebuilt from 892-game backtest. 3 factors, /5 scale. clean monotonic gradient. active.
