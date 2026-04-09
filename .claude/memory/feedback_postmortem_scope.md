---
name: postmortem scope
description: post-mortem "what we missed" should only cover actual mistakes, not honorable mentions going under
type: feedback
---

don't frame honorable mentions going under as something we "missed" in the post-mortem. we're strictly doing 2-leg parlays — other games going under is just the base rate (~72%). so long as the parlay hits, there's no issue.

**Why:** the user pointed out this is flawed reasoning. the model's job is to pick the best 2 legs, not every game that might go under. complaining about HMs going under implies we should be adding more legs, which contradicts the 2-leg discipline.

**How to apply:** in the post-mortem "what we missed" section, only include genuine analytical errors — things like: a pick that lost and we should have seen warning signs, or a pattern the model failed to account for. never list HMs going under as a "miss." the one exception: if parlays are consistently losing while HMs are consistently winning, that IS a problem — it means the model's confidence ranking is inverted and picking worse games over better ones. flag that pattern if it emerges.
