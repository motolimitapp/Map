#!/usr/bin/env python3
"""Read-only validation of the topology-gated AWV/OSM crosswalk on live v3 map."""
import argparse
import json
import pathlib
import sqlite3

from pyproj import Transformer
from shapely.geometry import LineString, shape
from shapely.ops import transform as shp_transform

from awv_osm_crosswalk import CrosswalkIndex, validate_topology
from probe_official_evidence import bbox_to_31370, get_layer

TO_31370 = Transformer.from_crs("EPSG:4326", "EPSG:31370", always_xy=True)


def flatten_speed_features(collection):
    lines=[]
    for feature in collection.get("features",[]):
        props=feature.get("properties") or {}
        road=props.get("Wegsegment_ID")
        geom=feature.get("geometry")
        if road is None or not geom:
            continue
        try:
            geometry=shp_transform(TO_31370.transform,shape(geom))
        except Exception:
            continue
        geoms=list(geometry.geoms) if geometry.geom_type=="MultiLineString" else [geometry]
        for n,line in enumerate(geoms):
            if line.geom_type=="LineString" and len(line.coords)>=2 and line.length>=1:
                lines.append((line,int(road),f"{feature.get('id','')}#{n}"))
    return lines


def osm_rows(con,bbox):
    minlon,minlat,maxlon,maxlat=bbox
    sql="""
      SELECT s.id,s.lat1,s.lon1,s.lat2,s.lon2,s.name,p.osm_way_id,p.comparable,
             s.forward_kmh,s.backward_kmh
      FROM segments s JOIN osm_provenance p ON p.segment_id=s.id
      WHERE p.comparable=1
        AND max(s.lat1,s.lat2)>=? AND min(s.lat1,s.lat2)<=?
        AND max(s.lon1,s.lon2)>=? AND min(s.lon1,s.lon2)<=?
      ORDER BY s.id
    """
    return con.execute(sql,(minlat,maxlat,minlon,maxlon)).fetchall()


def build_case(con,config,case):
    bbox31370=bbox_to_31370(case["bbox"],config.get("bbox_margin_m",75))
    collection,urls,capped=get_layer(
        config["wfs_endpoint"],
        config["layers"]["speed"],
        bbox31370,
        config.get("page_size",500),
        config.get("max_features_per_layer",5000),
    )
    awv_lines=flatten_speed_features(collection)
    index=CrosswalkIndex(awv_lines)
    matches=[]
    for row in osm_rows(con,case["bbox"]):
        sid,lat1,lon1,lat2,lon2,name,way,comparable,fw,bw=row
        x1,y1=TO_31370.transform(lon1,lat1)
        x2,y2=TO_31370.transform(lon2,lat2)
        line=LineString(((x1,y1),(x2,y2)))
        road,info=index.match(line)
        matches.append({
            "osm_segment_id":sid,
            "osm_way_id":way,
            "name":name,
            "road_id":road,
            "start_xy":[round(x1,3),round(y1,3)],
            "end_xy":[round(x2,3),round(y2,3)],
            "length_m":round(line.length,2),
            "osm_forward":fw,
            "osm_backward":bw,
            "info":info,
        })
    accepted,diagnostics=validate_topology(matches)
    for item in matches:
        item["topology"]=diagnostics.get(item["osm_segment_id"],{
            "topology_accepted":False,
            "reason":"no_topology_component",
        })
        item["topology_accepted"]=item["osm_segment_id"] in accepted

    anchors=[]
    for anchor in case.get("anchors",[]):
        ax,ay=TO_31370.transform(anchor["lon"],anchor["lat"])
        ranked=[]
        for item in matches:
            line=LineString((item["start_xy"],item["end_xy"]))
            distance=line.distance(shape({"type":"Point","coordinates":[ax,ay]}))
            if distance<=50:
                ranked.append({
                    "distance_m":round(float(distance),2),
                    "osm_segment_id":item["osm_segment_id"],
                    "osm_way_id":item["osm_way_id"],
                    "name":item["name"],
                    "osm_forward":item["osm_forward"],
                    "osm_backward":item["osm_backward"],
                    "road_id":item["road_id"],
                    "crosswalk_reason":item["info"].get("reason"),
                    "topology_accepted":item["topology_accepted"],
                    "crosswalk_mean_distance_m":item["info"].get("mean_distance_m"),
                })
        ranked.sort(key=lambda x:x["distance_m"])
        anchors.append({
            "label":anchor["label"],
            "app_selected_road":anchor.get("app_selected_road"),
            "app_selected_limit":anchor.get("app_selected_limit"),
            "bearing_deg":anchor.get("bearing_deg"),
            "nearby_osm":ranked[:12],
        })

    accepted_rows=[m for m in matches if m["topology_accepted"]]
    return {
        "name":case["name"],
        "awv_speed_features":len(collection.get("features",[])),
        "awv_lines":len(awv_lines),
        "wfs_pages":len(urls),
        "wfs_capped":capped,
        "osm_segments_considered":len(matches),
        "raw_crosswalk_matches":sum(1 for m in matches if m["road_id"] is not None),
        "topology_accepted_segments":len(accepted_rows),
        "topology_accepted":[
            {
                "osm_segment_id":m["osm_segment_id"],
                "osm_way_id":m["osm_way_id"],
                "name":m["name"],
                "road_id":m["road_id"],
                "length_m":m["length_m"],
                "osm_forward":m["osm_forward"],
                "osm_backward":m["osm_backward"],
                "mean_offset_m":m["info"].get("mean_distance_m"),
                "component_segments":m["topology"].get("component_segments"),
                "component_length_m":m["topology"].get("component_length_m"),
            } for m in accepted_rows
        ],
        "anchors":anchors,
    }


def main():
    p=argparse.ArgumentParser()
    p.add_argument("map_db")
    p.add_argument("config")
    p.add_argument("output")
    a=p.parse_args()
    config=json.loads(pathlib.Path(a.config).read_text(encoding="utf-8"))
    cases=[c for c in config["cases"] if c["name"] in {"dendermonde","wieze"}]
    con=sqlite3.connect(pathlib.Path(a.map_db).resolve().as_uri()+"?mode=ro",uri=True)
    try:
        meta=dict(con.execute("SELECT key,value FROM metadata"))
        if meta.get("format")!="motolimiet-3":
            raise SystemExit("Not a MotoLimiet v3 map")
        result={
            "map_metadata":{k:meta.get(k) for k in ("format","built_utc","conflict_check","source")},
            "policy":{
                "max_distance_m":40,
                "max_axis_angle_deg":15,
                "max_offset_variation_m":8,
                "competitor_margin_m":5,
                "topology_min_segments":2,
                "topology_min_length_m":25,
                "same_osm_way_required":True,
                "same_nonempty_name_required":True,
            },
            "cases":[build_case(con,config,c) for c in cases],
            "guardrail":"Research only. Topology acceptance is not permission to assign a speed limit.",
        }
    finally:
        con.close()
    pathlib.Path(a.output).write_text(json.dumps(result,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    print(json.dumps(result,indent=2,ensure_ascii=False))


if __name__=="__main__":
    main()
