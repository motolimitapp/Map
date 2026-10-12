#!/usr/bin/env python3
"""Read-only inspection of candidate-map segments around 12 Oct ride anchors."""
import argparse,json,pathlib,sqlite3
from pyproj import Transformer
from shapely.geometry import LineString,Point

TO_LOCAL=Transformer.from_crs("EPSG:4326","EPSG:31370",always_xy=True)

def dist(anchor,row):
    p=Point(*TO_LOCAL.transform(anchor["lon"],anchor["lat"]))
    a=TO_LOCAL.transform(row[2],row[1]);b=TO_LOCAL.transform(row[4],row[3])
    return float(p.distance(LineString((a,b))))

def main():
    ap=argparse.ArgumentParser();ap.add_argument("db");ap.add_argument("config");ap.add_argument("out")
    a=ap.parse_args();cfg=json.loads(pathlib.Path(a.config).read_text())
    con=sqlite3.connect(f"file:{pathlib.Path(a.db).resolve()}?mode=ro",uri=True)
    report={"metadata":dict(con.execute("SELECT key,value FROM metadata")),"cases":[]}
    evidence={}
    awv_properties={}
    db_name=pathlib.Path(a.db).name
    region=db_name.split("-quality.db")[0] if db_name.endswith("-quality.db") else ""
    snapshot=pathlib.Path(f"awv-{region}.json") if region else None
    if snapshot and snapshot.exists():
        raw=json.loads(snapshot.read_text(encoding="utf-8"))
        awv_properties={}
        for feature in raw.get("features",[]):
            props=dict(feature.get("properties") or {})
            geom=feature.get("geometry") or {}
            coords=[]
            if geom.get("type")=="MultiLineString":
                coords=[point for line in geom.get("coordinates",[]) for point in line]
            elif geom.get("type")=="LineString":
                coords=list(geom.get("coordinates",[]))
            if coords:
                props["_geometry_first"]=coords[0]
                props["_geometry_last"]=coords[-1]
                props["_geometry_points"]=len(coords)
            awv_properties[str(feature.get("id"))]=props
    try:
        for row in con.execute("SELECT id,feature_id,kind,speed,sign FROM awv_features"):
            evidence[str(row[0])]={"feature_id":row[1],"kind":row[2],"speed":row[3],"sign":row[4]}
    except sqlite3.OperationalError:
        evidence={}
    try:
        for case in cfg["cases"]:
            if case["name"] not in ("dendermonde","wieze"):continue
            cr={"name":case["name"],"anchors":[]}
            for anchor in case["anchors"]:
                lat,lon=anchor["lat"],anchor["lon"]
                rows=con.execute("""
                    SELECT s.id,s.lat1,s.lon1,s.lat2,s.lon2,s.forward_kmh,s.backward_kmh,s.oneway,s.name,
                           q.forward_state,q.backward_state,q.osm_forward,q.osm_backward,q.forward_evidence,q.backward_evidence
                    FROM segments s JOIN segment_quality q ON q.segment_id=s.id
                    WHERE min(s.lat1,s.lat2)<=? AND max(s.lat1,s.lat2)>=?
                      AND min(s.lon1,s.lon2)<=? AND max(s.lon1,s.lon2)>=?
                """,(lat+.0005,lat-.0005,lon+.0008,lon-.0008)).fetchall()
                candidates=[]
                for row in rows:
                    d=dist(anchor,row)
                    if d<=35:
                        candidates.append({
                            "distance_m":round(d,2),"segment_id":row[0],"name":row[8],
                            "forward_kmh":row[5],"backward_kmh":row[6],
                            "forward_state":row[9],"backward_state":row[10],
                            "osm_forward":row[11],"osm_backward":row[12],
                            "forward_evidence":row[13],"backward_evidence":row[14],
                            "forward_evidence_detail":[dict(evidence[x],awv_properties=awv_properties.get(evidence[x]["feature_id"],{})) for x in str(row[13]).split("|") if x in evidence],
                            "backward_evidence_detail":[dict(evidence[x],awv_properties=awv_properties.get(evidence[x]["feature_id"],{})) for x in str(row[14]).split("|") if x in evidence]
                        })
                candidates.sort(key=lambda x:x["distance_m"])
                cr["anchors"].append({
                    "label":anchor["label"],"app_selected_road":anchor.get("app_selected_road"),
                    "app_selected_limit":anchor.get("app_selected_limit"),"candidates":candidates[:15]
                })
            report["cases"].append(cr)
    finally:con.close()
    pathlib.Path(a.out).write_text(json.dumps(report,indent=2),encoding="utf-8")
    print(json.dumps(report,indent=2))
if __name__=="__main__":main()
