---
name: never rewrite deterministic code
description: never regenerate scripts or rewrite deterministic computation logic — use existing tools (run_analysis.py) that already have all fixes baked in
type: feedback
---

never rewrite code that computes deterministic things (data collection, API fetching, metrics, confidence scoring, poisson, system profiles). it's a waste of time — the logic doesn't change between runs, and regenerating it means re-discovering and re-fixing the same bugs every time.

**Why:** generating analysis scripts from scratch took 41 minutes due to writing, debugging (403 errors, moneypuck ID mapping, league avg xGA calculation), and back-and-forth. the pre-built `run_analysis.py` runs in ~32 seconds with all fixes baked in. deterministic code should be written once, saved, and reused.

**How to apply:**
- use `run_analysis.py` for ALL nhl data collection and analysis. never write a new python script for this.
- run: `python3 run_analysis.py {YYYY-MM-DD} --goalies '{json}'` — outputs full JSON to stdout, progress to stderr
- if the script needs a bug fix or new feature, EDIT the existing `run_analysis.py` — don't write a replacement
- claude handles only the non-deterministic parts: yesterday's post-mortem, goalie/injury web fetches, context modifiers, output formatting, email, picks log updates
- goalie arg format: `--goalies '{"BOS":"swayman","NYR":"shesterkin",...}'` (last names, lowercase)
