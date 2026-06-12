---
name: project-v43-model
description: v4.3 model (jun 12 2026) — r15 replaced by day-game factor; why, the validation, and what to re-check next season.
metadata:
  type: project
---

v4.3 (active jun 12 2026): r5 + day-game + goalie + line on /6. the r15 factor was unscored after failing holdout validation on a 1393-game point-in-time dataset (research/build_dataset.py + factor_lab.py + backtest_v43.py — chronological split feb 15 2026, wilson CIs).

**why:** r15 was +1.6pp full-season and INVERTED on holdout; its +1 fired on 63% of games (any 15-game window sits near base rate), which pushed no-edge games over the 4/6 pick line — the 208 picks it added vs the day-swap variant hit 75.0% = exactly base rate. day games (<5pm ET) hit 83.2% u2.5 (119/143) vs 72.7% prime-time, holding on both sides of the split. the day-game hypothesis came from the user ("early start games tend to go under") — the engine's old "early start" kill had used a too-narrow definition (11am/12pm CT only).

**how to apply:**
- r15 stays computed/logged/displayed + in the deterministic tiebreak — never scored. don't "helpfully" re-add it.
- expect lower confidence scores and roughly half the pick volume (~2-3 parlay nights/week) — that is the design, and it matches the user's fewer-bets-bigger-stakes philosophy ([[user_betting_strategy]]).
- conf-6 is now rare (needs a day game); 5/6 is the practical top tier most nights.
- next-season re-checks (run research/ scripts on new-season data first): does the day factor hold (n=143 this season)? goalie map — point-in-time audit found backup+tandem ≈ base (74.0%) and tandem+tandem worst (67.4%), map left unchanged pending re-audit; g1 cap — live g1s ran 73.3% vs the 63.3% audit basis, retire if it keeps tracking pooled.
- season record correction shipped the same day: 18-5 parlays / 41-5 legs after the apr-9/apr-26 accounting fixes (top-2 parlay scoring in record.py, sweep-resolve, tier backfill migration).
