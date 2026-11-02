import json,sys,urllib.request,urllib.error
from pathlib import Path
url=sys.argv[1];state=json.loads(urllib.request.urlopen(url+'/api/state').read());report=[]
for d,s in [(1,-2),(1,2),(2,1),(3,0),(4,-1),(0,127),(5,-1),(4,0),(1,-3)]:
    body=dict(phases=[15],widths=[20],d=d,s=s,byte=20,bit=0,repeats=1,budget=3,targets=['B_frame_correct'])
    request=urllib.request.Request(url+'/api/plan',data=json.dumps(body).encode(),headers={'Content-Type':'application/json','X-Lab-Token':state['csrf']})
    expected=1<=d<=4 and -2<=s<=3-d
    try:
        result=json.loads(urllib.request.urlopen(request).read());assert expected
        assert result['fixed']['d']==d and result['fixed']['s']==s
    except urllib.error.HTTPError as e:
        error=e.read();assert not expected and e.code==409 and b'RECEIVER_PROFILE_CURRENT' in error
    report.append(dict(d=d,s=s,accepted=expected))
Path(sys.argv[2]).write_text(json.dumps(dict(status='PASS',cases=report),indent=2),encoding='utf-8');print('HTTP profile cases PASS:',len(report))
