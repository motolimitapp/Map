from pathlib import Path
import ijson
class Features:
 def __init__(self,path,count):self.path,self.count=path,count
 def __len__(self):return self.count
 def __iter__(self):
  seen=0
  with self.path.open('rb') as f:
   for feature in ijson.items(f,'features.item',use_float=True):seen+=1;yield feature
  if seen!=self.count:raise ValueError('Incomplete snapshot')
def load_snapshot(path):
 path=Path(path);result={}
 for key in ('crs','numberMatched','numberReturned','motolimiet_snapshot'):
  with path.open('rb') as f:result[key]=next(ijson.items(f,key,use_float=True))
 count=int(result['numberMatched'])
 if count<=0 or count!=int(result['numberReturned']):raise ValueError('Incomplete snapshot')
 result['features']=Features(path,count);return result
