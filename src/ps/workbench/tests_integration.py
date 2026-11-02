"""HTTP/worker and refusal tests. No PYNQ, Overlay, MMIO or hardware service."""
import ast,base64,copy,hashlib,http.client,json,sys,tempfile,threading,time,unittest
from pathlib import Path
from common import ROOT,verify
from server import create

class Integration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base=Path(tempfile.mkdtemp(prefix='unified_http_test_',dir=str(ROOT.parent)))
        cls.s=create(cls.base/'data');cls.thread=threading.Thread(target=cls.s.serve_forever,daemon=True);cls.thread.start()
        _,s=cls.http('GET','/api/status');cls.token=s['token']
    @classmethod
    def tearDownClass(cls):cls.s.shutdown();cls.s.server_close();print('Retained software test artifacts:',cls.base)
    @classmethod
    def http(cls,method,path,v=None,headers=None):
        c=http.client.HTTPConnection('127.0.0.1',cls.s.server_port,timeout=20)
        h={'Content-Type':'application/json','X-Workbench-Token':getattr(cls,'token','')};h.update(headers or {})
        c.request(method,path,json.dumps(v).encode() if v is not None else None,h);r=c.getresponse();data=r.read();status=r.status;c.close()
        try:data=json.loads(data)
        except (ValueError,UnicodeDecodeError):pass
        return status,data
    def job(self,action,request):
        status,v=self.http('POST','/api/jobs',dict(action=action,request=request));self.assertEqual(status,202,v)
        for _ in range(100):
            _,j=self.http('GET','/api/jobs/'+v['id'])
            if j['state']!='RUNNING':return j
            time.sleep(.1)
        self.fail('Worker timeout')
    def test_01_manifest_and_python38(self):
        self.assertGreater(verify(),700)
        for p in ROOT.glob('*.py'):ast.parse(p.read_text(encoding='utf-8'),feature_version=(3,8))
    def test_01b_notebook_output_changes_do_not_change_code(self):
        from common import notebook_code
        original=(ROOT/'workbench.ipynb').read_bytes();nb=json.loads(original)
        cell=next(c for c in nb['cells'] if c['cell_type']=='code');cell['outputs']=[dict(output_type='stream',name='stdout',text=['checked'])];cell['execution_count']=1
        self.assertEqual(notebook_code(original),notebook_code(json.dumps(nb).encode()))
        cell['source'].append('\nprint("changed code")')
        self.assertNotEqual(notebook_code(original),notebook_code(json.dumps(nb).encode()))
    def test_02_real_samples_and_inline_report_csp(self):
        code,v=self.http('GET','/samples/c_reference44.json');self.assertEqual(code,200)
        self.assertEqual(v['statistics']['valid_records'],44)
        c=http.client.HTTPConnection('127.0.0.1',self.s.server_port);c.request('GET','/samples/ds64/report.html');r=c.getresponse()
        self.assertIn('sha256-',r.getheader('Content-Security-Policy'));self.assertIn(b'<script',r.read());c.close()
    def test_02b_native_viewer_and_fonts(self):
        code,data=self.http('GET','/samples/ds64/viewer_data.json');self.assertEqual(code,200);self.assertEqual(len(data['items']),64)
        c=http.client.HTTPConnection('127.0.0.1',self.s.server_port);c.request('GET','/fonts/intervariable.woff2');r=c.getresponse()
        self.assertEqual(r.status,200);self.assertEqual(r.getheader('Content-Type'),'font/woff2');self.assertEqual(r.read()[:4],b'wOF2');c.close()
        code,data=self.http('GET','/');self.assertEqual(code,200);self.assertNotIn(b'<iframe',data);self.assertNotIn(b'reference.css',data);self.assertIn(b'presentation.css',data)

    def test_03_csrf_and_host_refusal(self):
        code,_=self.http('POST','/api/jobs',dict(action='train',request={}),{'X-Workbench-Token':'wrong'});self.assertEqual(code,400)
        code,_=self.http('GET','/api/status',headers={'Host':'evil.example'});self.assertEqual(code,404)
        code,_=self.http('POST','/api/jobs',dict(action='train',request={}));self.assertEqual(code,400)
    def test_04_scan_preview_and_changed_illegal(self):
        r=dict(receiver_B=dict(d=2,s=1),mode='TYPE3A_SINGLE',fault=dict(byte=24,bit=2,count=1),scan=dict(points=[dict(phase=7,width=3)]),repeats=3,max_records=5,target='B_frame_correct')
        j=self.job('scan_preview',dict(request=r,strategy='sequential'));self.assertEqual(j['state'],'COMPLETE');self.assertEqual(j['result']['status'],'ACCEPTED')
        r['scan']['points'][0]['width']=44
        j=self.job('scan_preview',dict(request=r));self.assertIsNone(j['result']['plan']);self.assertTrue(j['result']['rejected_conditions'])
    def test_05_native_model_predict_and_refusal(self):
        q=dict(schema='EDGE_AI_QUERY_V1',receiver_B=dict(d=3,s=-1),mode='TYPE3A_SINGLE',fault=dict(byte=20,bit=0,count=1,phase=15,width=10),route_mode=0,target='B_frame_correct',payload_sha256=hashlib.sha256(bytes(range(256))).hexdigest())
        unknown=copy.deepcopy(q);unknown['receiver_B']['d']=2;unknown['receiver_B']['s']=1
        j=self.job('ai_predict',dict(queries=[q,unknown]));self.assertEqual(j['state'],'COMPLETE',j.get('error'))
        p=j['result']['predictions'];self.assertIsNotNone(p[0]['score']);self.assertIsNone(p[1]['score'])
    def test_06_upload_and_all_fourteen_uniform_profiles(self):
        from worker import bind
        bind('image');from image_service import gray_png
        raw=bytes(range(256))*64;png=gray_png(raw);body=dict(filename='in-memory-test.png',original_base64=base64.b64encode(png).decode(),raw_base64=base64.b64encode(raw).decode(),transform=dict(width=128,height=128,original_width=128,original_height=128,fit='contain',conversion='BROWSER_CANVAS_BT601_ROUND'))
        code,a=self.http('POST','/api/upload',body);self.assertEqual(code,200,a)
        r=dict(asset_id=a['asset_id'],receiver_B=dict(d=4,s=-2),seed=20261018,fault_mode='random',fixed_fault=None)
        j=self.job('image_preview',r);self.assertEqual(j['state'],'COMPLETE',j.get('error'));p=j['result']['plan']
        self.assertEqual(len(p['items']),64);self.assertEqual({tuple(i['receiver_B'].values()) for i in p['items']},{(4,-2)})
        self.assertEqual(p['CONFIG_receiver_B'],dict(d=3,s=-1))
        from worker import image_bind
        image_bind()
        from image_plan import schedule,validate
        r.pop('asset_id');r['source_sha256']=a['source_sha256']
        for d in range(1,5):
            for s in range(-2,4-d):
                r['receiver_B']=dict(d=d,s=s);v=schedule(r);self.assertTrue(validate(v));self.assertEqual(len(v['items']),64)
        r['fault_mode']='fixed';r['fixed_fault']=dict(first_byte=20,count=256,bit=7,phase=44,width=1)
        p=schedule(r);self.assertTrue(all(i['count']==256 for i in p['items']))
        changed=copy.deepcopy(p);changed['items'][2]['receiver_B']['s']=0
        with self.assertRaises(ValueError):validate(changed)
        r['fixed_fault']['width']=2
        with self.assertRaises(ValueError):schedule(r)
    def test_07_live_has_no_implicit_permission(self):
        code,v=self.http('POST','/api/jobs',dict(action='live_scan',request=dict(plan=dict(sha256='a'*64),confirmation='START '+('a'*12),manual_7010_ready=True)))
        self.assertEqual(code,400);self.assertIn('LIVE_NOT_CONFIGURED',v['error'])
        self.assertFalse(any(n=='pynq' or n.startswith('pynq.') for n in sys.modules))
    def test_08_session_and_path_boundaries(self):
        code,v=self.http('POST','/api/jobs',dict(action='scan_replay',request=dict(session='../../private')));self.assertEqual(code,400)
        self.assertEqual(self.http('GET','/output/'+'a'*32+'/../request.json')[0],404)
        self.assertEqual(self.http('GET','/../common.py')[0],404)
    def test_09_raw_feedback_history_is_not_accepted_from_http(self):
        # Selection accepts registered originals, not arbitrary client-invented labels.
        code,v=self.http('POST','/api/jobs',dict(action='ai_suggest',request=dict(session='session_00000000',records=[dict(labels={'B_frame_correct':True})])))
        self.assertEqual(code,400)
    def test_10_round_grant_is_never_implicit_and_software_is_free(self):
        code,v=self.http('GET','/api/demo-round/status');self.assertEqual(code,200);self.assertIsNone(v['active_round'])
        code,v=self.http('POST','/api/demo-round/create',dict(budget=100,scope={},operator='fixture',confirmation='',acknowledged=False));self.assertEqual(code,400)
        code,v=self.http('GET','/api/demo-round/status');self.assertIsNone(v['active_round']);self.assertEqual(v['mode'],'PREVIEW')
    def test_11_preview_round_api_free_job_topup_and_close(self):
        from demo_authority import default_scope
        code,d=self.http('POST','/api/demo-round/create',dict(budget=100,scope=default_scope(),operator='合成预览测试',confirmation='批准本轮 100 条',acknowledged=True));self.assertEqual(code,200,d)
        rid=d['active_round']['id'];self.assertEqual(d['active_round']['available'],100)
        r=dict(receiver_B=dict(d=3,s=-1),mode='TYPE3A_SINGLE',fault=dict(byte=20,bit=0,count=1),scan=dict(points=[dict(phase=5,width=1)]),repeats=1,max_records=3,target='B_frame_correct')
        j=self.job('scan_preview',dict(request=r,strategy='sequential'));self.assertFalse(j['quota_consumes']);self.assertIsNone(j['session_name'])
        _,d=self.http('GET','/api/demo-round/status');self.assertEqual(d['active_round']['available'],100)
        code,d=self.http('POST','/api/demo-round/top-up',dict(round_id=rid,amount=10,confirmation='追加本轮 10 条'));self.assertEqual(code,200,d);self.assertEqual(d['active_round']['total'],110)
        code,d=self.http('POST','/api/demo-round/close',dict(round_id=rid,confirmation='结束本轮'));self.assertEqual(code,200,d);self.assertIsNone(d['active_round'])

if __name__=='__main__':unittest.main(verbosity=2)
