#!/usr/bin/env python3
"""Annotate a regional research candidate with topology-gated AWV evidence.

Safety boundary: this script NEVER changes segments.forward_kmh/backward_kmh.
It writes a separate research_crosswalk_annotations table and JSON report.
"""
import argparse,json,sqlite3
from collections import defaultdict
from pathlib import Path
from pyproj import Transformer
from shapely.geometry import LineString
from awv_osm_crosswalk import CrosswalkIndex,validate_topology
from validate_live_crosswalk import flatten_speed_features
from research_directional_evidence import build_road_evidence,directional_summary
from probe_official_evidence import bbox_to_31370,get_layer

TO=Transformer.from_crs("EPSG:4326","EPSG:31370",always_xy=True)

def evidence_by_road(collection):
    result=defaultdict(list)
    for feature in collection.get("features",[]):
        p=feature.get("properties") or {}
        rid=p.get("Wegsegment_ID")
        if rid is None: continue
        result[int(rid)].append({
            "feature_id":feature.get("id",""),
            "speed":p.get("Snelheid"),
            "sign":p.get("Bepalend_bord"),
            "zone":str(p.get("Zone") or ""),
            "previous_road_id":p.get("Vorige_wegsegment_ID"),
        })
    return result

def classify(items):
    valid=[x for x in items if type(x["speed"]) is int]
    zone30=[x for x in valid if x["speed"]==30 and x["sign"]=="F4a" and "SnelheidsZone" in x["zone"]]
    numeric={x["speed"] for x in valid}
    if not valid:return "unproven",None
    if zone30 and numeric=={30}:return "f4a_zone30_candidate",30
    if len(numeric)>1:return "conflicting_official_numeric",None
    return "other_official_evidence",None

def main():
    p=argparse.ArgumentParser()
    p.add_argument("database");p.add_argument("config");p.add_argument("case");p.add_argument("report")
    a=p.parse_args()
    cfg=json.loads(Path(a.config).read_text())
    case=next(c for c in cfg["cases"] if c["name"]==a.case)
    collection,urls,capped=get_layer(cfg["wfs_endpoint"],cfg["layers"]["speed"],bbox_to_31370(case["bbox"],75),500,5000)
    if capped:raise SystemExit("AWV WFS result capped")
    lines=flatten_speed_features(collection)
    idx=CrosswalkIndex(lines)
    ev=build_road_evidence(collection)
    db=sqlite3.connect(a.database)
    west,south,east,north=case["bbox"]
    rows=db.execute("""SELECT s.id,s.lat1,s.lon1,s.lat2,s.lon2,s.name,s.forward_kmh,s.backward_kmh,p.osm_way_id
                       FROM segments s JOIN osm_provenance p ON p.segment_id=s.id
                       WHERE p.comparable=1 AND max(s.lat1,s.lat2)>=? AND min(s.lat1,s.lat2)<=?
                       AND max(s.lon1,s.lon2)>=? AND min(s.lon1,s.lon2)<=?""",(south,north,west,east)).fetchall()
    matches=[]
    original={}
    for sid,lat1,lon1,lat2,lon2,name,fw,bw,way in rows:
        x1,y1=TO.transform(lon1,lat1);x2,y2=TO.transform(lon2,lat2)
        rid,info=idx.match(LineString(((x1,y1),(x2,y2))))
        matches.append({"osm_segment_id":sid,"osm_way_id":way,"name":name,"road_id":rid,"start_xy":[x1,y1],"end_xy":[x2,y2],"info":info})
        original[sid]=(fw,bw)
    accepted,diag=validate_topology(matches)
    db.execute("""CREATE TABLE IF NOT EXISTS research_crosswalk_annotations(
      segment_id INTEGER,case_name TEXT,awv_road_id INTEGER,evidence_state TEXT,
      evidence_kmh INTEGER,original_forward INTEGER,original_backward INTEGER,
      component_segments INTEGER,component_length_m REAL,
      candidate_forward_state TEXT,candidate_forward_kmh INTEGER,
      candidate_backward_state TEXT,candidate_backward_kmh INTEGER,
      applied_speed_change INTEGER NOT NULL DEFAULT 0,
      PRIMARY KEY(segment_id,case_name))""")
    db.execute("DELETE FROM research_crosswalk_annotations WHERE case_name=?",(a.case,))
    report=[]
    for m in matches:
        sid=m["osm_segment_id"]
        if sid not in accepted:continue
        rid=m["road_id"];fw,bw=original[sid];d=diag[sid]
        dx=m["end_xy"][0]-m["start_xy"][0];dy=m["end_xy"][1]-m["start_xy"][1]
        directions=directional_summary(ev.get(rid,[]),dx,dy)
        forward=directions["forward"];backward=directions["backward"]
        state="directed_research_candidate";khm=None
        db.execute("INSERT INTO research_crosswalk_annotations VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,0)",(sid,a.case,rid,state,khm,fw,bw,d["component_segments"],d["component_length_m"],forward["state"],forward["candidate_kmh"],backward["state"],backward["candidate_kmh"]))
        report.append({"segment_id":sid,"name":m["name"],"osm_way_id":m["osm_way_id"],"awv_road_id":rid,
                       "evidence_state":state,"evidence_kmh":khm,"forward_evidence":forward,"backward_evidence":backward,"original_forward":fw,"original_backward":bw,
                       "component_segments":d["component_segments"],"component_length_m":d["component_length_m"],
                       "applied_speed_change":False})
    db.commit()
    changed=db.execute("SELECT count(*) FROM research_crosswalk_annotations WHERE case_name=? AND applied_speed_change!=0",(a.case,)).fetchone()[0]
    db.close()
    if changed:raise SystemExit("Safety violation: research annotator changed speed state")
    Path(a.report).write_text(json.dumps({"case":a.case,"status":"research_annotation_only","speed_changes_applied":0,
      "accepted_topology_segments":len(report),"annotations":report,
      "guardrail":"No numeric speed was written to segments; directed candidates require further field validity and topology validation."},indent=2)+"\n")
if __name__=="__main__":main()
