nhl 1p u2.5 betting model

systematic model for betting nhl 1st period under 2.5 goals. data-driven, no gut feels. real money. nothing here is ever a sure thing.

---

a game day, start to finish · the plain-english walkthrough

this is what actually happens when /nhl runs, in order. every number quoted below defers to model_params.json (regenerated from the backtest, stamped with a validated-through date) · if this file and the params file disagree, the params file wins.

1. settle yesterday. resolve_results.py sweeps every unresolved past date against real 1p scores from the nhl api, voids postponed games, recomputes the season record (parlays scored on the top-2 legs actually bet), and runs log-health checks. in parallel, prefetch.py pulls tonight's starting goalies (dailyfaceoff + nhl.com) and total lines (espn + pinnacle), flagging source disagreements · including gate straddles, where a half-point between books would flip the model's line factor and possibly the pick. also in parallel, maintenance.py checks its state file: 7+ days since the last weekly health sweep fires the review trio right now, and the first run of a new season fires the full annual ritual · the checkups ride the runs, so forgetting them is impossible. any drift alert it raises appears as a health line in the analysis.
2. the postmortem. claude writes what we got right / what we got wrong for yesterday, and stamps a structured bust-reason tag (tag_results.py, fixed taxonomy: backup_surprise, pp_goals, track_meet, soft_goals, late_1p_flurry, late_news, plain_variance, other) onto every loss · so bust patterns accumulate in the log instead of evaporating as prose.
3. the engine. run_analysis.py walks each team's last 15 games (regular season + playoffs only · preseason is filtered), computes combined recent-form over the union of both teams' windows, classifies tonight's goalies by starts share, and scores each game 0-6: recent form (0-2), day game (0-1), goalie matchup (-1 to +2), total line (-1 to +1). fail-closed caps pin a game below the pick line when the model shouldn't trust itself: no sourced line, either team with fewer than 5 played games (early season), or playoff game 1. every cap is named in the log with the uncapped score, so cap decisions get graded later.
4. the ticket. games scoring 4+ are picks; the top 2 (by confidence, then recent form, then a fixed tiebreak) become the 2-leg parlay. one qualifier = no parlay tonight. zero = no play tonight. extra qualifiers demote to honorable mentions · never a third leg. games at 2-3 are honorable mentions, below 2 are avoids, and every non-pick carries a one-line reason it missed.
5. the paper trail. the full analysis (at-a-glance board, parlay legs with pre-bet decision info and a computed risk line, per-game blocks with 15-game tables, the postmortem, the season record) prints to terminal and saves as analysis_{date}.md. update_log.py writes every game to picks_log.jsonl with its factor breakdown; line movement between runs is recorded automatically as closing-line value. commit + push, author raz.

what to expect, honestly: over five seasons (2021-22 through 2025-26, 6,992 games, point-in-time backtest) the pick tier hits 78.2% [75.8, 80.4] against a 74.6% league base rate, the 5+/6 tier hits 81.5%, and simulated parlay nights land 61.2% at about a third of slates. the live 2025-26 record (18-5 parlays, 41-5 legs) ran hotter than that · treat the pooled numbers as the expectation and the hot season as variance in our favor. sizing and discipline: fewer bets, bigger stakes, only confirmed goalies, never chase.

---

the v4.3.1 model (active jul 3 2026)

v4.3 formula, unchanged: combined r5 (0-2) + day game (0-1) + goalie matchup (-1..+2) + total line (-1..+1) on a /6 scale, pick at >=4. v4.3.1 changed no scoring · it is the adaptivity release:

- parameter loop: research/emit_params.py regenerates model_params.json (all factor cutoffs, point maps, thresholds, measured hit rates with wilson CIs, parlay simulation, playoff rates, a watch list, validated-through stamp). the engine, formatter, review, revalidate, and season review read it with fallbacks. docs defer to it. the analysis footer prints the validated-through date so staleness is visible.
- data loop: research/build_dataset.py --season {year} builds one point-in-time csv per season (nhl api scores + moneypuck starters/xg with auto-download + espn stored pregame totals with the live-odds provider filtered out and raw responses cached). --validate rebuilds a season already on disk and diffs core columns · the 2025-26 rebuild matched with zero score mismatches. wrong-date and wrong-season guards are fatal, never silent.
- judgment loop: every fail-closed cap logs the uncapped score + a named cap, structured bust tags accumulate via tag_results.py, and season_review.py measures tier calibration, cap precision, goalie-prediction accuracy, the live day-factor, clv, and line-source health against the params baselines.
- live-path replay: replay_season.py pushes historical slates through the real selection code (walk_scores → compute_matchups → tiering → parlay pick) and reconciles every game against the vectorized backtest. its first run caught a real bug (goalie-share state drifting after a skipped date).
- the honest re-baselining: v4.3's 83.0% pick tier was one season. across five seasons the same rules hit 78.2% [75.8, 80.4] on 1,243 picks · above base every season except 2024-25 (74.8% ≈ base). tier >=5: 81.5%. the edge is real, modest, and concentrated at the top of the scale.

on watch (see model_params.json watch list): the day-game factor inverted in 2023-24 and 2024-25 (pooled +2.0pp; 2025-26's 83.2% was the good year) · the goalie ladder is nearly flat pooled (s+s 75.8% vs b+b 72.7%) · playoff g1 pooled 69.3% vs g2+ 77.0% (cap stays). no variant without these factors beats the shipped composite (research/backtest_variants.py), so the scoring stands and the watch list decides what 2026-27's evidence must answer.

killed factors (not in scoring, do not re-add): r15 (v4.3 · inverted on holdout), poisson, elite bonus, b2b, context modifiers, system profile, penalty rate, h2h, venue-split form, day-of-week, rolling 1p goal/sog/xg environments, standings-status playoff context (display only).

fail-closed caps: no sourced line → 3/6 max. either team under 5 played games → 3/6 max (new in v4.3.1 · the validated regime requires 5+; october small samples were scoring spurious +2s). playoff game 1 → 3/6 max. named playoff goalies classify as starter (v4.2 override).

---

pipeline

daily runs use a 5-script pipeline (~5 min):

```
resolve_results.py ─┐
prefetch.py ────────┼─→ run_analysis.py ─→ format_output.py ─→ update_log.py
maintenance.py ─────┘
         (+ tag_results.py for yesterday's losses, step 2)
```

```
step  script              what it does
1a    resolve_results.py  sweep-resolves all unresolved past dates, voids
                          postponed games, season record, invariant warnings
1b    prefetch.py         goalies (dfo + nhl.com) and lines (espn + pinnacle)
                          in parallel · gate-straddle + unmapped-name warnings
2     tag_results.py      structured bust tags on yesterday's losses
3     run_analysis.py     the engine · windows, goalie classification,
                          v4.3.1 confidence from model_params.json, caps
4     format_output.py    minimalist analysis file + typography sanitizer ·
                          --out for mocks (never touches the live archive)
5     update_log.py       picks_log.jsonl upsert, 2-leg demotion, clv capture
```

shared record math (season record, top-2 parlay scoring, deterministic pick ordering, log invariants) lives in record.py · imported by resolve_results, update_log, format_output, and close_line so the numbers can never drift apart.

weekly, in season (auto-fenced · maintenance.py fires this trio inside the first /nhl run 7+ days after the last sweep):

```
python3 review.py --last 14          # patterns, factor hit rates, clv, drift
python3 research/revalidate.py       # recent-100 vs params baselines, alerts >5pp
python3 season_review.py             # judgment loop: tiers, caps, busts, goalies
```

annual ritual, before the first bet of each season (auto-fenced · maintenance.py fires it on the first run of a new season and refuses to stamp it complete if any step fails):

```
python3 research/build_dataset.py --season {just_finished}
python3 research/build_dataset.py --season {prior_season} --validate
python3 research/drift_lab.py            # read section 3 drift flags
python3 research/backtest_variants.py    # composite variants head-to-head
python3 research/emit_params.py          # regenerate model_params.json
python3 season_review.py --since {season_start}
```

a drift flag is a research prompt, not a switch. any behavior change bumps the version and updates README + CLAUDE.md + the skill in the same commit.

---

repo files

pipeline scripts

```
run_analysis.py     analysis engine · windows, goalie classification, caps,
                    v4.3.1 confidence (policy from model_params.json)
prefetch.py         parallel fetcher · goalies (dfo, nhl.com), lines (espn,
                    pinnacle), injuries, gate-straddle + unmapped-name warnings
record.py           shared record math · season record, pick sort key, log io,
                    invariant checker
resolve_results.py  sweep-resolves past dates, voids postponed, updates record
format_output.py    minimalist analysis file · typography sanitizer, per-game
                    miss reasons, params footer, --out mock mode
update_log.py       picks_log.jsonl upsert · 2-leg demotion, cap telemetry,
                    transparent clv capture
tag_results.py      structured bust-reason tags (fixed taxonomy)
maintenance.py      self-fencing gate · auto-runs the weekly trio (7-day
                    counter) + the annual ritual (new-season counter) inside
                    /nhl runs · state in maintenance_state.json
season_review.py    judgment-loop calibration vs params baselines
replay_season.py    live-path replay of past seasons + backtest reconciliation
review.py           weekly pattern analysis
close_line.py       standalone closing-line refresh (optional)
```

research

```
research/build_dataset.py       point-in-time csv per season (the data loop)
research/season_dataset_{y}.csv the datasets · 2021-2025, ~1,400 games each
research/drift_lab.py           per-season factor stability, z-tests,
                                threshold re-learning
research/backtest_variants.py   scoring variants head-to-head, multi-season
research/emit_params.py         writes model_params.json (the parameter loop)
research/revalidate.py          weekly health check vs params baselines
research/factor_lab.py          preserved jun-2026 v4.3 decision artifact
research/backtest_v43.py        preserved jun-2026 v4.3 decision artifact
research/migrate_*.py           one-time log migrations (audit-trail pattern)
```

data + docs

```
model_params.json        machine-generated · every quoted number, stamped
                         validated-through · never hand-edited
maintenance_state.json   machine-written · last weekly sweep + last annual
                         ritual season · never hand-edited
picks_log.jsonl          full pick history · factors, caps, results, clv
analysis_{date}.md       daily analysis file (previous day's deleted each run)
research/mock_*.md       mock analysis files from replay/mock runs
CLAUDE.md                single source of truth for all rules
MODEL_REVIEW_2026-07.md  the jul 2026 audit · findings, drift experiments,
                         what was built and why
README.md                this file · walkthrough, model docs, changelog
.claude/commands/nhl.md  the /nhl skill · points at CLAUDE.md
```

setup on a new machine

```
git clone <repo-url> && cd nhl
ln -s "$(pwd)/.claude/memory" ~/.claude/projects/-Users-raz-Library-Mobile-Documents-com-apple-CloudDocs-claude-nhl/memory
mkdir -p ~/.claude/agents && ln -s "$(pwd)/.claude/agents/ice.md" ~/.claude/agents/ice.md
```

stack: nhl api (api-web.nhle.com, free) · moneypuck (xg + historical starters) · dailyfaceoff + nhl.com (goalies) · espn + pinnacle (lines) · python · claude code (/nhl skill).

---

changelog

- jul 3 2026 (v4.3.1 addendum) · self-fencing maintenance gate. new maintenance.py runs in step 1 of every /nhl run: a 7-day counter fires the weekly health trio (review.py, revalidate.py, season_review.py) and a season counter fires the full annual ritual on the first run of a new season, saving output to research/annual_ritual_{season}.txt. state lives in maintenance_state.json (machine-written) and the gate persists its summary there, so format_output renders the health block into the analysis file deterministically · no agent hand-copying. drift alerts + ritual status appear under the masthead; an incomplete annual ritual blocks betting until it passes. no cron · the checkups ride the runs, so they cannot be forgotten.
- jul 3 2026 (v4.3.1) · the adaptivity release. no scoring change; every constant and claim now regenerates from evidence.
  - three loops closed. parameter loop: model_params.json emitted by research/emit_params.py from a new 5-season 6,992-game point-in-time backtest · engine/formatter/review/revalidate/season_review read it with fallbacks; the analysis footer shows validated-through. data loop: build_dataset.py parameterized by season (was frozen to 2025-26 four ways), moneypuck auto-download, espn stored pregame totals as the historical line source, --validate mode (2025 rebuild: zero score mismatches). judgment loop: named fail-closed caps logged with uncapped scores, tag_results.py bust taxonomy, season_review.py calibration report.
  - honest re-baselining. the pick tier is 78.2% [75.8, 80.4] pooled over five seasons (not the one-season 83.0%); tier >=5 81.5%; parlay sim 61.2% at 32% of slates. day-game factor inverted in 2023-24/2024-25 and the goalie ladder is nearly flat pooled · both on the params watch list, kept only because no variant without them wins (backtest_variants.py).
  - live-path replay. new replay_season.py replays whole seasons through the actual selection code and reconciles per-game with the backtest. its divergence hunt found and fixed a goalie-share state bug; a 2021-22 dry run graded 51-28 parlay nights (64.6%) with legs at 79.7%.
  - data-source forensics. espn's stored odds since 2024-25 mix a pregame line with an in-game live-odds snapshot · a naive median leaked final-score information into "pregame" totals (93.8% u2.5 on <=5.5 lines, impossible). the live provider is excluded, totals outside 5.0-8.5 dropped, raw responses cached.
  - live bugs fixed before they cost money. preseason games polluted early-october windows (gameType now filtered everywhere); r5 on <5 games scored spurious +2s (new short_window cap); utah mammoth's may-2025 rename silently killed uta pinnacle lines + dfo goalie mapping for a full season (maps fixed, unmapped names now warn loudly); nhl.com lineup url was hardcoded to 2025-26 (now season-derived); the schedule-endpoint fallback parsed zero games; september dates mapped to the wrong season and standings assumed 82 games (2026-27 plays 84 from late september); gate-straddle warnings when books disagree across a line-factor boundary.
  - output contract. typography sanitizer in format_output.py (no bolds/headings/em dashes · banned characters spelled as unicode escapes so a sweep can't neuter it), per-game one-line miss reasons, --out mock mode that never touches the live archive or the log. review.py's saved report restyled to match.
  - docs. CLAUDE.md + README fully restyled to the same typography and re-anchored to params; MODEL_REVIEW_2026-07.md holds the audit, experiments, and rationale.
- jun 12 2026 (v4.3 + audit): record correction (18-5 parlays / 41-5 legs after top-2 scoring + sweep-resolve + tier backfill), engine hardening (no cache-on-failure, fail-closed line gate, de-duped combined windows), r15 replaced by the day-game factor after a 1393-game point-in-time revalidation, minimalist analysis redesign, telemetry (model_version, factors.day, is_day_game).
- jun 6 2026: fixed format_output dropping the postmortem when yesterday had no games.
- may 16 2026: ice critic disabled (spec kept for re-enablement).
- apr 26 2026: series score surfaced in always-visible sections.
- apr 22 2026: emails disabled.
- apr 19 2026: ice upgraded to a research-driven agent spec.
- apr 18 2026 (v4.2): playoff overrides · dfo-named playoff goalies classify as starter (88-team-series audit); game-1 confidence cap (g1 u2.5 below baseline). rich telemetry schema (factors, goalie predictions, referees, clv via close_line.py); revalidate.py health check; ice critic added (informational only).
- apr 9 2026: playoff-race context as informational display.
- apr 7 2026: CLAUDE.md became the single source of truth; skill file points at it.
- apr 6 2026 (v4.1): backup+starter split from backup+tandem (+1, not -1) · 275-game audit.

model history

- v1 (feb 2026): 8-factor /10 scale. killed · no predictive power.
- v2 (mar 2026): 15-game goalie window, hardcoded elite list, r5>=90 overvalued. killed · picks underperformed avoids.
- v3 (mar 24 2026): 3 factors /5. clean gradient, missing the line factor.
- v4 (mar 28 2026): + total line factor, /6 scale.
- v4.1 (apr 6 2026): backup penalty split by partner type.
- v4.2 (apr 18 2026): playoff goalie override + g1 cap.
- v4.3 (jun 12 2026): r15 → day game after point-in-time revalidation.
- v4.3.1 (jul 3 2026): the adaptivity release · loops closed, numbers regenerated, scoring unchanged. active.
