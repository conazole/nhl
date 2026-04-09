---
name: strip poisson from output
description: don't display poisson in analysis output — it's not a scoring factor and adds noise
type: feedback
---

strip poisson from all output — final table, per-game breakdowns, honorable mention lines. if it doesn't predict outcomes, showing it just clutters the output and makes it look like it matters.

**Why:** user pointed out that displaying a killed factor is pointless noise. poisson had zero predictive power in the 135-game backtest and is not used in v2 confidence scoring.

**How to apply:** run_analysis.py still computes poisson (for future validation if we ever want to check it again), but the skill output must not show it anywhere. no poisson column in the parlay table, no poisson lines in game breakdowns, no poisson percentages in HM/avoid summaries.
