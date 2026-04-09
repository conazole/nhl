---
name: analysis file uses github markdown
description: analysis file must be proper github-flavored markdown — user reads it on phone via github, not terminal
type: feedback
---

analysis file must use proper github-flavored markdown that renders on github mobile. user reads it on their phone via the github repo.

**Why:** box-drawing characters (┌─┐│└─┘═) and fixed-width text tables don't render on github. user couldn't read the analysis on mobile. changed apr 4 2026.

**How to apply:**
- use `#`/`##`/`###` for headers, not box-drawing borders
- use markdown tables (`| col | col |`), not fixed-width text alignment
- use `**bold**`, `> blockquotes`, inline code blocks for emphasis
- ✅/❌ emojis work fine in github markdown
- confidence dots (●○) work fine
- `🔒` picks, `💡` hm, `⛔` avoid labels still work
- format_output.py must generate github-flavored markdown, not terminal-style output
- NO box-drawing characters anywhere (═ ─ ┌ ┐ └ ┘ │)
