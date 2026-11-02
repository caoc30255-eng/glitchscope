"""Pure constants for model statistics; not an execution plan or extra quota."""
import hashlib,json
CELLS=tuple(dict(point_id='p%d_w%d'%(p,w),phase=p,width=w)
    for p in (5,15,25,35) for w in (1,10,20,30,40) if p+w<=45)
BY_ID={c['point_id']:c for c in CELLS}
def digest(v):return hashlib.sha256(json.dumps(v,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False).encode('ascii')).hexdigest()
