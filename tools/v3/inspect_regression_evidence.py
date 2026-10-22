#!/usr/bin/env python3
"""Research-only evidence inspector for known ride regression anchors.

Reads a regional quality DB + the exact AWV snapshot used to build it.
Does not change any map values.
"""
import argparse,json,math,sqlite3
from pathlib import Path
from pyproj import Transformer
from shapely.geometry import shape,Point
from shapely.ops import transform

TO_LOCAL=Transformer.from_crs("EPSG:4326","EPSG:31370",always_xy=True)
AWV_LOCAL=Transformer.from_crs("EPSG:3857","EPSG:31370",always_xy=True)

def dist_to_feature(feature,lat,lon):
    geometry=feature.get("geometry")
    if not geometry:return None
    try:
        g=transform(AWV_LOCAL.transform,shape(geometry))
        x,y=TO_LOCAL.transform(lon,lat)
        return float(g.distance(Point(x,y)))
    except Exception:
        return None

def main():
    p=argparse.ArgumentParser()
    p.add_argument("database");p.add_argument("snapshot");p.add_argument("fixture");p.add_argument("output")
    p.add_argument("--ids",required=True)
    a=p.parse_args()
    wanted={x.strip() for x in a.ids.split(",") if x.strip()}
    fixture=json.loads(Path(a.fixture).read_text(encoding="utf-8"))
    anchors=[x for x in fixture["anchors"] if x["id"] in wanted]
    snap=json.loads(Path(a.snapshot).read_text(encoding="utf-8"))
    features=snap.get("features",[])
    db=sqlite3.connect("file:"+str(Path(a.database).resolve())+"?mode=ro",uri=True)
    result={"status":"research_only","anchors":[]}
    for anchor in anchors:
        lat,lon=anchor["lat"],anchor["lon"]
        latpad=40/110000
        lonpad=40/(110000*math.cos(math.radians(lat)))
        rows=db.execute("""SELECT s.id,s.name,s.lat1,s.lon1,s.lat2,s.lon2,s.forward_kmh,s.backward_kmh,
                                  q.forward_state,q.backward_state,q.original_forward,q.original_backward,
                                  q.forward_features,q.backward_features,p.osm_way_id
                           FROM segments s JOIN segment_quality q ON q.segment_id=s.id
                           JOIN osm_provenance p ON p.segment_id=s.id
                           WHERE max(s.lat1,s.lat2)>=? AND min(s.lat1,s.lat2)<=?
                           AND max(s.lon1,s.lon2)>=? AND min(s.lon1,s.lon2)<=?""",
                        (lat-latpad,lat+latpad,lon-lonpad,lon+lonpad)).fetchall()
        segments=[]
        for row in rows:
            segments.append({
                "segment_id":row[0],"name":row[1],"osm_way_id":row[14],
                "lat1":row[2],"lon1":row[3],"lat2":row[4],"lon2":row[5],
                "forward_kmh":row[6],"backward_kmh":row[7],
                "forward_state":row[8],"backward_state":row[9],
                "original_forward":row[10],"original_backward":row[11],
                "forward_feature_refs":row[12],"backward_feature_refs":row[13],
            })
        nearby=[]
        for feature in features:
            d=dist_to_feature(feature,lat,lon)
            if d is None or d>60:continue
            props=feature.get("properties") or {}
            nearby.append({
                "distance_m":round(d,2),
                "feature_id":str(feature.get("id") or ""),
                "wegsegment_id":props.get("Wegsegment_ID"),
                "previous_wegsegment_id":props.get("Vorige_wegsegment_ID"),
                "speed":props.get("Snelheid"),
                "sign":props.get("Bepalend_bord"),
                "zone":props.get("Zone"),
                "begin_position":props.get("Beginpositie"),
                "end_position":props.get("Eindpositie"),
            })
        nearby.sort(key=lambda x:(x["distance_m"],str(x["feature_id"])))
        result["anchors"].append({
            "id":anchor["id"],"lat":lat,"lon":lon,"bearing_deg":anchor["bearing_deg"],
            "expected_kmh":anchor.get("expected_kmh"),"segments":segments,
            "nearby_awv_features":nearby[:40],
        })
    db.close()
    Path(a.output).write_text(json.dumps(result,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")

if __name__=="__main__":
    main()
