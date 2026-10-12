import sys
import unittest
from pathlib import Path

from shapely.geometry import LineString

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools/v3"))
from awv_osm_crosswalk import CrosswalkIndex, classify_corridor


class CrosswalkTests(unittest.TestCase):
    # Research guardrails for systematic AWV/OSM lateral offsets.
    def test_constant_20m_offset_matches(self):
        osm = LineString([(0, 0), (100, 0)])
        awv = LineString([(0, 20), (100, 20)])
        index = CrosswalkIndex([(awv, 1001, "a")])
        road, info = index.match(osm)
        self.assertEqual(road, 1001)
        self.assertEqual(info["reason"], "matched")
        self.assertAlmostEqual(info["mean_distance_m"], 20.0, places=1)

    def test_constant_34m_offset_matches(self):
        osm = LineString([(0, 0), (100, 0)])
        awv = LineString([(0, 34), (100, 34)])
        road, info = CrosswalkIndex([(awv, 2002, "b")]).match(osm)
        self.assertEqual(road, 2002)
        self.assertAlmostEqual(info["mean_distance_m"], 34.0, places=1)

    def test_crossing_road_rejected_by_axis(self):
        osm = LineString([(0, 0), (100, 0)])
        awv = LineString([(50, -30), (50, 30)])
        road, info = CrosswalkIndex([(awv, 3003, "c")]).match(osm)
        self.assertIsNone(road)
        self.assertEqual(info["reason"], "no_persistent_candidate")

    def test_unstable_offset_rejected(self):
        osm = LineString([(0, 0), (100, 0)])
        awv = LineString([(0, 5), (100, 30)])
        road, info = CrosswalkIndex([(awv, 4004, "d")]).match(osm)
        self.assertIsNone(road)
        self.assertEqual(info["reason"], "offset_not_stable")

    def test_parallel_competitor_blocks(self):
        osm = LineString([(0, 0), (100, 0)])
        awv1 = LineString([(0, 20), (100, 20)])
        awv2 = LineString([(0, 23), (100, 23)])
        road, info = CrosswalkIndex([(awv1, 5005, "e"), (awv2, 6006, "f")]).match(osm)
        self.assertIsNone(road)
        self.assertEqual(info["reason"], "competing_road_ids")

    def test_clear_parallel_winner_allowed(self):
        osm = LineString([(0, 0), (100, 0)])
        awv1 = LineString([(0, 18), (100, 18)])
        awv2 = LineString([(0, 30), (100, 30)])
        road, info = CrosswalkIndex([(awv1, 7007, "g"), (awv2, 8008, "h")]).match(osm)
        self.assertEqual(road, 7007)
        self.assertEqual(info["reason"], "matched")


if __name__ == "__main__":
    unittest.main()


class CorridorTests(unittest.TestCase):
    def item(self, sid, road):
        return {"osm_segment_id": sid, "osm_way_id": sid * 10, "road_id": road, "start_xy": (0, 0), "end_xy": (1, 0), "info": {}}

    def test_two_segment_same_road_run_is_accepted(self):
        rows = classify_corridor([self.item(1, 100), self.item(2, 100)], min_run=2)
        self.assertTrue(rows[0]["corridor_accepted"])
        self.assertTrue(rows[1]["corridor_accepted"])

    def test_isolated_match_is_rejected(self):
        rows = classify_corridor([self.item(1, 100), self.item(2, None)], min_run=2)
        self.assertFalse(rows[0]["corridor_accepted"])
        self.assertEqual(rows[0]["corridor_reason"], "isolated_or_broken_run")

    def test_road_id_switch_breaks_corridor(self):
        rows = classify_corridor([self.item(1, 100), self.item(2, 200), self.item(3, 200)], min_run=2)
        self.assertFalse(rows[0]["corridor_accepted"])
        self.assertTrue(rows[1]["corridor_accepted"])
        self.assertTrue(rows[2]["corridor_accepted"])

    def test_unmatched_segment_breaks_run(self):
        rows = classify_corridor([self.item(1, 100), self.item(2, None), self.item(3, 100)], min_run=2)
        self.assertFalse(rows[0]["corridor_accepted"])
        self.assertFalse(rows[2]["corridor_accepted"])
