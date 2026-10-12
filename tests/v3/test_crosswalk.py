import sys
import unittest
from pathlib import Path

from shapely.geometry import LineString

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools/v3"))
from awv_osm_crosswalk import CrosswalkIndex, validate_topology


class CrosswalkTests(unittest.TestCase):
    def test_constant_20m_offset_matches(self):
        osm = LineString([(0, 0), (100, 0)])
        awv = LineString([(0, 20), (100, 20)])
        road, info = CrosswalkIndex([(awv, 1001, "a")]).match(osm)
        self.assertEqual(road, 1001)
        self.assertEqual(info["reason"], "matched")

    def test_constant_34m_offset_matches(self):
        osm = LineString([(0, 0), (100, 0)])
        awv = LineString([(0, 34), (100, 34)])
        road, info = CrosswalkIndex([(awv, 2002, "b")]).match(osm)
        self.assertEqual(road, 2002)

    def test_crossing_road_rejected_by_axis(self):
        osm = LineString([(0, 0), (100, 0)])
        awv = LineString([(50, -30), (50, 30)])
        road, info = CrosswalkIndex([(awv, 3003, "c")]).match(osm)
        self.assertIsNone(road)

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


class TopologyTests(unittest.TestCase):
    def row(self, sid, way, name, road, a, b):
        return {"osm_segment_id":sid,"osm_way_id":way,"name":name,"road_id":road,"start_xy":a,"end_xy":b,"info":{}}

    def test_connected_same_way_same_name_is_accepted(self):
        rows=[
            self.row(1,10,"Nieuwstraat",100,(0,0),(20,0)),
            self.row(2,10,"Nieuwstraat",100,(20,0),(40,0)),
        ]
        accepted, diag=validate_topology(rows)
        self.assertEqual(accepted,{1,2})
        self.assertTrue(diag[1]["topology_accepted"])

    def test_single_side_street_is_rejected(self):
        rows=[self.row(1,20,"Lodewijk Dosfelstraat",200,(0,0),(40,0))]
        accepted, diag=validate_topology(rows)
        self.assertEqual(accepted,set())
        self.assertFalse(diag[1]["topology_accepted"])

    def test_different_osm_way_is_not_combined(self):
        rows=[
            self.row(1,10,"Kerkstraat",100,(0,0),(20,0)),
            self.row(2,11,"Kerkstraat",100,(20,0),(40,0)),
        ]
        accepted,_=validate_topology(rows)
        self.assertEqual(accepted,set())

    def test_different_name_is_not_combined(self):
        rows=[
            self.row(1,10,"Gentsesteenweg",100,(0,0),(20,0)),
            self.row(2,10,"Kerkstraat",100,(20,0),(40,0)),
        ]
        accepted,_=validate_topology(rows)
        self.assertEqual(accepted,set())

    def test_disconnected_same_way_is_rejected(self):
        rows=[
            self.row(1,10,"Nieuwstraat",100,(0,0),(20,0)),
            self.row(2,10,"Nieuwstraat",100,(50,0),(70,0)),
        ]
        accepted,_=validate_topology(rows)
        self.assertEqual(accepted,set())

    def test_short_connected_component_is_rejected(self):
        rows=[
            self.row(1,10,"Nieuwstraat",100,(0,0),(5,0)),
            self.row(2,10,"Nieuwstraat",100,(5,0),(10,0)),
        ]
        accepted,_=validate_topology(rows)
        self.assertEqual(accepted,set())


if __name__ == "__main__":
    unittest.main()
