# nhl project memory

all rules live in CLAUDE.md (single source of truth). memory files below capture the "why" behind rules and project history.

## feedback
- [never rewrite deterministic code — use run_analysis.py, edit if needed](feedback_use_run_analysis.md)
- [goalie sourcing: external sources (dfo), not starts-share math](feedback_goalie_backup_detection.md)
- [table formatting: fixed-width padding, ft = full-game total](feedback_table_formatting.md)
- [postmortem: only flag genuine analytical errors as "misses"](feedback_postmortem_scope.md)
- [strip poisson from all output — noise, not signal](feedback_strip_poisson.md)
- [run /nhl early afternoon (1-3pm ET) for goalie confirmations](feedback_run_timing.md)
- [goalie always scores — never zero out for unconfirmed](feedback_goalie_always_scores.md)
- [no shortcuts — real money, correct data scope always](feedback_no_shortcuts.md)
- [goalie confirmation mandatory — fetch ALL sources](feedback_goalie_confirmation.md)
- [odds sources: ESPN API + Pinnacle for accurate 6.0 lines](reference_odds_sources.md)
- [track parlays/legs by model version separately](feedback_track_by_version.md)
- [season record: only show latest model version (v4)](feedback_latest_version_record.md)
- [analysis file: minimalist — no emojis/bolds/headings/dots, monospace blocks, github-mobile renderable](feedback_analysis_file_format.md)
- [never rewrite daily scripts from scratch](feedback_never_rewrite_scripts.md)
- [use prefetch pipeline for speed (~7 turns not 32)](feedback_use_prefetch_pipeline.md)
- [flag script errors immediately — never silently work around](feedback_flag_errors.md)
- [run review.py weekly + "what we learned" report](feedback_weekly_review.md)
- [playoff context + cautions displayed per game, never scored](feedback_playoff_context_display.md)
- [r5 carries late-reg-season dilution noise for early playoff picks (commentary caveat; r15 unscored since v4.3)](feedback_r5_playoff_noise.md)

## feedback (unlisted)
- [betting discipline — parlay sizing, bankroll](feedback_betting_discipline.md)

## user
- [user profile — betting strategy, preferences](user_betting_strategy.md)

## project
- [v4 model details — line factor, backtest, validation data](project_v4_model.md)
- [v4.1: backup+starter → +1, split from backup+tandem (77.4%)](project_v41_backup_split.md)
- [v4.3: r15 → day-game factor (<5pm et), point-in-time revalidation, corrected 18-5/41-5 record, next-season re-checks](project_v43_model.md)
- [v4.3.1: adaptivity release — model_params.json, 5-season pooled 78.2% pick tier, day factor + goalie ladder on watch, annual ritual, espn live-odds trap](project_v431_adaptivity.md)
- [playoff model research backlog — h2h tiebreak, series-state factor (do not implement without go-ahead)](project_playoff_model_research.md)
- [html mirror + pinned artifact url — build_html.py, mlb lessons, no-bold taste rules](project_html_mirror.md)
