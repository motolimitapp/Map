#!/usr/bin/env python3
"""Fetch a bounded AWV speed-regime snapshot compatible with v3 builders."""
import argparse,json,urllib.parse,urllib.request
from pathlib import Path
from pyproj import Transformer

def main():
    p=argparse.ArgumentParser();p.add_argument("out");p.add_argument("--bbox",required=True)
    a=p.parse_args();bbox=[float(x) for x in a.bbox.split(",")]
    t=Transformer.from_crs("EPSG:4326","EPSG:31370",always_xy=True)
    x1,y1=t.transform(bbox[0],bbox[1]);x2,y2=t.transform(bbox[2],bbox[3])
    params={"service":"WFS","version":"2.0.0","request":"GetFeature","typeNames":"awv:Afgeleide_snelheidsregimes",
            "outputFormat":"application/json","srsName":"EPSG:3857",
            "bbox":f"{min(x1,x2)},{min(y1,y2)},{max(x1,x2)},{max(y1,y2)},EPSG:31370","count":50000}
    url="https://opendata.apps.mow.vlaanderen.be/opendata-geoserver/awv/wfs?"+urllib.parse.urlencode(params)
    req=urllib.request.Request(url,headers={"User-Agent":"MotoLimiet-regional-candidate/1.0","Accept":"application/json"})
    with urllib.request.urlopen(req,timeout=120) as r:data=json.load(r)
    feats=data.get("features",[])
    data["numberMatched"]=len(feats);data["numberReturned"]=len(feats)
    data["motolimiet_snapshot"]={"endpoint":"bounded-research","layer":"awv:Afgeleide_snelheidsregimes","bbox":bbox,"number_matched":len(feats)}
    Path(a.out).write_text(json.dumps(data,separators=(",",":")),encoding="utf-8")
    print("features",len(feats))
if __name__=="__main__":main()
