---
name: betting discipline — only bet on confirmed goalies
description: never bet until goalies are confirmed. 3 cron runs are informational only — only place bets after verifying confirmed starters on dailyfaceoff/edgehalla.
type: feedback
---

only bet when goalies are confirmed. never bet off projected/unconfirmed starters.

**why:** mar 22 both parlay legs lost because model assumed starters but all 4 actual goalies were backups. conf 5 is 1-3 (25%) — the goalie factor contributes 3 of 5 points and is the primary failure mode. individual legs (71.4%) are below the 72.4% base rate, meaning the model currently has no edge when goalie info is wrong.

**how to apply:**
- 3 cron runs (10:17am, 1:03pm, 3:05pm CT) stay intact for information/tracking.
- user will NOT place bets based on any run where goalies are unconfirmed.
- emails should clearly flag goalie confirmation status so user can decide at a glance.
- the analysis is still valuable for tracking and model validation even without betting.
