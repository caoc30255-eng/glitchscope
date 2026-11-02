import json,shutil,sys,tempfile,unittest,urllib.request,urllib.error
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import web_service
from image_service import ImageService
from test_upload_images import body,Owner


class ImageHTTP(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);shutil.copytree(web_service.FUNCTIONAL/'results',self.root/'workspace')
        self.service=ImageService(self.root/'workspace');self.handle=web_service.start(self.root/'workspace',image=self.service,port=0)
        self.addCleanup(self.close);self.url='http://127.0.0.1:%d'%self.handle.http.server_address[1]
        self.csrf=self.get('/api/images/state')['csrf']
    def close(self):
        if self.service.pilot and self.service.pilot.status()['state'] in ('READY','RUNNING','STOPPING'):
            p=self.service.pilot.status();self.service.command('stop',dict(plan_sha256=p['plan_sha256'],idempotency_key='cleanup-image-stop'))
        if self.service.pilot:self.service.pilot.join(5)
        self.handle.shutdown()
    def get(self,path):return json.loads(urllib.request.urlopen(self.url+path).read())
    def post(self,route,value,token=None):
        req=urllib.request.Request(self.url+'/api/images/'+route,data=json.dumps(value).encode(),headers={'Content-Type':'application/json','X-Lab-Token':self.csrf if token is None else token})
        return json.loads(urllib.request.urlopen(req).read())
    def test_upload_and_preview_exact_saved_bytes_offline(self):
        meta=self.post('upload',body());read=urllib.request.urlopen(self.url+'/api/images/asset/'+meta['asset_id']+'/source.png').read()
        self.assertEqual(read,self.service.assets.read(meta['asset_id'])['files']['source.png'])
        self.assertFalse(self.get('/api/images/state')['linked'])
        with self.assertRaises(urllib.error.HTTPError):self.post('prepare',dict(asset_id=meta['asset_id'],seed=1))
    def test_bad_token_cannot_upload_or_start(self):
        with self.assertRaises(urllib.error.HTTPError):self.post('upload',body(),token='wrong')
        self.assertEqual(self.service.assets.list(),[])
    def test_sealed_plan_start_uses_only_uploaded_source(self):
        made=[]
        def factory(asset,seed):
            value=Owner(asset,seed);made.append(value);return value
        self.service.factory=factory
        meta=self.post('upload',body());state=self.post('prepare',dict(asset_id=meta['asset_id'],seed=7))
        self.assertEqual(made[0].attempts,0);cmd=dict(plan_sha256=state['pilot']['plan_sha256'],idempotency_key='http-image-start')
        self.post('start',cmd);self.service.pilot.join(5);self.post('start',cmd)
        self.assertEqual(made[0].attempts,65)
        self.assertEqual(self.get('/api/images/state')['pilot']['plan']['source_sha256'],meta['source_sha256'])
    def test_wrong_plan_and_arbitrary_fields_rejected(self):
        self.service.factory=lambda a,s:Owner(a,s)
        meta=self.post('upload',body());state=self.post('prepare',dict(asset_id=meta['asset_id'],seed=7))
        for cmd in (dict(plan_sha256='a'*64,idempotency_key='http-image-start'),dict(plan_sha256=state['pilot']['plan_sha256'],idempotency_key='http-image-start',limit=999)):
            with self.assertRaises(urllib.error.HTTPError):self.post('start',cmd)
        self.assertEqual(self.service.pilot.owner.attempts,0)
    def test_unready_results_are_not_faked_and_traversal_rejected(self):
        for path in ('/api/images/artifact/crc_burst_B/data.png','/api/images/asset/../source.png','/api/images/session.zip'):
            with self.assertRaises(urllib.error.HTTPError):urllib.request.urlopen(self.url+path)


if __name__=='__main__':unittest.main()
