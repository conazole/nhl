---
name: no shortcuts — real money is at stake
description: never take implementation shortcuts in the betting model. user lost money because goalie classification used a 15-game window instead of full-season data, misclassifying starters as tandems.
type: feedback
---

never take shortcuts on data that feeds the confidence model. every factor must use the right data scope — not whatever's convenient.

**Why:** user lost real money because shesterkin (undisputed #1) was classified as "tandem" (47%) due to a 15-game window. this lowered confidence scores and flipped pick decisions. a 15-game window is appropriate for u2.5 trends (recent form), but goalie role is a season-level attribute that needs full-season data.

**How to apply:** before implementing any model factor, ask: what's the correct data scope for this metric? don't default to reusing whatever data is already available. if the right answer requires more work (extra API calls, wider lookback, separate data source), do the work. cutting corners on inputs means garbage outputs, and garbage outputs cost money.
