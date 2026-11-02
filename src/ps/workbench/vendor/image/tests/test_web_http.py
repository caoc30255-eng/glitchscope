"""Loopback HTTP checks with a modeled owner; no device imports."""
import json
from pathlib import Path
import shutil
import sys
import tempfile
from types import SimpleNamespace
import unittest
import urllib.request
import urllib.error
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from pilot_service import PilotService
from test_pilot_service import Owner
import web_service


class HTTP(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        shutil.copytree(web_service.FUNCTIONAL/'results',self.root/'workspace')
        self.owner=Owner();self.owner.session=SimpleNamespace(root=self.root/'session')
        self.owner.session.root.mkdir();(self.owner.session.root/'actual_test_evidence.bin').write_bytes(b'modeled-only')
        self.pilot=PilotService(self.owner,self.root/'WEB')
        self.handle=web_service.start(self.root/'workspace',pilot=self.pilot,port=0)
        self.addCleanup(self.close)
        self.url='http://127.0.0.1:%d'%self.handle.http.server_address[1]
        self.csrf=self.get('/api/pilot')['csrf'];self.plan=self.pilot.status()['plan_sha256']
    def close(self):
        if self.pilot.status()['state'] in ('READY','RUNNING','STOPPING'):
            self.pilot.command('stop','cleanup-stop-1234',self.plan)
        self.pilot.join(5);self.handle.shutdown()
    def get(self,path):
        return json.loads(urllib.request.urlopen(self.url+path).read())
    def post(self,path,body,token=None,origin=None):
        headers={'Content-Type':'application/json','X-Lab-Token':self.csrf if token is None else token}
        if origin:headers['Origin']=origin
        request=urllib.request.Request(self.url+path,data=json.dumps(body).encode(),headers=headers)
        return json.loads(urllib.request.urlopen(request).read())
    def body(self,key='http-start-key'):
        return dict(plan_sha256=self.plan,idempotency_key=key)
    def test_read_and_refresh_do_not_execute(self):
        for _ in range(5):self.get('/api/pilot')
        self.assertEqual(self.owner.calls,0)
        raw=urllib.request.urlopen(self.url+'/').read()
        self.assertIn(b'/pilot',raw)
    def test_token_and_origin_required_before_start(self):
        for token,origin in [('bad',None),(self.csrf,'http://other.invalid')]:
            with self.assertRaises(urllib.error.HTTPError) as e:self.post('/api/pilot/start',self.body(),token,origin)
            self.assertEqual(e.exception.code,409)
        self.assertEqual(self.owner.calls,0)
    def test_arbitrary_parameters_rejected(self):
        body=self.body();body['d']=4
        with self.assertRaises(urllib.error.HTTPError):self.post('/api/pilot/start',body)
        self.assertEqual(self.owner.calls,0)
    def test_duplicate_POST_does_not_repeat(self):
        first=self.post('/api/pilot/start',self.body());second=self.post('/api/pilot/start',self.body())
        self.assertEqual(first,second);self.assertTrue(self.pilot.join(5))
        self.assertEqual(self.owner.attempts,4)
        with self.assertRaises(urllib.error.HTTPError):self.post('/api/pilot/start',self.body('http-another-key'))
    def test_terminal_evidence_download_has_session_only(self):
        self.post('/api/pilot/stop',self.body('http-stop-key'));self.pilot.join(5)
        import io,zipfile
        raw=urllib.request.urlopen(self.url+'/api/pilot/evidence.zip').read()
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            self.assertEqual(z.namelist(),['session/actual_test_evidence.bin'])
            self.assertEqual(z.read(z.namelist()[0]),b'modeled-only')
    def test_simulation_and_general_scan_denied_when_linked(self):
        for path in ('/api/start','/api/submit-mainline'):
            with self.assertRaises(urllib.error.HTTPError):self.post(path,{})
        self.assertEqual(self.owner.calls,0)
    def test_offline_service_has_no_live_entry(self):
        shutil.copytree(web_service.FUNCTIONAL/'results',self.root/'offline')
        handle=web_service.start(self.root/'offline',port=0)
        try:
            url='http://127.0.0.1:%d'%handle.http.server_address[1]
            status=json.loads(urllib.request.urlopen(url+'/api/pilot').read())
            self.assertFalse(status['linked']);self.assertFalse(status['hardware_controls_enabled'])
            req=urllib.request.Request(url+'/api/pilot/start',data=json.dumps(self.body()).encode(),headers={'Content-Type':'application/json','X-Lab-Token':status['csrf']})
            with self.assertRaises(urllib.error.HTTPError):urllib.request.urlopen(req)
        finally:handle.shutdown()
        self.assertEqual(self.owner.calls,0)


if __name__=='__main__':unittest.main()
