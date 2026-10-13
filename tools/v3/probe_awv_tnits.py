#!/usr/bin/env python3
"""Read-only AWV/TN-ITS evidence probe for MotoLimiet.

No resolver logic is applied and no map data is modified. The output is raw
nearby source evidence for the 12 Oct 2026 test locations.
"""
from __future__ import annotations
import argparse, datetime as dt, json, math, re, urllib.parse, urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any
from pyproj import CRS, Transformer
from shapely.geometry import Point, shape
from shapely.ops import transform as geom_transform

AWV_WFS="https://opendata.apps.mow.vlaanderen.be/opendata-geoserver/awv/wfs"
TNITS_CKAN="https://transportdata.be/api/3/action/package_show?id=tn-its"
UA="MotoLimiet-AWV-TNITS-diagnostic/1.0"
TO_3857=Transformer.from_crs("EPSG:4326","EPSG:3857",always_xy=True).transform

CASES=[
 {"id":"dendermonde_before_first30","place":"Dendermonde","local_time":"2026-10-12T15:45:28+02:00","lat":51.0318418,"lon":4.0914824,"app":"Gentsesteenweg limit=0; nearby Kerkstraat=30","physical":"User reports Zone 30 began earlier"},
 {"id":"dendermonde_first_selected30","place":"Dendermonde","local_time":"2026-10-12T15:45:30+02:00","lat":51.0318247,"lon":4.0917542,"app":"Kerkstraat limit=30","physical":"Inside reported Zone 30"},
 {"id":"wieze_ambiguous_before30","place":"Wieze","local_time":"2026-10-12T20:14:39+02:00","lat":50.9807187,"lon":4.0831841,"app":"Nieuwstraat 30/0 ambiguous","physical":"User reports already inside Zone 30"},
 {"id":"wieze_first_stable30","place":"Wieze","local_time":"2026-10-12T20:14:45+02:00","lat":50.9807115,"lon":4.0823878,"app":"Nieuwstraat limit=30","physical":"Inside Zone 30"},
 {"id":"steven_wrong90","place":"Wieze/Steven","local_time":"2026-10-12T20:10:05+02:00","lat":50.9707056,"lon":4.1076901,"app":"Steven limit=90 quality=osm","physical":"User reports 50 km/h built-up area"},
 {"id":"gijzegem_zone30_outbound","place":"Gijzegem","local_time":"2026-10-12T19:51:23+02:00","lat":50.9863559,"lon":4.0473704,"app":"Pachthofstraat limit=30 quality=osm","physical":"Zone 30 confirmed by user"},
 {"id":"gijzegem_zone30_return","place":"Gijzegem","local_time":"2026-10-12T20:19:11+02:00","lat":50.9845405,"lon":4.0505517,"app":"Pachthofstraat limit=30 quality=local_restriction; no audio attempt","physical":"Zone 30 confirmed by user"}
]
GROUPS={
 "speed_regime":["afgeleide_snelheidsregimes"],
 "zone30":["afgeleide_zones_zone30"],
 "zone50":["afgeleide_zones_zone50"],
 "built_up":["afgeleide_zones_bebouwdekom","bebouwdekom"],
 "residential":["afgeleide_zones_woonerf","woonerf"],
 "bicycle_zone":["afgeleide_zones_fietsstraten","fietsstraten","fietszone"],
 "motorway":["afgeleide_zones_autosnelweg","autosnelweg"],
 "traffic_signs":["verkeersborden","verkeersbord"],
 "sign_installations":["opstellingen","opstelling"]
}

def get_bytes(url,accept="*/*",timeout=120):
 req=urllib.request.Request(url,headers={"User-Agent":UA,"Accept":accept})
 with urllib.request.urlopen(req,timeout=timeout) as r:return r.read()

def get_json(url,timeout=120):
 return json.loads(get_bytes(url,"application/json",timeout))

def local(tag):return tag.rsplit("}",1)[-1]

def capabilities():
 q=urllib.parse.urlencode({"service":"WFS","version":"2.0.0","request":"GetCapabilities"})
 root=ET.fromstring(get_bytes(AWV_WFS+"?"+q,"application/xml,text/xml"))
 names=[]
 for e in root.iter():
  if local(e.tag)=="Name" and e.text and ":" in e.text:names.append(e.text.strip())
 return sorted(set(names))

def select_layers(names):
 out={}
 for group,aliases in GROUPS.items():
  exact=[];fuzzy=[]
  for name in names:
   suffix=name.lower().split(":")[-1]
   if any(suffix==a for a in aliases):exact.append(name)
   elif any(a in suffix for a in aliases):fuzzy.append(name)
  out[group]=sorted(exact or fuzzy)[:6]
 return out

def bbox(lat,lon,r):
 dlat=r/111320.0;dlon=r/(111320.0*max(.2,math.cos(math.radians(lat))))
 return lon-dlon,lat-dlat,lon+dlon,lat+dlat

def wfs(layer,lat,lon,r):
 w,s,e,n=bbox(lat,lon,r)
 p={"service":"WFS","version":"2.0.0","request":"GetFeature","typeNames":layer,
    "outputFormat":"application/json","srsName":"EPSG:4326",
    "bbox":f"{w},{s},{e},{n},urn:ogc:def:crs:OGC:1.3:CRS84","count":"500"}
 return get_json(AWV_WFS+"?"+urllib.parse.urlencode(p))

def clean(props):
 out={}
 for k,v in props.items():
  if v is None or v=="":continue
  if isinstance(v,str) and len(v)>500:v=v[:500]+"..."
  out[str(k)]=v
 return out

def nearest(fc,lat,lon,r):
 p=geom_transform(TO_3857,Point(lon,lat));out=[]
 for f in fc.get("features",[]):
  if not f.get("geometry"):continue
  try:d=float(p.distance(geom_transform(TO_3857,shape(f["geometry"]))))
  except Exception as exc:
   out.append({"id":f.get("id"),"geometry_error":str(exc),"properties":clean(f.get("properties",{}))});continue
  if d<=r:out.append({"id":f.get("id"),"distance_m":round(d,2),"properties":clean(f.get("properties",{}))})
 out.sort(key=lambda x:x.get("distance_m",1e12))
 return out[:12]

def tnits_resource():
 pkg=get_json(TNITS_CKAN)
 if not pkg.get("success"):raise RuntimeError("CKAN package_show failed")
 scored=[]
 for r in pkg["result"].get("resources",[]):
  if not r.get("url"):continue
  fmt=str(r.get("format") or "").lower();name=str(r.get("name") or "").lower()
  score=(3 if "xml" in fmt else 0)+(2 if "tn-its" in name or "tnits" in name else 0)+(1 if r["url"].startswith("https://") else 0)
  scored.append((score,r))
 if not scored:raise RuntimeError("No TN-ITS resource URL discovered")
 return sorted(scored,key=lambda x:x[0],reverse=True)[0][1]

def numbers(text):
 return [float(x) for x in re.findall(r"[-+]?\d+(?:\.\d+)?",text)]

def crs_from(value):
 if not value:return None
 for code in ("4326","4258","31370","3812","3857"):
  if code in value:
   try:return CRS.from_epsg(int(code))
   except Exception:pass
 try:return CRS.from_user_input(value)
 except Exception:return None

def coords(elem):
 out=[]
 for n in elem.iter():
  if local(n.tag).lower() not in {"pos","poslist","coordinates"} or not n.text:continue
  vals=numbers(n.text);source=crs_from(n.attrib.get("srsName") or elem.attrib.get("srsName"))
  for a,b in zip(vals[0::2],vals[1::2]):
   try:
    if source:lon,lat=Transformer.from_crs(source,"EPSG:4326",always_xy=True).transform(a,b)
    elif abs(a)<=180 and abs(b)<=90:lon,lat=a,b
    elif abs(b)<=180 and abs(a)<=90:lon,lat=b,a
    else:continue
    if 49<=lat<=52 and 2<=lon<=7:out.append((lon,lat))
   except Exception:pass
 return out

def hav(lat1,lon1,lat2,lon2):
 r=6371000;p1=math.radians(lat1);p2=math.radians(lat2)
 a=math.sin((p2-p1)/2)**2+math.cos(p1)*math.cos(p2)*math.sin(math.radians(lon2-lon1)/2)**2
 return 2*r*math.asin(math.sqrt(a))

def parse_tnits(data,radius):
 root=ET.fromstring(data);counts={}
 for e in root.iter():
  name=local(e.tag)
  if any(k in name.lower() for k in ("speed","limit","restriction")):counts[name]=counts.get(name,0)+1
 members=[]
 for e in root.iter():
  if local(e.tag).lower() in {"member","featuremember"}:members.extend(list(e))
 if not members:members=list(root)
 near=[]
 for f in members:
  pts=coords(f)
  if not pts:continue
  parts=[]
  for n in f.iter():
   if n.text and n.text.strip() and len(n.text.strip())<=300:parts.append(local(n.tag)+"="+n.text.strip())
  blob=" | ".join(parts)
  if not re.search(r"speed|limit|restriction|maximum|km/?h|C43|ZC43",blob,re.I):continue
  for case in CASES:
   d=min(hav(case["lat"],case["lon"],lat,lon) for lon,lat in pts)
   if d<=radius:near.append({"case_id":case["id"],"distance_m":round(d,2),"feature_tag":local(f.tag),"text":blob[:3000]})
 near.sort(key=lambda x:(x["case_id"],x["distance_m"]))
 urls=[]
 for e in root.iter():
  for v in e.attrib.values():
   if isinstance(v,str) and v.startswith(("http://","https://")):urls.append(v)
  if e.text and e.text.strip().startswith(("http://","https://")):urls.append(e.text.strip())
 refs=[]
 for e in root.iter():
  item={"tag":local(e.tag)}
  if e.attrib:item["attrs"]=dict(e.attrib)
  if e.text and e.text.strip() and len(e.text.strip())<500:item["text"]=e.text.strip()
  if len(item)>1:refs.append(item)
  if len(refs)>=80:break
 return {"xml_root":local(root.tag),"bytes":len(data),"tag_counts":dict(sorted(counts.items())),"urls":sorted(set(urls))[:100],"index_sample":refs},near

def inspect_tnits_dataset(url):
 data=get_bytes(url,"application/xml,text/xml,*/*",120)
 root=ET.fromstring(data)
 sample=[];counts={}
 for e in root.iter():
  name=local(e.tag);counts[name]=counts.get(name,0)+1
  item={"tag":name}
  if e.attrib:item["attrs"]=dict(e.attrib)
  if e.text and e.text.strip() and len(e.text.strip())<500:item["text"]=e.text.strip()
  if len(item)>1:sample.append(item)
  if len(sample)>=120:break
 return {"url":url,"bytes":len(data),"root":local(root.tag),"tag_counts":dict(sorted(counts.items())),"sample":sample}

def to_markdown(report):
 lines=["# MotoLimiet raw AWV / TN-ITS evidence probe","",
        "No resolver rules are applied. Missing evidence is not evidence of absence.","",
        "## Discovered AWV layers",""]
 for k,v in report["awv"]["selected_layers"].items():lines.append("- "+k+": "+(", ".join(v) if v else "NOT FOUND"))
 lines+=["","## Cases",""]
 for c in report["cases"]:
  lines+=["### "+c["id"],"- "+c["place"]+" - "+c["local_time"],
          "- GPS: %.7f, %.7f"%(c["lat"],c["lon"]),"- App trace: "+c["app"],"- Physical expectation: "+c["physical"],""]
  for group,e in c["awv"].items():
   lines.append("AWV "+group+":")
   if e.get("error"):lines.append("- ERROR: "+e["error"])
   elif not e["features"]:lines.append("- no nearby feature returned")
   else:
    for f in e["features"][:6]:lines.append("- %s m - %s - %s"%(f.get("distance_m","?"),f.get("id"),json.dumps(f.get("properties",{}),ensure_ascii=False,sort_keys=True)))
  tn=[x for x in report["tnits"].get("nearby",[]) if x["case_id"]==c["id"]]
  lines.append("TN-ITS:")
  if tn:
   for x in tn[:8]:lines.append("- %s m - %s - %s"%(x["distance_m"],x["feature_tag"],x["text"][:600]))
  else:lines.append("- none parsed nearby; this is not a negative assertion")
  lines.append("")
 return "\n".join(lines)+"\n"

def run(output,radius):
 names=capabilities();chosen=select_layers(names);cases=[]
 for base in CASES:
  c=dict(base);c["awv"]={}
  for group,layers in chosen.items():
   result={"layers":layers,"features":[]}
   try:
    for layer in layers:
     for f in nearest(wfs(layer,c["lat"],c["lon"],radius),c["lat"],c["lon"],radius):
      f["layer"]=layer;result["features"].append(f)
    result["features"].sort(key=lambda x:x.get("distance_m",1e12))
   except Exception as exc:result["error"]=type(exc).__name__+": "+str(exc)
   c["awv"][group]=result
  cases.append(c)
 tn={"metadata":{},"nearby":[]}
 try:
  res=tnits_resource();data=get_bytes(res["url"],"application/xml,text/xml,*/*",180);meta,near=parse_tnits(data,radius)
  meta["resource"]={k:res.get(k) for k in ("name","format","url","last_modified")}
  dataset_urls=[u for u in meta.get("urls",[]) if "/tn-its/rest/dataset/" in u][:3]
  meta["dataset_samples"]=[]
  for u in dataset_urls:
   try:meta["dataset_samples"].append(inspect_tnits_dataset(u))
   except Exception as exc:meta["dataset_samples"].append({"url":u,"error":type(exc).__name__+": "+str(exc)})
  tn={"metadata":meta,"nearby":near}
 except Exception as exc:tn={"metadata":{"error":type(exc).__name__+": "+str(exc)},"nearby":[]}
 report={"format":"motolimiet-raw-evidence-1","retrieved_utc":dt.datetime.now(dt.timezone.utc).isoformat(),
         "radius_m":radius,"awv":{"endpoint":AWV_WFS,"available_layer_count":len(names),"selected_layers":chosen},
         "tnits":tn,"cases":cases}
 output.write_text(json.dumps(report,ensure_ascii=False,indent=2,sort_keys=True)+"\n",encoding="utf-8")
 output.with_suffix(".md").write_text(to_markdown(report),encoding="utf-8")
 return report

if __name__=="__main__":
 p=argparse.ArgumentParser(description=__doc__);p.add_argument("--output",default="evidence-report.json");p.add_argument("--radius-m",type=float,default=175.0)
 a=p.parse_args();r=run(Path(a.output),a.radius_m)
 print(json.dumps({"format":r["format"],"cases":len(r["cases"]),"awv_layers":r["awv"]["selected_layers"],"tnits":r["tnits"]["metadata"]},ensure_ascii=False,indent=2))
