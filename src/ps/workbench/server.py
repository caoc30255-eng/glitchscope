"""Local unified workbench. Every computation runs in a fresh bounded worker."""
import argparse,base64,hashlib,json,mimetypes,os,re,secrets,subprocess,sys,threading,time,uuid,zipfile
from pathlib import Path
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from urllib.parse import urlparse,unquote,parse_qs
from common import ROOT,raw,write,require,inside,verify,digest,sha
from demo_authority import Authority,LIVE_ACTIONS,FREE_ACTIONS,RULES,plan_limit

ACTIONS={'scan_preview','scan_replay','ai_predict','ai_suggest','image_preview','image_repair','ds_analysis','live_scan','live_image','approval_template','validate_plan'}
class App:
    def __init__(self,data,runs=None,live=None):
        self.data=Path(data).resolve();require(self.data!=ROOT and ROOT not in self.data.parents,'DATA_MUST_BE_OUTSIDE_DELIVERY')
        self.data.mkdir(parents=True,exist_ok=True);(self.data/'jobs').mkdir(exist_ok=True);(self.data/'uploads').mkdir(exist_ok=True)
        self.runs=Path(runs).resolve() if runs else None;self.live=live;self.token=secrets.token_hex(32);self.lock=threading.Lock();self.active={};self.authority=Authority.for_live(live) if live else Authority(self.data/'preview_authority')
    def sessions(self):
        items=[]
        if self.runs and self.runs.is_dir():
            for p in sorted(self.runs.glob('session_*'),reverse=True):
                if not p.is_dir():continue
                is_scan=(p/'CUSTOM_SCAN/scope/scope.json').is_file();source=p/'EXECUTOR/plan/source.bin'
                alias=None
                try:
                    label=json.loads((p/'DEMO_UI/session_label.json').read_bytes())
                    if label.get('session_name')==p.name:alias=label.get('session_alias')
                except (OSError,ValueError,TypeError,AttributeError):pass
                items.append(dict(id=p.name,alias=alias,scan=is_scan,image=not is_scan and source.is_file() and source.stat().st_size==16384,path=str(p)))
        return items
    def session_path(self,name):
        require(self.runs is not None and type(name) is str and name.startswith('session_') and '/' not in name and '\\' not in name,'REGISTERED_SESSION_REQUIRED')
        p=inside(self.runs,self.runs/name);require(p.is_dir(),'SESSION_NOT_FOUND');return str(p)
    def upload(self,v):
        # Accepted asset parser independently validates dimensions, headers, sizes and exact pixel bytes.
        from worker import bind
        bind('image');from image_service import Assets
        return Assets(self.data/'uploads').upload(v)
    def assets(self):
        from worker import bind
        bind('image');from image_service import Assets
        return Assets(self.data/'uploads').list()
    def plan_authorization(self,kind,plan):
        require(type(plan) is dict,'PLAN_OBJECT')
        status=self.authority.check_plan(kind,plan)
        status.update(plan_sha256=plan.get('sha256'),hardware_access=False,new_STARTs=0)
        if self.live is None and status['ready']:status.update(ready=False,state='PREVIEW_ONLY',reason='本轮预览范围内；真实执行需板侧工作台')
        return status
    def demo_status(self):
        try:return self.authority.status()
        except (ValueError,OSError,KeyError,TypeError) as e:return dict(mode=self.authority.mode,active_round=None,state='NEEDS_REVIEW',error=str(e),rules=RULES)
    def validate_hardware_plan(self,kind,plan):
        out=self.data/'plan_checks'/uuid.uuid4().hex;out.mkdir(parents=True)
        write(out/'request.json',dict(kind=kind,plan=plan))
        with (out/'console.log').open('wb') as log:
            p=subprocess.run([sys.executable,'-B',str(ROOT/'worker.py'),'validate_plan',str(out/'request.json'),str(out)],stdout=log,stderr=subprocess.STDOUT,cwd=str(ROOT),timeout=120)
        require(p.returncode==0 and (out/'result.json').is_file(),'PLAN_VALIDATION_FAILED')
        require(json.loads((out/'result.json').read_bytes()).get('status')=='VALIDATED_PLAN','PLAN_VALIDATION_FAILED')
    def submit(self,action,v):
        require(action in ACTIONS,'ACTION_NOT_ALLOWED');v=dict(v)
        if 'session' in v:v['session']=self.session_path(v['session'])
        if action=='ai_predict':require(type(v.get('queries')) is list and 1<=len(v['queries'])<=256,'QUERY_LIMIT_256')
        if action in ('image_preview','live_image'):
            asset_id=v.pop('asset_id')
            from worker import bind
            bind('image');from image_service import Assets
            asset=Assets(self.data/'uploads').read(asset_id)
            if action=='image_preview':v['source_sha256']=asset['metadata']['source_sha256']
            else:
                require(v['plan']['source_sha256']==asset['metadata']['source_sha256'],'PLAN_ASSET_CHANGED')
                v['source']=str(asset['folder']/'source.bin')
        if action.startswith('live_'):
            require(self.live is not None,'LIVE_NOT_CONFIGURED')
            require(type(v.get('session_alias')) is str,'SESSION_ALIAS_REQUIRED');v['session_alias']=v['session_alias'].strip()
            require(v.get('confirmation')=='执行本任务 %d 条'%plan_limit(LIVE_ACTIONS[action],v['plan']) and v.get('manual_7010_ready') is True and v.get('task_review_ack') is True,'START_CONFIRMATION_REQUIRED')
            permission=self.plan_authorization('scan' if action=='live_scan' else 'image',v['plan'])
            require(permission['ready'],'PLAN_NOT_AUTHORIZED: '+permission['reason'])
            self.validate_hardware_plan(LIVE_ACTIONS[action],v['plan'])
            require(v.get('round_id')==permission.get('round_id'),'ROUND_CHANGED_REVIEW_PLAN_AGAIN')
            v['live_config']=self.live
        if action=='approval_template':
            require(self.live is not None,'CONFIGURE_ASSETS_FIRST');v['live_config']=self.live
        with self.lock:
            running=[p for p in self.active.values() if p.poll() is None]
            require(len(running)<2,'TWO_ACTIVE_JOBS_MAX')
            if action.startswith('live_'):
                require(not any(p.poll() is None and key.startswith('live_') for key,p in self.active.items()),'LIVE_JOB_ALREADY_RUNNING')
            job=uuid.uuid4().hex;folder=self.data/'jobs'/job;reservation=None
            if action in LIVE_ACTIONS:
                reservation=self.authority.reserve(LIVE_ACTIONS[action],v['plan'],job,v.get('session_alias',''),expected_round=v['round_id'],task_confirmation=v['confirmation'],manual_ready=v['manual_7010_ready'],review_ack=v['task_review_ack'])
                v['demo_permit']=reservation['permit_path'];v['job_id']=job
            try:
                folder.mkdir();write(folder/'request.json',v)
                meta=dict(id=job,action=action,created=time.time(),source='LIVE' if action in LIVE_ACTIONS else 'SOFTWARE_OR_EVIDENCE',quota_consumes=action in LIVE_ACTIONS,quota_rule=RULES['hardware'] if action in LIVE_ACTIONS else RULES['software'],source_session=Path(v['session']).name if 'session' in v else None,session_name=None,session_alias=v.get('session_alias') if action in LIVE_ACTIONS else None)
                if reservation:meta.update(round_id=reservation['round_id'],quota_limit=reservation['max_records'])
                write(folder/'meta.json',meta)
                log=(folder/'console.log').open('wb')
                try:p=subprocess.Popen([sys.executable,'-B',str(ROOT/'worker.py'),action,str(folder/'request.json'),str(folder)],stdout=log,stderr=subprocess.STDOUT,cwd=str(ROOT))
                finally:log.close()
                self.active[action+':'+job]=p
            except BaseException as error:
                if reservation:self.authority.settle(job,'SOFTWARE_REJECTED',True,repr(error),block=False)
                raise
        return dict(id=job,action=action,state='RUNNING')
    def folder(self,job):
        require(type(job) is str and len(job)==32 and all(c in '0123456789abcdef' for c in job),'JOB_ID')
        p=inside(self.data/'jobs',self.data/'jobs'/job);require(p.is_dir(),'JOB_NOT_FOUND');return p
    def job(self,job,detail=False):
        folder=self.folder(job);v=json.loads((folder/'meta.json').read_bytes());v['state']='RUNNING'
        try:accounting=self.authority.task(job) if v.get('quota_consumes') else None
        except (ValueError,OSError,KeyError,TypeError) as error:accounting=None;v['accounting_error']=str(error)
        if accounting:v.update(accounting=accounting,session_name=accounting.get('session_name'),session_alias=accounting.get('session_alias'),session_path=accounting.get('session_path'))
        if (folder/'result.json').exists():v['state']='COMPLETE'
        elif (folder/'error.json').exists():v.update(state='BLOCKED',error=json.loads((folder/'error.json').read_bytes()))
        else:
            p=self.active.get(v['action']+':'+job)
            if p is None or p.poll() is not None:
                if accounting and not accounting['terminal'] and accounting.get('worker_alive') is True:v['state']='RUNNING'
                else:v.update(state='INTERRUPTED',reason='进程状态需核对，额度预留不会自动释放；不自动重试或续跑')
        if detail:
            if (folder/'result.json').exists():v['result']=json.loads((folder/'result.json').read_bytes())
            if (folder/'receipt.json').exists():v['receipt']=json.loads((folder/'receipt.json').read_bytes())
            if (folder/'live_cleanup.json').exists():v['cleanup']=json.loads((folder/'live_cleanup.json').read_bytes())
            events=folder/'events.jsonl';v['events']=[json.loads(s) for s in events.read_text(encoding='utf-8').splitlines(keepends=True)[-80:] if s.endswith('\n')] if events.exists() else []
            v['files']=[p.relative_to(folder).as_posix() for p in folder.rglob('*') if p.is_file() and p.suffix in ('.html','.csv','.svg','.png','.json') and p.name not in ('request.json','meta.json')]
        return v
    def jobs(self):
        return [self.job(p.name) for p in sorted((self.data/'jobs').iterdir(),key=lambda p:p.stat().st_mtime,reverse=True) if p.is_dir() and (p/'meta.json').is_file()][:100]

class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args):pass
    def send(self,value,status=200,ctype=None,script_hashes='',font_cache=False):
        data=value if isinstance(value,bytes) else raw(value);self.send_response(status)
        self.send_header('Content-Type',ctype or 'application/json; charset=utf-8');self.send_header('Content-Length',str(len(data)))
        self.send_header('Cache-Control','public, max-age=86400' if font_cache else 'no-store');self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('Content-Security-Policy',"default-src 'self' data: blob:; script-src 'self' "+script_hashes+"; style-src 'self' 'unsafe-inline'; connect-src 'self'; object-src 'none'; frame-ancestors 'self'; base-uri 'none'")
        self.end_headers();self.wfile.write(data)
    @property
    def app(self):return self.server.app
    def do_GET(self):
        try:
            require(self.headers.get('Host') in self.server.allowed_hosts,'HOST_REJECTED')
            path=unquote(urlparse(self.path).path);q=parse_qs(urlparse(self.path).query)
            if path=='/api/status':return self.send(dict(version='GLITCHSCOPE_DEMO_V2_0_1',token=self.app.token,live_configured=bool(self.app.live),sessions=self.app.sessions(),jobs=self.app.jobs(),assets=self.app.assets(),approved_trials_in_delivery=0,demo=self.app.demo_status()))
            if path.startswith('/api/jobs/'):return self.send(self.app.job(path.split('/')[-1],True))
            if path=='/api/demo-round/status':return self.send(self.app.demo_status())
            if path=='/api/samples':return self.send(json.loads((ROOT/'samples/catalog.json').read_bytes()))
            if path.startswith('/samples/'):
                p=inside(ROOT/'samples',ROOT/path.lstrip('/'));return self.file(p)
            if path.startswith('/upload/'):
                parts=path.split('/');require(len(parts)==4 and parts[3]=='source.png','ASSET_IMAGE_ONLY')
                require(len(parts[2])==64 and all(c in '0123456789abcdef' for c in parts[2]),'ASSET_ID')
                p=inside(self.app.data/'uploads',self.app.data/'uploads'/parts[2]/'source.png');return self.file(p)
            if path.startswith('/output/'):
                parts=path.split('/');folder=self.app.folder(parts[2]);p=inside(folder,folder/'/'.join(parts[3:]));require(p.suffix in ('.html','.js','.css','.svg','.png','.csv','.json','.bin'),'OUTPUT_TYPE')
                require(p.name not in ('request.json','meta.json'),'PRIVATE_JOB_CONFIG');return self.file(p)
            if path.startswith('/export/'):
                folder=self.app.folder(path.split('/')[-1]);require(self.app.job(folder.name)['state']!='RUNNING','WAIT_FOR_TERMINAL_STATE')
                target=self.app.data/(folder.name+'.zip')
                with zipfile.ZipFile(target,'w',zipfile.ZIP_DEFLATED) as z:
                    inventory={}
                    for p in folder.rglob('*'):
                        if p.is_file() and p.name!='request.json':
                            name=p.relative_to(folder).as_posix();data=p.read_bytes();z.writestr(name,data)
                            inventory[name]=dict(bytes=len(data),sha256=hashlib.sha256(data).hexdigest())
                    z.writestr('EXPORT_manifest.json',raw(dict(schema='GLITCHSCOPE_OUTPUT_EXPORT_V1',files=inventory,complete_raw_session_included=False,original_session_retained_separately=True)))
                return self.send(target.read_bytes(),ctype='application/zip')
            p=inside(ROOT/'web',ROOT/'web'/('index.html' if path=='/' else path.lstrip('/')));return self.file(p)
        except (ValueError,KeyError,OSError) as e:self.send(dict(error=str(e)),404)
    def file(self,p):
        require(p.is_file(),'NOT_FOUND');data=p.read_bytes();hashes=''
        if p.suffix=='.html':
            # Browser HTML parsing normalizes CRLF/CR before computing script hashes.
            hashes=' '.join("'sha256-"+base64.b64encode(hashlib.sha256(m.replace(b'\r\n',b'\n').replace(b'\r',b'\n')).digest()).decode('ascii')+"'" for m in re.findall(rb'<script(?:\s[^>]*)?>([\s\S]*?)</script>',data) if m.strip())
        return self.send(data,ctype={'.js':'application/javascript; charset=utf-8','.html':'text/html; charset=utf-8','.css':'text/css; charset=utf-8','.json':'application/json; charset=utf-8','.woff2':'font/woff2','.ttf':'font/ttf'}.get(p.suffix,mimetypes.guess_type(str(p))[0] or 'application/octet-stream'),script_hashes=hashes,font_cache=p.suffix in ('.woff2','.ttf'))
    def do_POST(self):
        try:
            require(self.headers.get('Host') in self.server.allowed_hosts,'HOST_REJECTED')
            origin=self.headers.get('Origin');require(origin is None or origin in ['http://'+h for h in self.server.allowed_hosts],'CROSS_ORIGIN_REJECTED')
            require(self.headers.get('X-Workbench-Token')==self.app.token,'REQUEST_TOKEN_REQUIRED')
            require(self.headers.get('Content-Type','').split(';')[0]=='application/json','JSON_REQUIRED')
            n=int(self.headers.get('Content-Length','0'));require(0<n<=13*1024*1024,'BODY_TOO_LARGE')
            v=json.loads(self.rfile.read(n));path=urlparse(self.path).path
            if path=='/api/demo-round/create':return self.send(self.app.authority.create_round(v['budget'],v['scope'],v['operator'],v['confirmation'],v['acknowledged']))
            if path=='/api/demo-round/top-up':return self.send(self.app.authority.top_up(v['round_id'],v['amount'],v['confirmation']))
            if path=='/api/demo-round/close':return self.send(self.app.authority.close_round(v['round_id'],v['confirmation']))
            if path=='/api/upload':return self.send(self.app.upload(v))
            if path=='/api/authorization-status':return self.send(self.app.plan_authorization(v['kind'],v['plan']))
            if path=='/api/jobs':return self.send(self.app.submit(v['action'],v['request']),202)
            if path=='/api/stop':
                folder=self.app.folder(v['id']);require(self.app.job(v['id'])['state'] in ('RUNNING','INTERRUPTED'),'TERMINAL_NO_RESUME')
                if not (folder/'STOP_REQUESTED').exists():write(folder/'STOP_REQUESTED',dict(requested=True))
                return self.send(dict(state='STOP_REQUESTED',note='Current record finishes or faults; no retry or global reset'))
            raise ValueError('ENDPOINT_NOT_FOUND')
        except (ValueError,KeyError,OSError) as e:self.send(dict(error=str(e)),400)
def create(data,runs=None,live=None,port=0,forwarded_ports=(18768,)):
    server=ThreadingHTTPServer(('127.0.0.1',port),Handler);server.app=App(data,runs,live)
    server.allowed_hosts={'127.0.0.1:'+str(server.server_port),'localhost:'+str(server.server_port)}
    for browser_port in forwarded_ports:
        require(type(browser_port) is int and 1<=browser_port<=65535,'FORWARDED_PORT_RANGE')
        server.allowed_hosts.update({'127.0.0.1:'+str(browser_port),'localhost:'+str(browser_port)})
    return server
def main():
    p=argparse.ArgumentParser();p.add_argument('--port',type=int,default=8778);p.add_argument('--data',default=str(ROOT.parent/'glitchscope_workbench_data'));p.add_argument('--runs');p.add_argument('--live-config');p.add_argument('--forwarded-port',type=int,action='append',default=[18768]);a=p.parse_args()
    verify();live=json.loads(Path(a.live_config).read_bytes()) if a.live_config else None
    if live:require(a.runs and Path(live['runs']).resolve()==Path(a.runs).resolve(),'LIVE_RUNS_BINDING')
    s=create(a.data,a.runs,live,a.port,tuple(a.forwarded_port));print('GLITCHSCOPE http://127.0.0.1:%d/  · Ctrl+C停止网页服务'%s.server_port,flush=True)
    try:s.serve_forever()
    except KeyboardInterrupt:pass
    finally:s.server_close()
if __name__=='__main__':main()
