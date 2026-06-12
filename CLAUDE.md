# nhl 1p u2.5 betting analysis

real money is at stake — accuracy over speed. never estimate or guess scores. all output must be in lowercase.

## confidence formula v4.3 (4 factors, /6 scale, playoff-aware)

v4 core validated on 1149 games. v4.1 splits backup penalty by partner type (apr 6 2026). v4.2 adds playoff overrides (apr 18 2026). v4.3 (jun 12 2026) re-validated every factor on a 1393-game point-in-time season dataset (chronological train/holdout split at feb 15, wilson CIs — `research/build_dataset.py` + `factor_lab.py` + `backtest_v43.py`) and replaced the r15 factor with the day-game factor.

| factor | criteria | points |
| --- | --- | --- |
| combined r5 u2.5% (de-duped) | <70%: 0, 70-79%: +1, ≥80%: +2 | 0-2 |
| day game | local start before 5:00pm ET: +1, else 0 | 0-1 |
| goalie matchup type | starter+starter: +2, starter+tandem OR backup+starter: +1, tandem+tandem: 0, backup+tandem: -1, backup+backup: -1 | -1 to +2 |
| total line | ≤5.5: +1, ≤6.0: 0, ≥6.5: -1 | -1 to +1 |

- pick threshold: ≥4/6. honorable mention: 2-3/6. avoid: <2/6.
- why r15 was dropped (v4.3): +1.6pp full season, INVERTED on holdout; its near-free +1 (fired on 63% of games) promoted base-rate games into the pick tier — the 208 picks it added vs the day-swap variant hit 75.0% = exactly base rate. r15 is still computed, logged, displayed, and used in the deterministic tiebreak — it is just NOT scored.
- why day game was added (v4.3): day games (<5pm ET) hit 83.2% u2.5 (119/143) vs 72.7% prime-time; holds on both sides of the train/holdout split (matinee 81.6%/93.3%, afternoon 81.7%/88.5%). mechanism: routine disruption + the 1p feeling-out process. the old killed "early start" factor used a too-narrow definition (11am/12pm CT only); the real effect spans the whole pre-5pm window.
- combined r5/r15 are computed over the UNION of both teams' windows — games the two teams played against each other count once, not twice (matters deep in playoff series where most of the window is shared).
- goalie classification (regular season): full-season starts share from `/v1/club-stats/{team}/20252026/2` — ≥60% starter, 40-59% tandem, <40% backup.
- v4.1: backup+starter scores +1 (77.4% u2.5, starter anchors). note: the jun 12 point-in-time re-audit found backup+tandem ≈ base rate (74.0%) and tandem+tandem worst (67.4%) under to-date classification — map left unchanged (different classifier population); re-audit next season before any remap.
- goalie always scores — confirmed flag is informational only, not a scoring gate.
- fail-closed line gate: a game with NO sourced line is capped at 3/6 (can never be a pick) and flagged `line_missing`. wrong line = wrong gate decision; no line = no pick.
- killed factors (NOT in scoring): r15 (v4.3), poisson, elite bonus, b2b, context, system profile, penalty rate, h2h, venue-split form, day-of-week, rolling 1p goal/sog/xg environments, standings-status playoff context (informational display only).
- all log entries carry `"model": "v4"` (season-record continuity) plus `"model_version": "v4.3"` and `factors.day`.
- v4.3 backtest (1393 games, point-in-time): pick tier ≥4 = 83.0% (153 picks), tier ≥5 = 88.1%, conf-4 holdout 83.3%, simulated parlay nights 65.9% at ~23% of slates. v4.2 on the same dataset: 78.3% on 360 picks. volume drops by design — the cut games carried no edge.
- v4.3 starts tracking jun 12 2026. v4.2 (apr 18 – jun 6) and v4/v4.1 (mar 28 – apr 17) results remain under model "v4". v3/v2/v1 are dead.

### v4.2 playoff overrides (gameType=3 only — regular season untouched)

- **goalie override:** when `gameType == 3`, any dfo-named goalie is classified as `starter` regardless of regular-season starts share. justified by 88-team-series audit (88.2% of playoff starts go to team's #1, only 13% true tandems). regular-season starts share is dragged down by injuries/call-ups/tandems that disappear in playoffs.
- **game-1 confidence cap:** when `gameType == 3` and `seriesStatus.gameNumberOfSeries == 1`, confidence is capped at 3 (HM max). justified by 435-game playoff audit: g1 u2.5 rate is 72.0% pooled and **63.3% in the last 2 seasons** — BELOW the regular-season baseline (73%). g2+ recover to 77-80%, g4+ hit 81%. cap prevents false picks on high-variance g1 slates.
- **regular season behavior is unchanged.** all patches are gated on `gameType == 3`; gameType=2 games flow through the original v4.1 path with no modification.
- **both patches must ship together.** the goalie override alone would push g1s with starter+starter matchups to ≥4/6 picks — precisely the games the 63.3% audit says to avoid. goalie override without cap is net-negative EV.
- v4.2 starts tracking apr 18 2026 (first playoff slate).

## parlay rules

- always 2-leg parlay. top 2 picks ≥4/6 by the shared deterministic sort key: confidence desc, r5% desc, r15% desc, game string asc (`record.pick_sort_key` — used identically by update_log demotion, format_output display, and season-record scoring).
- additional qualifying games → honorable mentions, NOT additional legs (update_log demotes 3rd+ qualifiers automatically).
- if only 1 game qualifies → "no parlay tonight", log as HM.
- if 0 games qualify → "no play tonight".
- picks have no `tier` field. HMs have `"tier": "honorable_mention"`. avoids have `"tier": "avoid"`.
- picks must be deterministic — same data = same picks between runs.
- season parlay record is scored on the top-2 legs per date (what was actually bet) — `record.compute_season_record`. postponed games resolve as `"void"` and are excluded from all counts.
- log invariants (checked automatically on every update_log/resolve run): ≤2 untiered picks per date, no unresolved entries older than yesterday, no duplicate (date, game), every pick has a line. investigate any warning immediately.

## output rules

- all output must be in lowercase — every word, header, label, sentence. no exceptions.
- never show poisson in any output — it's noise.
- **minimalist style (jun 12 2026 — supersedes the old emoji/dots style):** NO markdown headings (#/##/###), NO bold or italics, NO emojis, NO confidence dots. section labels are plain text lines. the only ornaments allowed: one ━ masthead rule, > quote rails, plain ✓/✗ data marks, ← in streak strips.
- ALL tables are fenced monospace code blocks with space-aligned fixed-width columns (python f-string padding). never markdown table syntax — it renders bold headers.
- analysis file order: masthead (title line, ━ rule, slate context line) → tonight at a glance → parlay / no-parlay / no-play → honorable mentions → avoid → yesterday + post-mortem → season — v4 → game details (collapsible `<details>` per game, sorted by confidence) → footer (model formula line).
- at-a-glance columns: game, conf, line, pair, start, notes. goalie pairs abbreviated in ALL display: s+s, s+t, b+s, t+t, b+t, b+b (log keeps full words).
- parlay legs carry pre-bet decision info, one quote block per leg, in order: time · line · pair · tags / goalies confirmation line / factor strip / season record for that confidence tier / risk line (computed from factor math: what late line move or backup swap exits pick range) / note (series state or motivation caution).
- 15-game table columns: `#`, `date`, `opp`, `h/a`, `score`, `total`, `u2.5`, `w/l`, `line`, `ft`, `g`. score = 1p score (gf-ga), NOT full-game. u2.5 column plain ✓/✗. opp lowercase.
- each team block: goalie line (`uta — vejmelka (starter) · last-5 1p ga 1,0,2,1,0 · season sv% .912`), then the table code block with the u2.5 streak strip (✓✓✗✓✓ grouped in 5s, newest first) at the top.
- w/l is informational (no analytical significance).
- line = pre-game total from bookmakers. ft = full-game final total. g = s (starter) or b (backup).
- season record: only show v4 (latest model line), not combined or legacy.
- sort games by confidence level, highest first.
- terminal: show FULL detailed analysis — same string as the saved file.
- save full analysis to `analysis_{YYYY-MM-DD}.md`. delete previous day's file.
- playoff context + caution: every game block must show series state (playoffs) or playoff-race status + caution line (regular season — both fighting = favorable, clinched/eliminated mix = rest/variance risk). informational only, NOT in scoring. parlay legs must carry their caution as the `note:` line.

## email rules

**emails are DISABLED (apr 22 2026).** skip the email step entirely — do not send picks email, do not send analysis email, do not invoke osascript, do not quit Mail.app. terminal output + saved `analysis_{date}.md` file are the only deliverables. specs below kept for reference; will be re-enabled later.

- ~~two emails per run to `bk.conazole@icloud.com` via osascript.~~
- ~~email 1 (picks summary): subject "nhl 1p u2.5 — {date}". concise, phone-readable. parlay + 1-2 sentence reason per pick + season record + honorable mentions. under 20 lines, no tables.~~
- ~~email 2 (full analysis): subject "nhl 1p u2.5 analysis — {date}". mobile-optimized — NO tables. u2.5 streaks (`✓✓✓✗✓  ✗✓✗✓✗  ✓✓✓✓✓`, grouped in 5s). lines under 40 chars. all lowercase text, including section labels. postmortem at full depth. key stats per game.~~
- ~~u2.5 column: ✅/❌ in analysis file, plain ✓/✗ in emails.~~
- ~~send picks email first, analysis email second. quit Mail.app after both.~~
- ~~both emails sent EVERY run — first run, re-run, doesn't matter. re-runs reflect updated picks.~~

## postmortem rules

- every run includes "what we got right / what we got wrong" after yesterday's results.
- explain WHY picks hit or missed — what did the model catch? what did it miss?
- CRITICAL: don't frame HMs or avoids going under as "misses" — base rate is ~72%. only flag genuine analytical errors: a pick that lost with warning signs we ignored, or a pattern the model failed to account for.

## line sourcing

- fetch from ESPN + at least 1 additional source (Pinnacle). take consensus.
- ESPN sometimes rounds 6.0 to 5.5 or 6.5. 6.0 is the most common line (43% of season).
- wrong line = wrong gate decision. line sourcing is critical.
- display total line in each game's analysis with factor contribution (+1/0/-1).
- line data passed to engine via `--lines '{"AWAY@HOME": 6.5}'`.
- validation: 5.5=78.7%, 6.0=76.4%, 6.5=72.6% (1149 games).

## goalie rules

- goalie always scores — confirmed flag is informational only, never zero out for unconfirmed.
- tonight's starter sourced from external sources (dailyfaceoff), not starts-share math.
- fetch ALL sources — never accept "unconfirmed" when info is available.

## workflow rules

- always commit and push at end of each run. no confirmation needed.
- multiple runs per day allowed. full fresh execution each time — no caching, no skipping.
- re-runs: remove existing TARGET_DATE entries from picks_log before appending. never touch yesterday's resolved results.
- crontab: daily 1:03 PM CT. manual runs anytime.
- run in early afternoon (1-3pm ET) for goalie confirmations.
- never rewrite pipeline scripts from scratch — edit existing ones.
- flag script errors immediately — never silently work around them, stop and discuss.
- use prefetch pipeline (prefetch.py + resolve_results.py + format_output.py + update_log.py).
- review.py: weekly pattern analysis — run manually, not part of daily pipeline.
- no shortcuts — every model factor must use the correct data scope, not whatever's convenient.

## date selection

parse `$ARGUMENTS` to determine TARGET_DATE (YYYY-MM-DD):
- empty → today
- "tomorrow" → today + 1
- date string (e.g. "mar 2", "2026-03-05") → parse it (assume current year)

"yesterday" for results = TARGET_DATE - 1. future dates: flag goalie/injury uncertainty.

## execution pipeline (5 steps)

CRITICAL: use pipeline scripts. never manual WebFetch for goalies/lines.

### step 1: resolve yesterday + prefetch today (PARALLEL)

run simultaneously:

```bash
cd /Users/raz/claude/nhl && python3 resolve_results.py {TARGET_DATE}
```
```bash
cd /Users/raz/claude/nhl && python3 prefetch.py {TARGET_DATE}
```

resolve_results.py: resolves ALL unresolved dates < TARGET_DATE (sweep — gap days can never dangle), voids postponed games, updates picks_log.jsonl, computes v4 record (top-2 parlay scoring), and emits `invariant_warnings` — investigate any warning immediately.
prefetch.py: fetches goalies (dfo), lines (ESPN+Pinnacle), flags discrepancies. outputs `goalies_engine` + `lines` dicts.

### step 2: review + postmortem

1. write postmortem from resolve results (see postmortem rules).
2. check `lines_needing_verification` — ONE WebSearch if discrepancy matters for a pick.
3. check goalie conflicts (e.g. B2B) — ONE WebSearch max.
4. build extras JSON: `{"postmortem": "...", "injuries": {}, "context": {}}`

### step 3: run engine

```bash
cd /Users/raz/claude/nhl && python3 run_analysis.py {TARGET_DATE} \
  --goalies '{GOALIES_ENGINE_JSON}' \
  --lines '{LINES_JSON}' > /tmp/engine_output.json 2>&1
```

extract clean JSON (skip log lines): `tail -n +{first_json_line} > /tmp/engine_clean.json`

### step 3b: spawn ice — independent critic (picks OR hm nights)

**ice is DISABLED (may 16 2026).** skip this step entirely — do not spawn the ice agent, do not include ice in extras JSON, do not render an "🧊 ice review" section in the analysis. go directly from step 3 (engine) to step 4 (format output). spec sections below kept for reference; will be re-enabled later.

### step 4: format output

```bash
cd /Users/raz/claude/nhl && python3 format_output.py {TARGET_DATE} /tmp/engine_clean.json \
  --extras '{EXTRAS_JSON}'
```

extras JSON: `{"postmortem": "...", "injuries": {}, "context": {}}`. **ice key is NOT required (ice disabled may 16 2026).**

prints full analysis to terminal + saves `analysis_{TARGET_DATE}.md`.

### step 5: log + commit

```bash
cd /Users/raz/claude/nhl && python3 update_log.py {TARGET_DATE} /tmp/engine_clean.json
```

~~send 2 emails per email rules (picks first, analysis second). quit Mail.app.~~ **(emails disabled apr 22 2026 — skip entirely.)**
`git add` + `git commit` + `git push` — always, no confirmation.

**clv is transparent.** run `/nhl` as many times as you want in a day — the pipeline records the first observed line as `total_line` (opening) and automatically writes `closing_line` + `line_delta` any time a later run sees a different line. single run, no line movement, nothing gets recorded — that's fine. nothing for you to configure, nothing to remember, no cron required.

clv interpretation (informational, shown in review.py): for u2.5 bets, line going UP = market pricing more goals = our bet got harder (negative clv). review.py flips the sign so positive clv = market moved toward us.

`close_line.py` exists as a standalone lightweight "just refresh lines, don't rerun the full pipeline" option — useful if you want to pin a closing line without re-triggering picks/emails/commits.

### weekly: revalidate + review

```bash
cd /Users/raz/claude/nhl && python3 review.py --last 14
cd /Users/raz/claude/nhl && python3 research/revalidate.py
```

review.py: per-factor hit rates, CLV trend, base rate drift, weekly trend.
revalidate.py: compares recent 100 games to v4 baselines, flags >5pp drift.

## ice — critic agent spec (DISABLED may 16 2026 — kept for reference)

**ice is currently disabled. do not spawn the ice agent in any /nhl run.** the sections below describe how ice worked when active, kept here so we can re-enable cleanly later.

the full ice spec lives at `~/.claude/agents/ice.md`. she's a research-driven critic with `WebSearch`, `WebFetch`, `Read` tools and a built-in knowledge base (nhl 1p u2.5 edge tables from our audits + external reference rates). on every invocation she reads her own spec first, then runs mandatory live research per leg:

1. **goalie confirmation** (dailyfaceoff + beat-writer websearch)
2. **last-24hr lineup / injury** (espn injuries + team beat writers)
3. **referee crew / pp exposure** (scoutingtherefs)
4. **sharp line movement** (action network + pinnacle-direction websearch)
5. **1p-specific recent trend** (naturalstattrick + nhl api per-period)
6. **playoff series context** (nhl api + series-news websearch) — playoff only

she returns a strict per-leg verdict (approve / warn / veto) + overall parlay recommendation (bet as-is / bet 1-leg / skip), ≤300 words, every claim cited with a url. no fabrication — if a source is blocked she names it.

spawn ice via Agent tool with `subagent_type: general-purpose`, `run_in_background: false`. custom subagent_types aren't live mid-session; general-purpose is the vehicle — ice.md instructs her to read her own spec first, then apply it.

### ice — critic prompt template

fill in `{...}` placeholders with tonight's actual data before spawning. for hm-only nights, list the hms under "honorable mentions" and omit the "picks" block (or vice versa — whichever applies).

```
you are ice. the full spec is at ~/.claude/agents/ice.md — read that file FIRST to understand your role, mandatory research playbook, edge tables, checklist, and strict output format. then apply it to tonight's slate below. be skeptical — do not rubber-stamp.

target date: {TARGET_DATE}
phase: {regular season | playoff}

picks (≥4/6 confidence, skipped if none):
- leg 1: {AWAY1 @ HOME1} | conf {C1}/6 | line {LINE1} | r5 {R5_1}% | r15 {R15_1}% | goalies {AWAY1_GOALIE} ({type}) vs {HOME1_GOALIE} ({type}) | playoff ctx {AWAY1_STATUS} / {HOME1_STATUS} | caution {CAUTION1}
- leg 2 (if applicable): {same structure}

honorable mentions (2-3/6, skipped if none):
- {AWAY @ HOME} | conf {C}/6 | line {LINE} | r5 {R5}% | r15 {R15}% | goalies {AWAY_GOALIE} ({type}) vs {HOME_GOALIE} ({type}) | playoff ctx {AWAY_STATUS} / {HOME_STATUS} | caution {CAUTION}
- ... (repeat for each hm)

slate context:
- yesterday's postmortem (one line): {POSTMORTEM_ONE_LINER}
- prefetch injury flags: {INJURIES_OR_"none"}
- lines flagged for verification: {LINES_VERIFICATION_OR_"none"}
- b2b goalie situations: {B2B_FLAGS_OR_"none"}

run your mandatory research per ~/.claude/agents/ice.md (goalies, lineups, refs, line movement, 1p trends, playoff narrative). return the strict verdict format. cite every non-obvious claim.
```

action policy: **informational only.** ice's output is flagged as a concern in the analysis + picks email. it does NOT downgrade, drop, or skip any pick or hm. the v4.2 model is deterministic and validated — its picks stand. ice exists to surface blindspots so we can see them, track them, and later evaluate whether her calls correlate with outcomes. treat her verdict as a warning light, not a kill switch.

## change documentation

notable changes (model updates, architecture changes, new rules, killed factors, pipeline changes) must be documented in README.md with a date and brief description.

## what NOT to do

- never WebFetch dailyfaceoff, nhl.com, ESPN odds, pinnacle, covers — prefetch.py handles all of this.
- never write inline python for result resolution, formatting, or log updates — use the pipeline scripts.
- never write ad-hoc python scripts — use run_analysis.py. edit it if needed.
- never read engine's raw JSON output manually — format_output.py parses it.
- never override confidence scores — computed by run_analysis.py using the v4.3 formula.
- never hand-edit picks_log.jsonl — pipeline scripts only. one-off migrations live in `research/` with verification + audit trail (see `research/migrate_2026_06_12_parlay_integrity.py` for the pattern).
- never reintroduce display decoration (emojis, bolds, headings, dots) — minimalist style is a user requirement (jun 12 2026).

## model validation

- moneypuck: `https://peter-tanner.com/moneypuck/downloads/shots_2025.zip` — for xG context only, not in confidence scoring.
- reproducible backtest: `research/build_dataset.py` (point-in-time season table) → `research/factor_lab.py` (per-factor train/holdout) → `research/backtest_v43.py` (variant comparison). re-run at season start on the new season's data before trusting v4.3 weights.
- what to watch (v4.3): does the day-game factor hold next season (this season n=143)? does conf-4 stay ≥75%? is pick volume (~2-3 parlay nights/week) acceptable? does the 6.5 gate hold? g1 cap — live g1s running 73.3% vs the 63.3% audit basis; retire the cap if it keeps tracking the pooled 72% instead. goalie map — re-audit backup+tandem (-1) and tandem+tandem (0) with point-in-time classification.

## api reference (free, no auth)

| endpoint | use |
| --- | --- |
| `https://api-web.nhle.com/v1/score/{YYYY-MM-DD}` | games + goals by period |
| `https://api-web.nhle.com/v1/score/now` | today's scoreboard |
| `https://api-web.nhle.com/v1/schedule/now` | this week's schedule |
| `https://api-web.nhle.com/v1/standings/now` | current standings |
