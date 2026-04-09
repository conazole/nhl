---
name: odds sources for total line fetching
description: multi-source approach for accurate pre-game total lines (5.5/6.0/6.5). ESPN API + SBR for v4 line factor.
type: reference
---

v4 requires accurate total lines. ESPN alone only shows DraftKings lines (5.5 or 6.5 — never 6.0). must cross-reference with a second source.

**source 1: ESPN scoreboard API (primary)**
- URL: `https://site.api.espn.com/apis/site/v2/sports/hockey/nhl/scoreboard?dates=YYYYMMDD`
- pure JSON, no HTML parsing. path: `events[N].competitions[0].odds[0].overUnder`
- sportsbook: DraftKings only. always half-points (5.5/6.5), never 6.0.
- most reliable — always available, clean data.

**source 2: SportsBookReview (secondary, for 6.0 detection)**
- URL: `https://www.sportsbookreview.com/betting-odds/nhl-hockey/totals/` (append `?date=YYYYMMDD` for specific dates)
- data embedded in `<script id="__NEXT_DATA__">` JSON in HTML.
- path: `props.pageProps.oddsTables[0].oddsTableModel.gameRows[N].oddsViews[1..4].currentLine.total`
- shows lines from multiple books: Kalshi, Thrillzz, ProphetX, NoVig. ProphetX/Thrillzz often show 6.0 when DraftKings shows 6.5.
- opening lines also available: `gameRows[N].oddsViews[N].openingLine.total`

**consensus logic:**
1. fetch ESPN API → get DraftKings line per game
2. fetch SBR → get lines from all available books per game
3. collect all line values for each game (ESPN + SBR books)
4. use the **median** as the consensus line
5. if ESPN says 6.5 but SBR median is 6.0 → use 6.0 (game stays in v4 pool)
6. if all sources agree on 6.5 → use 6.5 (game gets -1 penalty)

**fallback:** if SBR fails, use ESPN alone. if ESPN fails, WebSearch for "nhl odds tonight over under" as last resort.
