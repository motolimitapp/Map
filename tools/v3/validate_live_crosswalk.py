#!/usr/bin/env python3
"""Validate the research crosswalk against the live MotoLimiet v3 map.

Read-only:
- downloads/opens an existing live map database supplied by the workflow;
- queries live OSM-derived segments near configured ride anchors;
- fetches official AWV speed-regime features in the same windows;
- evaluates the research AWV/Wegenregister -> OSM crosswalk;
- writes a JSON report only.
"""
import argparse
import json
import pathlib
import sqlite3
import urllib.parse
import urllib.request

from pyproj import Transformer
from shapely.geometry import LineString, shape
from shapely.ops import transform as shp_transform

from awv_osm_crosswalk import CrosswalkIndex

UA="MotoLimiet-live-crosswalk-validation/1.0"

def fetch_json(url):
    req=urllib.request.Request(url,headers={"User-Agent":UA,"Accept":"application/json, application/geo+json"})
    with urllib.request.urlopen(req,timeout=90) as r:
        return json.load(r)

def bbox31370(bbox):
    t=Transformer.from_crs("EPSG:4326","EPSG:31370",always_xy=True)
    x1,y1=t.transform(bbox[0],bbox[1]); x2,y2=t.transform(bbox[2],bbox[3])
    return [min(x1,x2),min(y1,y2),max(x1,x2),max(y1,y2)]

def wfs_features(endpoint,typename,bbox):
    b=bbox31370(bbox)
    params={
      "service":"WFS","version":"2.0.0","request":"GetFeature","typeNames":typename,
      "outputFormat":"application/json","srsName":"EPSG:4326",
      "bbox":",".join(str(round(v,3)) for v in b)+",EPSG:31370","count":5000
    }
    data=fetch_json(endpoint+"?"+urllib.parse.urlencode(params))
    return data.get("features",[])

def awv_lines(features):
    to_local=Transformer.from_crs("EPSG:4326","EPSG:31370",always_xy=True)
    out=[]
    for f in features:
        p=f.get("properties") or {}
        rid=p.get("Wegsegment_ID")
        if rid in (None,""):
            continue
        try: rid=int(rid)
        except Exception: continue
        g=f.get("geometry")
        if not g: continue
        geom=shp_transform(to_local.transform,shape(g))
        geoms=list(geom.geoms) if geom.geom_type=="MultiLineString" else [geom]
        for n,line in enumerate(geoms):
            if line.geom_type=="LineString" and len(line.coords)>=2 and line.length>=1:
                out.append((line,rid,f"{f.get('id','')}#{n}"))
    return out

def live_segments(db,bbox):
    con=sqlite3.connect(f"file:{pathlib.Path(db).resolve()}?mode=ro",uri=True)
    try:
        rows=con.execute("""
          SELECT s.id,s.lat1,s.lon1,s.lat2,s.lon2,s.forward_kmh,s.backward_kmh,s.oneway,s.name,
                 p.osm_way_id,q.forward_state,q.backward_state
          FROM segments s
          JOIN osm_provenance p ON p.segment_id=s.id
          JOIN segment_quality q ON q.segment_id=s.id
          WHERE max(s.lat1,s.lat2)>=? AND min(s.lat1,s.lat2)<=?
            AND max(s.lon1,s.lon2)>=? AND min(s.lon1,s.lon2)<=?
        """,(bbox[1],bbox[3],bbox[0],bbox[2])).fetchall()
        meta=dict(con.execute("SELECT key,value FROM metadata"))
        return meta,rows
    finally:
        con.close()

def local_line(row):
    t=Transformer.from_crs("EPSG:4326","EPSG:31370",always_xy=True)
    return LineString([t.transform(row[2],row[1]),t.transform(row[4],row[3])])

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("db"); ap.add_argument("config"); ap.add_argument("out")
    a=ap.parse_args()
    cfg=json.loads(pathlib.Path(a.config).read_text())
    report={"cases":[]}
    active={"dendermonde","wieze"}
    first_meta=None
    for case in cfg["cases"]:
        if case["name"] not in active: continue
        features=wfs_features(cfg["wfs_endpoint"],cfg["layers"]["speed"],case["bbox"])
        lines=awv_lines(features)
        index=CrosswalkIndex(lines)
        meta,rows=live_segments(a.db,case["bbox"])
        if first_meta is None:
            first_meta={k:meta.get(k) for k in ("format","built_utc","source","conflict_check","awv_snapshot_sha256")}
            report["live_map_metadata"]=first_meta
        result={"name":case["name"],"live_segments":len(rows),"awv_speed_features":len(features),"anchors":[]}
        for anchor in case.get("anchors",[]):
            candidates=[]
            alat,alon=anchor["lat"],anchor["lon"]
            for row in rows:
                line=local_line(row)
                # Anchor-to-segment distance in Lambert72.
                p=Transformer.from_crs("EPSG:4326","EPSG:31370",always_xy=True).transform(alon,alat)
                from shapely.geometry import Point
                d=float(Point(*p).distance(line))
                if d>25: continue
                road,info=index.match(line)
                candidates.append({
                  "segment_id":row[0],"osm_way_id":row[9],"name":row[8],
                  "anchor_distance_m":round(d,2),"forward_kmh":row[5],"backward_kmh":row[6],
                  "forward_state":row[10],"backward_state":row[11],
                  "crosswalk_road_id":road,"crosswalk":info
                })
            candidates.sort(key=lambda x:x["anchor_distance_m"])
            result["anchors"].append({
              "label":anchor["label"],"app_selected_road":anchor.get("app_selected_road"),
              "app_selected_limit":anchor.get("app_selected_limit"),"candidates":candidates[:12]
            })
        report["cases"].append(result)
    pathlib.Path(a.out).write_text(json.dumps(report,indent=2),encoding="utf-8")
    print(json.dumps(report,indent=2))
if __name__=="__main__": main()
