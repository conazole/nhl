---
name: r5 factor carries late-regular-season noise in playoff picks
description: when picking playoff games, flag r5 as noisier than r15 — last-5 windows include end-of-reg-season games played under different motivations (rested starters, tanking, clinched seeds)
type: feedback
originSessionId: f02563ec-aadf-444f-9a1f-4da5993a34cf
---
the r5 factor (last 5 games, combined u2.5%) becomes less reliable for playoff picks because the window pulls in late-regular-season games with motivational noise — rested starters, tanking bottom-feeders, teams mathematically eliminated or already clinched.

**why:** v4 was backtested on 1149 regular-season games where every team's context was broadly consistent. it was never validated on "playoff games using end-of-reg-season r5 data." the underlying distribution shift isn't captured in any factor. the user raised this on apr 20 2026, the 2nd playoff slate, when r5 windows for playoff teams were mostly 4 late-reg + 1 playoff g1 (and g1 teams were entirely reg-season).

**how to apply:**
- deterministic model still stands — r5 is still in the formula and picks don't get overridden.
- but when r5 and r15 disagree on a playoff pick, weight r15 heavier in commentary/ice brief (r15 is more robust to motivational swings, larger sample).
- include this caveat in analysis commentary for playoff picks, especially for g1/g2 where the r5 window is mostly pre-playoff games.
- revalidation (v4.3 candidate): test whether r5 should be replaced with "last 5 meaningful games" (excluding games where either team was mathematically eliminated, tanking, or had clinched w/ nothing to play for). add to weekly review.py checklist.
- this fades over time — as a playoff run progresses, r5 rolls forward into playoff-only games. by r1 g5 most teams' r5 will be 4-5 playoff games. concern is highest in r1 g1-g3.
