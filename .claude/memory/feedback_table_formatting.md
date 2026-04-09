---
name: table formatting rules
description: 15-game tables must use fixed-width padding and show full-game total in ft column
type: feedback
---

tables must use fixed-width padding for monospace alignment — every column cell padded to consistent width. use the python formatting script pattern to generate tables from JSON data.

tables need BOTH columns: `line` (pre-game o/u from bookmakers) AND `ft` (full-game final total). cross-reference picks_log entries (which store `total_line` since mar 7) to backfill historical pre-game lines where available. show `-` only where we truly don't have the data. `ft` always has data from the API's `full_total` field.

**Why:** user flagged that unpadded markdown tables look broken in monospace terminal, and empty "-" columns waste space when we have the actual final total available.

**How to apply:** always generate tables via python script from JSON data with fixed-width f-string formatting. use `full_total` from game data in the ft column.
