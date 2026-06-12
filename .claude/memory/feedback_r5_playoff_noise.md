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
- update (jun 12 2026, [[project-v43-model]]): r15 is no longer SCORED (failed holdout validation), so "weight r15 heavier" now applies only to postmortem/commentary framing, not to any score. the r5 late-reg-season dilution caution itself remains valid for early playoff rounds.
- include this caveat in analysis commentary for playoff picks, especially g1/g2 where the r5 window is mostly pre-playoff games (g1 is also hard-capped at 3/6 by v4.2).
- open research item: test "last 5 meaningful games" (excluding eliminated/tanking/clinched-idle opponents) as an r5 variant on the point-in-time dataset (research/build_dataset.py) before next season.
- this fades over time — by r1 g5 most teams' r5 is playoff-only games. concern is highest in r1 g1-g3.
