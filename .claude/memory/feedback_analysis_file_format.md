---
name: analysis-file-minimalist-style
description: analysis file must render on github mobile AND be minimalist — no emojis, no bolds, no markdown headings, no confidence dots. plain text + fenced monospace blocks only.
metadata:
  type: feedback
---

the analysis file must (a) render cleanly on github mobile — user reads it on their phone via the repo (apr 4 2026) — and (b) be minimalist: no decoration (jun 12 2026, supersedes the apr-4 guidance to use headers/bolds/emojis/dots).

**why:** apr 4: raw box-drawing text tables didn't render on github mobile, so the file moved to github-flavored markdown. jun 12: user reviewed the rendered file on github and rejected decoration in three explicit rounds — "remove all ●●●●●○, all bolds, stupid childish stuff, i want clean and minimalist style"; then markdown headings too ("there are still bolds, for titles"); then the `── title ──` brackets ("way too excessive"). this is the last screen read before money moves — quiet and information-dense wins.

**how to apply:**
- NO markdown headings (#/##/###), NO bold/italics, NO emojis, NO confidence dots. section labels are bare plain-text lines.
- all tables = fenced ``` code blocks with space-aligned fixed-width columns (these DO render on github mobile, unlike raw text). never markdown table syntax — table headers render bold.
- allowed ornaments: one ━ masthead rule, > quote rails, plain ✓/✗ data marks, ← in streak strips.
- goalie pairs abbreviated in display: s+s, s+t, b+s, t+t (log keeps full words).
- parlay legs carry pre-bet info: goalie confirmation line, season record for the confidence tier, computed risk line (what late news exits pick range) — user picked these three (declined the checklist option).
- team lines carry the named goalie's last-5 1p ga + season sv%.
- full spec in CLAUDE.md output rules; style snapshot at research/sample_analysis_v43.md. see [[project-v43-model]].
