# nhl 1p u2.5 betting analysis

real money is at stake — accuracy over speed. never estimate or guess scores. all output must be in lowercase.

## confidence formula v4.2 (4 factors, /6 scale, playoff-aware)

v4 core validated on 1149 games (full 2025-26 season with pre-game lines). v4.1 splits backup penalty by partner type (275-game audit, apr 6 2026). v4.2 adds playoff-only overrides (435-game playoff audit + 88-team-series goalie audit, apr 18 2026).

| factor | criteria | points |
| --- | --- | --- |
| combined r5 u2.5% | <70%: 0, 70-79%: +1, ≥80%: +2 | 0-2 |
| combined r15 u2.5% | <70%: 0, ≥70%: +1 | 0-1 |
| goalie matchup type | starter+starter: +2, starter+tandem OR backup+starter: +1, tandem+tandem: 0, backup+tandem: -1, backup+backup: -1 | -1 to +2 |
| total line | ≤5.5: +1, ≤6.0: 0, ≥6.5: -1 | -1 to +1 |

- pick threshold: ≥4/6. honorable mention: 2-3/6. avoid: <2/6.
- goalie classification (regular season): full-season starts share from `/v1/club-stats/{team}/20252026/2` — ≥60% starter, 40-59% tandem, <40% backup.
- v4.1: backup+starter scores +1 (77.4% u2.5, starter anchors). backup+tandem stays -1 (62.0%).
- goalie always scores — confirmed flag is informational only, not a scoring gate.
- killed factors (NOT in scoring): poisson, elite bonus, b2b, context, system profile, penalty rate, early start, standings-status playoff context (mar-jun only, informational display only).
- all log entries must include `"model": "v4"`.
- v4 backtest: 64.8% parlays (+6.3pp over v3), 80.5% legs (+3.4pp). perfectly monotonic gradient.
- v4 starts tracking mar 28 2026. v3 (mar 24-27) and v1/v2 are dead.

### v4.2 playoff overrides (gameType=3 only — regular season untouched)

- **goalie override:** when `gameType == 3`, any dfo-named goalie is classified as `starter` regardless of regular-season starts share. justified by 88-team-series audit (88.2% of playoff starts go to team's #1, only 13% true tandems). regular-season starts share is dragged down by injuries/call-ups/tandems that disappear in playoffs.
- **game-1 confidence cap:** when `gameType == 3` and `seriesStatus.gameNumberOfSeries == 1`, confidence is capped at 3 (HM max). justified by 435-game playoff audit: g1 u2.5 rate is 72.0% pooled and **63.3% in the last 2 seasons** — BELOW the regular-season baseline (73%). g2+ recover to 77-80%, g4+ hit 81%. cap prevents false picks on high-variance g1 slates.
- **regular season behavior is unchanged.** all patches are gated on `gameType == 3`; gameType=2 games flow through the original v4.1 path with no modification.
- **both patches must ship together.** the goalie override alone would push g1s with starter+starter matchups to ≥4/6 picks — precisely the games the 63.3% audit says to avoid. goalie override without cap is net-negative EV.
- v4.2 starts tracking apr 18 2026 (first playoff slate).

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

### step 3b: spawn ice — parlay critic (parlay nights only)

if the engine returned 2 picks (n=2 at ≥4/6), ALWAYS spawn ice (via the `Agent` tool) before step 4. ice is a skeptical critic with fresh context — her job is to surface reasons the parlay could lose that the deterministic model can't price.

**informational only.** ice's verdict is flagged as a concern in the analysis + picks email — it does NOT downgrade, drop, or skip the parlay. the v4 model is deterministic and validated; its picks stand. ice exists so we see the blindspots, track them, and later assess whether her calls correlate with outcomes.

when to spawn ice:
- 2 picks (parlay night) → YES, spawn ice
- 0-1 picks (no play / solo HM) → SKIP ice, nothing to review

ice agent spec:
- subagent_type: general-purpose
- description: "ice — parlay critic review"
- run_in_background: false (need her verdict before format_output)
- prompt: use the template in the "## ice — parlay critic" section below, filled with tonight's data

render ice's verdict in the analysis report and picks email under an "🧊 ice review" section. the parlay text itself stays unchanged — ice is a warning light, not a kill switch.

### step 4: format output

```bash
cd /Users/raz/claude/nhl && python3 format_output.py {TARGET_DATE} /tmp/engine_clean.json \
  --extras '{EXTRAS_JSON}'
```

extras JSON must include ice's verdict when applicable: `{"postmortem": "...", "ice": {"verdict": "BET AS-IS|BET 1-LEG|SKIP", "per_leg": [...], "concerns": "..."}, "injuries": {}, "context": {}}`.

prints full analysis to terminal + saves `analysis_{TARGET_DATE}.md`.

### step 5: log + emails + commit

```bash
cd /Users/raz/claude/nhl && python3 update_log.py {TARGET_DATE} /tmp/engine_clean.json
```

send 2 emails per email rules (picks first, analysis second). quit Mail.app.
`git add` + `git commit` + `git push` — always, no confirmation.

### optional step 6: closing line capture (~30 min before first puck drop)

```bash
cd /Users/raz/claude/nhl && python3 close_line.py {TARGET_DATE}
```

re-fetches lines and writes `closing_line`, `line_delta`, `line_direction`, `closing_ts` to each unresolved entry. safe to run multiple times. safe alongside /nhl re-runs (update_log.py preserves these fields across re-runs).

clv interpretation: for u2.5 bets, line going UP = market pricing more goals = our bet got harder (negative clv). flip sign in review.py so positive clv = market-moved-toward-us.

### weekly: revalidate + review

```bash
cd /Users/raz/claude/nhl && python3 review.py --last 14
cd /Users/raz/claude/nhl && python3 research/revalidate.py
```

review.py: per-factor hit rates, CLV trend, base rate drift, weekly trend.
revalidate.py: compares recent 100 games to v4 baselines, flags >5pp drift.

## ice — parlay critic

ice reviews the engine's 2-leg parlay before the report is written. she has no memory of the main thread's reasoning — that's the point. she finds blindspots the deterministic model can't score (goalie risk the model marked "starter" but external signals disagree, playoff context that inverts a pick, sharp line movement, recent trend contradictions, divisional high-scoring traps).

ice only reviews parlays (n=2). she does NOT review solo HMs, avoids, or no-play nights.

spawn ice via Agent tool with `subagent_type: general-purpose`, `run_in_background: false`. prompt template (fill in `{...}` placeholders with tonight's actual data before spawning):

```
you are ice, a skeptical critic for an nhl 1st-period-under-2.5-goals betting model. your ONLY job is to find reasons the 2-leg parlay could lose. DO NOT rubber-stamp. DO NOT expand scope (no adding legs, no switching picks). focus only on pick quality and blindspots the deterministic model misses.

target date: {TARGET_DATE}

the engine has selected these 2 legs:

leg 1: {AWAY1 @ HOME1}
- confidence: {C1}/6
- total line: {LINE1}
- combined r5 u2.5%: {R5_1}%
- combined r15 u2.5%: {R15_1}%
- goalie matchup: {AWAY1_GOALIE} ({type}) vs {HOME1_GOALIE} ({type})
- playoff context: {AWAY1_STATUS} / {HOME1_STATUS}
- caution: {CAUTION1}

leg 2: {AWAY2 @ HOME2}
- confidence: {C2}/6
- total line: {LINE2}
- combined r5 u2.5%: {R5_2}%
- combined r15 u2.5%: {R15_2}%
- goalie matchup: {AWAY2_GOALIE} ({type}) vs {HOME2_GOALIE} ({type})
- playoff context: {AWAY2_STATUS} / {HOME2_STATUS}
- caution: {CAUTION2}

context:
- yesterday's results: {POSTMORTEM_ONE_LINER}
- injury/lineup flags: {INJURIES_OR_"none"}
- lines flagged for verification: {LINES_VERIFICATION_OR_"none"}
- any b2b goalie situations: {B2B_FLAGS_OR_"none"}

your review checks:

1. GOALIE RISK: is either "starter" classification wrong? is there a b2b that likely flips the goalie to a backup the model hasn't seen? is the "starter" coming off a pull or 40+ saves that increases mid-period fatigue risk?

2. PLAYOFF / MOTIVATION TRAP: is either game a situation that historically produces a hot 1p (desperation spot, elimination, home opener intensity, rivalry with bad blood)? or the opposite — rest/rotation risk disguised as starter+starter?

3. LINE SIGNAL: is the 6.0 line actually a 6.5 at sharper books (implies hidden over lean)? is a 5.5 line soft for a reason (goalie upside)?

4. RECENT TREND CONTRADICTION: do the r5/r15 numbers hide a recent pattern (e.g., last 2 games both went 8+ total, or last 3 games all had 3+ in 1p)? check directional momentum, not just the aggregate %.

5. CORRELATION / PORTFOLIO: are both legs exposed to the same failure mode (both involve a division known for hot starts, both on teams coming off heavy travel, both playing same goalie archetype that's been leaking 1p lately)? if one leg cracks, does the other go with it?

6. PER-LEG VERDICT: for each leg, return: APPROVE / WARN ([one specific concern]) / VETO ([dealbreaker]).

7. OVERALL RECOMMENDATION: BET AS-IS | BET 1-LEG (specify which to drop) | SKIP (specify why).

output format (strict):
- bullet points only, under 220 words total
- no hedging, no "on the other hand" — commit to your read
- end with one-line verdict: BET AS-IS | BET 1-LEG (drop leg X) | SKIP
```

action policy: **informational only.** ice's output is flagged as a concern in the analysis + picks email. it does NOT downgrade, drop, or skip the parlay. the v4 model is deterministic and validated — its picks stand. ice exists to surface blindspots so we can see them, track them, and later evaluate whether her calls correlate with outcomes. treat her verdict as a warning light, not a kill switch.

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
