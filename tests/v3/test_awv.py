import json
import io
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/"tools/v3"))
from build_belgium_db import awv_eligible
from enrich_awv import AwvIndex, TO_LOCAL, enrich
from download_awv import download
from pyproj import Transformer
from shapely.geometry import Point

LOCAL_TO_AWV=Transformer.from_crs(31370,3857,always_xy=True).transform
X,Y=TO_LOCAL(4.07,51.03)


def feature(road,previous,coords,value=50,sign="F1a",suffix=""):
    return dict(type="Feature",id=f"{road}-{previous}-{suffix}",geometry=dict(type="MultiLineString",coordinates=[[LOCAL_TO_AWV(X+x,Y+y) for x,y in coords]]),properties=dict(Wegsegment_ID=road,Vorige_wegsegment_ID=previous,Snelheid=value,Bepalend_bord=sign))


def collection(features):
    return dict(type="FeatureCollection",crs={"name":"EPSG:3857"},numberMatched=len(features),features=features)


def ordinary():
    return [feature(1,0,[(-30,0),(0,0)],70,"C43"),feature(2,1,[(0,0),(100,0)]),feature(3,4,[(130,0),(100,0)]),feature(2,3,[(100,0),(0,0)],70,"C43","reverse")]


class Tags(dict):
    def __iter__(self):
        return iter([type("Tag",(),{"k":key})() for key in self.keys()])


class FallbackTests(unittest.TestCase):
    def test_explicit_and_semantic_limits_excluded(self):
        for extra in ({"maxspeed":"30"},{"maxspeed":"BE:urban"},{"maxspeed:conditional":"30 @ (08:00-16:00)"},{"maxspeed:variable":"yes"},{"zone:maxspeed":"30"},{"cyclestreet":"yes"},{"bicycle_road":"yes"},{"bridge":"yes"},{"layer":"1"},{"tunnel":"yes"},{"highway":"living_street"},{"junction":"roundabout"},{"maxspeed:forward":"50"}):
            with self.subTest(extra=extra):
                self.assertFalse(awv_eligible(Tags({"highway":"residential",**extra})))
        self.assertTrue(awv_eligible(Tags(highway="secondary")))

    def test_direction_is_not_inferred_from_nearest_value(self):
        index=AwvIndex(collection(ordinary()))
        self.assertEqual(index.match(Point(X+50,Y),1,0)[0],50)
        self.assertEqual(index.match(Point(X+50,Y),-1,0)[0],70)

    def test_connected_multiline_preserves_direction(self):
        features=ordinary()
        features[1]["geometry"]["coordinates"]=[[LOCAL_TO_AWV(X,Y),LOCAL_TO_AWV(X+50,Y)],[LOCAL_TO_AWV(X+50,Y),LOCAL_TO_AWV(X+100,Y)]]
        index=AwvIndex(collection(features))
        self.assertEqual(index.match(Point(X+75,Y),1,0)[0],50)

    def test_disconnected_multiline_does_not_create_bridge(self):
        features=ordinary()
        features[1]["geometry"]["coordinates"]=[[LOCAL_TO_AWV(X,Y),LOCAL_TO_AWV(X+40,Y)],[LOCAL_TO_AWV(X+60,Y),LOCAL_TO_AWV(X+100,Y)]]
        index=AwvIndex(collection(features))
        self.assertEqual(index.match(Point(X+75,Y),1,0)[0],0)

    def test_downloader_rejects_duplicate_page(self):
        data=collection(ordinary()[:2]);data["numberMatched"]=3;data["numberReturned"]=2
        with tempfile.TemporaryDirectory() as root,patch("urllib.request.urlopen",side_effect=[io.StringIO(json.dumps(data)),io.StringIO(json.dumps(data))]):
            output=Path(root)/"snapshot.json"
            with self.assertRaisesRegex(ValueError,"Duplicate"):
                download(output)
            self.assertFalse(output.exists())

    def test_downloader_accepts_complete_pagination(self):
        first=collection(ordinary()[:2]);first["numberMatched"]=3;first["numberReturned"]=2
        second=collection([ordinary()[2]]);second["numberMatched"]=3;second["numberReturned"]=1
        with tempfile.TemporaryDirectory() as root,patch("urllib.request.urlopen",side_effect=[io.StringIO(json.dumps(first)),io.StringIO(json.dumps(second))]):
            output=Path(root)/"snapshot.json";download(output)
            self.assertEqual(len(json.loads(output.read_text())["features"]),3)

    def test_predecessor_required(self):
        index=AwvIndex(collection([ordinary()[1]]))
        self.assertEqual(index.match(Point(X+50,Y),1,0)[0],0)

    def test_no_extrapolation_beyond_boundary(self):
        index=AwvIndex(collection(ordinary()))
        self.assertEqual(index.match(Point(X+105,Y),1,0)[0],0)
        self.assertEqual(index.match(Point(X-5,Y),1,0)[0],0)

    def test_conflicting_parallel_road_blocks(self):
        features=ordinary()+[feature(8,0,[(-30,3),(0,3)]),feature(9,8,[(0,3),(100,3)],30,"ZC43")]
        index=AwvIndex(collection(features))
        self.assertEqual(index.match(Point(X+50,Y),1,0)[0],0)

    def test_unknown_parallel_record_blocks(self):
        features=ordinary()+[feature(9,99,[(0,3),(100,3)],0,None)]
        self.assertEqual(AwvIndex(collection(features)).match(Point(X+50,Y),1,0)[0],0)

    def test_crossing_road_is_not_selected(self):
        index=AwvIndex(collection(ordinary()))
        self.assertEqual(index.match(Point(X+50,Y),0,1)[0],0)

    def test_incomplete_snapshot_rejected(self):
        data=collection(ordinary());data["numberMatched"]+=1
        with self.assertRaises(ValueError): AwvIndex(data)

    def test_oneway_reverse_remains_unknown(self):
        from enrich_awv import FROM_LOCAL
        lon1,lat1=FROM_LOCAL(X+10,Y);lon2,lat2=FROM_LOCAL(X+90,Y)
        parts=AwvIndex(collection(ordinary())).pieces((1,lat1,lon1,lat2,lon2,0,0,1,"test"))
        self.assertTrue(all(p[2]==50 and p[3]==0 for p in parts))

    def test_existing_direction_remains_unchanged(self):
        from enrich_awv import FROM_LOCAL
        lon1,lat1=FROM_LOCAL(X+10,Y);lon2,lat2=FROM_LOCAL(X+90,Y)
        parts=AwvIndex(collection(ordinary())).pieces((1,lat1,lon1,lat2,lon2,30,0,0,"test"))
        self.assertTrue(all(p[2]==30 and p[3]==70 for p in parts))

    def test_limit_change_splits_an_osm_edge(self):
        from enrich_awv import FROM_LOCAL
        features=[feature(1,0,[(-30,0),(0,0)]),feature(2,1,[(0,0),(50,0)]),feature(3,2,[(50,0),(100,0)],30,"ZC43")]
        lon1,lat1=FROM_LOCAL(X+10,Y);lon2,lat2=FROM_LOCAL(X+90,Y)
        parts=AwvIndex(collection(features)).pieces((1,lat1,lon1,lat2,lon2,0,0,1,"test"))
        self.assertEqual([p[2] for p in parts],[50,30])
        self.assertAlmostEqual(parts[0][1],.5,places=5)

    def test_old_database_refused_and_input_unchanged(self):
        with tempfile.TemporaryDirectory() as root:
            root=Path(root);source=root/"old.db";snapshot=root/"awv.json";output=root/"out.db"
            db=sqlite3.connect(source);db.execute("CREATE TABLE metadata(key,value)");db.execute("INSERT INTO metadata VALUES ('format','motolimiet-2')");db.commit();db.close()
            snapshot.write_text(json.dumps(collection(ordinary())))
            before=source.read_bytes()
            with self.assertRaisesRegex(ValueError,"Rebuild from OSM"):
                enrich(source,snapshot,output,root/"report.json")
            self.assertEqual(before,source.read_bytes());self.assertFalse(output.exists())


if __name__ == "__main__": unittest.main()
