"""Additional pure software acceptance; synthetic checked rows are not hardware evidence."""
import copy
import json
import math
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from custom_plan import compile_plan, typed_profile, capabilities
from tests_backend import request, rows
from custom_stats import aggregate
from custom_refine import suggest
from learning_domain import digest


class V02Tests(unittest.TestCase):
    def test_all_legal_and_neighbor_receiver_profiles(self):
        for d in range(0,6):
            for s in range(-3,4):
                self.assertEqual(compile_plan(request(d,s))['status']=='ACCEPTED',1<=d<=4 and -2<=s<=3-d)

    def test_every_payload_byte_and_bit(self):
        for byte in range(19,277):
            for bit in range(-1,9):
                r=request();r['fault'].update(byte=byte,bit=bit)
                self.assertEqual(compile_plan(r)['status']=='ACCEPTED',20<=byte<=275 and 0<=bit<=7)

    def test_entire_phase_width_triangle_and_neighbors(self):
        for phase in range(4,46):
            for width in range(0,43):
                r=request();r['scan']['points']=[dict(phase=phase,width=width)]
                self.assertEqual(compile_plan(r)['status']=='ACCEPTED',phase>=5 and width>=1 and phase+width<=45)

    def test_mpg1_counts_and_last_byte(self):
        for count in (0,1,4,255,256,257,True,1.0):
            for byte in (19,20,21,275,276):
                r=request();r['mode']='TYPE3C_CONTIGUOUS';r['fault'].update(byte=byte,count=count)
                ok=type(count) is int and 1<=count<=256 and 20<=byte and byte+count<=276
                result=compile_plan(r);self.assertEqual(result['status']=='ACCEPTED',ok)
                if ok:self.assertEqual(typed_profile(result['plan']['conditions'][0]).count,count)

    def test_disabled_is_not_type3c_zero(self):
        r=request();r['mode']='DISABLED';r['fault']['count']=0
        result=compile_plan(r);self.assertEqual(result['status'],'ACCEPTED');self.assertIsNone(typed_profile(result['plan']['conditions'][0]))
        r['mode']='TYPE3C_CONTIGUOUS';self.assertEqual(compile_plan(r)['status'],'REJECTED')
        r['mode']='TYPE3A_SINGLE';self.assertEqual(compile_plan(r)['status'],'REJECTED')

    def test_bad_scalar_types_every_field(self):
        for value in (True,False,1.0,float('nan'),float('inf'),None,'1'):
            for field in ('byte','bit','count'):
                r=request();r['fault'][field]=value;self.assertEqual(compile_plan(r)['status'],'REJECTED')
            for field in ('repeats','max_records'):
                r=request();r[field]=value;self.assertEqual(compile_plan(r)['status'],'REJECTED')
            for field in ('phase','width'):
                r=request();r['scan']['points'][0][field]=value;self.assertEqual(compile_plan(r)['status'],'REJECTED')

    def test_nonfinite_rejection_diagnostics_are_valid_json(self):
        from custom_plan import raw
        for value in (float('nan'),float('inf'),float('-inf')):
            r=request();r['scan']['points'][0]['phase']=value
            result=compile_plan(r);self.assertEqual(result['status'],'REJECTED')
            decoded=json.loads(raw(result));self.assertIn('rejected_nonfinite_float',decoded['rejected_conditions'][0]['requested']['phase'])
            self.assertIsNone(decoded['plan'])

    def test_unknown_empty_duplicate_and_range_rejection(self):
        for scan in ({'points':[]},{'points':[dict(phase=7,width=3)]*2},{'phase':[],'width':[1]},
                     {'phase':dict(start=7,stop=6,step=1),'width':[1]},
                     {'phase':dict(start=5,stop=1000000000000,step=1),'width':[1]},
                     {'phase':dict(start=5,stop=7,step=-1),'width':[1]},
                     {'points':[dict(phase=7,width=3,other=1)]}):
            r=request();r['scan']=scan;self.assertEqual(compile_plan(r)['status'],'REJECTED')

    def test_count_context_separates_same_geometry(self):
        a=request();a['mode']='TYPE3C_CONTIGUOUS';a['fault']['count']=1
        b=copy.deepcopy(a);b['fault']['count']=4
        self.assertNotEqual(compile_plan(a)['plan']['conditions'][0]['condition_sha256'],compile_plan(b)['plan']['conditions'][0]['condition_sha256'])

    def test_explicit_first_byte_alias_has_same_physical_condition(self):
        r=request();r['mode']='TYPE3C_CONTIGUOUS';r['fault']=dict(first_byte=20,count=4,bit=0)
        a=compile_plan(r);self.assertEqual(a['status'],'ACCEPTED')
        r['fault']=dict(byte=20,count=4,bit=0);b=compile_plan(r)
        self.assertEqual(a['plan']['conditions'],b['plan']['conditions'])
        self.assertNotEqual(a['plan']['sha256'],b['plan']['sha256'])

    def test_public_import_has_no_model_or_services(self):
        code="import sys; import custom_backend,custom_real,target_scan; assert not any(n in sys.modules for n in ('custom_model','custom_fixture','unittest','pynq','ch1_uartlite_realtime_transport','ch1_uartlite_native_transport')); print('PASS')"
        p=subprocess.run([sys.executable,'-B','-c',code],cwd=Path(__file__).resolve().parent,capture_output=True,text=True)
        self.assertEqual(p.returncode,0,p.stderr)

    def test_seal_does_not_start(self):
        from custom_backend import seal
        with tempfile.TemporaryDirectory() as tmp:
            p=compile_plan(request())['plan'];result=seal(p,Path(tmp)/'sealed')
            self.assertFalse(result['hardware_permission']);self.assertEqual(result['state'],'SEALED_NOT_STARTED')
            self.assertEqual(json.loads((Path(tmp)/'sealed/plan.json').read_bytes()),p)
            with self.assertRaises(FileExistsError):seal(p,Path(tmp)/'sealed')

    def test_false_approval_rejected_before_assets_or_devices(self):
        from custom_authorization import read_approval
        p=compile_plan(request())['plan']
        with tempfile.TemporaryDirectory() as tmp:
            f=Path(tmp)/'approval.json';f.write_text(json.dumps(dict(schema='SCAN_EXPLICIT_APPROVAL_V0_2',approved_by_user=False)),encoding='utf-8')
            with self.assertRaisesRegex(ValueError,'EXPLICIT_USER_APPROVAL'):read_approval(f,p,{},tmp,'physical_records')

    def test_three_target_maps_preserve_raw_counts(self):
        from custom_heatmaps import write_maps
        p=compile_plan(request(repeats=3,refine=True))['plan'];r=rows(p,[True,False,True]);r[-1]['labels']['STM_business_success']=False
        stats=aggregate(p,r,'unit_only_session')
        with tempfile.TemporaryDirectory() as tmp:
            dest=Path(tmp)/'maps';write_maps(dest,stats,'SYNTHETIC_UNIT_ONLY')
            self.assertEqual(len(list(dest.iterdir())),9)
            b=json.loads((dest/'B_frame_correct.json').read_bytes());stm=json.loads((dest/'STM_business_success.json').read_bytes())
            self.assertEqual(b['rows'][0]['counts']['success'],2);self.assertEqual(stm['rows'][0]['counts']['success'],1)
            self.assertFalse(b['interpolated']);self.assertEqual(b['rows'][1]['counts']['state'],'UNMEASURED')

    def test_no_hardware_verification_claim(self):
        c=capabilities();self.assertEqual(c['new_physical_STARTs_authorized'],0);self.assertFalse(c['TYPE3C_CONTIGUOUS']['real_hardware_verified'])


if __name__=='__main__':unittest.main(verbosity=2)
