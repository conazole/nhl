---
name: track parlays and legs by model version
description: season record must be broken down by model version (v1/v2/v3/v4) AND show combined total. each version performs differently.
type: feedback
---

track season record separately per model version AND show a combined total.

**why:** mixing v1/v2/v3/v4 records together hides whether a new model is actually improving. v1/v2 are dead models with different formulas. v3 had no line factor. v4 adds the line gate. each version's record should stand on its own so we can see the improvement.

**how to apply:** when displaying season record (terminal output, emails, analysis files), show:
```
season record:

v4 (mar 28+):
  parlays: x-y (zz%)
  legs: x-y (zz%)

v3 (mar 24-27):
  parlays: x-y (zz%)
  legs: x-y (zz%)

v1/v2 (before mar 24):
  parlays: x-y (zz%)
  legs: x-y (zz%)

combined (all versions):
  parlays: x-y (zz%)
  legs: x-y (zz%)
```

filter by `"model"` field in picks_log.jsonl. entries without a model field are v1/v2. avoids and HMs also tracked per version for filter validation.
