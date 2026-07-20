"""build_html: the html mirror is a betting surface · the components must
never mangle, invent, or silently drop report content, and every record
surface must grade a lost-leg-plus-void night as a loss."""
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import build_html as BH


def matchup(away, home, conf, r5=80.0, line=5.5, **kw):
    m = {"away": away, "home": home, "confidence": conf,
         "comb_r5_pct": r5, "comb_r15_pct": 80.0, "comb_r5": 8, "comb_r5_n": 10,
         "comb_r15": 24, "comb_r15_n": 30, "total_line": line,
         "start_utc": "2026-04-04T23:00:00Z",
         "factors": {"r5": 2, "day": 0, "goalie": 2, "line": 1,
                     "goalie_pair": "starter+starter"},
         "aw_goalie": "gibson", "hm_goalie": "shesterkin",
         "aw_goalie_cls": "starter", "hm_goalie_cls": "starter",
         "aw_confirmed": True, "hm_confirmed": False,
         "h2h": [], "b2b_teams": [], "is_playoff": False, "info": {}}
    m.update(kw)
    return m


def log_entry(game, tier=None, date="2026-04-04", result=None, conf=5):
    e = {"date": date, "game": game, "pick": "1p u2.5", "confidence": conf,
         "combined_recent5_pct": 80.0, "combined_last15_pct": 80.0,
         "total_line": 5.5, "model": "v4"}
    if tier:
        e["tier"] = tier
    if result:
        e["result"] = result
    return e


class TestAtoms(unittest.TestCase):
    def test_game_anchor_slug(self):
        self.assertEqual(BH.game_anchor("det @ nyr"), "game-det-nyr")
        self.assertEqual(BH.game_anchor(None), "game-")

    def test_conf_meter_shows_cap_ghosts(self):
        out = BH.conf_meter(3, uncapped=5)
        self.assertEqual(out.count('seg on'), 3)
        self.assertEqual(out.count('seg cap'), 2)
        self.assertIn('confidence 3 of 6', out)

    def test_short_time_drops_tz_tag(self):
        self.assertEqual(BH.short_time("2026-04-04T23:00:00Z"), "7:00p")
        self.assertEqual(BH.short_time("2026-04-04T17:30:00Z"), "1:30p")

    def test_factor_chips_signed_and_r15_excluded(self):
        out = BH.factor_chips({"r5": 2, "day": 1, "goalie": -1, "line": 0,
                               "r15": 1})
        self.assertIn("r5 +2", out)
        self.assertIn("goalie -1", out)
        self.assertIn('fchip neg', out)
        self.assertNotIn("r15", out)


class TestMdFallback(unittest.TestCase):
    def test_unknown_content_never_dropped(self):
        out = BH.md_to_html("some future block the parser has never seen")
        self.assertIn("some future block", out)

    def test_fence_rail_list_escape(self):
        out = BH.md_to_html("```\na <b> c\n```\n> rail line\n- item one")
        self.assertIn("a &lt;b&gt; c", out)
        self.assertIn('<div class="rail">rail line</div>', out)
        self.assertIn("<li>item one</li>", out)


class TestTicketLock(unittest.TestCase):
    def test_logged_tiers_win_over_engine(self):
        # engine would pick a@b + c@d (5,4). the log says c@d + e@f were bet.
        ms = [matchup("A", "B", 5), matchup("C", "D", 4), matchup("E", "F", 4)]
        entries = [log_entry("a @ b", tier="honorable_mention"),
                   log_entry("c @ d"), log_entry("e @ f")]
        tiers = BH.tier_map(ms, entries, "2026-04-04")
        self.assertEqual(tiers["a @ b"], "hm")
        self.assertEqual(tiers["c @ d"], "pick")
        self.assertEqual(tiers["e @ f"], "pick")

    def test_mock_skips_log(self):
        ms = [matchup("A", "B", 5), matchup("C", "D", 4)]
        entries = [log_entry("a @ b", tier="honorable_mention"),
                   log_entry("c @ d")]
        tiers = BH.tier_map(ms, entries, "2026-04-04", use_log=False)
        self.assertEqual(tiers["a @ b"], "pick")

    def test_engine_fallback_demotes_third_and_solo(self):
        ms = [matchup("A", "B", 5), matchup("C", "D", 4),
              matchup("E", "F", 4, r5=70.0), matchup("G", "H", 1)]
        tiers = BH.tier_map(ms, [], "2026-04-04")
        self.assertEqual(tiers["a @ b"], "pick")
        self.assertEqual(tiers["c @ d"], "pick")
        self.assertEqual(tiers["e @ f"], "hm")     # 3rd qualifier demoted
        self.assertEqual(tiers["g @ h"], "avoid")
        solo = BH.tier_map([matchup("A", "B", 5)], [], "2026-04-04")
        self.assertEqual(solo["a @ b"], "hm")      # solo qualifier → hm


class TestRecordSurfaces(unittest.TestCase):
    def test_masthead_and_ledger_grade_lost_plus_void_as_loss(self):
        entries = [log_entry("a @ b", result="loss", date="2026-03-01"),
                   log_entry("c @ d", result="void", date="2026-03-01"),
                   log_entry("e @ f", result="win", date="2026-03-02"),
                   log_entry("g @ h", result="win", date="2026-03-02")]
        nights = BH.parlay_nights(entries)
        self.assertEqual([(d, o) for d, o, _ in nights],
                         [("2026-03-01", "loss"), ("2026-03-02", "win")])
        import record as R
        rec = R.compute_season_record(entries)
        self.assertEqual((rec["parlay_w"], rec["parlay_l"]), (1, 1))
        html = BH.build_masthead(0, rec, nights)
        self.assertIn("1-1", html)                 # parlays cell
        self.assertIn('lamp l', html)              # loss lamp lit
        season = BH.build_season(rec, nights)
        self.assertIn('pill loss', season)

    def test_pending_night_shows_pending_not_dropped(self):
        entries = [log_entry("a @ b", result="win", date="2026-03-01"),
                   log_entry("c @ d", date="2026-03-01")]
        nights = BH.parlay_nights(entries)
        self.assertEqual(nights[0][1], "pending")


class TestPage(unittest.TestCase):
    def _engine(self, matchups):
        teams = {}
        for m in matchups:
            for t in (m["away"], m["home"]):
                teams[t] = {"games": [], "goalie_labels": [],
                            "goalie_per_game": [], "r5_u25": 4, "r15_u25": 12,
                            "venue_u25": 5, "venue_total": 7, "wavg_gf": 0.8,
                            "sys_class": "structured", "tonight_ha": "h"}
        return {"target_date": "2026-04-04", "model_version": "v4.3.1",
                "base_rate": 72.3, "league_total": 300,
                "teams": teams, "matchups": matchups}

    def test_page_has_slip_deeplinks_and_no_bold(self):
        data = self._engine([matchup("A", "B", 5), matchup("C", "D", 4)])
        page = BH.build_page("2026-04-04", data, {}, [], mock=True)
        self.assertIn('<a class="leg" href="#game-a-b">', page)
        self.assertIn('id="game-a-b"', page)
        self.assertIn('name="game-acc"', page)     # exclusive accordion
        self.assertIn("<title>nhl 1p board</title>", page)
        # no bold anywhere · regular weight is a user requirement
        self.assertNotIn("font-weight:6", page)
        self.assertNotIn("font-weight:7", page)
        self.assertNotIn("font-weight:8", page)
        self.assertNotIn("<b>", page)
        # viewport injected at runtime for the artifact wrapper
        self.assertIn('m.name="viewport"', page)
        # display shorthand: no year prefixes survive
        self.assertNotIn("2026-", page)
        # the meter is the only confidence carrier · no "n/6" text anywhere
        # (user 2026-07-20); the aria-label says "n of 6" instead
        self.assertNotRegex(page, r"\d/6")

    def test_no_games_day_renders(self):
        data = {"error": "no games found", "target_date": "2026-06-12"}
        page = BH.build_page("2026-06-12", data, {"postmortem": "season over."},
                             [], mock=True)
        self.assertIn("no play tonight · 0 games scheduled", page)
        self.assertIn("season over.", page)

    def test_content_lowercase(self):
        data = self._engine([matchup("A", "B", 5), matchup("C", "D", 4)])
        page = BH.build_page("2026-04-04", data, {}, [], mock=True)
        for token in ("a @ b", ">u2.5<", "parlays", "legs"):
            self.assertIn(token, page)
        self.assertNotIn("A @ B", page)


class TestFreshnessGate(unittest.TestCase):
    def test_stale_engine_json_refused(self):
        import json, subprocess, tempfile
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            json.dump({"target_date": "2026-04-03", "matchups": [],
                       "teams": {}}, f)
            path = f.name
        p = subprocess.run([sys.executable, os.path.join(ROOT, "build_html.py"),
                            "2026-04-04", path, "--out", "/dev/null"],
                           capture_output=True, text=True)
        os.unlink(path)
        self.assertNotEqual(p.returncode, 0)
        self.assertIn("stale artifact", p.stderr + p.stdout)




class TestRankChips(unittest.TestCase):
    def test_summary_title_carries_ranks_with_record_tip(self):
        rankings = {"BUF": {"rank": 5, "gp": 15, "u25": 12, "ga_pg": 0.667},
                    "WSH": {"rank": 30, "gp": 15, "u25": 9, "ga_pg": 1.2}}
        m = matchup("BUF", "WSH", 1)
        out = BH.title_html(m, rankings)
        self.assertIn("#5", out)
        self.assertIn("#30", out)
        # the chip's u2.5 record rides in data-tip (hover/tap · user 2026-07-20)
        self.assertIn('data-tip="u2.5 12/15 · ga 0.67/gp"', out)
        self.assertIn('data-tip="u2.5 9/15 · ga 1.2/gp"', out)

    def test_missing_rankings_degrade_gracefully(self):
        m = matchup("BUF", "WSH", 1)
        self.assertEqual(BH.title_html(m, None), "buf @ wsh")
        # rank without stats → chip renders, no tip
        out = BH.title_html(m, {"BUF": {"rank": 5}})
        self.assertIn("#5", out)
        self.assertNotIn("data-tip", out)


class TestDisplayTags(unittest.TestCase):
    def test_day_tag_dropped_others_kept(self):
        m = matchup("BUF", "WSH", 1, is_day_game=True, line_missing=True)
        tags = BH.display_tags(m)
        self.assertNotIn("day", tags)
        self.assertIn("no line", tags)
        page_m = matchup("BUF", "WSH", 1, is_day_game=True)
        self.assertEqual(BH.display_tags(page_m), [])


if __name__ == "__main__":
    unittest.main()
