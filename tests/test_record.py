"""record.py grading rules · real money rides on these.

the load-bearing rule (jul 2026, ported from the mlb 7-3 vs 6-4 audit): a
parlay night with a LOST leg is a LOSS on every surface, even when the other
leg voided (postponed) or is still pending. top-2 selection happens before
any result filtering so a void leg can never promote the 3rd qualifier."""
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from record import (compute_season_record, parlay_outcome_for_date,
                    pick_sort_key, tier_of)


def leg(game, conf, result=None, r5=80.0, date="2026-03-01", tier=None):
    e = {"date": date, "game": game, "pick": "1p u2.5", "confidence": conf,
         "combined_recent5_pct": r5, "combined_last15_pct": 80.0,
         "total_line": 5.5, "model": "v4"}
    if result is not None:
        e["result"] = result
    if tier:
        e["tier"] = tier
    return e


class TestParlayOutcome(unittest.TestCase):
    def test_both_win(self):
        out, _ = parlay_outcome_for_date([leg("a @ b", 5, "win"),
                                          leg("c @ d", 4, "win")])
        self.assertEqual(out, "win")

    def test_loss_plus_win(self):
        out, _ = parlay_outcome_for_date([leg("a @ b", 5, "loss"),
                                          leg("c @ d", 4, "win")])
        self.assertEqual(out, "loss")

    def test_loss_plus_void_is_loss(self):
        # a lost leg kills the ticket · the void leg must not drop the night
        out, _ = parlay_outcome_for_date([leg("a @ b", 5, "loss"),
                                          leg("c @ d", 4, "void")])
        self.assertEqual(out, "loss")

    def test_loss_plus_pending_is_loss(self):
        out, _ = parlay_outcome_for_date([leg("a @ b", 5, "loss"),
                                          leg("c @ d", 4, None)])
        self.assertEqual(out, "loss")

    def test_win_plus_void_is_void(self):
        # reduced ticket · excluded like all voids, never counted as a win
        out, _ = parlay_outcome_for_date([leg("a @ b", 5, "win"),
                                          leg("c @ d", 4, "void")])
        self.assertEqual(out, "void")

    def test_win_plus_pending_is_pending(self):
        out, _ = parlay_outcome_for_date([leg("a @ b", 5, "win"),
                                          leg("c @ d", 4, None)])
        self.assertEqual(out, "pending")

    def test_single_pick_no_parlay(self):
        out, _ = parlay_outcome_for_date([leg("a @ b", 5, "win")])
        self.assertEqual(out, "no_parlay")

    def test_void_leg_never_promotes_third_pick(self):
        # legacy 3-pick date: top-2 by sort key are the 5/6 and the (void)
        # 4/6-at-90 legs. the void must NOT promote the 4/6-at-70 into the
        # graded ticket (which would have read win+win).
        picks = [leg("a @ b", 5, "win"),
                 leg("c @ d", 4, "void", r5=90.0),
                 leg("e @ f", 4, "win", r5=70.0)]
        out, top2 = parlay_outcome_for_date(picks)
        self.assertEqual(out, "void")
        self.assertEqual({e["game"] for e in top2}, {"a @ b", "c @ d"})


class TestSeasonRecord(unittest.TestCase):
    def test_lost_leg_plus_void_night_counts_as_parlay_loss(self):
        entries = [leg("a @ b", 5, "loss", date="2026-03-01"),
                   leg("c @ d", 4, "void", date="2026-03-01")]
        r = compute_season_record(entries)
        self.assertEqual((r["parlay_w"], r["parlay_l"]), (0, 1))

    def test_win_plus_void_night_excluded(self):
        entries = [leg("a @ b", 5, "win", date="2026-03-01"),
                   leg("c @ d", 4, "void", date="2026-03-01")]
        r = compute_season_record(entries)
        self.assertEqual((r["parlay_w"], r["parlay_l"]), (0, 0))
        # the resolved winning leg still counts in the leg record
        self.assertEqual((r["leg_w"], r["leg_l"]), (1, 0))

    def test_pending_today_not_counted_yet(self):
        entries = [leg("a @ b", 5, None, date="2026-03-01"),
                   leg("c @ d", 4, None, date="2026-03-01")]
        r = compute_season_record(entries)
        self.assertEqual((r["parlay_w"], r["parlay_l"]), (0, 0))

    def test_normal_nights_unchanged(self):
        entries = [leg("a @ b", 5, "win", date="2026-03-01"),
                   leg("c @ d", 4, "win", date="2026-03-01"),
                   leg("e @ f", 5, "loss", date="2026-03-02"),
                   leg("g @ h", 4, "win", date="2026-03-02"),
                   leg("hm @ x", 3, "win", date="2026-03-02", tier="honorable_mention")]
        r = compute_season_record(entries)
        self.assertEqual((r["parlay_w"], r["parlay_l"]), (1, 1))
        self.assertEqual((r["leg_w"], r["leg_l"]), (3, 1))
        self.assertEqual((r["hm_w"], r["hm_l"]), (1, 0))


class TestSortKeyCompat(unittest.TestCase):
    def test_sort_key_accepts_log_and_engine_field_names(self):
        log_e = leg("a @ b", 5)
        eng_m = {"away": "A", "home": "B", "confidence": 5,
                 "comb_r5_pct": 80.0, "comb_r15_pct": 80.0}
        self.assertEqual(pick_sort_key(log_e)[:3], pick_sort_key(eng_m)[:3])

    def test_tier_of(self):
        self.assertEqual(tier_of(leg("a @ b", 5)), "pick")
        self.assertEqual(tier_of(leg("a @ b", 3, tier="honorable_mention")), "hm")
        self.assertEqual(tier_of(leg("a @ b", 1, tier="avoid")), "avoid")


class TestSeasonRankings(unittest.TestCase):
    """run_analysis.rank_teams · the season u2.5 ranking order rule."""

    def test_rate_desc_then_least_ga_pg_tiebreak(self):
        import run_analysis as RA
        stats = {
            "AAA": {"gp": 10, "u25": 8, "ga": 12},   # 80% · ga/gp 1.2
            "BBB": {"gp": 10, "u25": 8, "ga": 9},    # 80% · ga/gp 0.9 → wins tie
            "CCC": {"gp": 20, "u25": 18, "ga": 30},  # 90% → rank 1
            "DDD": {"gp": 10, "u25": 5, "ga": 5},    # 50% → last
            "EEE": {"gp": 0, "u25": 0, "ga": 0},     # no games → unranked
        }
        r = RA.rank_teams(stats)
        self.assertEqual(r["CCC"]["rank"], 1)
        self.assertEqual(r["BBB"]["rank"], 2)
        self.assertEqual(r["AAA"]["rank"], 3)
        self.assertEqual(r["DDD"]["rank"], 4)
        self.assertNotIn("EEE", r)
        self.assertEqual(r["BBB"]["u25_pct"], 80.0)
        self.assertEqual(r["BBB"]["ga_pg"], 0.9)

    def test_full_tie_deterministic_by_abbrev(self):
        import run_analysis as RA
        stats = {"ZZZ": {"gp": 4, "u25": 3, "ga": 4},
                 "AAA": {"gp": 4, "u25": 3, "ga": 4}}
        r = RA.rank_teams(stats)
        self.assertEqual(r["AAA"]["rank"], 1)
        self.assertEqual(r["ZZZ"]["rank"], 2)


if __name__ == "__main__":
    unittest.main()
