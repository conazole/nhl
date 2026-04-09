---
name: goalie sourcing and classification
description: tonight's starting goalie must come from external sources (dailyfaceoff, team announcements), not starts-share math. historical classification uses starts-share thresholds.
type: feedback
---

tonight's starting goalie must be sourced from external sources — never assumed from math.

**why:** on mar 22, both parlay picks lost because the model assumed starters based on 15-game starts-share percentages. actual boxscores showed all 4 goalies were backups (johansson, cooley, lyon, husso). if we'd known the real starters, both games would have been avoids (1/6), not picks (4-5/6). real money was lost on mathematical assumptions.

**how to apply:**
- **tonight's starter:** always use dailyfaceoff.com/starting-goalies as the primary source. fetch it via WebFetch every run. if unconfirmed, flag it prominently and note the confidence is conditional.
- **historical classification (15-game tables):** starts-share thresholds are fine for the "g" column (s/b) in tables — that's backward-looking fact. ≥60% = starter, 40-59% = tandem, <40% = backup.
- **confidence scoring:** the goalie matchup factor (+2/-1) and elite bonus (+1) must be based on the externally-sourced tonight's starter, not the starts-share projection. if dailyfaceoff is unconfirmed, present both scenarios (with projected starter vs with backup) and flag the risk.
- never say "likely ran a backup" in post-mortems without checking the boxscore first.
