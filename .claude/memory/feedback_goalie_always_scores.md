---
name: goalie always scores
description: goalie factor must always score using best-available info — never zero out for unconfirmed, confirmed flag is informational only
type: feedback
---

goalie factor always scores using best-available goalie info from DFO/NHL.com. the `confirmed` flag is informational, not a scoring gate.

**Why:** v4's original design zeroed out the goalie factor when goalies were unconfirmed. this made picks mathematically impossible without confirmation (max without goalie = r5:2 + r15:1 + line:1 = 4/6, below the 5/6 threshold). on saturdays with 14/15 unconfirmed goalies, 0 picks from a 15-game slate. user correctly identified this as leaving money on the table — early games all went under while we had "no play."

**How to apply:** always pass goalie names to the engine and let the matchup type score. DFO names an expected goalie for virtually every game — use that. only zero the factor if genuinely no goalie info is available (no source names anyone). threshold also lowered from ≥5/6 to ≥4/6 as part of this fix.
