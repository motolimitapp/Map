MISSING,OSM,AGREEMENT,AWV,LOCAL_RESTRICTION=0,1,2,3,4
CONFLICT,VARIABLE,AMBIGUOUS=10,11,12

def resolve(osm,state,evidence,can_fill):
 kind,value,sign,_=evidence
 if state==VARIABLE or kind=='variable':return 0,VARIABLE
 if kind=='ambiguous':return 0,AMBIGUOUS
 if kind!='fixed':return osm,state
 if osm:
  if osm==value:return osm,AGREEMENT
  if value==50 and sign in ('F1a','F1b') and osm<50:return osm,LOCAL_RESTRICTION
  return 0,CONFLICT
 return (value,AWV) if can_fill else (0,state)
