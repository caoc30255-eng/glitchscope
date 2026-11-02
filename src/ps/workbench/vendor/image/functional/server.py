import io,json,mimetypes,os,secrets,threading,time,zipfile
from contextlib import closing
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse,parse_qs,unquote
from labutil import *
from scans import make_plan,default_plan,aggregate,TARGETS
from controller import Store,live_submit
from render import svg_heatmap,csv_heatmap

ROOT=Path(__file__).resolve().parent
class Application:
    def __init__(self,workspace):
        self.workspace=Path(workspace).resolve();self.prepared=read(self.workspace/'prepared.json')
        require(sha((self.workspace/'real_records.json').read_bytes())==self.prepared['real_records_sha256'],'AUDITED_CACHE_CHANGED')
        require(sha((self.workspace/'image_repair/metrics.json').read_bytes())==self.prepared['image_metrics_sha256'],'IMAGE_METRICS_CHANGED')
        self.real=read(self.workspace/'real_records.json');self.store=Store(self.workspace);self.csrf=secrets.token_hex(24);self.shutdown=threading.Event()
        self.store.plan(default_plan(3));self.store.plan(default_plan(4))
    def worker(self):
        while not self.shutdown.wait(.08):
            for r in self.store.runs():
                if r['state']=='RUNNING':
                    try:self.store.step(r['run_id'])
                    except Exception as exc:
                        # Failure is durable and never resumes an in-progress experiment automatically.
                        with self.store.lock,closing(self.store.connect()) as c:
                            current=json.loads(c.execute('SELECT body FROM runs WHERE id=?',(r['run_id'],)).fetchone()[0])
                            if current['state']=='RUNNING':
                                current['state']='BLOCKED_ERROR';current['reason']=str(exc);c.execute('UPDATE runs SET body=? WHERE id=?',(canonical(current).decode(),r['run_id']));c.commit()
    def heatmap(self,plan_id,run_id=None):
        plan=self.store.get_plan(plan_id)
        if run_id:
            r=next((x for x in self.store.runs() if x['run_id']==run_id),None);require(r and r['plan_sha256']==plan_id,'RUN_PLAN')
            return aggregate(plan,r['records'],r['predictions'])
        return aggregate(plan,self.real)
    def status(self):
        return dict(csrf=self.csrf,runs=self.store.runs(),default_plans={str(d):default_plan(d) for d in (3,4)},
            evidence=dict(audited_records=77,unlocated_unknown=[r for r in self.real if r['status']=='UNKNOWN'],source='Approved v0.6 public-source review'),
            image_metrics=read(self.workspace/'image_repair/metrics.json'),
            algorithms=read(self.workspace/'algorithm/comparison.json') if (self.workspace/'algorithm/comparison.json').exists() else None,
            execution=dict(simulation_available=True,real_replay_available=True,live_executor_available=False,
                reason='Mainline new bounded scan executor / grid evidence / training authorization required'),hardware_access=False)

class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args):pass
    def send(self,data,kind='application/json',status=200,filename=None):
        raw=canonical(view(data)) if kind=='application/json' else data
        self.send_response(status);self.send_header('Content-Type',kind+'; charset=utf-8' if kind.startswith(('text/','application/json','image/svg')) else kind)
        self.send_header('Content-Length',str(len(raw)));self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff')
        if filename:self.send_header('Content-Disposition','attachment; filename="'+filename+'"')
        self.end_headers();self.wfile.write(raw)
    @property
    def app(self):return self.server.app
    def do_GET(self):
        try:
            url=urlparse(self.path);q=parse_qs(url.query)
            if url.path=='/api/state':return self.send(self.app.status())
            if url.path=='/api/plan':return self.send(self.app.store.get_plan(q['hash'][0]))
            if url.path=='/api/heatmap':return self.send(self.app.heatmap(q['plan'][0],q.get('run',[None])[0]))
            if url.path in ('/api/export.svg','/api/export.csv'):
                result=self.app.heatmap(q['plan'][0],q.get('run',[None])[0]);target=q.get('target',['B_frame_correct'])[0];require(target in TARGETS,'TARGET')
                if url.path.endswith('.svg'):return self.send(svg_heatmap(result,target),'image/svg+xml',filename=target+'.svg')
                return self.send(csv_heatmap(result),'text/csv',filename='scan_points.csv')
            if url.path=='/api/images.zip':
                buf=io.BytesIO()
                with zipfile.ZipFile(buf,'w',zipfile.ZIP_DEFLATED) as z:
                    for p in (self.app.workspace/'image_repair').rglob('*'):
                        if p.is_file():z.write(p,p.relative_to(self.app.workspace/'image_repair').as_posix())
                return self.send(buf.getvalue(),'application/zip',filename='image_repair_results.zip')
            if url.path.startswith('/artifacts/'):
                rel=Path(unquote(url.path[len('/artifacts/'):]))
                require(rel.parts and rel.parts[0] in ('image_repair','algorithm'),'ARTIFACT_SCOPE')
                root=self.app.workspace;p=(root/rel).resolve();require(root in p.parents and p.is_file(),'ARTIFACT_PATH')
                return self.send(p.read_bytes(),mimetypes.guess_type(str(p))[0] or 'application/octet-stream')
            rel='index.html' if url.path=='/' else unquote(url.path.lstrip('/'));root=ROOT/'web';p=(root/rel).resolve()
            require(root in p.parents and p.is_file(),'NOT_FOUND');return self.send(p.read_bytes(),mimetypes.guess_type(str(p))[0] or 'application/octet-stream')
        except Exception as exc:self.send(dict(error=str(exc)),status=400)
    def do_POST(self):
        try:
            require(self.headers.get('X-Lab-Token')==self.app.csrf,'LOCAL_SESSION_TOKEN')
            origin=self.headers.get('Origin');require(not origin or urlparse(origin).netloc==self.headers.get('Host'),'SAME_ORIGIN_REQUIRED')
            size=int(self.headers.get('Content-Length','0'));require(0<size<=65536,'REQUEST_SIZE')
            require(self.headers.get_content_type()=='application/json','JSON_REQUIRED');body=json.loads(self.rfile.read(size))
            if self.path=='/api/plan':
                plan=make_plan(bytes.fromhex(body.get('payload_hex',bytes(range(256)).hex())),body['phases'],body['widths'],
                    d=body['d'],s=body['s'],byte=body['byte'],bit=body['bit'],repeats=body['repeats'],budget=body['budget'],targets=body['targets'])
                return self.send(self.app.store.plan(plan))
            if self.path=='/api/start':
                require(body.get('origin')=='SIMULATED_DEVELOPMENT','LIVE_DISABLED; choose explicit development simulation')
                return self.send(self.app.store.start(body['plan_sha256'],body['seed'],body['strategy'],body['idempotency_key'],body.get('unknown_rate',0)))
            if self.path=='/api/stop':return self.send(self.app.store.stop(body['run_id'],body['idempotency_key']))
            if self.path=='/api/submit-mainline':live_submit(body)
            raise Rejected('API_NOT_FOUND')
        except Exception as exc:self.send(dict(error=str(exc),hardware_permission=False),status=409)

def serve(workspace,port=8765):
    workspace=output_path(workspace);require((workspace/'prepared.json').is_file(),'PREPARED_WORKSPACE_REQUIRED')
    lock=(workspace/'service.lock').open('a+b');lock.seek(0);app=None
    try:
        if os.name=='nt':
            import msvcrt
            lock.write(b'1');lock.flush();lock.seek(0);msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
        else:
            import fcntl
            fcntl.flock(lock.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
        app=Application(workspace)
        server=ThreadingHTTPServer(('127.0.0.1',port),Handler);server.app=app
        worker=threading.Thread(target=app.worker,daemon=True);worker.start()
        print('Functional lab: http://127.0.0.1:%d — simulation and real offline replay; live hardware disabled'%port,flush=True)
        server.serve_forever()
    finally:
        if app:app.shutdown.set()
        lock.close()
