import argparse,json,sqlite3
from pathlib import Path
p=argparse.ArgumentParser()
p.add_argument("database");p.add_argument("config");p.add_argument("output")
a=p.parse_args()
cfg=json.loads(Path(a.config).read_text())
db=sqlite3.connect("file:"+str(Path(a.database).resolve())+"?mode=ro",uri=True)
report={"status":"research_only","cases":[]}
for case in cfg["cases"]:
 if case["name"] not in ("dendermonde","wieze"):continue
 west,south,east,north=case["bbox"]
 rows=db.execute("SELECT id,name,forward_kmh,backward_kmh FROM segments WHERE max(lat1,lat2)>=? AND min(lat1,lat2)<=? AND max(lon1,lon2)>=? AND min(lon1,lon2)<=?",(south,north,west,east)).fetchall()
 report["cases"].append({"name":case["name"],"segment_count":len(rows),"speed_distribution":{str(speed):sum(1 for r in rows if r[2]==speed) for speed in sorted(set(r[2] for r in rows))}})
db.close()
Path(a.output).write_text(json.dumps(report,indent=2)+"\n")
