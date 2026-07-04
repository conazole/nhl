#!/usr/bin/env python3
"""self-fencing maintenance gate · runs due health checks inside /nhl runs.

usage:
    python3 maintenance.py 2026-10-14                # normal (step 1 of /nhl)
    python3 maintenance.py 2026-10-14 --force-weekly
    python3 maintenance.py 2026-10-14 --force-annual
    python3 maintenance.py 2026-10-14 --dry-run      # report due-ness, run nothing

why this exists: the weekly reviews (review.py, research/revalidate.py,
season_review.py) and the annual ritual only matter if they actually run,
and there is no cron. this script keeps a machine-written state file
(maintenance_state.json · never hand-edit) and, on every /nhl run:

  - weekly: if 7+ days since the last weekly sweep, runs the trio and
    stamps the state. full output streams to stderr; stdout gets a compact
    json summary with any drift alerts for the agent to surface in the
    analysis.
  - annual: if this is the first run of a NEW season (september boundary),
    runs the full annual ritual (build finished season → validate prior →
    drift_lab → backtest_variants → emit_params → season_review), saves the
    research output to research/annual_ritual_{season}.txt, and stamps the
    state. a failed step leaves the state unstamped so the ritual refires
    on the next run instead of vanishing.

the gate runs things and reports · it never changes model policy. drift
flags remain research prompts for a human.
"""

import json, os, sys, argparse, subprocess
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
STATE_PATH = os.path.join(HERE, "maintenance_state.json")
WEEKLY_EVERY_DAYS = 7


def season_of(date_str):
    """season start-year · sep+ = this year (2026-27 opens late september)."""
    dt = datetime.strptime(date_str, "%Y-%m-%d")
    return dt.year if dt.month >= 9 else dt.year - 1


def read_state():
    try:
        with open(STATE_PATH) as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}


def write_state(state):
    with open(STATE_PATH, "w") as f:
        json.dump(state, f, indent=2)
        f.write("\n")


def run_step(label, cmd, timeout, capture_to=None, extra_note=""):
    """run one subprocess. streams stdout to stderr (and optionally a file).
    returns (ok, exit_code, captured_text)."""
    print(f"── maintenance: {label} ──{extra_note}", file=sys.stderr, flush=True)
    try:
        proc = subprocess.run(cmd, cwd=HERE, timeout=timeout,
                              capture_output=True, text=True)
    except subprocess.TimeoutExpired:
        print(f"   TIMEOUT after {timeout}s", file=sys.stderr)
        return False, -1, ""
    text = (proc.stdout or "") + (("\n" + proc.stderr) if proc.stderr else "")
    print(proc.stdout or "", file=sys.stderr)
    if proc.stderr:
        print(proc.stderr, file=sys.stderr)
    if capture_to:
        with open(capture_to, "a") as f:
            f.write(f"\n{'=' * 60}\n{label}\n{'=' * 60}\n{text}\n")
    return proc.returncode == 0, proc.returncode, text


def weekly_due(state, target_date):
    last = state.get("last_weekly")
    if not last:
        return True
    gap = (datetime.strptime(target_date, "%Y-%m-%d")
           - datetime.strptime(last, "%Y-%m-%d")).days
    return gap >= WEEKLY_EVERY_DAYS


def run_weekly(target_date, summary):
    season_start = f"{season_of(target_date)}-09-01"
    results = {}
    ok1, _, _ = run_step("weekly 1/3 · review.py --last 14",
                         [sys.executable, "review.py", "--last", "14"], 300)
    results["review"] = "ok" if ok1 else "failed"
    ok2, code2, text2 = run_step("weekly 2/3 · research/revalidate.py",
                                 [sys.executable, "research/revalidate.py"], 300)
    # revalidate exits 1 on drift, 2 on thin data · both are reports, not failures
    alerts = [ln.strip(" -") for ln in text2.splitlines()
              if ln.strip().startswith("- ") and "drift" in ln]
    results["revalidate"] = {"exit": code2,
                             "drift_alerts": alerts,
                             "note": ("drift alert · read before betting" if code2 == 1
                                      else ("thin data" if code2 == 2 else "stable"))}
    ok3, _, _ = run_step("weekly 3/3 · season_review.py",
                         [sys.executable, "season_review.py",
                          "--since", season_start], 300)
    results["season_review"] = "ok" if ok3 else "failed"
    summary["weekly"] = {"ran": True, "results": results}
    # a drift EXIT is still a successful sweep · only a crashed script
    # (review/season_review nonzero) blocks the stamp so it retries next run
    return ok1 and ok3 and code2 in (0, 1, 2)


def run_annual(target_date, summary):
    season = season_of(target_date)
    finished = season - 1
    prior = season - 2
    out = os.path.join(HERE, "research", f"annual_ritual_{season}.txt")
    if os.path.exists(out):
        os.remove(out)
    with open(out, "w") as f:
        f.write(f"annual ritual · run {target_date} for the {season}-{str(season + 1)[2:]} "
                f"season · builds season {finished}\n")
    steps = [
        (f"annual 1/6 · build_dataset --season {finished}",
         [sys.executable, "research/build_dataset.py", "--season", str(finished)], 3600),
        (f"annual 2/6 · build_dataset --season {prior} --validate",
         [sys.executable, "research/build_dataset.py", "--season", str(prior),
          "--validate"], 3600),
        ("annual 3/6 · drift_lab",
         [sys.executable, "research/drift_lab.py"], 600),
        ("annual 4/6 · backtest_variants",
         [sys.executable, "research/backtest_variants.py"], 600),
        ("annual 5/6 · emit_params",
         [sys.executable, "research/emit_params.py"], 600),
        ("annual 6/6 · season_review",
         [sys.executable, "season_review.py", "--since", f"{finished}-09-01"], 300),
    ]
    all_ok = True
    for label, cmd, timeout in steps:
        ok, code, _ = run_step(label, cmd, timeout, capture_to=out)
        # validate exits 1 on mismatch · that is a real failure to investigate
        if not ok and not (label.startswith("annual 6") and code == 2):
            all_ok = False
            print(f"   step failed (exit {code}) · ritual NOT stamped, will "
                  f"refire next run · investigate before betting", file=sys.stderr)
            break
    summary["annual"] = {
        "ran": True, "season": season, "output": out, "complete": all_ok,
        "note": ("read the drift flags + model_params.json watch list before "
                 "the first bet of the season · a flag is a research prompt, "
                 "not a switch" if all_ok else
                 "RITUAL INCOMPLETE · do not bet until it passes"),
    }
    return all_ok


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("target_date", help="YYYY-MM-DD (the /nhl run date)")
    parser.add_argument("--force-weekly", action="store_true")
    parser.add_argument("--force-annual", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    state = read_state()
    season = season_of(args.target_date)
    w_due = args.force_weekly or weekly_due(state, args.target_date)
    a_due = args.force_annual or season > state.get("last_annual_season", 0)

    summary = {
        "target_date": args.target_date,
        "weekly": {"ran": False, "due": w_due,
                   "last": state.get("last_weekly")},
        "annual": {"ran": False, "due": a_due,
                   "last_season": state.get("last_annual_season")},
    }

    if args.dry_run:
        print(json.dumps(summary))
        return

    # annual first · a new season's params should exist before the weekly
    # sweep measures against them
    if a_due:
        if run_annual(args.target_date, summary):
            state["last_annual_season"] = season
            write_state(state)
    if w_due:
        if run_weekly(args.target_date, summary):
            state["last_weekly"] = args.target_date
            write_state(state)

    print(json.dumps(summary))


if __name__ == "__main__":
    main()
