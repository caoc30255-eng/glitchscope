import base64,copy,json
from pathlib import Path
import sys,tempfile,threading,unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from image_service import Assets,ImageService,gray_png


def body(raw=None):
    raw=bytes(range(256))*64 if raw is None else raw
    return dict(filename='my image.png',original_base64=base64.b64encode(gray_png(raw)).decode(),
                raw_base64=base64.b64encode(raw).decode(),transform=dict(width=128,height=128,
                original_width=128,original_height=128,fit='contain',conversion='BROWSER_CANVAS_BT601_ROUND'))


class Owner:
    def __init__(self,asset,seed):
        self.plan=dict(max_physical_starts_including_CONFIG=65,source_sha256=asset['metadata']['source_sha256'],seed=seed)
        self.session_name='modeled-image';self.attempts=self.completed=0;self.closed=False
        self.artifacts={'status':'WAITING'};self.gate=None;self.entered=threading.Event();self.failure=None
    def counts(self):return dict(attempts=self.attempts,completed=self.completed)
    def step(self,stop):
        if stop.is_set() or self.completed==65:return dict(action='STOP',summary=dict(retire_count=self.completed,grant_count=self.completed))
        self.attempts+=1;self.entered.set()
        if self.gate:self.gate.wait(5)
        if self.failure:raise self.failure
        self.completed+=1
        return dict(action='RECORD_COMPLETED',verified_result={'record_id':self.completed})
    def fail(self,e):pass
    def close_receiver(self):self.closed=True


class Uploads(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.store=Assets(self.root/'uploads')
    def test_upload_exact_bytes_preview_and_idempotence(self):
        request=body();a=self.store.upload(request);b=self.store.upload(request)
        self.assertEqual(a,b);loaded=self.store.read(a['asset_id'])
        self.assertEqual(loaded['source'],bytes(range(256))*64)
        self.assertEqual(loaded['files']['source.png'],gray_png(loaded['source']))
        self.assertEqual(len(self.store.list()),1)
    def test_different_source_has_different_id_and_preserves_old(self):
        a=self.store.upload(body());b=self.store.upload(body(bytes([77])*16384))
        self.assertNotEqual(a['asset_id'],b['asset_id']);self.assertEqual(len(self.store.list()),2)
        self.assertEqual(self.store.read(a['asset_id'])['source'],bytes(range(256))*64)
    def test_file_name_is_metadata_never_path(self):
        value=body();value['filename']='../../outside.png';meta=self.store.upload(value)
        self.assertFalse((self.root/'outside.png').exists());self.assertEqual(self.store.read(meta['asset_id'])['metadata']['filename'],value['filename'])
    def test_corrupted_upload_rejected_on_read(self):
        a=self.store.upload(body());(self.store.root/a['asset_id']/'source.bin').write_bytes(bytes(16384))
        with self.assertRaises(ValueError):self.store.read(a['asset_id'])
    def test_bad_raw_length_and_invalid_image_magic(self):
        for raw in (b'abc',b''):
            value=body();value['raw_base64']=base64.b64encode(raw).decode()
            with self.assertRaises(ValueError):self.store.upload(value)
        value=body();value['original_base64']=base64.b64encode(b'<svg/>').decode()
        with self.assertRaises(ValueError):self.store.upload(value)
    def test_dimensions_and_conversion_policy_checked(self):
        for key,value in [('fit','other'),('original_width',9000),('conversion','source_fill'),('width',64)]:
            request=body();request['transform'][key]=value
            with self.assertRaises(ValueError):self.store.upload(request)
    def test_asset_path_escape_rejected(self):
        for value in ('../other','g'*64,'a'):
            with self.assertRaises(ValueError):self.store.read(value)
    def test_offline_upload_never_prepares_hardware(self):
        service=ImageService(self.root/'work');meta=service.upload(body())
        self.assertFalse(service.status()['linked']);self.assertIsNone(service.pilot)
        with self.assertRaises(ValueError):service.prepare(dict(asset_id=meta['asset_id'],seed=1))
    def test_shared_upload_repository_carries_exact_image_to_fresh_session(self):
        offline=ImageService(self.root/'offline',assets_root=self.root/'shared')
        meta=offline.upload(body())
        live=ImageService(self.root/'live',assets_root=self.root/'shared',owner_factory=lambda a,s:Owner(a,s))
        self.assertEqual(live.status()['assets'][0]['asset_id'],meta['asset_id'])
        state=live.prepare(dict(asset_id=meta['asset_id'],seed=1))
        self.assertEqual(state['prepared']['metadata']['source_sha256'],meta['source_sha256'])
        self.assertEqual(live.pilot.owner.attempts,0)
    def service(self):
        self.created=[]
        def factory(asset,seed):
            owner=Owner(asset,seed);self.created.append(owner);return owner
        service=ImageService(self.root/'work',owner_factory=factory)
        meta=service.upload(body());return service,meta
    def test_prepare_binds_source_and_no_physical_attempt(self):
        service,meta=self.service();result=service.prepare(dict(asset_id=meta['asset_id'],seed=42))
        self.assertEqual(result['pilot']['max_records'],65);self.assertEqual(self.created[0].attempts,0)
        self.assertEqual(result['pilot']['plan']['source_sha256'],meta['source_sha256'])
        service.prepare(dict(asset_id=meta['asset_id'],seed=42));self.assertEqual(len(self.created),1)
        with self.assertRaises(ValueError):service.prepare(dict(asset_id=meta['asset_id'],seed=43))
        with self.assertRaises(ValueError):service.upload(body())
    def test_65_limit_and_duplicate_start_does_not_repeat(self):
        service,meta=self.service();state=service.prepare(dict(asset_id=meta['asset_id'],seed=42))
        command=dict(plan_sha256=state['pilot']['plan_sha256'],idempotency_key='image-start-123')
        first=service.command('start',command);self.assertEqual(first,service.command('start',command))
        self.assertTrue(service.pilot.join(5));self.assertEqual(self.created[0].attempts,65)
        self.assertEqual(service.status()['pilot']['completed_records'],65)
        with self.assertRaises(ValueError):service.command('start',dict(command,idempotency_key='image-new-start-123'))
    def test_stop_during_item_waits_boundary(self):
        service,meta=self.service();state=service.prepare(dict(asset_id=meta['asset_id'],seed=42));owner=self.created[0]
        owner.gate=threading.Event();command=dict(plan_sha256=state['pilot']['plan_sha256'],idempotency_key='image-start-123')
        service.command('start',command);self.assertTrue(owner.entered.wait(2))
        service.command('stop',dict(command,idempotency_key='image-stop-123'));owner.gate.set();self.assertTrue(service.pilot.join(5))
        self.assertEqual(owner.attempts,1);self.assertEqual(service.status()['pilot']['state'],'STOPPED')
    def test_unknown_occupies_and_no_retry(self):
        service,meta=self.service();state=service.prepare(dict(asset_id=meta['asset_id'],seed=42));self.created[0].failure=TimeoutError('modeled uncertain')
        cmd=dict(plan_sha256=state['pilot']['plan_sha256'],idempotency_key='image-start-123');service.command('start',cmd);service.pilot.join(5)
        result=service.status()['pilot'];self.assertEqual(result['state'],'BLOCKED_UNKNOWN');self.assertIsNone(result['unresolved_label']);self.assertEqual(result['attempts'],1)
    def test_seed_bound_and_setup_error_no_retry(self):
        service,meta=self.service()
        for seed in (True,-1,2**32):
            with self.assertRaises(ValueError):service.prepare(dict(asset_id=meta['asset_id'],seed=seed))
        calls=[]
        def broken(a,s):calls.append(1);raise ValueError('modeled setup failed')
        service.factory=broken
        with self.assertRaises(ValueError):service.prepare(dict(asset_id=meta['asset_id'],seed=1))
        with self.assertRaises(ValueError):service.prepare(dict(asset_id=meta['asset_id'],seed=1))
        self.assertEqual(len(calls),1);self.assertEqual(service.status()['stage'],'BLOCKED_SETUP')


if __name__=='__main__':unittest.main()
