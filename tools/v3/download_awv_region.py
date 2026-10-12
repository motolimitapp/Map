#!/usr/bin/env python3
"""Fetch bounded AWV speed + Zone30 context for research candidate builds."""
import argparse,json,urllib.parse,urllib.request
from pathlib import Path
from pyproj import Transformer

ENDPOINT="https://opendata.apps.mow.vlaanderen.be/opendata-geoserver/awv/wfs"

def fetch_layer(layer,bbox,srs):
    t=Transformer.from_crs("EPSG:4326","EPSG:31370",always_xy=True)
    x1,y1=t.transform(bbox[0],bbox[1]);x2,y2=t.transform(bbox[2],bbox[3])
    params={"service":"WFS","version":"2.0.0","request":"GetFeature","typeNames":layer,
            "outputFormat":"application/json","srsName":srs,
            "bbox":f"{min(x1,x2)},{min(y1,y2)},{max(x1,x2)},{max(y1,y2)},EPSG:31370","count":50000}
    url=ENDPOINT+"?"+urllib.parse.urlencode(params)
    req=urllib.request.Request(url,headers={"User-Agent":"MotoLimiet-regional-candidate/2.0","Accept":"application/json"})
    with urllib.request.urlopen(req,timeout=120) as response:
        return json.load(response)

def main():
    p=argparse.ArgumentParser();p.add_argument("out");p.add_argument("--bbox",required=True)
    a=p.parse_args();bbox=[float(x) for x in a.bbox.split(",")]

    data=fetch_layer("awv:Afgeleide_snelheidsregimes",bbox,"EPSG:3857")
    feats=data.get("features",[])
    data["numberMatched"]=len(feats);data["numberReturned"]=len(feats)

    zone=fetch_layer("awv:Afgeleide_zones_zone30",bbox,"EPSG:4326")
    positive=set();negative=set()
    for feature in zone.get("features",[]):
        props=feature.get("properties") or {}
        try: signed=int(props.get("WegsegmentId"))
        except (TypeError,ValueError): continue
        if str(props.get("Snelheid"))!="30" or props.get("BordType")!="SnelheidsZone": continue
        if signed>0: positive.add(signed)
        elif signed<0: negative.add(-signed)
    bidirectional=sorted(positive & negative)

    data["motolimiet_snapshot"]={
        "endpoint":"bounded-research",
        "layer":"awv:Afgeleide_snelheidsregimes",
        "bbox":bbox,
        "number_matched":len(feats),
        "zone30_layer":"awv:Afgeleide_zones_zone30",
        "zone30_feature_count":len(zone.get("features",[])),
        "zone30_bidirectional_road_ids":bidirectional
    }
    Path(a.out).write_text(json.dumps(data,separators=(",",":")),encoding="utf-8")
    print("speed_features",len(feats),"zone30_features",len(zone.get("features",[])),"bidirectional_zone30_roads",len(bidirectional))
if __name__=="__main__":main()
