"""Exercise the real browser Host/Origin sent through the user's SSH tunnel."""
import base64,http.client,json,sys,tempfile,threading,time,unittest
from pathlib import Path
from common import ROOT,verify,write
from server import create

class ForwardedHost(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.out=Path(tempfile.mkdtemp(prefix='forwarded_host_check_',dir=str(ROOT.parent)))
        verify();cls.server=create(cls.out/'data');threading.Thread(target=cls.server.serve_forever,daemon=True).start()
        cls.token=cls.request('GET','/api/status')[1]['token']
    @classmethod
    def tearDownClass(cls):cls.server.shutdown();cls.server.server_close();print('Retained:',cls.out)
    @classmethod
    def request(cls,method,path,data=None,host='127.0.0.1:18768',origin=None,token=None):
        c=http.client.HTTPConnection('127.0.0.1',cls.server.server_port,timeout=30)
        headers={'Host':host,'Content-Type':'application/json','X-Workbench-Token':getattr(cls,'token','') if token is None else token}
        if origin is not None:headers['Origin']=origin
        c.request(method,path,None if data is None else json.dumps(data).encode(),headers);r=c.getresponse();body=r.read();status=r.status;c.close()
        try:body=json.loads(body)
        except (ValueError,UnicodeDecodeError):pass
        return status,body
    def test_1_tunnel_page_status_and_localhost(self):
        code,body=self.request('GET','/');self.assertEqual(code,200);self.assertIn(b'presentation.css',body)
        self.assertEqual(self.request('GET','/api/status',host='localhost:18768')[0],200)
        self.assertEqual(self.request('GET','/api/status')[1]['version'],'GLITCHSCOPE_DEMO_V2_0_1')
    def test_2_tunnel_upload_origin(self):
        from worker import bind
        bind('image');from image_service import gray_png
        pixels=bytes(range(256))*64;png=gray_png(pixels)
        request=dict(filename='forwarded-contract.png',original_base64=base64.b64encode(png).decode(),raw_base64=base64.b64encode(pixels).decode(),transform=dict(width=128,height=128,original_width=128,original_height=128,fit='contain',conversion='BROWSER_CANVAS_BT601_ROUND'))
        code,value=self.request('POST','/api/upload',request,origin='http://127.0.0.1:18768');self.assertEqual(code,200,value);self.assertEqual(value['bytes'],16384)
    def test_3_tunnel_button_request(self):
        plan=dict(receiver_B=dict(d=3,s=-1),mode='TYPE3A_SINGLE',fault=dict(byte=20,bit=0,count=1),scan=dict(points=[dict(phase=5,width=1)]),repeats=1,max_records=3,target='B_frame_correct')
        code,j=self.request('POST','/api/jobs',dict(action='scan_preview',request=dict(request=plan)),origin='http://127.0.0.1:18768');self.assertEqual(code,202,j)
        deadline=time.monotonic()+120
        while time.monotonic()<deadline:
            _,v=self.request('GET','/api/jobs/'+j['id'])
            if v['state']!='RUNNING':break
            time.sleep(.25)
        self.assertEqual(v['state'],'COMPLETE',v.get('error'));self.assertEqual(v['result']['status'],'ACCEPTED')
    def test_4_foreign_hosts_origins_and_missing_token_still_rejected(self):
        self.assertEqual(self.request('GET','/api/status',host='evil.example:18768')[0],404)
        code,v=self.request('POST','/api/jobs',{},origin='http://evil.example:18768');self.assertEqual(code,400);self.assertEqual(v['error'],'CROSS_ORIGIN_REJECTED')
        code,v=self.request('POST','/api/jobs',{},origin='http://127.0.0.1:18768',token='wrong');self.assertEqual(code,400);self.assertEqual(v['error'],'REQUEST_TOKEN_REQUIRED')
        self.assertNotIn('pynq',sys.modules)

if __name__=='__main__':
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(ForwardedHost))
    if hasattr(ForwardedHost,'out'):write(ForwardedHost.out/'report.json',dict(status='PASS_FORWARDED_HOST_FIX' if result.wasSuccessful() else 'FAILED_FORWARDED_HOST_FIX',tests=result.testsRun,hardware_access=False,new_STARTs=0))
    raise SystemExit(0 if result.wasSuccessful() else 1)
