"""Pure synthetic safeguards for read-only directional ride regression audit."""
import json
import sqlite3
import sys
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/"tools/v3"))
from evaluate_ride_regressions import angular_error, candidates, evaluate

def anchor(bearing=90,level="official_directional",expected=50):
    return dict(id="test",date="2026-10-13",lat=51.0,lon=4.0,
                bearing_deg=bearing,evidence_level=level,expected_kmh=expected)

def db_with_roads(roads):
    db=sqlite3.connect(":memory:")
    db.executescript("""
      CREATE TABLE segments(id INTEGER PRIMARY KEY,name TEXT,lat1 REAL,lon1 REAL,
        lat2 REAL,lon2 REAL,forward_kmh INTEGER,backward_kmh INTEGER,oneway INTEGER);
      CREATE TABLE segment_quality(segment_id INTEGER PRIMARY KEY,
        forward_state INTEGER,backward_state INTEGER);
    """)
    for sid,lon_off,fw,bw,fs,bs,oneway in roads:
        db.execute("INSERT INTO segments VALUES (?,?,?,?,?,?,?,?,?)",
                   (sid,"Demo",51.0,4.0+lon_off,51.0,4.001+lon_off,fw,bw,oneway))
        db.execute("INSERT INTO segment_quality VALUES (?,?,?)",(sid,fs,bs))
    return db

class RegressionAuditTests(unittest.TestCase):
    def test_bearing_wraparound(self):
        self.assertEqual(angular_error(359,1),2)
        self.assertEqual(angular_error(10,190),180)

    def test_direction_is_not_assumed_symmetric(self):
        db=db_with_roads([(1,0,50,70,3,2,0)])
        east=anchor(90)
        west=anchor(270,expected=70)
        self.assertEqual(evaluate(db,east)["status"],"matches_verified_reference")
        self.assertEqual(evaluate(db,west)["status"],"matches_verified_reference")
        self.assertEqual(candidates(db,east)[0]["direction"],"forward")
        self.assertEqual(candidates(db,west)[0]["direction"],"backward")

    def test_wrong_confident_limit_is_regression(self):
        db=db_with_roads([(1,0,70,70,2,2,0)])
        self.assertEqual(evaluate(db,anchor())["status"],"verified_regression")

    def test_uncertainty_is_not_reported_as_false_limit(self):
        db=db_with_roads([(1,0,0,70,10,2,0)])
        self.assertEqual(evaluate(db,anchor())["status"],"uncertain_safe")

    def test_parallel_conflict_is_inconclusive(self):
        db=db_with_roads([(1,0,50,70,2,2,0),(2,0.00001,70,70,2,2,0)])
        self.assertEqual(evaluate(db,anchor())["status"],"ambiguous_candidates_unresolved")

    def test_rider_observation_is_not_certified_truth(self):
        db=db_with_roads([(1,0,90,90,1,1,0)])
        self.assertEqual(evaluate(db,anchor(level="rider_observation"))["status"],"rider_discrepancy_unverified")

    def test_date_gates_do_not_use_expired_restrictions(self):
        db=db_with_roads([(1,0,70,70,2,2,0)])
        a=anchor()
        a["valid_from"]="2026-10-14"
        self.assertEqual(evaluate(db,a)["status"],"evidence_not_yet_valid")
        del a["valid_from"]
        a["valid_until"]="2026-10-12"
        self.assertEqual(evaluate(db,a)["status"],"evidence_expired")

    def test_oneway_reverse_rejected(self):
        db=db_with_roads([(1,0,50,70,2,2,1)])
        self.assertEqual(evaluate(db,anchor(270))["status"],"not_covered_or_no_directional_match")

    def test_fixture_is_research_only_and_directional(self):
        path=Path(__file__).resolve().parent/"fixtures"/"ride-regressions-20261013.json"
        data=json.loads(path.read_text(encoding="utf-8"))
        self.assertGreaterEqual(len(data["anchors"]),3)
        for row in data["anchors"]:
            self.assertIn(row["evidence_level"],("official_directional","rider_observation","unverified"))
            self.assertIn("bearing_deg",row)
            self.assertIn("date",row)
        bridge=next(x for x in data["anchors"] if x["id"]=="ooiebrug-dendermonde-to-appels")
        self.assertEqual((bridge["app_reported_kmh"],bridge["expected_kmh"]),(70,50))
        self.assertTrue(bridge["reference_url"].startswith("https://wegenenverkeer.be/"))

if __name__=="__main__":
    unittest.main()
