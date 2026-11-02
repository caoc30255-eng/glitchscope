"""Headless JSON/CSV export. No web page or production service."""
import csv,io,json
from pathlib import Path
from custom_plan import raw,TARGETS
from custom_stats import aggregate

def export(directory,owner):
    directory=Path(directory);directory.mkdir(parents=True,exist_ok=False)
    rows=owner.checked_records();stats=aggregate(owner.plan,rows,owner.session.root.name)
    stats['confirmation_groups']=owner.confirmation_groups()
    data={'plan.json':raw(owner.plan)+b'\n','status.json':raw(owner.status())+b'\n','records.jsonl':b''.join(raw(r)+b'\n' for r in rows),
        'decisions.jsonl':b''.join(raw(d)+b'\n' for d in owner.decisions),'statistics.json':raw(stats)+b'\n'}
    out=io.StringIO(newline='');writer=csv.writer(out);writer.writerow(['condition_sha256','d','s','payload_sha256','route_mode','mode','byte','bit','phase','width','count','target','state','success','failure','unknown','valid','required'])
    for cell in stats['conditions']:
        c=cell['condition']
        for target,v in cell['per_target'].items():writer.writerow([c['condition_sha256'],c['receiver_B']['d'],c['receiver_B']['s'],c['payload_sha256'],c['route_mode'],c['mode'],c['fault']['byte'],c['fault']['bit'],c['fault']['phase'],c['fault']['width'],c['count'],target,v['state'],v['success'],v['failure'],v['unknown'],v['valid'],v['required']])
    data['statistics.csv']=out.getvalue().encode('utf-8-sig')
    for name,value in data.items():
        with (directory/name).open('xb') as f:f.write(value)
    from custom_heatmaps import write_maps
    write_maps(directory/'heatmaps',stats,owner.origin)
    return stats
