"""Independent association tests; outer file SHA checks are deliberately absent."""
import copy
import json
import struct
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import Mock
import custom_plan
from custom_mmio_binding import ADDRESSES, bind_reads, journal_entries, packets, saved_record_binding
from ch1_control_session import frame, decode_frame, event_payload, ApplicationJournal, PeerControlSession
import ch1_evidence_store as store

IDENTITY=int('0000000001800001480000000900000148000000011000002901000000000000',16)


def fixture(points=1):
    native=int.from_bytes(event_payload(IDENTITY,0),'little')
    words=[(native>>shift)&0xffffffff for shift in range(224,-1,-32)]
    observed=dict(epoch=9,record_id=1,identity_hex='%064x'%IDENTITY,expected_points=points,
                  native_identity_words=words,count_status_before=[points|(points<<9),1],count_status_after=[points|(points<<9),1])
    proof=dict(observed,configured_points=points,emitted_points=points,actual_DONE_fenced=True,source_fault=False)
    rows=[dict(event='peer_event_effect',effect='W19_DONE',event_receipt=dict(identity=IDENTITY),journal_index=0)]
    values=[0x4d504731]+observed['count_status_before']+words+observed['count_status_after']
    for index,(address,value) in enumerate(zip(ADDRESSES,values)):
        header=struct.pack('>IIBBH',17,index+20,0,1,address)
        request=frame(0x3b,header+bytes(20))
        reply=frame(0x7b,header+bytes((0,0,1,0))+value.to_bytes(4,'big')+bytes(12))
        rows.extend([dict(event='control_tx_intent',raw_hex=request.hex(),journal_index=2*index+1),
                     dict(event='control_rx_stream',raw_hex=reply.hex(),journal_index=2*index+2)])
    for row in rows:
        row['_journal_path']='application_00000009.jsonl';row['sha256']=store.sha(store._json(row))
    return rows,proof,observed,dict(path=rows[0]['_journal_path'],start_index=1,stop_index=27,control_epoch=17)


def execute(data):
    rows,proof,observed,window=data
    # Supply raw bytes without pre-decoding. CRC failures must be raised by
    # bind_reads itself, not an inventory check or this test setup.
    captures={bytes.fromhex(e['raw_hex']) for e in rows if e['event']=='control_rx_stream'}
    captures.update(bytes.fromhex(e['rx_hex']) for e in rows if e['event']=='uart_byte_exchange_saved')
    return bind_reads(rows,captures,proof,observed,window)


def change(data, row, offset, replacement, crc=True):
    entry=data[0][row];raw=bytes.fromhex(entry['raw_hex']);kind,body=decode_frame(raw)
    body=body[:offset]+replacement+body[offset+len(replacement):]
    raw=frame(kind,body)
    if not crc:raw=raw[:-1]+bytes((raw[-1]^1,))
    entry['raw_hex']=raw.hex()


class BindingTests(unittest.TestCase):
    def reject(self, edit):
        data=fixture();edit(data)
        with self.assertRaises(ValueError):execute(data)

    def test_normal_counts(self):
        for count in (0,1,4,255,256):
            bound=execute(fixture(count));self.assertTrue(bound['raw_MMIO_transaction_binding_verified'])
            self.assertEqual([t['address'] for t in bound['transactions']],ADDRESSES)
            self.assertEqual(len(bound['transactions']),13)

    def test_missing_reply(self):self.reject(lambda d:d[0].pop(2))
    def test_missing_capture_set(self):
        rows,proof,observed,window=fixture()
        with self.assertRaisesRegex(ValueError,'MISSING_FROM_CAPTURE'):bind_reads(rows,set(),proof,observed,window)
    def test_wrong_reply_txn(self):self.reject(lambda d:change(d,2,4,(999).to_bytes(4,'big')))
    def test_wrong_reply_address(self):self.reject(lambda d:change(d,2,10,b'\x0d\x24'))
    def test_wrong_reply_value(self):self.reject(lambda d:change(d,4,16,(999).to_bytes(4,'big')))
    def test_wrong_control_epoch(self):self.reject(lambda d:d[3].update(control_epoch=999))
    def test_wrong_request_address(self):self.reject(lambda d:change(d,1,10,b'\x0d\x24'))
    def test_request_write(self):self.reject(lambda d:change(d,1,8,b'\x01'))
    def test_request_count(self):self.reject(lambda d:change(d,1,9,b'\x02'))
    def test_reply_status(self):self.reject(lambda d:change(d,2,12,b'\x01'))
    def test_reply_count(self):self.reject(lambda d:change(d,2,14,b'\x02'))
    def test_reply_padding(self):self.reject(lambda d:change(d,2,31,b'\x01'))
    def test_crc_bad_reply(self):self.reject(lambda d:change(d,2,16,b'\x00',crc=False))
    def test_crc_bad_request(self):self.reject(lambda d:change(d,1,16,b'\x00',crc=False))
    def test_duplicate_reply(self):
        def edit(d):d[0][2]['raw_hex']*=2
        self.reject(edit)
    def test_cross_record_replay(self):
        def edit(d):
            for target in (d[1],d[2]):target['identity_hex']='%064x'%(IDENTITY+(1<<88));target['record_id']=2
        self.reject(edit)
    def test_native_identity_altered(self):self.reject(lambda d:change(d,8,16,(123).to_bytes(4,'big')))
    def test_before_after_inconsistent_even_summaries_match(self):
        def edit(d):
            change(d,24,16,(1026).to_bytes(4,'big'))
            d[1]['count_status_after'][0]=1026;d[2]['count_status_after'][0]=1026
        self.reject(edit)
    def test_capability_altered(self):self.reject(lambda d:change(d,2,16,bytes(4)))
    def test_after_retire(self):
        def edit(d):d[0].append(dict(event='strict_three_party_retire_intent',identity=IDENTITY,journal_index=0,_journal_path=d[3]['path']))
        self.reject(edit)
    def test_window_excludes_request(self):self.reject(lambda d:d[3].update(start_index=2))
    def test_reordered_transactions(self):
        def edit(d):d[0][3]['journal_index'],d[0][5]['journal_index']=d[0][5]['journal_index'],d[0][3]['journal_index']
        self.reject(edit)
    def test_native_request_mismatch(self):
        def edit(d):d[0][2].update(event='uart_byte_exchange_saved',native_error=0,pending_hex='',bad_rx_word=None,
                                 request_hex='00',rx_hex=d[0][2]['raw_hex'],tx_bytes_confirmed=39)
        self.reject(edit)

    def test_native_capture_positive(self):
        data=fixture()
        for i in range(2,27,2):
            e=data[0][i]
            e.update(event='uart_byte_exchange_saved',native_error=0,pending_hex='',bad_rx_word=None,
                     request_hex=data[0][i-1]['raw_hex'],rx_hex=e['raw_hex'],tx_bytes_confirmed=39)
        self.assertTrue(execute(data)['raw_MMIO_transaction_binding_verified'])

    def test_reused_txn_with_matching_reply(self):
        def edit(d):
            change(d,3,4,(20).to_bytes(4,'big'));change(d,4,4,(20).to_bytes(4,'big'))
        self.reject(edit)

    def test_monitor_live_protocol_component_and_saved_refs(self):
        # Real protocol adapter + durable journal; scripted bytes, zero devices.
        from custom_monitor import CustomMonitor
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);journal=ApplicationJournal(root,9)
            journal.record('peer_event_effect',effect='W19_DONE',event_receipt=dict(identity=IDENTITY))
            rows,_,observed,_=fixture(0)
            values=dict(zip(ADDRESSES,[0x4d504731]+observed['count_status_before']+observed['native_identity_words']+observed['count_status_after']))
            class Transport:
                def exchange(self,request,expected):
                    _,body=decode_frame(request);address=int.from_bytes(body[10:12],'big')
                    return frame(0x7b,body[:12]+bytes((0,0,1,0))+values[address].to_bytes(4,'big')+bytes(12))
            peer=PeerControlSession(Transport(),journal,17)
            binding=NS(record_id=1,epoch=9,identity=IDENTITY,kind=2)
            owner=NS(binding=binding,started=True,done=True)
            monitor=CustomMonitor.__new__(CustomMonitor)
            monitor.hardware=True;monitor.epoch=9;monitor.expected=(0,);monitor.receipts={}
            monitor.root=root/'MPG1_SCAN';monitor.executor=NS(_verify_plan=Mock(),_bound_raw={1:b'bound'})
            monitor.session=NS(root=root,journal=journal,peer=peer,current=owner)
            monitor.buses={'SYS':NS(read=lambda address:0)};monitor._verify=Mock();monitor.points=lambda rid:0
            try:
                proof=monitor.verify_completed(owner,0)
                entries=journal_entries(root);captures={packet for e in entries for offset,packet in packets(e)}
                scope=root/'CUSTOM_SCAN/scope';scope.mkdir(parents=True);(scope/'scope.json').write_text('{}')
                result=dict(MPG1_pre_retirement=proof,identity_hex=proof['identity_hex'])
                bound=saved_record_binding(root,1,result,(entries,captures,[]))
                self.assertEqual(len(bound['transactions']),13)
                # Corrupt only the separately committed reference object, not
                # an outer manifest; the association checker must reject it.
                path=monitor.root/'record_00000001/raw_MMIO_binding/binding.json'
                bad=json.loads(path.read_bytes());bad['transactions'][0]['txn']+=1
                path.write_bytes(store._json(bad))
                with self.assertRaisesRegex(ValueError,'REFERENCES_REQUIRED'):saved_record_binding(root,1,result,(entries,captures,[]))
            finally:journal.close()


if __name__=='__main__':unittest.main(verbosity=2)
