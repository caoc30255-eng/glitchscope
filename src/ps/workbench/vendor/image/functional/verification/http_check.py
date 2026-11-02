import json,sys,uuid,urllib.request,urllib.error
from pathlib import Path
url=sys.argv[1];origin=url.rstrip('/');report=[]
def get(path):return urllib.request.urlopen(origin+path).read()
state=json.loads(get('/api/state'));token=state['csrf']
def post(path,body):
    req=urllib.request.Request(origin+path,data=json.dumps(body).encode(),headers={'Content-Type':'application/json','X-Lab-Token':token,'Origin':origin})
    return json.loads(urllib.request.urlopen(req).read())
p=state['default_plans']['3'];pid=p['plan_sha256']
assert b'<svg' in get('/api/export.svg?plan='+pid)
assert b'phase_tick' in get('/api/export.csv?plan='+pid)
assert get('/api/images.zip').startswith(b'PK')
body={'origin':'SIMULATED_DEVELOPMENT','plan_sha256':pid,'seed':99,'strategy':'grid','idempotency_key':uuid.uuid4().hex,'unknown_rate':0}
first=post('/api/start',body);second=post('/api/start',body);assert first==second
run=first['run_id'];stopped=post('/api/stop',{'run_id':run,'idempotency_key':uuid.uuid4().hex})
assert stopped['state']=='STOPPED' and stopped['cancelled_unstarted']>0
body.update(idempotency_key=uuid.uuid4().hex,unknown_rate=.5)
unknown=post('/api/start',body)
import time
for _ in range(30):
    current=json.loads(get('/api/state'));r=next(r for r in current['runs'] if r['run_id']==unknown['run_id'])
    if r['state']!='RUNNING':break
    time.sleep(.1)
assert r['state']=='BLOCKED_UNKNOWN' and r['used_starts']>0
try:post('/api/submit-mainline',{})
except urllib.error.HTTPError as e:assert e.code==409 and b'MAINLINE' in e.read()
else:raise AssertionError('Live entry must remain blocked')
report={'status':'PASS','exports':['SVG','CSV','image ZIP'],'idempotent_start':True,'stop_cancelled_unstarted':stopped['cancelled_unstarted'],
        'UNKNOWN_blocks_and_consumes':True,'live_entry_rejected':True,'target':origin,'hardware_access':False}
Path(sys.argv[2]).write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps(report))
