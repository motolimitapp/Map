"""Evaluate topology crosswalk on regional candidate OSM database, read-only."""
import argparse,json,sqlite3
from pathlib import Path
from shapely.geometry import LineString
from pyproj import Transformer
from awv_osm_crosswalk import CrosswalkIndex,validate_topology
from validate_live_crosswalk import flatten_speed_features
from probe_official_evidence import bbox_to_31370,get_layer
p=argparse.ArgumentParser()
p.add_argument("db");p.add_argument("config");p.add_argument("case");p.add_argument("out")
a=p.parse_args()
config=json.loads(Path(a.config).read_text())
case=next(c for c in config["cases"] if c["name"]==a.case)
collection,urls,capped=get_layer(config["wfs_endpoint"],config["layers"]["speed"],bbox_to_31370(case["bbox"],75),500,5000)
lines=flatten_speed_features(collection)
if capped or not lines:raise SystemExit("AWV data unavailable or truncated")
idx=CrosswalkIndex(lines)
t=Transformer.from_crs("EPSG:4326","EPSG:31370",always_xy=True)
db=sqlite3.connect("file:"+str(Path(a.db).resolve())+"?mode=ro",uri=True)
rows=db.execute("SELECT s.id,s.lat1,s.lon1,s.lat2,s.lon2,s.name,p.osm_way_id FROM segments s JOIN osm_provenance p ON p.segment_id=s.id WHERE p.comparable=1").fetchall()
matches=[]
for sid,lat1,lon1,lat2,lon2,name,way in rows:
 x1,y1=t.transform(lon1,lat1);x2,y2=t.transform(lon2,lat2)
 road,info=idx.match(LineString(((x1,y1),(x2,y2))))
 matches.append({"osm_segment_id":sid,"osm_way_id":way,"name":name,"road_id":road,"start_xy":[x1,y1],"end_xy":[x2,y2],"info":info})
accepted,diagnostics=validate_topology(matches)
report={"case":a.case,"source":"regional research OSM + AWV","raw_matches":sum(m["road_id"] is not None for m in matches),"accepted":len(accepted),"segments":[{"id":m["osm_segment_id"],"way":m["osm_way_id"],"name":m["name"],"awv_road_id":m["road_id"],"accepted":m["osm_segment_id"] in accepted} for m in matches if m["road_id"] is not None],"warning":"No speed assignment; no production map update"}
Path(a.out).write_text(json.dumps(report,indent=2)+"\n")
db.close()
