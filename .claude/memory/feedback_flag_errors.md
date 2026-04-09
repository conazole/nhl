---
name: flag script errors immediately
description: never silently work around script errors — stop and flag them for discussion before proceeding
type: feedback
---

never ignore or silently work around errors from pipeline scripts. if a script fails, stop and flag it to the user so we can discuss and fix the root cause together.

**Why:** during the apr 5 run, format_output.py and update_log.py both errored due to interface mismatches. instead of flagging them, I worked around them with inline python and extra tool calls — wasting time and hiding bugs that should have been fixed immediately.

**How to apply:** if any script (prefetch.py, run_analysis.py, format_output.py, update_log.py, resolve_results.py, review.py) exits non-zero, immediately show the error to the user and propose a fix. don't silently retry, don't write ad-hoc workarounds, don't keep going as if nothing happened.
