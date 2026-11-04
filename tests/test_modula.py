"""Run with: py -m unittest discover tests"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "eval"))

from modula.catalogue import DIMS, GRID_COLS, GRID_ROWS, MODULE_BY_ID
from modula.engine import cheapest_possible, config_vector, recommend
from modula.keyword_parser import found_nothing, keyword_parse, parse_budget
from modula.prompts import parse_model_reply
from score import evaluate


def need(**values):
    return {d: values.get(d, 0.1) for d in DIMS}


def ids(build):
    return [m.id for m in build.mods]


class EngineTests(unittest.TestCase):
    def test_builds_fit_the_frame_without_overlaps(self):
        for n in (need(camera=1, storage=0.9), need(performance=1), need(durability=1, battery=1)):
            for build in recommend(n)[0]:
                seen = set()
                for p in build.placed:
                    for y in range(p.y, p.y + p.h):
                        for x in range(p.x, p.x + p.w):
                            self.assertTrue(x < GRID_COLS and y < GRID_ROWS)
                            self.assertNotIn((x, y), seen)
                            seen.add((x, y))

    def test_budget_is_a_hard_limit(self):
        for build in recommend(need(camera=1, performance=1), budget=40000)[0]:
            self.assertLessEqual(build.config.price, 40000)

    def test_must_have_modules_are_included(self):
        for build in recommend(need(camera=1), must_have=("net-sat", "sen-health"))[0]:
            self.assertIn("net-sat", ids(build))
            self.assertIn("sen-health", ids(build))

    def test_gaming_soc_never_ships_without_cooling(self):
        for build in recommend(need(performance=1))[0]:
            if "c-game" in ids(build):
                self.assertIn("cool-vc", ids(build))

    def test_cameras_sit_in_the_top_rows(self):
        for build in recommend(need(camera=1))[0]:
            for p in build.placed:
                if p.mod.cat == "camera":
                    self.assertLessEqual(p.y + p.h, 2)

    def test_priorities_change_the_phone(self):
        photographer = recommend(need(camera=1))[0][0]
        gamer = recommend(need(performance=1))[0][0]
        self.assertGreater(photographer.config.vec["camera"], gamer.config.vec["camera"])
        self.assertGreater(gamer.config.vec["performance"], photographer.config.vec["performance"])

    def test_bigger_battery_adds_endurance_and_weight(self):
        base = [MODULE_BY_ID["c-bal"], MODULE_BY_ID["cam-50"]]
        small = config_vector([*base, MODULE_BY_ID["b-3000"]])
        big = config_vector([*base, MODULE_BY_ID["b-8000"]])
        self.assertGreater(big.vec["battery"], small.vec["battery"])
        self.assertLess(big.vec["portability"], small.vec["portability"])

    def test_impossible_budget_returns_nothing(self):
        self.assertEqual(recommend(need(camera=1), budget=5000)[0], [])

    def test_cheapest_phone_is_achievable(self):
        self.assertTrue(recommend(need(battery=0.5), budget=cheapest_possible())[0])


class ParsingTests(unittest.TestCase):
    def test_keyword_parser_says_when_it_found_nothing(self):
        self.assertTrue(found_nothing(keyword_parse("I fix wind turbines and climb towers in storms.")))
        self.assertFalse(found_nothing(keyword_parse("I shoot videos and need storage.")))
        self.assertFalse(found_nothing(keyword_parse("Phone garam nahi hona chahiye.")))

    def test_reply_in_code_fences_is_usable_but_not_clean(self):
        parsed = parse_model_reply('```json\n{"needs": {"camera": 0.9}, "budget": 60000, "must_have": []}\n```')
        self.assertTrue(parsed.ok)
        self.assertFalse(parsed.strict)
        self.assertEqual(parsed.budget, 60000)

    def test_unusable_reply_is_rejected(self):
        self.assertFalse(parse_model_reply("I can't help with that").ok)

    def test_unknown_module_ids_are_dropped(self):
        parsed = parse_model_reply('{"needs": {}, "must_have": ["net-sat", "warp-drive"]}')
        self.assertEqual(parsed.must_have, ["net-sat"])

    def test_indian_number_forms(self):
        self.assertEqual(parse_budget("budget 50 hazaar"), 50000)
        self.assertEqual(parse_budget("₹1,00,000 budget"), 100000)
        self.assertEqual(parse_budget("1.2 lakh is fine"), 120000)


class ReportedResultsTests(unittest.TestCase):
    """The numbers on the Results slide must come out of this code and these replies."""

    def test_held_out_results(self):
        summary, _ = evaluate("test")
        expected = {"fixed": (0.506, 7), "keyword": (0.743, 0), "v1": (0.638, 3), "v2": (0.768, 2), "v3": (0.760, 0)}
        for method, (fit, failed) in expected.items():
            self.assertAlmostEqual(summary[method]["fit"], fit, places=3, msg=method)
            self.assertEqual(summary[method]["failed_builds"], failed, method)
        self.assertEqual(round(summary["v3"]["must_recall"], 2), 1.0)
        self.assertEqual(round(summary["v3"]["must_precision"], 2), 0.89)
        self.assertEqual(round(summary["v2"]["must_recall"], 2), 0.12)
        self.assertEqual(round(summary["v1"]["strict_json"], 2), 0.19)


if __name__ == "__main__":
    unittest.main()
