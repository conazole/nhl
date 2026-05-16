# nhl 1p u2.5 betting model

systematic model for betting nhl 1st period under 2.5 goals. data-driven, no gut feels. real money.

## v4.1 model (active since apr 6, 2026)

v4 core validated on 1149 games. v4.1 splits backup penalty by partner type (275-game audit, apr 6). 4-factor confidence score on a /6 scale:

| factor | criteria | points |
| --- | --- | --- |
| combined r5 u2.5% | <70%: 0, 70-79%: +1, ≥80%: +2 | 0-2 |
| combined r15 u2.5% | <70%: 0, ≥70%: +1 | 0-1 |
| goalie matchup type | starter+starter: +2, starter+tandem OR backup+starter: +1, tandem+tandem: 0, backup+tandem: -1, backup+backup: -1 | -1 to +2 |
| total line | ≤5.5: +1, ≤6.0: 0, ≥6.5: -1 | -1 to +1 |

- **pick threshold: ≥4/6.** honorable mention: 2-3. avoid: <2.
- goalie classification: full-season starts share (≥60% starter, 40-59% tandem, <40% backup).
- goalie always scores — confirmed flag is informational, not a scoring gate.
- always a 2-leg parlay (top 2 picks by confidence, tiebreak by r5%). if <2 games qualify, no bet.
- line sourcing: ESPN API + Pinnacle API. take consensus, trust Pinnacle for 6.0 lines (ESPN rounds to 5.5/6.5).

### backtest results (1149 games + 275-game audit)

- **parlays: 64.8%** (+6.3pp over v3)
- **legs: 80.5%** (+3.4pp over v3)
- perfectly monotonic confidence gradient
- line factor validation: 5.5 line = 78.7%, 6.0 = 76.4%, 6.5 = 72.6%
- goalie matchup: starter+starter 81.0%, starter+tandem 75.8%, **backup+starter 77.4%**, tandem+tandem 72.7%, backup+tandem 62.0%, backup+backup 56.0%

### v4.1 change: backup+starter split (apr 6, 2026)

275-game audit found backup+starter hits u2.5 at 77.4% — same as starter+tandem (75.8%). the old flat -1 for "any backup" was averaging this with backup+tandem (62.0%). the starter anchors the game regardless of the other goalie's starts share. backup save percentage showed no signal — partner type is the predictor.

### killed factors (not in scoring)

poisson edge, elite bonus, b2b/fatigue, context modifiers, system profile, penalty rate, early start, playoff context (mar-jun only). computed for informational display only.

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

## repo files

### pipeline scripts

| file | purpose |
| --- | --- |
| `run_analysis.py` | analysis engine — walks 15 games/team, fetches boxscores + xG, computes v4 confidence, fetches standings (mar-jun) |
| `prefetch.py` | parallel fetcher for goalies (dailyfaceoff, nhl.com) and lines (ESPN, Pinnacle) |
| `resolve_results.py` | resolves yesterday's unresolved picks against actual 1p scores, updates season record |
| `format_output.py` | transforms engine JSON into styled markdown analysis (box-drawing, emojis, fixed-width tables) |
| `update_log.py` | manages picks_log.jsonl — adds/replaces entries, preserves resolved results |
| `review.py` | weekly pattern analysis — confidence calibration, blind spots, synthesis |

### data files

| file | purpose |
| --- | --- |
| `picks_log.jsonl` | full pick history — every game scored, with results, tiers, lines, goalies, model version |
| `analysis_{date}.md` | daily analysis file with 15-game tables, all metrics, confidence breakdowns. previous day's file deleted each run |
| `review_{date}.md` | weekly review output — pattern analysis, blind spots, synthesis |

### config + rules

| file | purpose |
| --- | --- |
| `CLAUDE.md` | single source of truth — all rules, confidence formula, parlay discipline, output/email format, execution pipeline |
| `README.md` | project overview, model docs, file index, changelog |
| `.claude/commands/nhl.md` | `/nhl` skill file — points to CLAUDE.md, triggers the pipeline |
| `.gitignore` | excludes .DS_Store, __pycache__, .cache/ |

### memory (claude code context across conversations)

| file | purpose |
| --- | --- |
| `.claude/memory/MEMORY.md` | memory index — loaded into every conversation |
| `.claude/memory/feedback_*.md` | user corrections and confirmed approaches (16 files) |
| `.claude/memory/project_*.md` | project decisions and their rationale |
| `.claude/memory/user_*.md` | user profile and preferences |
| `.claude/memory/reference_*.md` | pointers to external resources |

### setup on a new machine

```bash
git clone <repo-url> && cd nhl
# symlink memory so claude code finds it
ln -s "$(pwd)/.claude/memory" ~/.claude/projects/-Users-raz-Library-Mobile-Documents-com-apple-CloudDocs-claude-nhl/memory
# symlink ice agent spec into user-scope agents dir
mkdir -p ~/.claude/agents && ln -s "$(pwd)/.claude/agents/ice.md" ~/.claude/agents/ice.md
```

## stack

- **nhl api** (`api-web.nhle.com`) — scores, boxscores, play-by-play, club stats. free, no auth.
- **moneypuck** (`peter-tanner.com`) — xG data for opponent-adjusted context (informational only).
- **dailyfaceoff + nhl.com** — goalie confirmations via prefetch.py.
- **ESPN API + Pinnacle API** — game total lines. dual-source to catch 6.0 lines ESPN misses.
- **python** — data collection, metric computation, v4 confidence scoring, all pipeline scripts.
- **applescript** — email delivery via macOS Mail (2 emails: picks summary + mobile analysis).
- **claude code** — orchestration via `/nhl` skill. crontab runs daily at 1:03 PM CT.

## changelog

- **may 16, 2026**: pipeline — **ice critic disabled.** step 3b skipped entirely; extras JSON no longer includes ice key; analysis files no longer render "🧊 ice review" section. agent spec at `~/.claude/agents/ice.md` left intact and CLAUDE.md spec/template sections kept as reference for easy re-enablement. v4.2 model unchanged — picks/hms continue to be generated deterministically.
- **apr 26, 2026**: display — series score now visible in always-shown sections (parlay leg headers, hm table, per-game collapsed summary). format: `🏆 g4 · col 3-0 lak`. previously only buried in the per-game expanded context. informational only — model still doesn't score series position; the g1 cap remains the only series-state factor in confidence math.
- **apr 19, 2026**: ice upgrade — moved from inline CLAUDE.md template to dedicated agent spec at `~/.claude/agents/ice.md`. now research-driven: mandatory live websearch/webfetch per leg for goalie confirmations (dailyfaceoff), last-24hr lineup/injuries (espn + beat writers), referee crew pp exposure (scoutingtherefs), sharp line movement (action network + pinnacle), 1p-specific recent trend (naturalstattrick + nhl api), and playoff series narrative. built-in knowledge tables (g1 63.3%, g2-3 77-80%, g4+ 81%, line gate 78.7/76.4/72.6, goalie-pair rates). strict per-leg verdict with cited sources, ≤300 words, no fabrication. trigger expanded: now runs on ≥1 pick OR ≥1 hm (was parlay-only) — hm nights benefit from independent goalie/lineup/ref verification. still informational only, parlay text unchanged.
- **apr 18, 2026 (later still)**: telemetry — rich picks_log schema for long-run model improvement. every new entry now carries: factor breakdown (individual r5/r15/goalie/line scores), goalie_pair + per-team classifications, predicted goalies + confirmed flags, is_playoff + series_info. post-game resolution adds: away_1p_goals + home_1p_goals (split from total), actual_goalie_away/home (from nhl api boxscore), goalie_prediction_hit (did dfo match reality?), referees + linesmen (for future ref-crew analysis). new `close_line.py` captures closing lines + clv delta (run ~30 min before first puck drop). new `research/revalidate.py` weekly health check (alerts if any metric drifts >5pp from v4 baseline). new `research/fetch_moneypuck.py` scaffolds xG data for a future v5 factor. `review.py` extended with per-factor hit rates, rolling clv, and base-rate drift monitor. all additions are backward-compatible — legacy entries without these fields still read cleanly.
- **apr 18, 2026 (later)**: model — **v4.2 playoff overrides** added. two patches gated on `gameType==3`: (1) goalie override — dfo-named goalies classify as `starter` regardless of regular-season starts share (88-team-series audit: 88.2% of playoff starts go to team's #1, only 13% true tandems); (2) game-1 confidence cap — g1 playoff games cap at 3/6 (HM max) because g1 u2.5 rate is **63.3% last 2 seasons** (below 73% regular-season baseline). regular-season path unchanged. both patches ship together — goalie override without cap pushes g1s to false picks. backtest: 435-game playoff audit shows +2.4pp u2.5 lift in last 2 seasons from cap, forfeits 17% of playoff games. research data + backtest script in `research/`.
- **apr 18, 2026**: pipeline — added ice critic agent (step 3b) that reviews 2-leg parlays for blindspots before format_output. spawned via Agent tool (general-purpose subagent), renders into analysis + picks email as "🧊 ice review". **informational only** — flags concerns, does NOT downgrade the parlay (v4 is deterministic and validated; ice is a warning light, not a kill switch). fixed update_log.py solo-qualifier bug (n=1 at ≥4/6 now correctly logged as honorable_mention per parlay rules, was being logged as pick). backfilled 3 entries (apr 13 wpg@vgk, apr 14 njd@bos, apr 16 ana@nsh); corrected v4 leg record from 21-6 to 20-4 (83.3%). also hardened format_output.py against zero-games days.
- **apr 9, 2026**: pipeline — added playoff context (standings) as informational display alongside b2b. shows pts/remaining/status (clinched/fighting/eliminated) per team. gated to mar-jun only. not in confidence scoring.
- **apr 7, 2026**: architecture — CLAUDE.md is now single source of truth for all rules. skill file (`/nhl`) references CLAUDE.md instead of duplicating rules. MEMORY.md slimmed to feedback/project index only. eliminates duplication and drift.
- **apr 6, 2026**: v4.1 — backup+starter split from backup+tandem (+1 instead of -1). 275-game audit.

## model history

- **v1** (feb 2026): 8-factor /10 scale. killed — no predictive power.
- **v2** (mar 2026): goalie classification used 15-game window, elite list hardcoded, r5≥90% overvalued. killed — picks underperformed avoids.
- **v3** (mar 24, 2026): 3 factors, /5 scale. validated on 892 games. clean gradient but missing line factor — 6.5-line picks hit only 58.3% vs 78.6% on 5.5.
- **v4** (mar 28, 2026): v3 core + total line factor. 4 factors, /6 scale. validated on 1149 games. 64.8% parlays, 80.5% legs.
- **v4.1** (apr 6, 2026): split backup penalty by partner type. backup+starter → +1 (was -1). 275-game audit: 77.4% u2.5 = same as starter+tandem.
- **v4.2** (apr 18, 2026): playoff overrides (gameType=3 only). (a) named playoff goalies classify as starter regardless of regular-season share (88-team-series audit, 88.2% #1-usage in playoffs); (b) g1 confidence cap at 3/6 (435-game audit, g1 u2.5 rate 63.3% last 2 sns vs 73% reg-season baseline). regular-season path unchanged. active.
