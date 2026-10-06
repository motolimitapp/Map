import argparse,json,sqlite3
from pathlib import Path
def validate(source,output,full=False):
 db=sqlite3.connect(Path(output).resolve().as_uri()+'?mode=ro',uri=True)
 try:
  db.execute('ATTACH DATABASE ? AS original',(Path(source).resolve().as_uri()+'?mode=ro',))
  meta=dict(db.execute('SELECT key,value FROM metadata'))
  if meta.get('format')!='motolimiet-3' or meta.get('quality_schema')!='1' or meta.get('conflict_check')!='osm-awv-1':raise ValueError('Missing comparison metadata')
  snapshot=json.loads(meta['awv_snapshot'])
  if full and (snapshot.get('bbox') is not None or not snapshot.get('retrieved_utc') or int(snapshot.get('number_matched',0))<500000):raise ValueError('Not a complete AWV snapshot')
  if full and db.execute('SELECT count(*) FROM segments').fetchone()[0]<3000000:raise ValueError('Incomplete Belgium map')
  checks={
   'uncertain_numeric':"SELECT count(*) FROM segments s JOIN segment_quality q ON s.id=q.segment_id WHERE (q.forward_state IN (0,10,11,12) AND s.forward_kmh!=0) OR (q.backward_state IN (0,10,11,12) AND s.backward_kmh!=0)",
   'invalid_states':"SELECT count(*) FROM segment_quality WHERE forward_state NOT IN (0,1,2,3,4,10,11,12) OR backward_state NOT IN (0,1,2,3,4,10,11,12)",
   'known_without_number':"SELECT count(*) FROM segments s JOIN segment_quality q ON s.id=q.segment_id WHERE (q.forward_state BETWEEN 1 AND 4 AND s.forward_kmh<=0) OR (q.backward_state BETWEEN 1 AND 4 AND s.backward_kmh<=0)",
   'missing_quality':"SELECT count(*) FROM segments s LEFT JOIN segment_quality q ON s.id=q.segment_id WHERE q.segment_id IS NULL",
   'missing_tiles':"SELECT count(*) FROM segments s LEFT JOIN tiles t ON s.id=t.id WHERE t.id IS NULL",
   'missing_original':"SELECT count(*) FROM original.segments o LEFT JOIN segments s ON s.id=o.id WHERE s.id IS NULL",
   'original_evidence_changed':"SELECT count(*) FROM quality_changes c JOIN segment_quality q ON q.segment_id=c.segment_id JOIN original.segments o ON o.id=c.original_segment_id WHERE q.osm_forward!=o.forward_kmh OR q.osm_backward!=o.backward_kmh",
   'numeric_osm_replaced_by_other_number':"SELECT count(*) FROM segments s JOIN segment_quality q ON s.id=q.segment_id WHERE (q.osm_forward>0 AND s.forward_kmh>0 AND q.osm_forward!=s.forward_kmh) OR (q.osm_backward>0 AND s.backward_kmh>0 AND q.osm_backward!=s.backward_kmh)"}
  result={name:db.execute(sql).fetchone()[0] for name,sql in checks.items()}
  if any(result.values()):raise ValueError(json.dumps(result))
  if db.execute('PRAGMA quick_check').fetchone()[0]!='ok':raise ValueError('SQLite integrity failure')
  if Path(output).stat().st_size>1024**3:raise ValueError('Map exceeds app size limit')
  print(json.dumps(result,indent=2));return result
 finally:db.close()
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('source');p.add_argument('output');p.add_argument('--full',action='store_true');a=p.parse_args();validate(a.source,a.output,a.full)
