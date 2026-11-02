import sys,tempfile,threading,unittest
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import Mock,patch
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'runtime/host')]
from image_owner import ImageOwner


class OwnerStop(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
    def owner(self,count):
        owner=object.__new__(ImageOwner);owner.code={};owner.source_hash='a'*64
        owner.executor=NS(index=count,attempts=count,_verify_plan=Mock(),cancel_remaining=Mock())
        owner.monitor=NS(_verify=Mock(),receipts={i:True for i in range(1,count+1)})
        owner.session=NS(root=Path(self.temp.name));owner.buses={'SYS':NS(read=lambda a:count)}
        return owner
    def call(self,owner,stop=False):
        flag=threading.Event()
        if stop:flag.set()
        with patch('ps_idle_journal_segments._idle'),patch('ps_idle_journal_segments.verify_sealed_segments'):
            return owner.step(flag)
    def test_complete_requires_65_actual_count_receipts(self):
        owner=self.owner(65);result=self.call(owner)
        self.assertTrue(result['summary']['plan_complete']);self.assertEqual(result['summary']['retire_count'],65)
        owner.executor._verify_plan.assert_called_once();owner.monitor._verify.assert_called_once()
    def test_missing_point_receipt_blocks_final_completion(self):
        owner=self.owner(65);owner.monitor.receipts.pop(64)
        with self.assertRaises(ValueError):self.call(owner)
    def test_stop_cancels_only_remainder_with_real_counter_check(self):
        owner=self.owner(2);result=self.call(owner,True)
        owner.executor.cancel_remaining.assert_called_once();self.assertFalse(result['summary']['plan_complete'])
        self.assertEqual(result['summary']['completed_records'],2)
    def test_stop_counter_mismatch_not_accepted(self):
        owner=self.owner(2);owner.buses['SYS'].read=lambda a:1
        with self.assertRaises(ValueError):self.call(owner,True)


if __name__=='__main__':unittest.main()
