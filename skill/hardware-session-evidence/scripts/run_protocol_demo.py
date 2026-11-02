"""Actual H5E1 READ32 bytes over a local TCP peer emulator, not a board test."""
import argparse,json,socket,struct,threading
from pathlib import Path
from peer_read_adapter import decode,frame,run_readonly
def receive(sock,n):
    data=b''
    while len(data)<n:
        p=sock.recv(n-len(data))
        if not p:break
        data+=p
    return data
class Transport:
    def __init__(self,address):self.sock=socket.create_connection(address,timeout=3)
    def exchange(self,request,expected_type):self.sock.sendall(request);return receive(self.sock,39)
    def close(self):self.sock.close();return True
def demo(output,corrupt=False):
    out=Path(output);out.mkdir();server=socket.socket();server.bind(('127.0.0.1',0));server.listen(1);errors=[]
    words={0:0x48354531,4:0x20,0x24:0}
    def peer():
        try:
            conn,_=server.accept()
            with conn:
                conn.settimeout(3)
                while True:
                    request=receive(conn,39)
                    if not request:break
                    kind,p=decode(request)
                    if kind!=0x3b or p[8:10]!=bytes([0,1]):raise ValueError('READ_ONLY_DEMO')
                    address=int.from_bytes(p[10:12],'big');reply=p[:12]+bytes([0,0,1,0])+words[address].to_bytes(4,'big')+bytes(12)
                    raw=frame(0x7b,reply)
                    if corrupt:raw=raw[:-1]+bytes([raw[-1]^1])
                    conn.sendall(raw)
        except Exception as e:errors.append(str(e))
        finally:server.close()
    thread=threading.Thread(target=peer,daemon=True);thread.start()
    transport=Transport(server.getsockname())
    report=run_readonly(transport,out/'session',out/'device.lock',0x10000001,1,[dict(address=a,expected=v,access='RO',read_effect='none') for a,v in words.items()],incremental=True)
    thread.join(4)
    if thread.is_alive() or errors:raise ValueError(('LOCAL_PEER_FAILURE',errors))
    report.update(transport_origin='LOCAL_TCP_PEER_EMULATOR_NOT_BOARD',hardware_access=False,corrupt_fixture=corrupt)
    if corrupt and (report['unknown_or_unresolved']!=1 or report['occupied']!=1):raise ValueError('UNKNOWN_NOT_RECORDED')
    if not corrupt and report['recorded_completions']!=3:raise ValueError('READS_NOT_COMPLETED')
    (out/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8');print('PASS_LOCAL_PROTOCOL',report['occupied'],report['unknown_or_unresolved']);return report
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',required=True);p.add_argument('--corrupt-reply',action='store_true');a=p.parse_args();demo(a.output,a.corrupt_reply)
