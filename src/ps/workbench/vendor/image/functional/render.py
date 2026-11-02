import csv,html,io
def svg_heatmap(result,target):
    cells=result['cells'];phases=sorted({c['phase'] for c in cells});widths=sorted({c['width'] for c in cells});w=110+len(widths)*85;h=100+len(phases)*65
    content=['<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d">'%(w,h),'<rect width="100%" height="100%" fill="#0e1825"/>',
        '<text x="15" y="24" fill="white">%s · d=%s/s=%s · generator tick nominal 20 ns</text>'%(html.escape(target),result['fixed']['d'],result['fixed']['s'])]
    for c in cells:
        x=90+widths.index(c['width'])*85;y=65+phases.index(c['phase'])*65;s=c['targets'][target]
        color='#374151' if not c['legal'] else '#d97706' if s['unknown'] else '#152434' if s['fraction'] is None else '#22a68b' if s['fraction']>=.5 else '#c95c64'
        label='非法' if not c['legal'] else 'UNKNOWN' if s['unknown'] else '未测' if s['fraction'] is None else '%d/%d'%(s['success'],s['valid'])
        content+=['<rect x="%d" y="%d" width="80" height="60" fill="%s" stroke="#577082"/>'%(x,y,color),
            '<text x="%d" y="%d" fill="white" font-size="12">p%d / w%d</text>'%(x+5,y+18,c['phase'],c['width']),
            '<text x="%d" y="%d" fill="white" font-size="13">%s</text>'%(x+5,y+41,label)]
    return ('\n'.join(content)+'</svg>').encode('utf-8')
def csv_heatmap(result):
    out=io.StringIO(newline='');writer=csv.writer(out);writer.writerow(['phase_tick','width_tick','legal','state','target','valid','success','failure','UNKNOWN','rate','UIDs','required_repeats','occupied_ITEMs','missing_repeats','excess_repeats','valid_measurements_sufficient'])
    for c in result['cells']:
        for t,s in c['targets'].items():writer.writerow([c['phase'],c['width'],c['legal'],c['status'],t,s['valid'],s['success'],s['failure'],s['unknown'],s['fraction'],','.join(r['uid'] for r in c['measurements'])]+[c['completion'][k] for k in ('required_repeats','occupied_ITEMs','missing_repeats','excess_repeats','valid_measurements_sufficient')])
    return out.getvalue().encode('utf-8-sig')
