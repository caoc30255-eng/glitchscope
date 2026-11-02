"""Self-contained read-only HTML/SVG report; no server or external assets."""
from pathlib import Path
import json,hashlib

ROOT=Path(__file__).resolve().parent
def rle(values):
    return [[i,v] for i,v in enumerate(values) if i==0 or v!=values[i-1]]

def viewer_item(item,envelope,baseline,record):
    out=dict(item,source=None,raw=None,profiles=[],anchor=baseline.get('target_start_index'),
        period=baseline.get('byte_period_clocks'),target=baseline.get('target_byte'),
        target_bit=baseline.get('target_bit'),actual_local_bit_errors=envelope.get('actual_local_bit_errors'),
        phases=envelope.get('retained_phases',[]),warmup=baseline.get('warmup'))
    if record is None:return out
    out.update(source=list(record['source']),raw=rle(record['levels']),
        actual_B=[s['data'] for s in record['lanes']['b']],actual_B_flags=[s['flags'] for s in record['lanes']['b']])
    for row in envelope.get('profiles',[]):
        scenarios=[]
        for s in row['scenarios']:
            frames=[]
            for f in s.get('frames',[]):
                votes=[]
                for v in f['votes']:
                    votes.append([8 if v['bit']=='STOP' else v['bit']]+v['indices']+v['values']+[v['decision']])
                frames.append([f['byte_index'],f['start_index'],f['valid_index'],f['data'],int(f['framing_error']),votes])
            scenarios.append([s['phase'],bool(s.get('aligned')),s.get('bit_errors'),s.get('framing_errors'),frames])
        out['profiles'].append(dict(d=row['d'],s=row['s'],state=row['state'],low=row['bit_errors_min'],high=row['bit_errors_max'],scenarios=scenarios))
    return out

def safe_json(value):
    return json.dumps(value,ensure_ascii=False,separators=(',',':'),allow_nan=False).replace('<','\\u003c').replace('&','\\u0026').replace('\u2028','\\u2028').replace('\u2029','\\u2029')

def render(output):
    out=Path(output);summary=json.loads((out/'summary.json').read_bytes())
    items=[]
    for item in summary['items']:
        p=out/'items'/('item_%02d'%item['item_index'])/'viewer.json'
        items.append(json.loads(p.read_bytes()) if p.exists() else dict(item,raw=None,profiles=[],phases=[]))
    payload=dict(summary=summary,items=items)
    template=(ROOT/'report_template.html').read_text(encoding='utf-8')
    script=(ROOT/'viewer.js').read_text(encoding='utf-8')
    html=template.replace('/*__VIEWER_SCRIPT__*/',script).replace('__REPORT_PAYLOAD__',safe_json(payload))
    with (out/'report.html').open('x',encoding='utf-8') as f:f.write(html)
    lines=['# 第三功能分析报告','', '会话：'+summary['session'],'',
        '状态：'+summary['job_state'],'',
        '统一d/s软件候选：'+json.dumps(summary['global_minimax_candidate_set'],ensure_ascii=False),'',
        '达到声明门槛的候选区域：'+json.dumps(summary['threshold_candidate_region'],ensure_ascii=False),'',
        '局部参考候选：基于%d/64块，仅供参考。'%summary['local_reference']['covered_windows']+json.dumps(summary['local_reference']['candidate_set'],ensure_ascii=False),'',
        '未参与局部参考的ITEM（从1计数）：'+','.join(str(x['item_index']+1) for x in summary['local_reference']['excluded_items']),'',
        '以下是局部窗口软件模型的保守范围，不是候选配置的整图实测误码。','',
        '|d|s|已评分窗口|局部位数|误码下界|误码上界|全64排名资格|','|---:|---:|---:|---:|---:|---:|---|']
    for p in summary['profiles']:lines.append('|{d}|{s}|{evaluated_windows}/64|{compared_local_bits}|{bit_errors_lower_bound}|{bit_errors_upper_bound}|{eligible_for_global_software_ranking}|'.format(**p))
    lines+=['','输入门控：'+summary['input_gate'],'','参考前缀假设：'+str(summary['unmeasured_prefix_assumption']),
        '','硬件验证推荐区域为空；不替换原接收数据，不发送新START。',
        '','报告包含全局候选与门槛区域、64块状态、三条轨迹、相位与表决点浏览，以及JSON/CSV/SVG导出。',
        '','完整原始接收证据另存于原会话；本目录是分析产物。']
    with (out/'report_notes.md').open('x',encoding='utf-8') as f:f.write('\n'.join(lines)+'\n')

def seal_output(out):
    out=Path(out);files={}
    for p in sorted(out.rglob('*')):
        if p.is_file() and p.name!='output_sha256.json':
            raw=p.read_bytes();files[p.relative_to(out).as_posix()]=dict(bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())
    with (out/'output_sha256.json').open('x',encoding='utf-8') as f:json.dump(files,f,ensure_ascii=False,indent=2)

def verify_output(out):
    out=Path(out).resolve();manifest=json.loads((out/'output_sha256.json').read_bytes())
    for name,proof in manifest.items():
        p=(out/name).resolve()
        if out not in p.parents:raise ValueError('OUTPUT_PATH_ESCAPE')
        raw=p.read_bytes()
        if len(raw)!=proof['bytes'] or hashlib.sha256(raw).hexdigest()!=proof['sha256']:raise ValueError('OUTPUT_CHANGED:'+name)
    return dict(status='PASS_OUTPUT_MANIFEST',files=len(manifest),hardware_access=False)

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--verify',required=True);a=p.parse_args();print(json.dumps(verify_output(a.verify),indent=2))
