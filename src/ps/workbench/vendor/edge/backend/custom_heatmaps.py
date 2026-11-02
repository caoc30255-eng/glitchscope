"""Traceable static three-target maps; no interpolation or added measurements."""
import csv
import html
import io
import json
from pathlib import Path
from custom_plan import TARGETS, raw
from learning_domain import digest


def write_maps(directory, stats, origin):
    directory=Path(directory);directory.mkdir(parents=True,exist_ok=False)
    groups={}
    for cell in stats['conditions']:
        c=cell['condition'];context={k:v for k,v in c.items() if k not in ('fault','condition_sha256','condition_id')}
        context['byte']=c['fault']['byte'];context['bit']=c['fault']['bit']
        groups.setdefault(digest(context)[:16],dict(context=context,cells=[]))['cells'].append(cell)
    max_columns=max((len({c['condition']['fault']['width'] for c in g['cells']}) for g in groups.values()),default=1)
    canvas_width=max(1100,160+max_columns*132)
    canvas_height=120+sum(115+len({c['condition']['fault']['phase'] for c in g['cells']})*76 for g in groups.values())
    for target in TARGETS:
        rows=[];svg=['<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" viewBox="0 0 %d %d">'%(canvas_width,canvas_height,canvas_width,canvas_height),
                   '<rect width="100%" height="100%" fill="#101827"/>',
                   '<text x="24" y="32" fill="#f8fafc" font-family="sans-serif" font-size="19">'+html.escape(target+' | '+origin)+'</text>',
                   '<text x="24" y="57" fill="#94a3b8" font-family="sans-serif" font-size="12">X: width ticks; Y: phase ticks. Separate full stimulus groups. No interpolation. Counts are observations.</text>']
        y=88
        for group_id,group in groups.items():
            cells=group['cells'];widths=sorted({c['condition']['fault']['width'] for c in cells});phases=sorted({c['condition']['fault']['phase'] for c in cells})
            context=group['context'];label='d%s / s%s | %s | byte %s / payload offset %s / bit %s | count %s | payload %s'%(context['receiver_B']['d'],context['receiver_B']['s'],context['mode'],context['byte'],context['byte']-20,context['bit'],context['count'],context['payload_sha256'][:12])
            svg.append('<text x="24" y="%d" fill="#e2e8f0" font-family="sans-serif" font-size="14">%s</text>'%(y,html.escape(label)));y+=42
            for i,w in enumerate(widths):svg.append('<text x="%d" y="%d" fill="#cbd5e1" font-family="sans-serif" font-size="12">width %d</text>'%(112+i*132,y,w))
            y+=18
            for i,phase in enumerate(phases):svg.append('<text x="24" y="%d" fill="#cbd5e1" font-family="sans-serif" font-size="12">phase %d</text>'%(y+i*76+31,phase))
            for cell in sorted(cells,key=lambda c:(c['condition']['fault']['phase'],c['condition']['fault']['width'])):
                c=cell['condition'];v=cell['per_target'][target];state=v['state']
                colors={'UNMEASURED':'#283346','PARTIAL':'#9b762a','MIXED':'#a169c4','UNKNOWN':'#64748b','OBSERVED_ALL_PASS':'#177f6b','OBSERVED_ALL_FAIL':'#ae4d55'}
                x=102+widths.index(c['fault']['width'])*132;cy=y+phases.index(c['fault']['phase'])*76
                caption='%s / %s / %s'%(v['success'],v['failure'],v['unknown'])
                title=html.escape(json.dumps(dict(condition=c,counts=v,records=cell['record_refs']),ensure_ascii=True))
                short={'UNMEASURED':'UNMEASURED','PARTIAL':'PARTIAL','MIXED':'MIXED','UNKNOWN':'UNKNOWN','OBSERVED_ALL_PASS':'ALL PASS observed','OBSERVED_ALL_FAIL':'ALL FAIL observed'}[state]
                svg.extend(['<g><title>'+title+'</title><rect x="%d" y="%d" width="124" height="66" rx="6" fill="%s"/>'%(x,cy,colors[state]),
                    '<text x="%d" y="%d" fill="#fff" font-family="sans-serif" font-size="11">%s</text>'%(x+8,cy+23,short),
                    '<text x="%d" y="%d" fill="#fff" font-family="sans-serif" font-size="12">%s (P/F/U)</text></g>'%(x+8,cy+46,caption)])
                rows.append(dict(group_id=group_id,condition=c,counts=v,record_refs=cell['record_refs']))
            y+=len(phases)*76+55
        svg.append('</svg>')
        (directory/(target+'.svg')).write_text('\n'.join(svg),encoding='utf-8')
        (directory/(target+'.json')).write_bytes(raw(dict(schema='TRACEABLE_FINITE_CELLS_V0_2',origin=origin,target=target,plan_sha256=stats['plan_sha256'],interpolated=False,rows=rows))+b'\n')
        out=io.StringIO(newline='');writer=csv.writer(out);writer.writerow(['group_id','condition_sha256','d','s','mode','byte','payload_offset','bit','count','phase','width','state','success','failure','unknown','valid','required','record_refs_json'])
        for row in rows:
            c=row['condition'];f=c['fault'];v=row['counts']
            writer.writerow([row['group_id'],c['condition_sha256'],c['receiver_B']['d'],c['receiver_B']['s'],c['mode'],f['byte'],f['byte']-20,f['bit'],c['count'],f['phase'],f['width'],v['state'],v['success'],v['failure'],v['unknown'],v['valid'],v['required'],json.dumps(row['record_refs'],ensure_ascii=True)])
        (directory/(target+'.csv')).write_text(out.getvalue(),encoding='utf-8-sig')
