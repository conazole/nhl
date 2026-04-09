---
name: weekly review requirement
description: run review.py every week and provide a "what have we learned" report with insights
type: feedback
---

when user says "run review", run `python3 review.py` and provide a "what have we learned" report. not just the script output — interpret it, flag concerns, track trends, connect findings to model decisions, and capture notable learnings. save the report to `review_{YYYY-MM-DD}.md` in the nhl dir, then git add + commit + push. NOT a weekly report — user runs it whenever they want. title it as a review/learnings report, not "weekly review."

**Why:** user wants ongoing model health monitoring. the daily postmortem catches game-level errors; the review catches systemic patterns (confidence calibration drift, team-level blind spots, line factor effectiveness, day-of-week patterns).

**How to apply:** triggered manually by user saying "run review" — no schedule, no cron. run review.py, interpret output, save report file to repo, commit + push to github. key things to watch: confidence tier accuracy (especially 4/6 with v4.1 changes), 6.5 line gate, repeat offender teams, blowout loss patterns. started apr 6 2026.
