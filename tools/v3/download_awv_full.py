"""Complete paginated AWV download with per-page checkpoints and validation."""
import concurrent.futures,datetime,gzip,hashlib,json,time,urllib.parse,urllib.request
from pathlib import Path
import sys,os
import ijson
from download_awv import ENDPOINT,LAYER
PAGE=50000
def page(start):
 params=dict(service='WFS',version='2.0.0',request='GetFeature',typeNames=LAYER,outputFormat='application/json',srsName='EPSG:3857',count=PAGE,startIndex=start)
 request=urllib.request.Request(ENDPOINT+'?'+urllib.parse.urlencode(params),headers={'Accept-Encoding':'gzip'})
 for attempt in range(4):
  try:
   with urllib.request.urlopen(request,timeout=180) as r:
    return json.load(gzip.GzipFile(fileobj=r) if r.headers.get('Content-Encoding','').lower()=='gzip' else r)
  except Exception:
   if attempt==3:raise
   time.sleep(2**attempt)
def fingerprint(features):return hashlib.sha256(json.dumps(features,sort_keys=True).encode()).hexdigest()
def download(output):
 output=Path(output);cache=output.with_suffix('.pages');cache.mkdir(exist_ok=True)
 if output.exists():raise ValueError('Output exists')
 first=page(0);total=int(first['numberMatched']);first_hash=fingerprint(first['features'])
 if not total:raise ValueError('Empty snapshot')
 identity=cache/'identity.json'
 if identity.exists():
  old=json.loads(identity.read_text())
  if old['total']!=total or old['first_hash']!=first_hash:raise ValueError('Source changed; use a new output/cache path')
 else:identity.write_text(json.dumps(dict(total=total,first_hash=first_hash,retrieved_utc=datetime.datetime.now(datetime.timezone.utc).isoformat())))
 def get(start):
  path=cache/f'{start}.json'
  if path.exists():return json.loads(path.read_text())
  p=first if start==0 else page(start)
  if int(p['numberMatched'])!=total or len(p['features'])!=min(PAGE,total-start) or int(p['numberReturned'])!=len(p['features']) or '3857' not in str(p.get('crs')):raise ValueError('Changed or truncated AWV page')
  part=path.with_suffix('.part');part.write_text(json.dumps(p,separators=(',',':')));part.replace(path);return p
 temporary=output.with_suffix('.part');ids=set()
 try:
  with temporary.open('w') as f:
   meta=dict(endpoint=ENDPOINT,layer=LAYER,bbox=None,number_matched=total,**json.loads(identity.read_text()))
   header=dict(type='FeatureCollection',crs=first['crs'],numberMatched=total,numberReturned=total,motolimiet_snapshot=meta)
   f.write(json.dumps(header)[:-1]+',"features":[')
   with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
    starts=iter(range(0,total,PAGE));pending={}
    for _ in range(3):
     start=next(starts,None)
     if start is not None:pending[start]=pool.submit(get,start)
    while pending:
     start=min(pending);p=pending.pop(start).result()
     if int(p['numberMatched'])!=total or len(p['features'])!=min(PAGE,total-start):raise ValueError('Invalid cached page')
     block=[]
     for feature in p['features']:
      if feature['id'] in ids:raise ValueError('Duplicate feature')
      ids.add(feature['id']);block.append(json.dumps(feature,separators=(',',':')))
     if start:f.write(',')
     f.write(','.join(block));f.flush();os.fsync(f.fileno())
     print(f'AWV {len(ids):,}/{total:,}',flush=True)
     new=next(starts,None)
     if new is not None:pending[new]=pool.submit(get,new)
   f.write(']}');f.flush();os.fsync(f.fileno())
  last=page(0)
  if int(last['numberMatched'])!=total or fingerprint(last['features'])!=first_hash:raise ValueError('Source changed during retrieval')
  if len(ids)!=total:raise ValueError('Incomplete snapshot')
  with temporary.open('rb') as f:
   if sum(1 for _ in ijson.items(f,'features.item'))!=total:raise ValueError('Written snapshot is incomplete')
  temporary.replace(output)
 finally:temporary.unlink(missing_ok=True)
if __name__=='__main__':download(sys.argv[1])
