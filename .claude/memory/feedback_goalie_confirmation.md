---
name: goalie confirmation is mandatory, never lazy
description: must aggressively confirm goalies from multiple sources — never do a single passive fetch and accept "unconfirmed"
type: feedback
---

goalie confirmation must use ALL available sources (dailyfaceoff, nhl.com projections, web search) every single run. never do one lazy fetch and accept "unconfirmed" when the info is readily available.

**why:** on mar 25 2026, ran the analysis with all goalies as "unconfirmed" despite games being hours away. dailyfaceoff had "likely" status, nhl.com had the starters listed. a second fetch confirmed all four goalies, which changed nyr@tor from 3/5 to 4/5 (pick). the user had to catch the error. real money was at stake.

**how to apply:** always run the full 3-source goalie confirmation protocol in step 6 of the skill. never pass `"confirmed": false` when multiple sources agree on the same goalie. "likely" from dfo morning skate + nhl.com listing the same name = confirmed. never speculate with "if X starts" language — either confirmed or not.
