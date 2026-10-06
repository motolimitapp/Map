"""Compare immutable OSM v3 and complete directed AWV evidence offline."""
import argparse
from collections import Counter
import datetime,hashlib,json,math,sqlite3
from pathlib import Path
from shapely.geometry import LineString,Point
from enrich_awv import AwvIndex,TO_LOCAL,MAX_DISTANCE,MAX_ANGLE,SAMPLE_STEP
from quality_policy import resolve,VARIABLE,CONFLICT,AMBIGUOUS
from awv_snapshot import load_snapshot

class EvidenceIndex(AwvIndex):
 def __init__(self,data):
  super().__init__(data);self.edges=[]
  for line,entry in zip(self.lines,self.entries):
   a,b=line.coords;dx,dy=b[0]-a[0],b[1]-a[1]
   self.edges.append((a[0],a[1],b[0],b[1],dx,dy,math.hypot(dx,dy),entry))
 def at(self,point,dx,dy,indices):return self.at_xy(point.x,point.y,dx,dy,indices)
 def at_xy(self,x,y,dx,dy,indices,aligned=False):
  candidates=[];heading_length=math.hypot(dx,dy)
  for i in indices:
   ax,ay,bx,by,ex,ey,length,entry=self.edges[i];_,feature,road,first,last=entry
   projection=((x-ax)*ex+(y-ay)*ey)/(length*length)
   if (projection< -1e-7 and first) or (projection>1+1e-7 and last):continue
   if not aligned and (dx*ex+dy*ey)/(heading_length*length)<math.cos(math.radians(MAX_ANGLE)):continue
   t=max(0.,min(1.,projection));distance=math.hypot(x-ax-t*ex,y-ay-t*ey)
   if distance<=MAX_DISTANCE:candidates.append((distance,i,feature,road))
  if not candidates:return 'absent',0,'',''
  candidates.sort();best=candidates[0];near=[c for c in candidates if c[0]<=best[0]+4]
  evidence=[self.evidence[c[2]] for c in near];known=[e for e in evidence if e[0] in ('fixed','variable')]
  if not known:return 'unproven',0,'',best[2]
  if any(e[0]=='variable' for e in known):return next(e for e in known if e[0]=='variable')
  for c,e in zip(near,evidence):
   if e[0]!='fixed' or e[1]!=known[0][1]:return 'ambiguous',0,'',best[2]
   if c[3]!=best[3]:
    a,b=self.edges[c[1]],self.edges[best[1]]
    if min(math.hypot(a[2]-b[0],a[3]-b[1]),math.hypot(b[2]-a[0],b[3]-a[1]))>=.1:return 'ambiguous',0,'',best[2]
  return next((e for e in known if e[2] in ('C43','ZC43')),known[0])
 def quality_pieces(self,row,states,can_fill):
  a,b=TO_LOCAL(row[2],row[1]),TO_LOCAL(row[4],row[3]);line=LineString((a,b))
  indices=[int(i) for i in self.tree.query(line.buffer(MAX_DISTANCE))]
  original=(row[5],row[6],states[0],states[1],'','')
  if not indices or line.length<1:return [(0.,1.,*original)]
  if not any(self.evidence[self.entries[i][1]][0] in ('fixed','variable') for i in indices):return [(0.,1.,*original)]
  dx,dy=b[0]-a[0],b[1]-a[1];cuts={0.,1.};length=math.hypot(dx,dy);cosine=math.cos(math.radians(MAX_ANGLE))
  aligned={d:[i for i in indices if d*(dx*self.edges[i][4]+dy*self.edges[i][5])/(length*self.edges[i][6])>=cosine] for d in (1,-1)}
  for i in indices:
   for xy in (self.edges[i][:2],self.edges[i][2:4]):
    t=((xy[0]-a[0])*dx+(xy[1]-a[1])*dy)/(dx*dx+dy*dy)
    if 0<t<1:cuts.add(t)
  count=math.ceil(length/SAMPLE_STEP);cuts.update(i/count for i in range(1,count));cuts=sorted(cuts);pieces=[]
  for lo,hi in zip(cuts,cuts[1:]):
   results=[]
   for d,osm,oldstate in ((1,row[5],states[0]),(-1,row[6],states[1])):
    if row[7] and d==-1:results.append((osm,oldstate,''));continue
    samples=[self.at_xy(a[0]+dx*(lo+(hi-lo)*f),a[1]+dy*(lo+(hi-lo)*f),dx*d,dy*d,aligned[d],True) for f in (.1,.5,.9)]
    resolved=[resolve(osm,oldstate,e,can_fill) for e in samples]
    if all(r==resolved[0] for r in resolved):value,state=resolved[0]
    else:value,state=0,VARIABLE if any(r[1]==VARIABLE for r in resolved) else AMBIGUOUS
    results.append((value,state,'|'.join(sorted({e[3] for e in samples if e[3]}))))
   state=(results[0][0],results[1][0],results[0][1],results[1][1],results[0][2],results[1][2])
   if pieces and pieces[-1][2:6]==state[:4]:
    old=pieces[-1];refs=['|'.join(sorted(set(filter(None,(old[6+i]+'|'+state[4+i]).split('|'))))) for i in range(2)]
    pieces[-1]=(old[0],hi,*state[:4],*refs)
   else:pieces.append((lo,hi,*state))
  if any((p[1]-p[0])*length<1 for p in pieces):
   values=[];qualities=[];refs=[]
   for d in range(2):
    uncertain=[p[4+d] for p in pieces if p[4+d]>=10]
    qualities.append((VARIABLE if VARIABLE in uncertain else CONFLICT if CONFLICT in uncertain else AMBIGUOUS) if uncertain else states[d])
    values.append(0 if uncertain else row[5+d]);refs.append('|'.join(sorted({r for p in pieces for r in p[6+d].split('|') if r})))
   return [(0.,1.,*values,*qualities,*refs)]
  return pieces

_WORKER_INDEX=None

def calculate(extended):
 row=extended[:9];way,eligible,fs,bs=extended[9:]
 return extended,_WORKER_INDEX.quality_pieces(row,(fs,bs),bool(eligible))

def digest_file(path):
 with Path(path).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()

def build(source,snapshot,destination,report,workers=1,checkpoint_every=10000):
 """Atomic publication; committed .part checkpoints can be resumed with identical inputs/code."""
 import multiprocessing
 global _WORKER_INDEX
 source,snapshot,destination,report=map(Path,(source,snapshot,destination,report));temp=destination.with_suffix('.part')
 if destination.exists() or report.exists():raise ValueError('Final output exists')
 if workers<1 or checkpoint_every<1:raise ValueError('Positive workers/checkpoint interval required')
 identity=dict(source=digest_file(source),snapshot=digest_file(snapshot),code=hashlib.sha256(b''.join(Path(__file__).with_name(n).read_bytes() for n in ('build_quality_map.py','enrich_awv.py','quality_policy.py','awv_snapshot.py'))).hexdigest())
 if temp.exists():
  check=sqlite3.connect(temp)
  try:
   saved=json.loads(check.execute('SELECT value FROM build_checkpoint WHERE key="state"').fetchone()[0])
   if saved['identity']!=identity:raise ValueError('Checkpoint inputs or code differ; use a separate output path')
  finally:check.close()
 else:saved=dict(identity=identity,last_id=0,statistics={})
 data=load_snapshot(snapshot);metadata=dict(data['motolimiet_snapshot']);metadata['number_matched']=data['numberMatched']
 print('Building AWV index',flush=True);index=EvidenceIndex(data);del data;print('Index ready',len(index.lines),flush=True)
 _WORKER_INDEX=index;pool=None
 if workers>1:pool=multiprocessing.get_context('fork').Pool(workers)
 src=sqlite3.connect(source.resolve().as_uri()+'?mode=ro',uri=True,check_same_thread=False);dst=None;stats=Counter(saved['statistics'])
 try:
  meta=dict(src.execute('SELECT key,value FROM metadata'))
  if meta.get('format')!='motolimiet-3' or meta.get('conflict_check')!='osm-only':raise ValueError('Fresh v3 OSM source required')
  fresh=not temp.exists();dst=sqlite3.connect(temp)
  if fresh:
   src.backup(dst)
   dst.execute('CREATE TABLE awv_features(id INTEGER PRIMARY KEY,feature_id TEXT UNIQUE NOT NULL,kind TEXT NOT NULL,speed INTEGER,sign TEXT)')
   dst.execute('CREATE TABLE quality_changes(segment_id INTEGER PRIMARY KEY,original_segment_id INTEGER NOT NULL)')
   dst.execute('CREATE TABLE build_checkpoint(key TEXT PRIMARY KEY,value TEXT NOT NULL)')
   dst.execute('INSERT INTO build_checkpoint VALUES (?,?)',('state',json.dumps(saved)));dst.commit()
  evidence_ids={ref:key for key,ref in dst.execute('SELECT id,feature_id FROM awv_features')}
  def compact(refs):
   result=[]
   for ref in filter(None,refs.split('|')):
    if ref not in evidence_ids:
     key=len(evidence_ids)+1;evidence_ids[ref]=key;e=index.evidence[ref]
     dst.execute('INSERT INTO awv_features VALUES (?,?,?,?,?)',(key,ref,e[0],e[1],e[2]))
    result.append(str(evidence_ids[ref]))
   return '|'.join(result)
  maximum=dst.execute('SELECT max(id) FROM segments').fetchone()[0]
  def checkpoint(last_id):
   state=dict(identity=identity,last_id=last_id,statistics=dict(stats))
   dst.execute('UPDATE build_checkpoint SET value=? WHERE key="state"',(json.dumps(state),));dst.commit()
   print('Checkpoint',last_id,dict(stats),flush=True)
  rows=src.execute('SELECT s.*,p.osm_way_id,p.awv_eligible,q.forward_state,q.backward_state FROM segments s JOIN osm_provenance p ON p.segment_id=s.id JOIN segment_quality q ON q.segment_id=s.id WHERE s.id>? AND p.comparable=1 AND lat1 BETWEEN 50.65 AND 51.55 AND lon1 BETWEEN 2.5 AND 5.95 ORDER BY s.id',(saved['last_id'],))
  results=pool.imap(calculate,rows,chunksize=64) if pool else map(calculate,rows)
  last_id=saved['last_id']
  for extended,pieces in results:
   row=extended[:9];way,eligible,fs,bs=extended[9:];stats['compared_edges']+=1;last_id=row[0]
   if pieces!=[(0.,1.,row[5],row[6],fs,bs,'','')]:
    stats['annotated_edges']+=1
    for table,key in [('segments','id'),('tiles','id'),('osm_provenance','segment_id'),('segment_quality','segment_id')]:dst.execute(f'DELETE FROM {table} WHERE {key}=?',(row[0],))
    for n,(lo,hi,fw,bw,fstate,bstate,fr,br) in enumerate(pieces):
     if n:maximum+=1
     sid=maximum if n else row[0]
     lat1=row[1]+(row[3]-row[1])*lo;lon1=row[2]+(row[4]-row[2])*lo;lat2=row[1]+(row[3]-row[1])*hi;lon2=row[2]+(row[4]-row[2])*hi
     dst.execute('INSERT INTO segments VALUES (?,?,?,?,?,?,?,?,?)',(sid,lat1,lon1,lat2,lon2,fw,bw,row[7],row[8]))
     tile=math.floor((lat1+lat2)*100)*100000+math.floor((lon1+lon2)*100)+36000
     dst.execute('INSERT INTO tiles VALUES (?,?)',(sid,tile));dst.execute('INSERT INTO osm_provenance VALUES (?,?,?,?)',(sid,way,eligible,1))
     dst.execute('INSERT INTO segment_quality VALUES (?,?,?,?,?,?,?)',(sid,fstate,bstate,row[5],row[6],compact(fr),compact(br)))
     dst.execute('INSERT INTO quality_changes VALUES (?,?)',(sid,row[0]))
   if stats['compared_edges']%checkpoint_every==0:checkpoint(last_id)
  if not stats['annotated_edges']:raise ValueError('No AWV evidence accepted')
  checkpoint(last_id)
  dst.executemany('INSERT OR REPLACE INTO metadata VALUES (?,?)',[('built_utc',datetime.datetime.now(datetime.timezone.utc).isoformat()),('osm_built_utc',meta['built_utc']),('source',meta['source']+'; Bron: MOW - AWV'),('conflict_check','osm-awv-1'),('awv_snapshot_sha256',identity['snapshot']),('awv_snapshot',json.dumps(metadata))]);dst.commit()
  if dst.execute('PRAGMA quick_check').fetchone()[0]!='ok':raise ValueError('Invalid SQLite database')
  stats['quality_directions']=dict(dst.execute('SELECT state,count(*) FROM (SELECT forward_state state FROM segment_quality UNION ALL SELECT backward_state FROM segment_quality) GROUP BY state'))
  report.write_text(json.dumps(dict(policy='osm-awv-1',snapshot=metadata,sha256=identity['snapshot'],statistics=dict(stats)),indent=2)+'\n')
  dst.close();dst=None;temp.replace(destination);print(dict(stats),flush=True)
 finally:
  if pool:pool.terminate();pool.join()
  src.close()
  if dst:dst.close()
  _WORKER_INDEX=None
if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__)
 for name in ('source','snapshot','output','report'):p.add_argument(name)
 p.add_argument('--workers',type=int,default=1);p.add_argument('--checkpoint-every',type=int,default=10000)
 a=p.parse_args();build(a.source,a.snapshot,a.output,a.report,a.workers,a.checkpoint_every)
