nhl 1p u2.5 betting analysis

real money is at stake · accuracy over speed. never estimate or guess scores. all output must be in lowercase. no bet is ever a sure thing · the word lock never appears in any output.

---

confidence formula · v4.3.1 (4 factors, /6 scale, playoff-aware)

v4 core validated mar 2026. v4.1 split the backup penalty by partner type (apr 6 2026). v4.2 added playoff overrides (apr 18 2026). v4.3 (jun 12 2026) replaced r15 with the day-game factor after a point-in-time revalidation. v4.3.1 (jul 3 2026) is the adaptivity release: scoring unchanged, every quoted number re-anchored to a 5-season 6,992-game point-in-time backtest and regenerated into model_params.json (see MODEL_REVIEW_2026-07.md for the full evidence).

```
factor              criteria                                      points
combined r5 u2.5%   <70: 0 · 70-79: +1 · >=80: +2                 0..+2
day game            local start before 5:00pm et: +1, else 0      0..+1
goalie matchup      s+s +2 · s+t or b+s +1 · t+t 0                -1..+2
                    b+t -1 · b+b -1
total line          <=5.5: +1 · <=6.0: 0 · >=6.5: -1              -1..+1
```

- pick threshold: >=4/6. honorable mention: 2-3/6. avoid: <2/6.
- every cutoff, point value, threshold, and quoted rate lives in model_params.json (machine-generated · see parameter loop below). the engine reads it with fallbacks; docs defer to it. never hand-edit it · regenerate with research/emit_params.py.
- honest baselines (5 seasons, pooled, wilson CIs in params): pick tier 78.2% [75.8, 80.4] vs 74.6% base · tier >=5: 81.5% · simulated parlay nights 61.2% at ~32% of slates. the 83.0% quoted jun 12 was one season's number; the live 2025-26 record ran hotter (41-5 legs) partly on selection and a friendly year. expect the pooled numbers, be pleased by better.
- combined r5/r15 are computed over the UNION of both teams' windows · games the two teams played against each other count once, not twice.
- goalie classification (regular season): full-season starts share from /v1/club-stats/{team}/{season}/2 · >=60% starter, 40-59% tandem, <40% backup. goalie always scores · confirmed flag is informational only, not a scoring gate.
- r15 is still computed, logged, displayed, and used in the deterministic tiebreak · it is NOT scored (v4.3: +1.6pp full season, inverted on holdout, its near-free +1 promoted base-rate games into the pick tier).
- day-game factor is ON WATCH (jul 2026): pooled +2.0pp over 5 seasons but inverted in 2023-24 and 2024-25; 2025-26's 83.2% was the good year, not the rule. it stays scored because no variant without it beats the shipped composite (research/backtest_variants.py) · re-audit after 2026-27 before trusting it further.
- goalie ladder is also weak pooled (s+s 75.8% vs b+b 72.7%, middle rungs flat) · same watch treatment.

fail-closed caps (each pins confidence below the pick line, is named in the log's caps field, and is graded by season_review.py):

- line gate: a game with NO sourced line is capped at 3/6 and flagged line_missing. wrong line = wrong gate decision; no line = no pick.
- early-season gate (new, jul 2026): either team with fewer than 5 played games caps at 3/6 (short_window). every validation row required both teams at 5+ · r5 on a 2-game sample (2/2 = 100% = +2) is outside the validated regime. expect no picks in the first ~2 weeks of a season; that is the design. the engine also filters PRESEASON games (gameType 1) out of windows and slates · they used to pollute october r5/goalie stats.
- playoff game-1 cap (v4.2): gameType 3 + game 1 of a series caps at 3/6. pooled 5-season audit: g1 69.3% (n=75) vs g2+ 77.0% · g1 sits below base in 4 of 5 seasons.
- playoff goalie override (v4.2): in the playoffs any dfo-named goalie classifies as starter (88.2% of playoff starts go to the team's number 1). both v4.2 patches ship together · the override without the cap pushes g1s to false picks.

killed factors (NOT in scoring, do not re-add): r15 (v4.3), poisson, elite bonus, b2b, context, system profile, penalty rate, h2h, venue-split form, day-of-week, rolling 1p goal/sog/xg environments, standings-status playoff context (informational display only).

all log entries carry "model": "v4" (season-record continuity) plus "model_version" (v4.3.1), the factor breakdown, confidence_uncapped, and the caps list · so every cap decision is later gradable.

---

parlay rules

- always 2-leg parlay. top 2 picks >=4/6 by the shared deterministic sort key: confidence desc, r5% desc, r15% desc, game string asc (record.pick_sort_key · used identically by update_log demotion, format_output display, and season-record scoring).
- additional qualifying games become honorable mentions, NOT additional legs (update_log demotes 3rd+ qualifiers automatically).
- if only 1 game qualifies: "no parlay tonight", log as hm. if 0 qualify: "no play tonight".
- picks have no tier field. hms have "tier": "honorable_mention". avoids have "tier": "avoid".
- picks must be deterministic · same data = same picks between runs.
- season parlay record is scored on the top-2 legs per date (what was actually bet) · record.compute_season_record. postponed games resolve as "void" and are excluded from all counts.
- log invariants (checked automatically on every update_log/resolve run): <=2 untiered picks per date, no unresolved entries older than yesterday, no duplicate (date, game), every pick has a line. investigate any warning immediately.

---

output rules

- all output must be in lowercase · every word, header, label, sentence. no exceptions.
- never show poisson in any output · noise.
- typography (all files and all outputs): no bold, no italics, no markdown headings · plain title line, plain section labels, --- rules in docs. no em or en dashes · a middot separates phrases. format_output.py enforces this with a sanitizer whose banned characters are spelled as unicode escapes, so a repo-wide character sweep cannot neuter it. never weaken the sanitizer.
- allowed ornaments: one ━ masthead rule, > quote rails, plain ✓/✗ data marks, ← in streak strips.
- ALL tables are fenced monospace code blocks with space-aligned fixed-width columns (python f-string padding). never markdown table syntax · it renders bold headers.
- analysis file order: masthead (title line, ━ rule, slate context line) → health block (rendered automatically when the maintenance gate ran for this date · drift alerts + ritual status) → tonight at a glance → parlay / no-parlay / no-play → honorable mentions → avoid → yesterday + post-mortem → season · v4 → game details (collapsible <details> per game, sorted by confidence) → footer (model formula line + validated-through stamp from model_params.json).
- every game gets a full block: factor strip + key numbers, per-team goalie line + 15-game table, context, goalies. every game that misses the ticket gets a specific one-line reason (which cap fired, or which factors fell short) · rendered in the hm table ("why it misses") and in the game block ("misses the ticket: ...").
- at-a-glance columns: game, conf, line, pair, start, notes. goalie pairs abbreviated in ALL display: s+s, s+t, b+s, t+t, b+t, b+b (log keeps full words).
- parlay legs carry pre-bet decision info, one quote block per leg, in order: time · line · pair · tags / goalie confirmation line / factor strip / season record for that confidence tier / risk line (computed from factor math: what late line move or backup swap exits pick range) / note (series state or motivation caution).
- 15-game table columns: #, date, opp, h/a, score, total, u2.5, w/l, line, ft, g. score = 1p score (gf-ga), NOT full-game. u2.5 column plain ✓/✗. opp lowercase.
- each team block: goalie line (uta · vejmelka (starter) · last-5 1p ga 1,0,2,1,0 · season sv% .912), then the table code block with the u2.5 streak strip (✓✓✗✓✓ grouped in 5s, newest first) at the top.
- w/l is informational (no analytical significance). line = pre-game total from bookmakers. ft = full-game final total. g = s (starter) or b (backup).
- season record: only show v4 (latest model line), not combined or legacy.
- sort games by confidence, highest first.
- terminal: show FULL detailed analysis · same string as the saved file.
- save full analysis to analysis_{YYYY-MM-DD}.md. delete previous day's file. mock/replay runs use format_output --out {path} · never touches the live archive, never logged.
- playoff context + caution: every game block shows series state (playoffs) or playoff-race status + caution line (regular season · both fighting = favorable, clinched/eliminated mix = rest/variance risk). informational only, NOT in scoring. parlay legs carry their caution as the note line. warnings beyond that are game-specific news only, never standing rules.

---

email rules

emails are DISABLED (apr 22 2026). skip the email step entirely · no picks email, no analysis email, no osascript, no quitting Mail.app. deliverables: terminal output, saved analysis_{date}.md, and the html mirror republished to the claude.ai artifact (step 5).

---

html mirror · build_html.py (user feature 2026-07-20, ported from the mlb repo)

- a VIEW, never a second model path. consumes the SAME artifacts as format_output (/tmp/engine_clean.json + extras + picks_log + model_params + maintenance_state) and renders real components: masthead plate (games / parlays / legs cells + last-10 goal-lamp strip), ticket slip with deep-linking legs, at-a-glance table, hm/avoid boards, exclusive game accordion (details name=) with pick panels + real 15-game tables + colored streak marks, yesterday card, season card + night-by-night parlay ledger. every number comes from the artifacts · if something looks wrong, fix the generator, never the html.
- u2.5 form-rank chips (user feature 2026-07-20): every accordion title carries each team's rank ("buf #5 @ wsh #30"). computed by the ENGINE (run_analysis.compute_team_rankings → "team_rankings" + "rank_window" in the output json · backward walk over the shared scores cache, gameType 2+3, preseason excluded): ROLLING LAST 15 GAMES per team (user: teams change · current form beats a season-long running rank; 15 matches the report's own window), u2.5 rate desc, tie broken by least 1p goals allowed per game, then abbrev · early-season teams rank on the games they have. display context only · NEVER scored. the html renders whatever the engine emitted and degrades to plain titles on old json. each chip reveals its record ("u2.5 12/15 · ga 0.73/gp") on hover (desktop) or tap (mobile · tap pinned, second tap or outside tap hides, capture-phase so the accordion never toggles).
- the "day" tag never renders on the html surface (the start time already says it · user 2026-07-20); the scored day factor chip inside the card stays. playoff/no-line/short-window tags remain.
- line drift arrow (user feature 2026-07-20): when the log entry carries closing_line ≠ total_line (clv capture), the slip leg's line grows ↗ (market against · line up = more goals priced) or ↘ (toward us) · tap shows "open 6.0 → 6.5 · market against" and warns when the move crosses a line-factor boundary (thresholds read from model_params · the gate-straddle trap on the ticket). no clv fields = no arrow, clean degrade.
- the slate / hm / avoid tables render as folds, COLLAPSED by default, count on the summary ("slate · 15", "hm · 6", "avoid · 7") · the user opens them when they choose (2026-07-20: "not on my face"). the nav's slate link opens the fold via the generic hash handler.
- column-implied words never repeat in table cells (user 2026-07-20): "night start" → "night", "line 6.5" → "6.5" in why/reason columns · the header and context already say start/line.
- the word "line" NEVER precedes a total anywhere on the html (user 2026-07-20: self-explanatory) · slip legs read "12:30p · 6.0 · s+s", accordion subs "6.0 · s+s". prose sentences (fragility/risk lines) may still say "line". the slate table has no notes column · bet/avoid live in their own folds, tags stay on the accordion rows.
- bet window (2026-07-20): the slip carries a lamp line · green "all goalies confirmed" / amber "n unconfirmed · check dfo" (from the engine's confirmed flags) + "first puck {time}" with a live js countdown (epoch ms in data-start · NEVER the iso string, the year-strip shorthand mangles it). the ⤢ focus button strips the page to just the slip (tap again to exit).
- rank chips carry week movement in the tap detail ("↑4 wk" · engine emits delta7, the rank vs the same ranking 7 days earlier from the cached walk). yesterday's losses wear their bust-taxonomy chip (bust_reason from tag_results · bust_note rides in the tap tip).
- per-team 15-game tables fold closed inside game cards (user: both teams in one view ran too long) · the goalie row + tappable streak strip stay visible as the summary; tapping a streak mark opens the fold and flashes the matching table row.
- iphone-first interactions: the user is PHONE-ONLY · hover does not exist there. every disclosure must work by tap (the shared data-tip tooltip: hover previews on desktop, tap pins; capture-phase so taps never toggle the accordion or follow the leg link) and every tappable chip gets a grown hit area (padding + negative margin). never ship a hover-only affordance.
- freshness gate: refuses an engine json whose internal target_date differs from the run date (stale artifact). free text (postmortem) renders through a forgiving md fallback so content is never silently lost.
- ticket lock: on live runs the displayed tiers come from picks_log for the date (the logged bet), so rebuilding/republishing can never disagree with logged bets · engine-side tiering (same shared sort key) covers mocks/replays. --out {path} = mock mode: no live archive writes, no log lock.
- record integrity: masthead strip, season record, and ledger all grade through record.parlay_outcome_for_date · a lost leg plus a void/pending leg is a LOSS on every surface (top-2 selected BEFORE result filtering; win+void nights are void and excluded). covered by tests/.
- artifact-host quirks handled in-page: no doctype/html/head/body skeleton, viewport meta injected into the real head at runtime, ALL in-page anchors (nav, slip legs, slate rows, back-to-top) navigate programmatically because the wrapper swallows hash navigation; a details target opens before scrolling.
- design: "the rink" · cold ice grounds with a blue bias (day-ice light / night-rink dark, token-driven + data-theme override), steel-ice accent, center-line red only as the slip's leg divider, goal-lamp history dots, 6-segment confidence meters (ghost segments = capped-away points). confidence display (user 2026-07-20, two rounds): the TICKET SLIP keeps the 6-segment meter as-is; every other surface (accordion rows, slate/hm/avoid tables, yesterday) shows a bare number ("4", not "4/6" · out-of-six is known, the meter everywhere was too noisy). never render "n/6" text anywhere and keep the slip title just "u2.5". NO bold anywhere · regular weight everywhere, hierarchy from size/letterspacing/color. all text roles >= 4.5:1 both themes; status colors always carry a symbol or word. display shorthand page-wide: s+s pairs, "7:00p" times (no " et"), no year prefixes. single-line rows never wrap · containers scroll sideways; sticky-left date column + section titles on sideways scroll. no legends, no glossary, no duplicated info between sections.
- stable identity: <title>nhl 1p board</title> + 🏒 favicon, one artifact url pinned in step 5 · never mint a new one. run tests with python3 -m unittest discover -s tests after touching build_html.py or record.py.

---

postmortem rules

- every run includes "what we got right / what we got wrong" after yesterday's results.
- explain WHY picks hit or missed · what did the model catch? what did it miss?
- CRITICAL: don't frame hms or avoids going under as "misses" · base rate is ~74.6%. only flag genuine analytical errors: a pick that lost with warning signs we ignored, or a pattern the model failed to account for.
- structured bust tags (jul 2026): for every resolved LOSS, write a tags json and run python3 tag_results.py --date {yesterday} --tags /tmp/bust_tags.json. taxonomy (fixed): backup_surprise · pp_goals · track_meet · soft_goals · late_1p_flurry · late_news · plain_variance · other. tag picks, hms, AND avoids · a tagged avoid bust is evidence a cap earned its keep. season_review.py aggregates them.

---

line sourcing

- fetch from ESPN + Pinnacle via prefetch.py. take consensus · trust pinnacle when they disagree (espn rounds 6.0 to 5.5/6.5).
- gate-straddle warning: when espn and pinnacle sit on opposite sides of a line-factor boundary (5.5/6.0/6.5), prefetch flags GATE STRADDLE · a half-point flips f_line and can flip the pick. verify before betting.
- display the total line in each game's analysis with its factor contribution (+1/0/-1).
- line data passed to the engine via --lines '{"AWAY@HOME": 6.5}'.
- validation (5 seasons, pooled, in model_params.json): <=5.5 = 77.6% · 6.0 = 75.8% · >=6.5 = 71.7%.

---

goalie rules

- goalie always scores · confirmed flag is informational only, never zero out for unconfirmed.
- tonight's starter sourced from external sources (dailyfaceoff), not starts-share math.
- fetch ALL sources · never accept "unconfirmed" when info is available.
- dfo prediction accuracy is tracked (goalie_prediction_hit) · 93.2% on 2025-26, and the 5 missed predictions went 1-4. confirmation discipline matters.
- prefetch warns loudly on unmapped team names (the utah mammoth rename silently cost a season of uta goalie/line mappings) · fix the map immediately when that warning fires.

---

workflow rules

- always commit and push at end of each run. no confirmation needed. commit as raz, no co-authored-by trailer.
- multiple runs per day allowed. full fresh execution each time · no caching of decisions, no skipping.
- re-runs: remove existing TARGET_DATE entries from picks_log before appending. never touch yesterday's resolved results.
- run in early afternoon (1-3pm et) for goalie confirmations. manual runs anytime.
- never rewrite pipeline scripts from scratch · edit existing ones.
- flag script errors immediately · never silently work around them, stop and discuss.
- use the prefetch pipeline (prefetch.py + resolve_results.py + format_output.py + update_log.py).
- review.py: weekly pattern analysis · manual, not part of the daily pipeline. season_review.py: judgment-loop calibration · run weekly-ish and at season end.
- no shortcuts · every model factor must use the correct data scope, not whatever's convenient.
- never hand-edit model_params.json (regenerate via research/emit_params.py), maintenance_state.json (written by maintenance.py), or picks_log.jsonl (pipeline scripts only; one-off migrations live in research/ with verification + audit trail · see research/migrate_2026_06_12_parlay_integrity.py for the pattern).

---

date selection

parse $ARGUMENTS to determine TARGET_DATE (YYYY-MM-DD):
- empty → today
- "tomorrow" → today + 1
- date string (e.g. "mar 2", "2026-03-05") → parse it (assume current year)

"yesterday" for results = TARGET_DATE - 1. future dates: flag goalie/injury uncertainty.

---

execution pipeline (5 steps)

CRITICAL: use pipeline scripts. never manual WebFetch for goalies/lines.

step 1 · resolve yesterday + prefetch today + maintenance gate (PARALLEL)

```
cd /Users/raz/claude/nhl && python3 resolve_results.py {TARGET_DATE}
cd /Users/raz/claude/nhl && python3 prefetch.py {TARGET_DATE}
cd /Users/raz/claude/nhl && python3 maintenance.py {TARGET_DATE}
```

resolve_results.py: resolves ALL unresolved dates < TARGET_DATE (sweep · gap days can never dangle), voids postponed games, updates picks_log.jsonl, computes the v4 record (top-2 parlay scoring), and emits invariant_warnings · investigate any warning immediately.
prefetch.py: fetches goalies (dfo + nhl.com) and lines (espn + pinnacle) in parallel, flags discrepancies + gate straddles + unmapped team names. outputs goalies_engine + lines dicts.
maintenance.py: the self-fencing gate · auto-runs the weekly health trio when 7+ days have passed since the last sweep, and the full annual ritual on the first run of a new season (state in maintenance_state.json · machine-written, never hand-edit). format_output renders its summary automatically as a health block under the masthead whenever the gate ran for the target date · no agent copying required. still read the json: drift alerts deserve postmortem commentary, and an incomplete annual ritual means do not bet until it passes. forgetting the reviews is no longer possible · they ride the runs.

step 2 · review + postmortem + bust tags

1. write the postmortem from resolve results (see postmortem rules).
2. tag yesterday's losses: build /tmp/bust_tags.json, run python3 tag_results.py --date {yesterday} --tags /tmp/bust_tags.json.
3. check lines_needing_verification · ONE websearch if a discrepancy or gate straddle matters for a pick.
4. check goalie conflicts (e.g. b2b) · ONE websearch max.
5. build extras json: {"postmortem": "...", "injuries": {}, "context": {}}

step 3 · run engine

```
cd /Users/raz/claude/nhl && python3 run_analysis.py {TARGET_DATE} \
  --goalies '{GOALIES_ENGINE_JSON}' \
  --lines '{LINES_JSON}' > /tmp/engine_output.json 2>&1
```

extract clean json (skip log lines): tail -n +{first_json_line} > /tmp/engine_clean.json

step 3b · ice critic: DISABLED (may 16 2026). skip entirely · do not spawn ice, do not include ice in extras, do not render an ice section.

step 4 · format output

```
cd /Users/raz/claude/nhl && python3 format_output.py {TARGET_DATE} /tmp/engine_clean.json \
  --extras '{EXTRAS_JSON}'
```

extras json: {"postmortem": "...", "injuries": {}, "context": {}}. prints the full analysis to terminal + saves analysis_{TARGET_DATE}.md. for mocks/replays add --out {path} · no live-archive writes, and never run update_log on a mock.

step 5 · log + html mirror + commit

```
cd /Users/raz/claude/nhl && python3 update_log.py {TARGET_DATE} /tmp/engine_clean.json
cd /Users/raz/claude/nhl && python3 build_html.py {TARGET_DATE} /tmp/engine_clean.json --extras '{EXTRAS_JSON}'
```

build_html runs AFTER update_log so its ticket lock reads the freshly logged bet (see html mirror section). then publish via the Artifact tool: file_path = /Users/raz/claude/nhl/analysis_{TARGET_DATE}.html, favicon "🏒", and url = https://claude.ai/code/artifact/ff4d26da-4f8f-4b07-ac88-1a8ab604304e · ALWAYS pass this url so the user's saved link keeps working (omitting it from a new conversation mints a NEW url).

git add + git commit + git push · always, no confirmation, author raz, no co-authored-by trailer.

clv is transparent. run /nhl as many times as you want in a day · the pipeline records the first observed line as total_line (opening) and automatically writes closing_line + line_delta any time a later run sees a different line. close_line.py exists as a standalone "just refresh lines" option. clv interpretation (informational, shown in review.py): for u2.5 bets, line going UP = market pricing more goals = our bet got harder; review.py flips the sign so positive clv = market moved toward us.

---

weekly · in-season health (auto-fenced)

maintenance.py runs this trio automatically inside the first /nhl run that lands 7+ days after the previous sweep · manual runs anytime:

```
cd /Users/raz/claude/nhl && python3 review.py --last 14
cd /Users/raz/claude/nhl && python3 research/revalidate.py
cd /Users/raz/claude/nhl && python3 season_review.py --since {season_start}
```

review.py: per-factor hit rates, clv trend, base-rate drift vs params, weekly trend. revalidate.py: recent-100 vs params baselines, alerts on >5pp drift. season_review.py: tier calibration vs params, cap grading, bust taxonomy, goalie layer. force with python3 maintenance.py {date} --force-weekly.

---

annual ritual · run before the first bet of each season (auto-fenced)

maintenance.py fires the full ritual automatically on the first /nhl run of a new season (september boundary), saves the research output to research/annual_ritual_{season}.txt, and refuses to stamp the state if any step fails · an incomplete ritual means do not bet until it passes. manual equivalent:

```
cd /Users/raz/claude/nhl && python3 research/build_dataset.py --season {just_finished}
cd /Users/raz/claude/nhl && python3 research/build_dataset.py --season {prior_season} --validate
cd /Users/raz/claude/nhl && python3 research/drift_lab.py
cd /Users/raz/claude/nhl && python3 research/backtest_variants.py
cd /Users/raz/claude/nhl && python3 research/emit_params.py
cd /Users/raz/claude/nhl && python3 season_review.py --since {season_start}
```

read drift_lab section 3 (z-flags) and the watch list in model_params.json. a drift flag is a research prompt, not a switch · rule changes need pooled AND per-season evidence, and any behavior change bumps the model version and updates README + CLAUDE.md + the skill in the same commit. specifically re-check for 2026-27: does the day factor recover (inverted 2023-24 and 2024-25)? does the goalie ladder separate? does the 84-game late-september schedule shift day-game share or season boundaries? does conf-4 stay above base?

---

ice · critic agent spec (DISABLED may 16 2026 · kept for reference)

ice is currently disabled. do not spawn the ice agent in any /nhl run. the full spec lives at ~/.claude/agents/ice.md · a research-driven critic (goalie confirmation, last-24hr lineup/injury, referee crews, sharp line movement, 1p-specific trends, playoff series context) returning a strict per-leg verdict with cited sources. action policy when re-enabled: informational only · a warning light, not a kill switch; v4 picks stand. spawn via the Agent tool with subagent_type general-purpose; the full prompt template is preserved in git history (CLAUDE.md as of jun 12 2026).

---

change documentation

notable changes (model updates, architecture changes, new rules, killed factors, pipeline changes) must be documented in README.md with a date and brief description. README's plain-english game-day walkthrough is part of the versioning contract · any behavior change updates it, this file, and the skill file in the same commit.

---

what NOT to do

- never WebFetch dailyfaceoff, nhl.com, espn odds, pinnacle, covers · prefetch.py handles all of this.
- never write inline python for result resolution, formatting, or log updates · use the pipeline scripts.
- never write ad-hoc python scripts · use run_analysis.py. edit it if needed.
- never read the engine's raw json output manually · format_output.py parses it.
- never override confidence scores · computed by run_analysis.py from model_params.json policy.
- never hand-edit picks_log.jsonl or model_params.json · pipeline scripts only.
- never add scored factors that failed significance · new signals get logged as display context first and promoted only if they survive on the model's own picks later. display context (records, logs, totals) is fine; scoring it is not.
- never reintroduce display decoration (emojis, bolds, headings, dots, em dashes) · minimalist typography is a user requirement and the formatter's sanitizer enforces it.
- never quote a model number that is not in model_params.json (or derivable from picks_log) · and never call anything a lock.

---

model validation

- reproducible research stack (all in research/): build_dataset.py --season N (point-in-time csv per season · nhl api + moneypuck auto-download + espn stored pregame odds with the live-odds provider filtered and raw responses cached) → drift_lab.py (per-season factor tables, trailing-2 z-tests, threshold re-learning) → backtest_variants.py (composite variants head-to-head) → emit_params.py (writes model_params.json). factor_lab.py + backtest_v43.py are the preserved jun-2026 single-season v4.3 decision artifacts.
- replay_season.py: replays past seasons through the LIVE selection code (the real walk_scores → compute_matchups → tiering → parlay path), grades tickets against real finals, and reconciles per-game against the vectorized backtest · run it after any engine change that could move a score, and investigate every divergence.
- moneypuck: https://peter-tanner.com/moneypuck/downloads/shots_{season}.zip · xg context + historical starter detection, not in confidence scoring.
- espn stored odds caveat: since 2024-25 espn keeps only espn bet + a live-odds snapshot per event · the live provider leaked in-game state into "pregame" totals until filtered (jul 2026). assume nothing about apis; every fetcher guards dates/seasons.

---

api reference (free, no auth)

```
endpoint                                          use
https://api-web.nhle.com/v1/score/{YYYY-MM-DD}    games + goals by period (historical dates ok)
https://api-web.nhle.com/v1/score/now             today's scoreboard
https://api-web.nhle.com/v1/schedule/now          this week's schedule
https://api-web.nhle.com/v1/standings/now         current standings
https://api-web.nhle.com/v1/club-stats/{T}/{S}/2  full-season goalie stats
```

every fetcher checks the payload's own date/season against the request · a mismatch is fatal, never silent.
