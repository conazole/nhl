# nhl 1p u2.5 betting model

systematic model for betting nhl 1st period under 2.5 goals. data-driven, no gut feels. real money.

## v4 model (active since mar 28, 2026)

validated on 1149 games (full 2025-26 season with pre-game lines). 4-factor confidence score on a /6 scale:

| factor | criteria | points |
| --- | --- | --- |
| combined r5 u2.5% | <70%: 0, 70-79%: +1, ≥80%: +2 | 0-2 |
| combined r15 u2.5% | <70%: 0, ≥70%: +1 | 0-1 |
| goalie matchup type | starter+starter: +2, starter+tandem: +1, tandem+tandem: 0, any backup: -1 | -1 to +2 |
| total line | ≤5.5: +1, ≤6.0: 0, ≥6.5: -1 | -1 to +1 |

- **pick threshold: ≥4/6.** honorable mention: 2-3. avoid: <2.
- goalie classification: full-season starts share (≥60% starter, 40-59% tandem, <40% backup).
- goalie always scores — confirmed flag is informational, not a scoring gate.
- always a 2-leg parlay (top 2 picks by confidence, tiebreak by r5%). if <2 games qualify, no bet.
- line sourcing: ESPN API + Pinnacle API. take consensus, trust Pinnacle for 6.0 lines (ESPN rounds to 5.5/6.5).

### backtest results (1149 games)

- **parlays: 64.8%** (+6.3pp over v3)
- **legs: 80.5%** (+3.4pp over v3)
- perfectly monotonic confidence gradient
- line factor validation: 5.5 line = 78.7%, 6.0 = 76.4%, 6.5 = 72.6%
- goalie matchup: starter+starter 81.0%, starter+tandem 76.2%, tandem+tandem 71.6%, any backup 66-69%

### killed factors (not in scoring)

poisson edge, elite bonus, b2b/fatigue, context modifiers, system profile, penalty rate, early start. computed for informational display only.

## pipeline

daily runs use a 5-script pipeline (~5 min, ~7 tool calls):

```
resolve_results.py ─┐
                     ├─→ run_analysis.py ─→ format_output.py ─→ update_log.py
prefetch.py ────────┘
```

| step | script | what it does |
| --- | --- | --- |
| 1a | `resolve_results.py` | resolves yesterday's picks against actual 1p scores, computes v4 season record |
| 1b | `prefetch.py` | fetches goalies (dailyfaceoff + nhl.com) and lines (ESPN + Pinnacle) in parallel |
| 2 | `run_analysis.py` | analysis engine — walks 15 games/team, fetches boxscores + xG, computes v4 confidence |
| 3 | `format_output.py` | formats engine JSON into styled analysis file (box-drawing, emojis, fixed-width tables) |
| 4 | `update_log.py` | adds/replaces entries in picks_log.jsonl for the target date |

steps 1a and 1b run in parallel. step 2 takes the goalies + lines from prefetch as CLI args. the skill (`/nhl`) orchestrates the full pipeline, writes the postmortem, sends emails, and commits.

### weekly review

`review.py` analyzes picks_log.jsonl to find patterns the daily postmortem can't see (sample size too small). inspired by [karpathy's llm wiki pattern](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f) — the idea of a persistent synthesis that compounds over time.

```bash
python3 review.py              # all v4 data
python3 review.py --last 14    # last 2 weeks only
```

outputs: confidence calibration, tier accuracy, line factor impact, 1p total distribution, day-of-week splits, team frequency in losses, weekly trend, and a synthesis of systematic blind spots.

## key files

| file | purpose |
| --- | --- |
| `run_analysis.py` | analysis engine — data collection, 15-game walks, boxscores, xG, v4 scoring |
| `prefetch.py` | parallel fetcher for goalies (dailyfaceoff, nhl.com) and lines (ESPN, Pinnacle) |
| `resolve_results.py` | resolves yesterday's unresolved picks against actual scores |
| `format_output.py` | transforms engine JSON into styled markdown analysis file |
| `update_log.py` | manages picks_log.jsonl — adds/replaces entries, preserves resolved results |
| `review.py` | weekly pattern analysis — confidence calibration, blind spots, synthesis |
| `picks_log.jsonl` | full pick history with results, tiers, lines, goalies |
| `analysis_{date}.md` | daily analysis file with 15-game tables, metrics, confidence breakdowns |

## stack

- **nhl api** (`api-web.nhle.com`) — scores, boxscores, play-by-play, club stats. free, no auth.
- **moneypuck** (`peter-tanner.com`) — xG data for opponent-adjusted context (informational only).
- **dailyfaceoff + nhl.com** — goalie confirmations via prefetch.py.
- **ESPN API + Pinnacle API** — game total lines. dual-source to catch 6.0 lines ESPN misses.
- **python** — data collection, metric computation, v4 confidence scoring, all pipeline scripts.
- **applescript** — email delivery via macOS Mail (2 emails: picks summary + mobile analysis).
- **claude code** — orchestration via `/nhl` skill. crontab runs daily at 1:03 PM CT.

## model history

- **v1** (feb 2026): 8-factor /10 scale. killed — no predictive power.
- **v2** (mar 2026): goalie classification used 15-game window, elite list hardcoded, r5≥90% overvalued. killed — picks underperformed avoids.
- **v3** (mar 24, 2026): 3 factors, /5 scale. validated on 892 games. clean gradient but missing line factor — 6.5-line picks hit only 58.3% vs 78.6% on 5.5.
- **v4** (mar 28, 2026): v3 core + total line factor. 4 factors, /6 scale. validated on 1149 games. 64.8% parlays, 80.5% legs. active.
