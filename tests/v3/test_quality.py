import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'tools/v3'))
from quality_policy import *
class PolicyTests(unittest.TestCase):
 def check(self,osm,evidence,expected,fill=False,state=None):self.assertEqual(resolve(osm,(OSM if osm else MISSING) if state is None else state,evidence,fill),expected)
 def test_agreement(self):self.check(50,('fixed',50,'F1a','id'),(50,AGREEMENT))
 def test_missing_osm(self):self.check(0,('fixed',50,'F1a','id'),(50,AWV),True)
 def test_semantic_osm(self):self.check(0,('fixed',50,'F1a','id'),(0,MISSING))
 def test_missing_awv(self):self.check(70,('absent',0,'',''),(70,OSM))
 def test_conflict(self):self.check(70,('fixed',50,'F1a','id'),(0,CONFLICT))
 def test_local_30(self):self.check(30,('fixed',50,'F1a','id'),(30,LOCAL_RESTRICTION))
 def test_not_lowest_wins(self):self.check(30,('fixed',50,'C43','id'),(0,CONFLICT))
 def test_lower_awv_not_selected(self):self.check(50,('fixed',30,'ZC43','id'),(0,CONFLICT))
 def test_variable(self):self.check(70,('variable',30,'IVMS1','id'),(0,VARIABLE))
 def test_conditional(self):self.check(0,('fixed',50,'C43','id'),(0,VARIABLE),True,VARIABLE)
 def test_ambiguous(self):self.check(70,('ambiguous',0,'','id'),(0,AMBIGUOUS))
 def test_unproven(self):self.check(70,('unproven',50,'F1a','id'),(70,OSM))
 def test_crosswalk_fills_missing_zone30_at_20m_offset(self):
  from test_awv import feature,collection,X,Y
  from build_quality_map import EvidenceIndex
  from enrich_awv import FROM_LOCAL
  index=EvidenceIndex(collection([
   feature(1,0,[(-30,20),(0,20)],50,'F1a'),
   feature(2,1,[(0,20),(100,20)],30,'F4a',zone='["SnelheidsZone"]')
  ]))
  lon1,lat1=FROM_LOCAL(X+10,Y);lon2,lat2=FROM_LOCAL(X+90,Y)
  pieces=index.quality_pieces((1,lat1,lon1,lat2,lon2,0,0,0,'Testweg'),(MISSING,MISSING),True)
  self.assertTrue(any(p[2]==30 and p[4]==AWV for p in pieces))

 def test_direct_7m_evidence_precedes_crosswalk_fallback(self):
  from test_awv import feature,collection,X,Y
  from build_quality_map import EvidenceIndex
  from enrich_awv import FROM_LOCAL
  index=EvidenceIndex(collection([
   feature(1,0,[(-30,2),(0,2)],50,'F1a'),
   feature(2,1,[(0,2),(100,2)],50,'F1a'),
   feature(3,0,[(-30,20),(0,20)],50,'F1a'),
   feature(4,3,[(0,20),(100,20)],30,'F4a',zone='["SnelheidsZone"]')
  ]))
  lon1,lat1=FROM_LOCAL(X+10,Y);lon2,lat2=FROM_LOCAL(X+90,Y)
  pieces=index.quality_pieces((1,lat1,lon1,lat2,lon2,0,0,0,'Testweg'),(MISSING,MISSING),True)
  self.assertTrue(any(p[2]==50 and p[4]==AWV for p in pieces))
  self.assertFalse(any(p[2]==30 for p in pieces))
 def test_crosswalk_may_refine_direct_ambiguity_only(self):
  from test_awv import feature,collection,X,Y
  from build_quality_map import EvidenceIndex
  from enrich_awv import FROM_LOCAL
  index=EvidenceIndex(collection([
   feature(1,0,[(-30,2),(100,2)],30,'F4a',zone='["SnelheidsZone"]'),
   feature(2,0,[(-30,4),(100,4)],50,'F1a')
  ]))
  index.crosswalk.match=lambda line:(1,{"reason":"matched"})
  lon1,lat1=FROM_LOCAL(X+10,Y);lon2,lat2=FROM_LOCAL(X+90,Y)
  pieces=index.quality_pieces((1,lat1,lon1,lat2,lon2,0,0,0,'Testweg'),(MISSING,MISSING),True)
  self.assertTrue(all(p[2]==30 and p[4]==AWV for p in pieces))

 def test_crosswalk_does_not_override_direct_conflict(self):
  from test_awv import feature,collection,X,Y
  from build_quality_map import EvidenceIndex
  from enrich_awv import FROM_LOCAL
  index=EvidenceIndex(collection([
   feature(1,0,[(-30,2),(100,2)],30,'F4a',zone='["SnelheidsZone"]')
  ]))
  index.crosswalk.match=lambda line:(1,{"reason":"matched"})
  lon1,lat1=FROM_LOCAL(X+10,Y);lon2,lat2=FROM_LOCAL(X+90,Y)
  pieces=index.quality_pieces((1,lat1,lon1,lat2,lon2,50,50,0,'Testweg'),(OSM,OSM),True)
  self.assertTrue(all(p[2]==0 and p[4]==CONFLICT for p in pieces))

 def test_split_same_predecessor(self):
  from test_awv import feature,collection,X,Y
  from build_quality_map import EvidenceIndex
  from shapely.geometry import Point
  index=EvidenceIndex(collection([feature(1,0,[(-30,0),(0,0)]),feature(2,1,[(0,0),(50,0)],30,'IVMS1','variable'),feature(2,1,[(50,0),(100,0)],50,'F1a','fixed')]))
  indices=list(range(len(index.lines)))
  self.assertEqual(index.at(Point(X+25,Y),1,0,indices)[0],'variable')
  self.assertEqual(index.at(Point(X+75,Y),1,0,indices)[:3],('fixed',50,'F1a'))
  self.assertEqual(index.at(Point(X+75,Y),-1,0,indices)[0],'absent')
if __name__=='__main__':unittest.main()
