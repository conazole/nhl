---
name: never rewrite daily scripts
description: never rewrite formatting/analysis scripts from scratch — reuse existing ones, edit if needed
type: feedback
---

never rewrite scripts that are used daily. the repo has 4 permanent scripts — use them, edit them if needed, never write ad-hoc replacements.

**the 4 scripts:**
1. `run_analysis.py` — engine. fetches data, computes v4 confidence. outputs JSON.
2. `format_output.py` — formatter. takes engine JSON + extras, outputs styled analysis file.
3. `resolve_results.py` — resolves yesterday's picks against actual scores, updates log, outputs record JSON.
4. `update_log.py` — adds/replaces entries in picks_log.jsonl for a given date.

**Why:** rewriting from scratch loses accumulated formatting decisions, edge cases, and visual styling. ad-hoc scripts in /tmp are throwaway and can't be improved over time.

**How to apply:** every repeatable action in the /nhl workflow has a permanent script. if something needs to change, edit the existing script — don't write a new one. if a genuinely new capability is needed, add it as a permanent script in the repo.
