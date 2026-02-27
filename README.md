# nhl 1p u2.5 betting model

systematic model for betting nhl 1st period under 2.5 goals. built around data, not gut feels.

## how it works

- fetches last 15 games for every team playing tonight via the nhl api
- computes weighted poisson probabilities, venue splits, h2h history, and league-wide base rates
- scores each game on a transparent 0-10 confidence scale
- only recommends picks at confidence >= 7
- tracks every pick, avoid, and honorable mention with actual results for ongoing optimization

## key files

- `picks_log.jsonl` — full pick history with results, avoids, and honorable mentions
- `nhl.md` — detailed workflow and methodology docs

## stack

- nhl api (`api-web.nhle.com`) — free, no auth
- dailyfaceoff — starting goalie confirmations
- python for data collection and poisson modeling
