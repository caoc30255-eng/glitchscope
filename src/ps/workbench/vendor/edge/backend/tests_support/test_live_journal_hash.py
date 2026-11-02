"""Live exact-byte verification vs independent hash-chain audit; real fsync."""
from pathlib import Path
import sys,uuid,json,os,unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'host'))
from ch1_control_session import ApplicationJournal,audit_application_journal

class LiveJournalTests(unittest.TestCase):
    def setUp(self):
        self.j=ApplicationJournal(ROOT/'evidence/offline_journal_hash_tests'/uuid.uuid4().hex,1)
        self.addCleanup(self.j.close)
    def test_owned_records_match_independent_chain_and_exact_LF(self):
        for i in range(30):self.j.record('sample',value=i,path='中文',status=[4,0,5,4]*30)
        self.j.verify()
        audit=audit_application_journal(self.j.path)
        self.assertEqual(audit['records'],self.j.index)
        self.assertNotIn(b'\r\n',self.j.path.read_bytes())
    def test_early_tamper_same_size_and_mtime_is_detected(self):
        self.j.record('sample',value=1)
        stat=self.j.path.stat();raw=self.j.path.read_bytes()
        edited=raw.replace(b'"begin"',b'"begim"',1)
        self.assertEqual(len(raw),len(edited));self.j.path.write_bytes(edited)
        os.utime(self.j.path,ns=(stat.st_atime_ns,stat.st_mtime_ns))
        with self.assertRaises(ValueError):self.j.verify()
        self.assertTrue(self.j.fault)
    def test_truncation_is_detected(self):
        self.j.path.write_bytes(self.j.path.read_bytes()[:-1])
        with self.assertRaises(ValueError):self.j.verify()
    def test_external_appended_record_is_detected(self):
        with self.j.path.open('ab') as f:f.write(b'{}\n')
        with self.assertRaises(ValueError):self.j.verify()
    def test_live_state_mutation_is_detected(self):
        self.j.index+=1
        with self.assertRaises(ValueError):self.j.verify()
    def test_failed_fsync_locks_before_next_record(self):
        with patch('ch1_control_session.os.fsync',side_effect=OSError('disk')):
            with self.assertRaises(OSError):self.j.record('partial')
        self.assertTrue(self.j.fault)
        with self.assertRaises(RuntimeError):self.j.record('later')
    def test_live_verify_avoids_repeated_JSON_decode(self):
        self.j.record('sample',value=1)
        with patch('ch1_control_session.json.loads',side_effect=AssertionError('reparse')):
            self.j.verify()
    def test_effect_and_ACK_intent_batch_has_one_fsync_and_valid_chain(self):
        original=os.fsync
        with patch('ch1_control_session.os.fsync',wraps=original) as sync:
            self.j.record_many([('peer_event_effect',{'effect':'synthetic'}),
                ('control_tx_intent',{'raw_hex':'a55a'})])
        self.assertEqual(sync.call_count,1)
        self.assertTrue(self.j.matches_intent(bytes.fromhex('a55a')))
        self.j.verify();self.assertEqual(audit_application_journal(self.j.path)['records'],3)
        self.j.record('other');self.assertFalse(self.j.matches_intent(bytes.fromhex('a55a')))
    def test_batch_fsync_failure_never_grants_owned_intent(self):
        with patch('ch1_control_session.os.fsync',side_effect=OSError('disk')):
            with self.assertRaises(OSError):
                self.j.record_many([('peer_event_effect',{}),('control_tx_intent',{'raw_hex':'a55a'})])
        self.assertFalse(self.j.matches_intent(bytes.fromhex('a55a')))
        self.assertTrue(self.j.fault)
