---
name: html-mirror-artifact
description: build_html.py html mirror + pinned claude.ai artifact url — the taste rules and mlb lessons behind it
metadata: 
  node_type: memory
  type: project
  originSessionId: 95f506ec-b2b0-4acb-8d4a-cfc1761de2c0
  modified: 2026-07-20T22:08:43.687Z
---

the daily report ships as a clickable html mirror (build_html.py, jul 20 2026), republished every run to ONE pinned claude.ai artifact url (in CLAUDE.md step 5 · never mint a new one). ported from the mlb repo's 2026-07-19/20 feature; the mechanics live in CLAUDE.md's "html mirror" section.

**why (context not in the repo):**
- the user's phone view: github mobile renders html as raw source and repos are private, so the artifact is the only mobile path.
- mlb lessons baked in, learned the hard way there: viewport meta must be injected into the real head at runtime (body-level meta ignored → tiny fonts); the artifact wrapper swallows ALL hash navigation (every in-page anchor needs a programmatic handler); a "skip unsettled days" record rule duplicated in three places silently flattered mlb's record (7-3 vs 6-4) → nhl centralizes grading in record.parlay_outcome_for_date with tests.
- taste (non-negotiable, stated jul 20 2026): all lowercase, NO bold anywhere (regular weight, even titles), no redundant chrome/legends/glossaries, terse labels without articles, display shorthand page-wide, single-line rows scroll sideways instead of wrapping, decoration only when it carries data.
- design identity is "the rink" (ice blues, center-line red divider, goal lamps) · deliberately NOT mlb's green scoreboard skin. themes are token-driven; [[v431-adaptivity]] era model.

**how to apply:** any change to the html goes through build_html.py + tests; a wrong number means fix the generator, never the html. republish always passes the pinned url.

**interaction taste (jul 20 2026):** the user loved the rank-chip hover/tap record reveal ("did not even think of that") · prefer data-on-demand (tap to reveal detail) over printing more numbers inline. rows stay quiet; depth lives one tap away. confidence: meter on the ticket slip only, bare numbers elsewhere; no day tag (start time carries it); rankings are last-15 form, not season-long.
