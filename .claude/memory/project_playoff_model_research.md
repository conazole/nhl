---
name: playoff-specific model research backlog
description: future audit ideas for playoff-aware model improvements beyond v4.2 (goalie override + g1 cap)
type: project
originSessionId: 9e719d16-5c8c-4bfd-a5ed-6b5204c07c0f
---
playoffs are functionally a different season — lineup intensity, defensive structure, series-specific matchup dynamics — and the regular-season-trained v4 factors don't price all of it. v4.2 only has 2 playoff overrides (goalie classification, g1 cap). more audits queued for future v4.3+ patches.

**Why:** raised apr 26, 2026 after buf@bos (5/6, h2h 0/0/1 locked-down) lost the r5 tiebreak to tbl@mtl (5/6, h2h 1/2/2 looser) by a single game in r5. user observed model can't see series-specific 1p tightness when picking between equally-confident playoff games.

**How to apply:** when user says "let's revisit playoff stuff" or asks about model improvements, surface this list. do NOT implement these without explicit go-ahead — sample size is ~435 playoff games (vs 1149 reg-season) so each new factor risks overfitting.

### audit candidates (one at a time, in priority order)

1. **h2h-series tiebreak.** when 2+ playoff games tie on confidence, does "this series's prior 1p u2.5 rate" beat "r5%" as the picker? smallest, most testable change. specific to: same series, ≥1 prior game played.

2. **series-state factor.** does "team trailing at home / facing elimination / close-out road" affect 1p u2.5 rate vs base? bucketed by scenario (down 0-1 home, 1-2 home, facing elim, close-out, g7, etc.). likely small samples per bucket.

3. **playoff-specific r5/r15 thresholds.** is the 70%/80% boundary still right in playoffs, or does playoff base rate (73-81% by g1/g2-3/g4+) shift the cutoff?

4. **series tightness as a single combined factor.** rather than 5 separate state checks, one "tight series" indicator: avg 1p total <1.5 across prior series games + close score → +1 confidence?

### constraints

- 435 playoff games total (2019-2026) across all factors → can probably afford 1-2 new factors max before overfitting risk.
- v4.2 base patches (goalie override + g1 cap) were validated on the same 435-game pool — adding more factors compounds the multiple-comparison problem.
- don't add factors that just re-encode information already in r5/r15 (e.g., "team scoring under form" — that's r5).
