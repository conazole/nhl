---
name: v4.1 backup+starter split
description: apr 6 2026 — backup+starter scored +1 instead of -1, based on 275-game audit showing 77.4% u2.5 rate
type: project
---

v4.1 splits backup goalie penalty by partner type. backup+starter now scores +1 (same as starter+tandem) instead of -1.

**Why:** 275-game audit (apr 6 2026) found backup+starter hits u2.5 at 77.4% (53 games) — essentially identical to starter+tandem (75.8%, 62 games). the starter anchors the game regardless of the other goalie's starts share. the old "any backup = -1" rule was masking this by averaging backup+starter (77%) with backup+tandem (62%) into a blended 66-69%.

backup save percentage showed NO signal (elite .910+ backups hit 66.7%, average .890-.899 hit 82.4% — no gradient). the partner's classification, not the backup's quality, is the predictor.

**How to apply:** engine scoring in run_analysis.py line ~789. backup+starter → +1, backup+tandem → -1, backup+backup → -1. track as v4.1 in picks_log (model field stays "v4" — this is a refinement, not a new model). watch whether backup+starter picks maintain 75%+ hit rate over next 30 games.
