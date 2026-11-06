"""Reproducible headless ModelSim comparison of frozen B/NCO RTL and Python.

Explicit command invocation only, no hardware access or GUI. Outputs require a
new external directory; failure logs/inputs remain. Tested on ModelSim 10.1d.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
from b_receiver import PROFILES, replay
from window_audit import load_record


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def stimulus(word):
    return [1]*200+[0]*100+[(word>>bit)&1 for bit in range(8) for _ in range(100)]+[1]*250


def mixed_stimulus():
    out=[]
    for word in (0,255,0x55,0xaa,1,0x80):
        out.extend(stimulus(word))
    for word,bit,phase,width in ((0,0,15,20),(255,0,15,20),(0,7,5,1),(255,7,25,10),
                                  (0x55,3,15,30),(0xaa,4,5,40),(0,0,15,10),(255,0,15,10)):
        wave=stimulus(word)
        start=200+(1+bit)*100+phase*2
        for i in range(start,start+width*2):wave[i]^=1
        out.extend(wave)
    out.extend([1]*200+[0]*3+[1]*200)  # short false start
    out.extend([1]*200+[0]*20+[1]*300)  # start-center rejection
    out.extend([1]*200+[0]*2500+[1]*250)  # bad STOP and WAIT_HIGH
    out.extend(stimulus(0x81)[:700])  # no fabricated result from truncation
    return out


def generate(root, out):
    vectors=out/'vectors';vectors.mkdir()
    case_rows=[];manifest=[];count=0;cycles=0
    def case(levels,d,s,phase,origin):
        nonlocal count,cycles
        count+=1;cycles+=len(levels)
        events={f['valid_index']:f for f in replay(levels,d,s,phase,False)}
        data=fe=0;words=[]
        for i,value in enumerate(levels):
            if i in events:data,fe=events[i]['data'],int(events[i]['framing_error'])
            words.append('%08x\n'%((data<<3)|(fe<<2)|(int(i in events)<<1)|value))
        path=vectors/('case_%05d.mem'%count);path.write_text(''.join(words),encoding='ascii')
        case_rows.append('%d %d %d %d %d\n'%(count,d,s,phase,len(levels)))
        manifest.append(dict(case=count,d=d,s=s,accumulator=phase,clocks=len(levels),
                             origin=origin,vector_sha256=sha(path),result_events=len(events)))
    levels=mixed_stimulus()
    for d,s in PROFILES:
        for phase in range(25):case(levels,d,s,phase,'SYNTHETIC_MIXED_UART_AND_BURSTS')
    sources=json.loads((root/'examples/sources.json').read_bytes())
    for source in sources:
        record=load_record(root/'examples'/source['session'],source['record_id'])
        d,s=(record['result']['actual_receiver_B'][k] for k in ('d','s'))
        origin='HISTORICAL_DIGITAL_INPUT/%s/%d'%(source['session'],source['record_id'])
        for phase in range(25):case(record['levels'],d,s,phase,origin)
    (out/'cases.txt').write_text(''.join(case_rows),encoding='ascii')
    (out/'vector_manifest.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
    return count,cycles


def run(directory, simulator):
    root=Path(__file__).resolve().parent;out=Path(directory).resolve()
    rtl=root.parent/'rtl'
    if out==root or root in out.parents:raise ValueError('OUTPUT_OUTSIDE_FROZEN_PACKAGE_REQUIRED')
    out.mkdir(parents=True,exist_ok=False)
    report=dict(schema='B_RECEIVER_RTL_COSIM_V0_2',status='RUNNING',hardware_access=False,
                physical_STARTs=0,scope='RTL_vs_Python_outputs_and_NCO_each_clock; not new hardware evidence',
                model_sha256=sha(root/'b_receiver.py'),rtl_sha256={n:sha(rtl/n) for n in
                ('uart_rx_b_7020_observe_v0_1.v','rx_ce_gen_7020_v2_2.v','tb_b_receiver_cosim.sv')})
    def command(args,name):
        with (out/(name+'.log')).open('w',encoding='utf-8') as log:
            result=subprocess.run(args,cwd=out,stdout=log,stderr=subprocess.STDOUT,timeout=600)
        if result.returncode!=0:raise RuntimeError(name+'_FAILED_RETURN_'+str(result.returncode))
    try:
        count,cycles=generate(root,out);report.update(expected_cases=count,expected_compared_clocks=cycles)
        print('Prepared',count,'cases and',cycles,'clock comparisons',flush=True)
        sim=Path(simulator).resolve()
        def exe(n):return str(sim/(n+'.exe' if (sim/(n+'.exe')).is_file() else n))
        version=subprocess.run([exe('vsim'),'-version'],capture_output=True,text=True,timeout=30)
        report['simulator']=version.stdout.strip() or version.stderr.strip()
        command([exe('vlib'),'work'],'vlib')
        command([exe('vlog'),'-sv','-work','work']+[str(rtl/n) for n in
                ('uart_rx_b_7020_observe_v0_1.v','rx_ce_gen_7020_v2_2.v','tb_b_receiver_cosim.sv')],'vlog')
        (out/'run.do').write_text('onerror {quit -code 2}\nonfinish stop\nrun -all\nquit -f\n',encoding='ascii')
        command([exe('vsim'),'-c','-l',str(out/'transcript.log'),'-wlf',str(out/'wave.wlf'),
                 'work.tb_b_receiver_cosim','-do','run.do'],'vsim')
        text=(out/'vsim.log').read_text(encoding='utf-8',errors='replace')
        match=re.search(r'B_RX_RTL_COSIM_PASS cases=(\d+) cycles=(\d+)',text)
        if 'B_RX_RTL_FAIL' in text or not match or tuple(map(int,match.groups()))!=(count,cycles):
            raise RuntimeError('RTL_SCOREBOARD_DID_NOT_PASS_EXACT_COUNTS')
        report.update(status='PASS',actual_cases=count,actual_compared_clocks=cycles,
                      vector_manifest_sha256=sha(out/'vector_manifest.json'),simulator_log_sha256=sha(out/'vsim.log'))
    except Exception as error:
        report.update(status='FAIL',error=repr(error))
    (out/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False,indent=2),flush=True)
    return 0 if report['status']=='PASS' else 2


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',required=True);p.add_argument('--simulator-dir',required=True)
    a=p.parse_args();sys.exit(run(a.output,a.simulator_dir))
