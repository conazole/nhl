---
name: v4 model — line factor added
description: v4 adds pre-game total line as 4th scoring factor (-1/0/+1), scale now /6, pick threshold ≥5/6. validated on 1149 games.
type: project
---

v4 model launched mar 27, 2026. adds pre-game total line as a scoring factor to the existing v3 core.

**why:** 1,149-game full-season analysis showed 5.5-line games hit 1p u2.5 at 78.7% vs 72.6% for 6.5-line games (+6.1pp). our picks on 6.5 lines only hit 58.3% (11/14 on 5.5, 7/12 on 6.5). the line captures forward-looking information (tonight's matchup, lineups, sharp money) that backward-looking r5/r15 miss. v4 backtest: 64.8% parlays (+6.3pp over v3), 80.5% legs (+3.4pp).

**how to apply:**
- 4 factors: r5 (0-2), r15 (0-1), goalie (-1 to +2), line (-1 to +1). scale /6.
- line scoring: ≤5.5 = +1, ≤6.0 = 0, ≥6.5 = -1.
- pick threshold: ≥5/6. HM: 2-4/6. avoid: <2/6.
- 6.5-line games effectively can't reach ≥5/6 (v3 max is 5, minus 1 = 4). acts as a hard gate.
- line data must be accurate — fetch from multiple sources, not just ESPN (which rounds to 5.5/6.5 and misses 6.0).
- engine accepts `--lines '{"AWAY@HOME": 6.5}'` argument.
- v4 entries tagged `"model": "v4"` in picks_log.
