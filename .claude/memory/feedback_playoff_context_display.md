---
name: playoff context + cautions must display per game (not scored)
description: every game block and picks email must show playoff status and a caution line flagging motivation/lineup risk. informational only — never added to v4 scoring.
type: feedback
originSessionId: 8ee0823d-b866-4db5-9309-4fecfc9fa1f4
---
every game in the analysis must show playoff status for both teams AND a caution line interpreting the status pair. picks email must flag the caution for each parlay leg. the v4.1 confidence formula stays untouched — playoff context is display-only.

**Why:** user gave this instruction once before and it was lost — only the data fetch + raw display was implemented (apr 9, 2026), but the caution/interpretation layer was missed. on apr 11, 2026 it nearly cost a pick: nyr@dal scored 6/6 on pure model data but had real oettinger rest risk from dal being clinched + nyr being eliminated. without a caution line, the user couldn't see the risk at a glance in the picks email. real money was at stake.

**How to apply:**
- format_output.py has a `playoff_caution()` helper that returns one of:
  - "✓ both fighting — max 1p defensive intensity, favors u2.5" (best case)
  - "⚠ meaningless game (clinched+eliminated/etc) — starter rest risk, high variance"
  - "⚠ {team} clinched — possible starter rest, less urgency"
  - "⚠ {team} eliminated — may be loose/unmotivated, variance risk"
- the caution line appears directly under `playoff:` in every game's analysis block
- when writing the picks email manually, include the caution per parlay leg if it's a ⚠ case (not just silent ✓ fighting games)
- NEVER fold this into the confidence score. the model is v4.1-validated; adding playoff scoring requires a full backtest and version bump, and user has explicitly declined that path for now
- claude.md line 48 has the rule: "playoff context + caution: every game block must show ... informational only, NOT in scoring"
