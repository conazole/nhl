# playoff 1p u2.5 dynamics — research findings

_scope: why playoff 1p scoring behaves the way it does, and what it means for a regular-season-trained u2.5 model._
_base rates for reference: regular season 1p u2.5 ≈ 73% (1149 games validated in-project). playoff 1p u2.5 = 78.4% pooled 5 sns, 74.7% last 2 sns (n=174, source: `research/playoff_1p_raw.csv`)._

---

## 1. goalie usage in playoffs (HIGH PRIORITY)

**hard data (from nhl api, 2019-20 through 2023-24, n=88 team-series):**

- total playoff starts across all team-series: **958**. starts by each team's #1 goalie: **845 = 88.2%** of all playoff starts.
- restricted to team-series with 5+ games (n=77, meaningful sample):
  - mean #1 share: **0.876**
  - **51.9% of team-series were 100% #1**, 76.6% were ≥80%, 13.0% were <65% (true tandems)
  - see `research/playoff_goalie_usage.csv` (134 rows)

**true tandems that persisted across a full series (recent examples):**
- 2022-23 vgk: adin hill (14) / laurent brossoit (8) — [#1=64%] — won cup
- 2022-23 car: andersen (9) / raanta (6) — [60%]
- 2021-22 stl: binnington (6) / husso (6) — [50%]
- 2023-24 vgk: logan thompson (4) / adin hill (3) — [57%] — short r1 exit
- 2020-21 fla: bobrovsky/driedger/knight rotation — [#1=33%] — short r1 exit

**starter-pulled-mid-game in playoffs:** no public source quantifies this separately from regular season. hockey-graphs notes no sustained pull-time differential playoff vs reg. this is a third-period phenomenon anyway — not a 1p signal (sources: [hockey-graphs](https://hockey-graphs.com/2020/05/18/the-state-of-goalie-pulling-in-the-nhl/)).

**2026 round 1 starter confirmations (dailyfaceoff):** 15 of 16 teams have clear starters; only pit is running a 27/25 skinner-silov split as a true tandem. min (gustavsson/wallstedt) and edm (ingram/jarry) have mild uncertainty but expect to settle on a #1 by g2-3.

**implication for model:** the "goalie matchup type" factor as currently defined (based on full-season starts share from game-type 2) will **misclassify many playoff teams as tandems or backups when they will actually deploy their starter 100%**. e.g., a regular-season tandem like car (andersen/kochetkov ~50/50) will run whoever plays game 1 for essentially the whole series. the backup category should effectively vanish in playoffs — there are no B2Bs, so coaches have no schedule-forced reason to rest the starter.

_sources: nhl api `/v1/club-stats/{team}/{season}/3`, [daily faceoff 2026 r1 preview](https://www.dailyfaceoff.com/news/breaking-down-goalie-matchups-2026-stanley-cup-playoffs-preview-first-round), [yahoo "why goalie depth matters less"](https://sports.yahoo.com/article/why-goalie-depth-matters-less-202626037.html)_

---

## 2. pace / shot volume in playoff 1p

**goals: playoffs average 4.56 non-PP goals/game vs 5.06 in reg season** (yahoo ca/yahoo sports) — a ~10% drop. 2024 playoffs: first full playoff under 6 total goals/game since 2021 (source: [sound of hockey 2024](https://soundofhockey.com/2024/05/07/data-dump-stanley-cup-playoff-series-length-scoring-and-more/)).

**broader dratings claim: scoring down 4.4% avg in playoffs, "more than 7%" in recent years** (source: [dratings scoring trends](https://www.dratings.com/nhl-scoring-trends-regular-season-vs-playoffs/)).

**1p-specific: nhl.com** cites an eastern conference playoff series where 1p held **<20% of all scoring** vs 27% for WC playoffs and 28% reg season — evidence of a magnified 1p suppression in high-stakes playoff series, though that's one series, not league-wide.

**"cagier" 1p mechanism — three drivers cited across sources:**
1. skaters/goalies fresh, teams play tight defensively out of the gate
2. long-change effect kicks in during p2, raising p2 scoring relative to p1/p3 (long-established — [sound of hockey: long-change effect](https://soundofhockey.com/2024/08/01/the-long-change-effect-nhl-scoring-trends-for-the-2023-24-season/))
3. in playoffs, "players could be more tentative, leading to fewer goals" — compounded by higher-stakes games

**no clean public xg-per-shot playoff 1p split found.** naturalstattrick has the data behind toggles but no summary page. moneypuck shots_YYYY.zip could be analyzed but wasn't pulled for this report.

**shots-per-game data gap:** no public summary found comparing playoff vs reg-season SOG **by period**. general playoff rhythm: total SOG ~similar, with possession/forecheck more sustained but fewer high-danger rushes.

_sources: [yahoo ca refs power play](https://ca.sports.yahoo.com/news/nhl-playoffs-refs-in-tough-spot-with-power-play-scoring-highest-in-decades-153831543.html), [nhl.com: playoff stat anomalies](https://www.nhl.com/news/nhl-playoff-statistics-in-eastern-conference/c-280410108), [dratings period breakdown](https://www.dratings.com/a-breakdown-of-nhl-goal-scoring-by-period/)_

---

## 3. officiating / penalty rates

**counter-intuitive but well-documented recent finding: pp conversion is *higher* in playoffs, not lower.** 

- 2024 playoff r1 pp rate: **25.1%** (highest since 1980-81). vs reg season 21.3-21.6% (same year)
- pp goals account for **26.9% of all playoff goals** vs 20.4% in reg season
- **reason: top teams have top pp units; r1 included 7 of the top 15 reg-season pp units**
- however: overall **non-pp goals/game drops** (4.56 vs 5.06) — it's *5v5 scoring* that shrinks, not pp

**total penalties/pp opps per game:** reg-season 24-25 was at a 20-year low (3.48 penalties/team/game, 2.71 pp opps). playoffs add ~0.19 pp opps/game vs reg season in r1 specifically (espn).

**"old-NHL" swallowed-whistle narrative is contradicted by the data.** calls rise slightly in r1, decline into conference finals. bleacher report's "refs call fewer" framing reflects older playoff eras (pre-2005 lockout).

**1p-specific officiating: not found.** no public data breaks PP opps by period playoff-only.

**net effect on 1p u2.5: mixed.**
- more pp → more scoring risk
- but 5v5 scoring (where most 1p goals happen) is demonstrably down
- on net: these roughly cancel, leaving the overall playoff 1p rate slightly above reg-season

_sources: [espn penalties down](https://www.espn.com/nhl/story/_/id/44428407/nhl-2024-25-penalties-decrease-power-plays-players-referees), [yahoo refs in tough spot](https://ca.sports.yahoo.com/news/nhl-playoffs-refs-in-tough-spot-with-power-play-scoring-highest-in-decades-153831543.html)_

---

## 4. series / game-in-series context

**from our raw csv (435 games, 5 sns):**

| game # | n | u2.5 hit | avg 1p goals |
|---|---|---|---|
| 1 | 75 | 72.0% | 1.933 |
| 2 | 75 | 77.3% | 1.667 |
| 3 | 75 | 72.0% | 1.693 |
| 4 | 75 | 81.3% | 1.547 |
| 5 | 67 | 80.6% | 1.627 |
| 6 | 48 | 83.3% | 1.396 |
| 7 | 20 | **100.0%** | 0.750 |

**last 2 sns only (n=174, closer to current scoring environment):**
- games 1-3: **68.9%** u2.5, avg 1.92 goals
- games 4-7: **81.0%** u2.5, avg 1.52 goals
- game 1 specifically: only **63.3%** u2.5 (n=30, sample thin but directionally strong)

**home/away 1p scoring:** home teams score 0.897 1p goals/game, away teams 0.722 — a 24% home edge in the period. partially reflects home team aggression on the first shift, and home coach's line-matching advantage.

**by round (pooled):** r1 79.7%, r2 76.3%, r3 80.0%, r4 72.4% — cup final runs looser (small n=29).

**rest/b2b:** playoff teams don't play B2Bs, which removes the single largest "backup goalie + tired team = shootout" trigger. nbc sports + ats.io: a 2-day rest edge is worth major series-opening swings. playoff-wide, everyone is rested — 1p scoring benefits from this (no fatigued/backup side raising totals).

**"road team down 3-0":** insufficient game-count data to isolate this cleanly (our csv has ~2-3 sweep games per sn). anecdotally, trailing road teams in elimination g4/g5 play tighter defensively — consistent with our late-series under bias.

_sources: [dratings scoring](https://www.dratings.com/nhl-scoring-trends-regular-season-vs-playoffs/), [nbc rest advantage](https://www.nbcsports.com/nhl/news/well-rested-teams-have-big-advantage-in-nhl-playoffs), [statsbylopez game 7s](https://statsbylopez.com/2014/04/30/on-nhl-game-7s/)_

---

## 5. booking / line behavior

**sportsbook standard 1p total = 1.5, NOT 2.5.** u2.5 is an alternate line with ~ -300 to -500 juice in typical games (odd shark, sportsbettingexperts — [standard 1p line](https://www.sportsbettingexperts.com/hockey-betting/understanding-hockey-lines/)).

**public bettors hammer the over.** docsports and odds shark both note 1p overs are more heavily bet, and sportsbooks juice accordingly — negative odds tilt toward the over.

**vsin's 4-year playoff totals finding:** 180 overs / 163 unders (**52.5% over rate**) on full-game playoff totals, 2022-25 — running counter to "playoff hockey is under-heavy" narrative. profit on overs +6.3u, unders -39.5u combined (source: [vsin playoff betting systems](https://vsin.com/nhl/nhl-playoff-betting-systems/)).

**but that's full-game, not 1p.** the full-game over-bias is driven by hot pp units and late-game empty-netters/desperation goals. the 1p remains the most under-friendly window. yahoo 2022 1p analysis: 57 1p goals in 28 early-round games (**2.04/game**), with 15 of 16 early playoff games hitting over 1.5.

**implication for our 2.5 line gate:** 1p totals lines rarely go above 1.5 in practice, so the model's full-game 6.0-line gate isn't directly applicable to 1p pricing. our full-game line as a proxy for scoring environment stays useful — playoff games priced at 5.5-6.0 will still indicate lower-scoring matchups; 6.5+ indicates an offensive shootout expected. the gate logic should hold.

_sources: [docsports strategy](https://www.docsports.com/current/nhl-first-period-betting-advice-strategy.html), [vsin playoff systems](https://vsin.com/nhl/nhl-playoff-betting-systems/), [yahoo 15 of 16](https://sports.yahoo.com/nhl-betting-this-first-period-bet-has-hit-in-15-of-last-16-playoff-games-171931203.html)_

---

## 6. gut-check the 78% base rate

**our 5-season playoff rate (78.4%) is consistent with public narrative.** sound of hockey: "playoffs score less, unders should work." dratings: scoring down 4-7% in playoffs. our 1p-specific 78.4% vs reg 73% is a **~5pp edge**, aligning directionally with 4-7% scoring decline claims.

**but the last-2-sns drift to 74.7% is a real convergence signal.** probable drivers:
- elite pp units concentrated in playoff field (25%+ pp rate vs 21% reg season)
- scoring environment generally rising league-wide (regulation scoring was near all-time highs in 2023-24 reg season)
- no back-to-backs removes the "backup+tired team" u2.5 boost that helps in reg season

**contradictions found:** none direct, but vsin's full-game over-bias contradicts the popular "bet playoff unders" narrative. this suggests the playoff under edge is **period-specific to p1**, not full-game — good news for our thesis.

**unanswered from public data:**
- playoff 1p goals per game historically vs reg season (no league-wide split found)
- goalie-pull frequency by period in playoffs vs reg season
- whether the 1p u2.5 edge is larger or smaller in odd-series vs even-series teams

---

## model implications

| change | supported? | basis |
|---|---|---|
| **remap goalie matchup for playoffs** | YES | 88% of playoff starts go to the team's #1. any reg-season "tandem" classification should be resolved to the confirmed playoff starter and scored as starter. backup designation should be essentially dead — when used, treat as starter-level. |
| **kill backup+X penalties in playoffs** | YES | no B2Bs means no schedule-driven backup usage. if a backup starts a playoff game, it's an injury or benching — a stronger signal than reg-season backup usage, but that's a separate factor, not the B2B-driven one the model was trained on. |
| **add game-in-series bias** | YES, strong | g1-3 u2.5 = 68.9%, g4-7 u2.5 = 81.0% in last 2 sns. clear 12pp gap. add small positive factor for games 4+ (familiarity + fatigue + conservatism). |
| **down-weight r5/r15 historical** | MAYBE | regular-season recent form (r5, r15) may be noisier in playoffs due to radically different competition. no direct data to prove this, but face-validity low — save this for backtest. |
| **keep 6.0/6.5 line gate** | YES | playoff full-game totals still correlate with expected scoring, and vsin data shows the over still hits full-game even in playoffs — i.e., books are pricing playoffs correctly and the model's line-based risk signal remains sound. |
| **ignore public-over-bias narrative** | YES | vsin 2022-25 shows playoff overs are +6.3u profitable. don't add an "unders bias" factor. the 1p under edge is real but narrow (78 vs 73 recent), and converging. |
| **skip game 1 of a series** | MAYBE, CAUTION | g1 u2.5 in last 2 sns = 63.3% (n=30). only 10pp below the base rate but sample is thin. consider treating g1 as "avoid" or penalizing confidence. |
| **don't add xg/pace factor** | NEUTRAL | no public evidence of a playoff-specific 1p pace shift we can exploit without building it from moneypuck raw shot data. defer. |

## caveats / open questions

- 2020-21 (85.7% u2.5) inflates the pooled average — covid-era bubble/short season. pull that season and pooled rate drops to ~76%, closer to recent.
- playoff goalie classification data here uses full-playoff-series starts — in real-time, you'd only know game 1's starter confidently before the series. use daily faceoff confirmations, not starts-share math, exactly as the existing `feedback_goalie_backup_detection.md` prescribes.
- game-in-series signal is only accessible on g2+, not g1. first game of every series is always coldest.
- 10 "tandem" team-series out of 77 isn't zero — still plan for vgk/pit/car-style splits in any given year.
