# nhl 1p u2.5 betting analysis

real money is at stake — accuracy over speed. never estimate or guess scores. all output must be in lowercase.

## confidence formula v4.1 (4 factors, /6 scale)

v4 core validated on 1149 games (full 2025-26 season with pre-game lines). v4.1 splits backup penalty by partner type (275-game audit, apr 6 2026).

| factor | criteria | points |
| --- | --- | --- |
| combined r5 u2.5% | <70%: 0, 70-79%: +1, ≥80%: +2 | 0-2 |
| combined r15 u2.5% | <70%: 0, ≥70%: +1 | 0-1 |
| goalie matchup type | starter+starter: +2, starter+tandem OR backup+starter: +1, tandem+tandem: 0, backup+tandem: -1, backup+backup: -1 | -1 to +2 |
| total line | ≤5.5: +1, ≤6.0: 0, ≥6.5: -1 | -1 to +1 |

- pick threshold: ≥4/6. honorable mention: 2-3/6. avoid: <2/6.
- goalie classification: full-season starts share from `/v1/club-stats/{team}/20252026/2` — ≥60% starter, 40-59% tandem, <40% backup.
- v4.1: backup+starter scores +1 (77.4% u2.5, starter anchors). backup+tandem stays -1 (62.0%).
- goalie always scores — confirmed flag is informational only, not a scoring gate.
- killed factors (NOT in scoring): poisson, elite bonus, b2b, context, system profile, penalty rate, early start, playoff context (mar-jun only). computed for informational display only.
- all log entries must include `"model": "v4"`.
- v4 backtest: 64.8% parlays (+6.3pp over v3), 80.5% legs (+3.4pp). perfectly monotonic gradient.
- v4 starts tracking mar 28 2026. v3 (mar 24-27) and v1/v2 are dead.

## parlay rules

- always 2-leg parlay. top 2 picks by confidence ≥4/6 (tiebreak by r5%).
- additional qualifying games → honorable mentions, NOT additional legs.
- if only 1 game qualifies → "no parlay tonight", log as HM.
- if 0 games qualify → "no play tonight".
- picks have no `tier` field. HMs have `"tier": "honorable_mention"`. avoids have `"tier": "avoid"`.
- picks must be deterministic — same data = same picks between runs.

## output rules

- all output must be in lowercase — every word, header, label, sentence. no exceptions.
- never show poisson in any output — it's noise.
- analysis file uses box-drawing dividers, emojis, ✅/❌, confidence dots — not plain markdown.
- tables MUST use fixed-width padding for monospace alignment (python f-string formatting).
- table columns: `#`, `date`, `opp`, `h/a`, `score`, `total`, `u2.5`, `w/l`, `line`, `ft`, `g`.
- score = 1p score (gf-ga), NOT full-game score. opp values lowercase.
- w/l is informational (no analytical significance).
- line = pre-game total from bookmakers. ft = full-game final total. g = s (starter) or b (backup).
- season record: only show v4 (latest model), not combined or legacy.
- sort games by confidence level, highest first.
- terminal: show FULL detailed analysis — 15-game tables, all metrics, confidence breakdowns.
- save full analysis to `analysis_{YYYY-MM-DD}.md`. delete previous day's file.
- playoff context + caution: every game block must show playoff status for both teams AND a caution line flagging the motivation/lineup risk (both fighting = favorable, clinched/eliminated mix = rest/variance risk). informational only, NOT in scoring. picks email must flag caution for each parlay leg.

## email rules

- two emails per run to `bk.conazole@icloud.com` via osascript.
- email 1 (picks summary): subject "nhl 1p u2.5 — {date}". concise, phone-readable. parlay + 1-2 sentence reason per pick + season record + honorable mentions. under 20 lines, no tables.
- email 2 (full analysis): subject "nhl 1p u2.5 analysis — {date}". mobile-optimized — NO tables. u2.5 streaks (`✓✓✓✗✓  ✗✓✗✓✗  ✓✓✓✓✓`, grouped in 5s). lines under 40 chars. all lowercase text, including section labels. postmortem at full depth. key stats per game.
- u2.5 column: ✅/❌ in analysis file, plain ✓/✗ in emails.
- send picks email first, analysis email second. quit Mail.app after both.
- both emails sent EVERY run — first run, re-run, doesn't matter. re-runs reflect updated picks.

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

resolve_results.py: resolves TARGET_DATE-1, updates picks_log.jsonl, computes v4 record.
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

### step 4: format output

```bash
cd /Users/raz/claude/nhl && python3 format_output.py {TARGET_DATE} /tmp/engine_clean.json \
  --extras '{EXTRAS_JSON}'
```

prints full analysis to terminal + saves `analysis_{TARGET_DATE}.md`.

### step 5: log + emails + commit

```bash
cd /Users/raz/claude/nhl && python3 update_log.py {TARGET_DATE} /tmp/engine_clean.json
```

send 2 emails per email rules (picks first, analysis second). quit Mail.app.
`git add` + `git commit` + `git push` — always, no confirmation.

## change documentation

notable changes (model updates, architecture changes, new rules, killed factors, pipeline changes) must be documented in README.md with a date and brief description.

## what NOT to do

- never WebFetch dailyfaceoff, nhl.com, ESPN odds, pinnacle, covers — prefetch.py handles all of this.
- never write inline python for result resolution, formatting, or log updates — use the pipeline scripts.
- never write ad-hoc python scripts — use run_analysis.py. edit it if needed.
- never read engine's raw JSON output manually — format_output.py parses it.
- never override confidence scores — computed by run_analysis.py using the v4 formula.

## model validation

- moneypuck: `https://peter-tanner.com/moneypuck/downloads/shots_2025.zip` — for xG context only, not in confidence scoring.
- what to watch: does ≥4/6 threshold maintain strong leg accuracy? does the 6.5 gate hold? does 6.0 stay closer to 5.5 than to 6.5? does always-score goalie improve pick volume without sacrificing accuracy?

## api reference (free, no auth)

| endpoint | use |
| --- | --- |
| `https://api-web.nhle.com/v1/score/{YYYY-MM-DD}` | games + goals by period |
| `https://api-web.nhle.com/v1/score/now` | today's scoreboard |
| `https://api-web.nhle.com/v1/schedule/now` | this week's schedule |
| `https://api-web.nhle.com/v1/standings/now` | current standings |
