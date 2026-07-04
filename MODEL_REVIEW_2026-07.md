model review · july 2026

a full read-through of the v4.3 pipeline (engine, prefetch, resolver, logger, formatter, record math, review, revalidate, the research stack, skill file, docs, and all 457 log entries) plus fresh multi-season drift experiments. focus: make the model adapt to new trends and maintain itself, instead of running on constants frozen at jun 12 2026 · the same treatment the nfl repo got in its v2.1 release.

status: implemented 2026-07-03 as v4.3.1 · everything in parts 5-7 (the drift experiments, the three loops, the live-path replay, the mock harness) is built, tested against real data, and documented. see README's jul 3 changelog entry for the release notes and research/mock_analysis_2026-04-22.md for a graded mock of the current engine on a real slate. what remains is the part no code can rush: a season of live data through the new loops, then the 2027 offseason evidence review (day factor's fate, goalie ladder, g1 cap).

---

tl;dr

the v4.3 design is sound and the research discipline that produced it (point-in-time dataset, train/holdout split, wilson CIs, a factor killed by its own holdout) is the best thing in the repo. the weakness is that v4.3 is a snapshot taken the day the season ended: it has zero live picks, its evidence base is one season that no script can extend, every quoted number is a hardcoded constant duplicated across five files, and the live engine scores october games a way no validation ever tested. the model also never grades what it passes on in a structured way · the postmortem is prose that evaporates.

the fix is not new factors (the data killed those, and the killed list stays killed). it is closing three loops: a data loop (multi-season dataset builder + annual refresh), a parameter loop (one generated model_params.json read by the live scripts), and a judgment loop (structured bust taxonomy + a season review that measures tier calibration and cap decisions against their own results) · plus a live-path replay that proved where the real bugs live before real money finds them.

---

part 1 · what's already strong (don't touch)

- the research discipline. build_dataset.py computes every feature from pre-game information only, factor_lab.py demands direction to hold on both sides of a chronological split, wilson CIs on every bucket, and the process killed its own r15 factor when it inverted on holdout. this is rarer than it should be. keep it as the bar for every future change.
- the killed-factors registry. poisson, elite bonus, b2b, h2h, venue form, day-of-week, environment rollups, r15 · an explicit do-not-re-add list, enforced in docs and memory. the hard rule stands: display context is fine, scoring it is not.
- shared record math. record.py is the single source for season record, top-2 parlay scoring, the deterministic sort key, and log invariants · resolve, format, update, close_line all import it. the jun 12 record correction (18-5, not 16-6) exists because duplicated math drifted; centralizing it ended that class of bug.
- log hygiene as a real audit trail. atomic writes, void-not-delete for postponed games, resolved entries are never touched, sweep-resolve so gap days can never dangle, invariant warnings on every write, migrations live in research/ with verification and abort-on-mismatch.
- fail-closed gates. a game with no sourced line can never be a pick; transient api failures never poison the games cache; combined windows de-dupe shared games. the engine fails toward not betting, which is the correct direction for money.
- every slate game is logged and graded. picks, hms, and avoids all resolve · so unlike most models, the tiers below the pick line already have measurable records (part 3 uses them). the judgment loop here is half-built already; part 6 finishes it.
- goalie prediction quality is measured: predicted-vs-actual starters logged since apr 18, 69/74 correct (93.2%).
- deterministic picks. same data, same picks, shared sort key across display, logging, and scoring. no vibes anywhere in selection.

---

part 2 · hardcoded constants vs regenerated

nothing in the live path is regenerated. every number below is a constant frozen at its last hand-edit, and most exist in more than one file:

- run_analysis.py: r5 buckets (70/80), day-game cutoff (17:00 et), the goalie-pair point map, line gate (5.5/6.0/6.5), g1 cap (3), pick threshold (4), plus validation rates quoted in comments (83.2%, 79.6%, 78.7/76.4/72.6, 63.3%).
- format_output.py: a duplicate goalie-pair point map (GOALIE_PTS, used by the risk line), the g1 cap note (63.3%), the footer formula line.
- review.py: 73.0% base-rate baseline, 75/81% conf-4 thresholds, killed-factors prose, v4.1 numbers.
- research/revalidate.py: the BASELINE dict (83.0/88.1/74.5/70.2/74.9) · hand re-anchored on jun 12; the previous set included an unsourced 92% that sat one bad week from a false drift alert. this file is the poster child for the parameter loop: its whole job is drift detection and its baselines are themselves hand-maintained constants.
- record.py: the model gate ("v4") and the absolute log path.
- research/build_dataset.py: SEASON_START (2025-10-07), the olympic break window, the moneypuck game-id offset (2025000000), the shots_2025.zip filename · all frozen to the season that just ended.
- prefetch.py: team-name maps (see part 4.2), the nhl.com lineup-projections url with a 2025-26 slug baked in, the pinnacle league id.
- CLAUDE.md + README.md: every number above, duplicated in prose and tables.

when a revalidation moves a number, roughly seven places must agree by hand. the jun 12 release already demonstrated the failure mode in miniature: revalidate's baselines had drifted from the docs and had to be manually re-anchored. part 6 replaces all of this with one generated model_params.json, emitted by the backtest, read by the live scripts with fallbacks, stamped with a validated-through date the output footer can display.

---

part 3 · the claimed edge, measured from the model's own log

the log can answer this better than most repos (every slate game resolves), with real caveats. all numbers below are v4-model entries, feb 26 · jun 6 2026, win/loss only, wilson 95% CIs.

what the log supports:

- picks (the money): 41-5 legs · 89.1% [77.0, 95.3] against a 72.9% slate base rate (n=236). parlays 18-5 (78.3%). the edge is real on this sample, and the CI floor sits above the base rate.
- the top of the scale carries it: conf-6 19-2 (90.5%), conf-5 14-0. conf-4 legs 8-3 (72.7% [43.4, 90.3]) · indistinguishable from base rate.
- all games scored 4/6 (including demoted extras): 17-9 = 65.4%. the v4.2-era conf-4 tier added nothing over the season, which is exactly the diagnosis that motivated v4.3's r15 removal. consistent story, honestly told.
- the middle is noise: hm tier 63.8% [54.7, 72.0], avoid tier 77.0% [66.3, 85.1]. the gradient is non-monotonic below the pick line · avoids out-hit hms. with these CIs that is not a crisis, but it means the 2-vs-1 tier boundary communicates precision the data does not have.

what the log cannot support:

- v4.3 has zero live evidence. it shipped jun 12; the season ended jun 12. the 83.0% pick tier, the day factor (n=143), and the demoted-volume story are backtest numbers only. the live record above validates v4.2's top tiers, not the shipped model.
- per-version attribution is impossible for most of the season: model_version was added to update_log on jun 12 and no entry carries it (zero games logged since). factor breakdowns exist on only 74 of 236 resolved v4 entries (apr 18+). the "v4" label spans four scoring regimes (v4.0/4.1/4.2/4.3).
- clv is unmeasurable: 6 entries carry closing lines. the transparent-clv plumbing shipped too late in the season to accumulate anything.
- the graveyard is honest: v2 picks went 10-4, v3 picks 3-1 before being killed for structural reasons, not results · correct process, and a reminder that small-n live records (like conf-5's 14-0) should not be worshipped either.

---

part 4 · silent breakage + staleness, ranked by money impact

4.1 · the october cold start: the live engine scores games no validation ever tested

two compounding problems at every season start, worth more money than anything else in this review because they hit the first bets of 2026-27:

- preseason pollution. api-web's score/{date} returns preseason games (gameType 1) as FINAL (verified live: 2025-09-25 shows 6 type-1 finals). walk_scores and fetch_todays_games never filter gameType. in the first 2-3 weeks of a season, the 15-game windows, r5, goalie-starts inference, league base rate, and h2h all silently ingest preseason games · lineups full of prospects, empty-building intensity, meaningless results.
- unvalidated small samples. the live engine computes combined r5 over whatever exists (a team with 2 games contributes 2), and 2/2 = 100% scores the full +2. every validation row that produced the 83% pick tier required 5 games per team (build_dataset emits comb_r5_pct only when both teams have 5+). the live path and the validated model literally disagree about october. nothing in the code knows this.

fix shape: gameType filter everywhere scores are walked, and a fail-closed early-season gate (r5 window short → cap below pick threshold, same pattern as the line gate). the replay (part 6) tests both.

4.2 · utah mammoth: the rename the pipeline never heard about

the team has been utah mammoth since may 2025, all of last season. prefetch's PINNACLE_TEAM_MAP still says "Utah Hockey Club" and TEAM_ABBREVS has no "utah mammoth"/"mammoth" entry. consequences, live all season: pinnacle lines for uta games silently never matched (uta rode espn-only lines · the source known to round 6.0 to 5.5/6.5, feeding the line gate the less reliable number), and dfo goalie rows for utah could not map to a team (uta goalie fell back to window inference; log shows uta sides confirmed only when supplemented by hand). one team, a full season, zero errors raised. the general lesson: every name map needs an unmatched-name warning, because the nhl renames and relocates teams.

4.3 · the evidence base is one season and no script can extend it

season_dataset.csv is 1393 games of 2025-26. build_dataset.py is frozen to that season four separate ways (start date, olympic break, game-id offset, moneypuck filename). the CLAUDE.md instruction "re-run the research pipeline on new-season data before the first bet of 2026-27" is currently impossible to follow without editing source. meanwhile the apis can serve much more: nhl score/{date} honors arbitrary historical dates (verified: 2024-01-15 returns that day's finals), moneypuck publishes shots_2021 through shots_2025 (all verified 200), and espn's core odds api serves stored per-event totals for historical nhl games across multiple books (verified on a 2024 game). a multi-season dataset · including per-game total lines · is buildable today. part 5 builds it.

4.4 · goalie source 2 dies next season

fetch_nhl_goalies and fetch_injuries scrape a hardcoded url containing "2025-26-season". next season it 404s: the nhl.com goalie cross-check goes dark (fewer two-source confirmations) and the injuries dict silently returns empty. dfo becomes a single point of failure for the most important input the model has.

4.5 · nothing guards against a wrong-season or wrong-date payload

the nfl repo's replay caught espn silently ignoring season= and serving the wrong year. the nhl api passes the equivalent test today (date is a path param and payloads echo gameDate; espn's scoreboard honors dates= · both verified live), but no fetcher asserts it. one cheap guard per fetcher · every consumed game must carry the requested date/season, mismatch is fatal · converts "verified in july 2026" into "enforced forever".

4.6 · drift detection is hand-fed

revalidate.py alerts when live rates drift >5pp from baselines that are themselves hand-typed, and review.py measures the base rate against a hardcoded 73.0. when a future re-validation moves the numbers, both files stale silently until someone remembers them. subsumed by the parameter loop.

4.7 · smaller staleness, still real

- record.py, review.py, revalidate.py gate on model == "v4" · a future v5 must edit them all.
- CLAUDE.md says a daily 1:03 pm ct crontab exists; README says crontab not installed. doc drift on how the thing actually runs.
- review.py's saved report uses markdown headings and bold ansi remnants · violates the repo's own output typography rules.
- moneypuck at season start: shots file for the new season may not exist for the first days; the engine falls back to goals-as-xg silently. informational only (xg is unscored), so low impact, but the fallback deserves one loud line.
- format_output deletes yesterday's analysis file as a side effect of a normal run · fine live, wrong for replays and mocks; needs a flag.

---

part 5 · fresh drift experiments (5 seasons, 6,992 games, run 2026-07-03)

the multi-season dataset behind these numbers: research/build_dataset.py
--season {2021..2025}, one point-in-time csv per season, exactly 1,312
regular-season games each plus playoffs, zero duplicate game ids, and the
2025 rebuild validated against the jun-12 file with zero score mismatches.
lines are the logged pinnacle-consensus line where a live run recorded one,
else espn's stored pregame median across books. reproduce with
research/drift_lab.py and research/backtest_variants.py.

5.1 · the environment is stable

league 1p u2.5 base rate by season: 75.0 / 74.8 / 73.4 / 74.7 / 74.9. first-
period goals per game 1.73-1.78. no regime shift anywhere in five seasons ·
the model's premise (1p unders are common and priceable) holds.

5.2 · a data-contamination catch worth naming: espn live-odds leakage

the first build of the historical line columns produced a 93.8% u2.5 rate on
≤5.5 lines in 2024-25 · impossible, and it traced to espn storing exactly two
"books" per event since 2024-25: the real pregame espn bet line, and an
in-game live-odds snapshot (totals of 4.0-4.5 next to -3000 moneylines). a
median across both leaked the in-game state into a "pregame" column. the
fetcher now excludes any provider whose name contains "live", keeps only
plausible pregame totals (5.0-8.5), and caches the raw per-provider list so
the filter can change without refetching. the lesson generalizes: the nfl
repo's replay caught espn ignoring season=; this repo's caught espn blending
market states. assume nothing about apis.

5.3 · factor edges, pooled and per season (clean data)

- total line: the workhorse, and the only factor with a stable, meaningful
  edge. ≤5.5 = 77.6% (n=2344), 6.0 = 75.8%, ≥6.5 = 71.7% (n=3030) · the
  ≤5.5-vs-≥6.5 gap is +5.9pp in the trailing 2 seasons vs +5.8pp earlier
  (z=+0.01). monotonic in essentially every season. note a market-mix shift:
  espn bet posts almost no 6.0 totals since 2024-25 · the 6.0-is-most-common
  claim in the docs describes the pinnacle line of record, not every book.
- combined r5: pooled ≥80 = 75.3% vs <70 = 73.0% · +2.3pp, and inverted in
  2024-25 (74.9 vs 76.1). trailing-2 gap +1.3pp vs earlier +2.9pp (z=-0.61,
  stable-but-small). threshold re-learning finds nothing better: every
  cutoff from 70 to 90 lands within ~1pp of 75. r5 is a weak sorter, not the
  edge the 2025-only numbers implied.
- day game (the v4.3 headline factor): pooled 76.4% vs 74.4% at night
  (+2.0pp) · but INVERTED in 2023-24 (71.2 vs 73.7) and 2024-25 (69.7 vs
  75.3). 2025-26's 83.2% (n=143) was the good year, not the rule. the
  matinee core (<2pm et) is the sturdiest slice (77.9% pooled, 78.2%
  trailing-2) but no cutoff hour fixes the inversion years. verdict: the
  factor survives pooled, fails 2 of 5 seasons · on the watch list, re-audit
  after 2026-27 (see 5.5 for why it stays scored for now).
- goalie pair: the ladder is nearly flat pooled · s+s 75.4%, middle rungs
  74-75%, backup+backup 72.7% (the only rung meaningfully below base).
  2025-26's s+s = 79.6% was the outlier season. s+s-vs-rest trailing-2 gap
  +2.0pp (z=+0.50, stable-but-small).
- playoff g1 cap: pooled g1 = 69.3% (n=75) vs g2+ = 77.0% (n=357). g1 sits
  below base in 4 of 5 seasons. the cap stays.

5.4 · the shipped v4.3 score, replayed over five seasons

per season pick tier (≥4): 79.0 / 76.9 / 78.6 / 74.8 / 82.5 · pooled 78.2%
[75.8, 80.4] on 1,243 picks against a 74.6% base. tier ≥5: 81.5% [77.6,
84.8] (n=437). simulated parlay nights: 194-123 (61.2%) at 32% of slates.
above that season's base every year except 2024-25 (74.8 ≈ base) · the
model's edge is real, modest, and concentrated in the ≥5 tier. the honest
restatement: the 83.0% pick tier quoted since jun 12 was one good season;
the five-season number is 78.2%, and model_params.json now carries it.

5.5 · variants · why the scoring stays unchanged

head-to-head on all 6,992 games (research/backtest_variants.py): dropping
the day factor (pick ≥3 of /5) lands at 77.9% on 1,142 picks · dropping the
goalie factor (r5+day+line, pick ≥3 of /4) lands at 78.3% on 1,353 · the
r15 variant (v4.2) lands at 76.8% on 1,857. nothing beats the shipped
78.2%/1,243 by more than noise, and the shipped variant has the best parlay
sim (61.2% vs 59-60%). with no variant clearly superior, changing the
scoring would be churn, not improvement · v4.3.1 keeps the v4.3 formula and
re-anchors every quoted number to the pooled evidence. the day and goalie
factors are formally on watch: if 2026-27 repeats their weak years, the
evidence for a leaner v4.4 (r5 + line, or line + matinee-only) will be
sitting in the params history.

5.6 · league changes that move the goalposts in 2026-27

confirmed via the new cba coverage: the 2026-27 season plays 84 games and
opens in late september, with two extra divisional games. this broke two
baked-in assumptions found during this review · season_from_date treated
september as the previous season (a late-september slate would have walked
the wrong season's windows and club-stats), and the standings display
hardcoded 82 games. both fixed and the fixes are part of why the annual
ritual exists: the league moves, the model must notice.

---

part 6 · what was built (the v4.3.1 release)

judgment loop
- every game already logged + graded (picks, hms, avoids) · now every
  fail-closed cap also logs confidence_uncapped + a named caps list, so
  season_review.py grades each cap's blocked would-be picks against what
  they went on to do.
- tag_results.py stamps a fixed bust-reason taxonomy (backup_surprise,
  pp_goals, track_meet, soft_goals, late_1p_flurry, late_news,
  plain_variance, other) onto resolved losses · claude assigns tags while
  writing the daily postmortem, so the postmortem accumulates instead of
  evaporating.
- season_review.py: tier cover vs params baselines with wilson CIs, parlay
  record vs simulation, cap-decision grading, bust taxonomy, goalie
  prediction accuracy + confirmed-vs-unconfirmed splits, live day-factor
  check, clv summary, line-source health.

parameter loop
- research/emit_params.py → model_params.json: policy constants (factor
  cutoffs, point maps, thresholds, caps) + measured baselines with CIs +
  parlay sim + playoff rates + a watch list, stamped generated /
  validated-through. run_analysis.py, format_output.py, review.py,
  revalidate.py, season_review.py read it with fallbacks; the analysis
  footer prints validated-through so staleness is visible in every output.

data loop
- research/build_dataset.py --season {year}: one point-in-time csv per
  season from the nhl api + moneypuck (auto-download) + espn stored pregame
  odds (live-odds filtered, raw responses cached). --validate rebuilds a
  season already on disk and diffs core columns (2025: zero mismatches).
  wrong-date guards on every payload; game-id season guards; preseason
  filtered by gameType.
- annual ritual (documented in README + CLAUDE.md): build the finished
  season, drift_lab, backtest_variants, emit_params, season_review · then
  decide, with evidence, whether anything changes, and bump the version if
  it does.

live-path replay
- replay_season.py rebuilds every historical slate from the same cached
  score payloads the live fetcher consumes and pushes them through the real
  walk_scores → compute_team_metrics → compute_matchups → tiering →
  parlay-selection code, grades the tickets against real finals, and
  reconciles every game's score against the vectorized backtest. its first
  divergence hunt caught a real state-accumulation bug (a skipped date
  silently shifted every later goalie share) · fixed; see part 7.

live fixes shipped with the loops
- preseason games filtered everywhere scores are walked (october windows
  were silently ingesting gameType-1 games).
- early-season fail-closed gate: either team under 5 played games caps the
  score below the pick line (every validation row required 5+; 2/2 = 100%
  was scoring +2).
- utah mammoth added to the dfo + pinnacle name maps (the rename cost a
  season of uta pinnacle lines + goalie mapping) · unmapped team names now
  warn loudly instead of vanishing.
- nhl.com lineup-projections url derived per season (was hardcoded 2025-26).
- gate-straddle warning when espn and pinnacle disagree across a line-factor
  boundary (a half-point flips f_line and can flip the pick).
- september dates count as the new season (2026-27 opens late september);
  standings math uses 84 games from 2026-27.
- schedule-endpoint fallback actually parses gameWeek (it silently yielded
  zero games before).
- typography sanitizer in the formatter (banned characters spelled as
  unicode escapes so a sweep can't neuter it), per-game miss reasons, --out
  mock mode that never touches the live archive.

---

part 7 · live-engine replay results (added 2026-07-03, post-build)

replay_season.py pushed all five seasons through the REAL selection code
(walk_scores → compute_team_metrics → compute_matchups → update_log tiering →
record parlay selection), with actual starters, the line of record else the
espn pregame median, and no injuries/context · the mechanical floor.

```
season    parlay nights        legs           slates played
2021-22   49-27 (64.5%)   121-31 (79.6%)     76/231
2022-23   36-18 (66.7%)    88-20 (81.5%)     54/222
2023-24   13-10 (56.5%)    36-10 (78.3%)     23/231
2024-25   52-45 (53.6%)   143-51 (73.7%)     97/224
2025-26   48-32 (60.0%)   128-32 (80.0%)     80/210
combined  198-132 (60.0%) 516-144 (78.2%)
```

the live code path lands exactly on the vectorized backtest's pick tier
(78.2% legs vs 78.2% backtest) across 330 parlay nights it never saw · the
engine is validated, not just the rules. the same honest spread shows up
here as in part 5: 2024-25 was the weak year (53.6% parlay nights, legs
below base) and the recent live season ran hot. plan bankroll for the
combined line, not the best row.

what the divergence hunt caught (the whole point of replaying):
- a real state bug: the replay's first pass accumulated goalie starts only
  from dates it could score, so one skipped date silently shifted every
  later starts-share and flipped boundary classifications (tandem/starter
  at 57-60%). fixed · goalie state now advances from the dataset rows
  unconditionally. 40 divergences on 2021-22 alone dropped to 0.
- after the fix, 3 divergences remain across 6,992 games and all three are
  the same documented design difference: games with no line anywhere get
  the operational fail-closed cap in the live path (can never be a pick)
  while the vectorized backtest scores them f_line = 0. the live path is
  the stricter one, on purpose. zero unexplained disagreements.
- the g1-cap and short-window caps fired in replay exactly where the csv
  said they should · cap telemetry (confidence_uncapped + named caps) now
  flows to the log so the live season can grade them.

---

part 8 · what not to do

- do not add scored factors that failed significance. r15 stays unscored, poisson stays display-dead, and every candidate signal follows the pattern: log as display context first, promote only if it survives on the model's own picks later.
- do not auto-tune. at ~1300 games a season the loops close annually with human review, versioned per the existing convention. a drift flag is a research prompt, not a switch.
- do not trade the honesty discipline for adaptivity. every regenerated number keeps its CI and its validated-through stamp, and the word lock never appears in an output.
- do not soften the fail-closed direction. new gates (early-season sample, wrong-season payloads) fail toward not betting, like the line gate does.
