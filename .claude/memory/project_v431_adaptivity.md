---
name: project-v431-adaptivity
description: "v4.3.1 (jul 3 2026) — adaptivity release; scoring unchanged, all numbers regenerate from a 5-season backtest into model_params.json; day factor + goalie ladder on watch."
metadata: 
  node_type: memory
  type: project
  originSessionId: de5dfc65-85b0-4c62-811a-ed3316fdb83e
---

v4.3.1 (jul 3 2026): no scoring change. three loops closed (see MODEL_REVIEW_2026-07.md): parameter loop (research/emit_params.py → model_params.json, read by engine/formatter/review/revalidate/season_review with fallbacks · never hand-edit it), data loop (build_dataset.py --season N, per-season point-in-time csvs 2021-2025, --validate mode), judgment loop (caps logged with confidence_uncapped, tag_results.py bust taxonomy, season_review.py).

**why:** the [[project-v43-model]] numbers were one season. pooled over 6,992 games the pick tier is 78.2% [75.8, 80.4] vs 74.6% base (not 83.0%), tier ≥5 is 81.5%, parlay sim 61.2% at ~32% of slates. replay_season.py pushed all 5 seasons through the LIVE code path: legs 78.2% = exactly the backtest (198-132 parlay nights, 60.0%).

**how to apply:**
- quote numbers from model_params.json only; the analysis footer shows validated-through.
- day-game factor is ON WATCH: inverted 2023-24 (71.2 vs 73.7 night) and 2024-25 (69.7 vs 75.3); kept only because no variant without it wins (backtest_variants.py). goalie ladder nearly flat pooled (s+s 75.8 vs b+b 72.7). re-audit both after 2026-27 before trusting or removing.
- new fail-closed caps: short_window (either team <5 games · october produces no picks by design) joins line_missing and the g1 cap; every cap logs uncapped score for grading.
- annual ritual before the first bet of a season: build_dataset --season, drift_lab, backtest_variants, emit_params, season_review (documented in CLAUDE.md + README).
- 2026-27 league changes: 84 games, late-september opener · september now maps to the NEW season in season_from_date/prefetch; re-verify at season start.
- espn stored odds trap: since 2024-25 espn keeps espn bet + an in-game live-odds provider; the live one leaked final-score info into "pregame" totals until filtered. never trust a single-source historical line without provider filtering.
- typography contract: no bolds/headings/em dashes anywhere (middot instead); format_output's sanitizer spells banned chars as unicode escapes · never weaken it. commits as raz, no co-authored-by trailer.
