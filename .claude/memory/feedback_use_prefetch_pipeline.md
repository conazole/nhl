---
name: use prefetch pipeline for speed — MANDATORY
description: MUST use prefetch.py + resolve_results.py + format_output.py pipeline. never do manual WebFetch calls for goalies/lines. apr 3 took 11min, apr 4 took 16min — both from ignoring this.
type: feedback
---

**MANDATORY: use the python pipeline scripts. never do manual WebFetch/WebSearch for goalies or lines.**

the pipeline scripts do in parallel what 7+ WebFetch calls do sequentially — and they actually work, unlike most WebFetch targets (pinnacle, covers, fantasylabs, scoresandodds all return empty JS).

**Why:** apr 3 run took 11 minutes (32 turns), apr 4 took 16 minutes (25+ turns). the engine itself takes ~6s. ALL the time is wasted on sequential LLM web fetches that mostly fail. user explicitly flagged this as unacceptable twice.

**How to apply — the ONLY correct /nhl workflow (~7 turns):**

1. **parallel:** run resolve_results.py AND prefetch.py simultaneously
   - `python3 resolve_results.py {TARGET_DATE}` → resolves yesterday, returns JSON with results + season record
   - `python3 prefetch.py {TARGET_DATE}` → fetches goalies (DFO) + lines (ESPN API + oddsshark) in parallel (~1-2s)

2. **review prefetch output** — agent reads JSON, writes postmortem text (no tool call)
   - if ESPN line looks suspicious (6.5 when 6.0 likely), do ONE WebSearch to verify
   - this is the ONLY web fetch the agent should ever need
   - for goalie conflicts, do at most ONE WebSearch for the specific conflict

3. `python3 run_analysis.py {TARGET_DATE} --goalies '{...}' --lines '{...}'` with prefetched data

4. `python3 format_output.py {TARGET_DATE} /tmp/engine.json --extras '{postmortem, injuries, context}'` → generates analysis file + terminal output

5. emails via osascript + save log + git commit/push

**what NOT to do:**
- never WebFetch dailyfaceoff, nhl.com projections, ESPN odds, pinnacle, covers, scoresandodds, fantasylabs — prefetch.py handles all of these
- never inline python for result resolution — resolve_results.py does it
- never inline python for formatting — format_output.py does it
- never read the engine's raw 105KB JSON output manually — format_output.py parses it
