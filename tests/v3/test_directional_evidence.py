"""Tests for research-only AWV travel-direction evidence."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/"tools/v3"))
from pyproj import Transformer
from research_directional_evidence import build_road_evidence,directional_summary

TO_WGS=Transformer.from_crs(31370,4326,always_xy=True)
X,Y=155000.0,190000.0

def feature(rid,prev,points,speed=50,sign="C43",zone=""):
    return {
        "type":"Feature","id":f"{rid}/{prev}/{speed}/{sign}",
        "geometry":{"type":"LineString","coordinates":[list(TO_WGS.transform(X+x,Y+y)) for x,y in points]},
        "properties":{"Wegsegment_ID":rid,"Vorige_wegsegment_ID":prev,
                      "Snelheid":speed,"Bepalend_bord":sign,"Zone":zone},
    }

def analyze(features, road=2, dx=100, dy=0):
    evidence=build_road_evidence({"features":features}).get(road,[])
    return directional_summary(evidence,dx,dy)

class DirectionTests(unittest.TestCase):
    def test_predecessor_proves_forward_only(self):
        rows=[
            feature(1,None,[(-50,0),(0,0)]),
            feature(2,1,[(0,0),(100,0)],50,"C43"),
        ]
        result=analyze(rows)
        self.assertEqual(result["forward"]["candidate_kmh"],50)
        self.assertEqual(result["backward"]["state"],"no_directed_evidence")

    def test_predecessor_proves_reversed_coordinates(self):
        rows=[
            feature(1,None,[(-50,0),(0,0)]),
            feature(2,1,[(100,0),(0,0)],50,"C43"),
        ]
        result=analyze(rows,dx=-100)
        self.assertEqual(result["forward"]["state"],"no_directed_evidence")
        self.assertEqual(result["backward"]["candidate_kmh"],50)

    def test_no_predecessor_does_not_infer_direction(self):
        result=analyze([feature(2,999,[(0,0),(100,0)],30,"F4a","SnelheidsZone")])
        self.assertEqual(result["forward"]["state"],"unresolved_direction_provenance")
        self.assertIsNone(result["forward"]["candidate_kmh"])

    def test_both_endpoints_touch_is_ambiguous(self):
        rows=[
            feature(1,None,[(0,0),(100,0)]),
            feature(2,1,[(0,0),(100,0)],30,"F4a","SnelheidsZone"),
        ]
        self.assertIsNone(analyze(rows)["forward"]["candidate_kmh"])

    def test_zone30_candidate_not_published(self):
        rows=[
            feature(1,None,[(-50,0),(0,0)]),
            feature(2,1,[(0,0),(100,0)],30,"F4a","SnelheidsZone"),
        ]
        self.assertEqual(analyze(rows)["forward"]["state"],"zone30_candidate")

    def test_builtup_context_does_not_create_numeric(self):
        rows=[
            feature(1,None,[(-50,0),(0,0)]),
            feature(2,1,[(0,0),(100,0)],50,"F1a"),
        ]
        self.assertEqual(analyze(rows)["forward"]["state"],"context_only_no_numeric")

    def test_perpendicular_candidate_not_ascribed_to_osm(self):
        rows=[
            feature(1,None,[(0,-50),(0,0)]),
            feature(2,1,[(0,0),(0,100)],30,"F4a","SnelheidsZone"),
        ]
        self.assertEqual(analyze(rows)["forward"]["state"],"no_directed_evidence")

if __name__=="__main__":
    unittest.main()
