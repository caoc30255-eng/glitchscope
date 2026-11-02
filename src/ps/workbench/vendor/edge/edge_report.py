"""Self-contained model/evaluation report. No live data or network requests."""
from pathlib import Path
import json,html,sys,csv
ROOT=Path(__file__).resolve().parent;sys.path.insert(0,str(ROOT/'backend'))
from edge_api import EdgeAI
from custom_ai_core import TARGETS,query,canonical

NAMES={'B_frame_correct':'B完整帧正确','STM_payload_correct':'STM载荷正确','STM_business_success':'STM业务成功'}
def pct(v):return '—' if v is None else '%.1f%%'%(100*v)

def render(output):
    out=Path(output).resolve()
    if out==ROOT or ROOT in out.parents or out in ROOT.parents:raise ValueError('OUTPUT_OVERLAPS_PACKAGE')
    out.mkdir(parents=True,exist_ok=False);service=EdgeAI();evaluation=json.loads((ROOT/'reports/evaluation.json').read_bytes())
    rows=[];sections=[]
    for target in TARGETS:
        ev=evaluation['targets'][target];cv=ev['grouped_CV_raw'];val=ev['validation']['selective']
        sections.append('<h2>'+NAMES[target]+'</h2><p>按格点留出诊断：可估计覆盖 '+pct(cv['score_coverage'])+'，已估计记录的0.5阈值粗分类准确率 '+pct(cv['accuracy'])+'。验证集明确判定覆盖 '+pct(val['coverage'])+'，错误判断通过 '+str(val['FP_false_PASS'])+' 条。</p>')
        for d in (3,4):
            sections.append('<h3>d='+str(d)+'，s=−1</h3><table><tr><th>相位 / 宽度</th>'+''.join('<th>'+str(w)+'</th>' for w in (1,5,10,15,20,25,30,35,40))+'</tr>')
            for phase in (5,10,15,20,25,30,35):
                sections.append('<tr><th>'+str(phase)+'</th>')
                for width in (1,5,10,15,20,25,30,35,40):
                    if phase+width>45:sections.append('<td class="invalid">非法</td>');continue
                    prediction=service.predict(query(d=d,phase=phase,width=width,target=target));score=prediction['score'];obs=prediction.get('training_observation')
                    label='拒答' if score is None else '%.2f'%score
                    detail='未见训练格点' if obs is None else '训练观测 %d/%d'%(obs['successes'],obs['n'])
                    color='#eef2f6' if score is None else 'hsl(%d 55%% 88%%)'%int(score*125)
                    title=html.escape(detail+'；'+prediction['reason'])
                    sections.append('<td style="background:'+color+'" title="'+title+'">'+label+'<small>'+html.escape(detail)+'</small></td>')
                    rows.append(dict(prediction,d=d,s=-1,phase=phase,width=width))
                sections.append('</tr>')
            sections.append('</table>')
    intro='''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>GLITCHSCOPE 边缘AI v1.0</title>
<style>body{font-family:system-ui,"Microsoft YaHei",sans-serif;background:#f4f6fa;color:#1b2b42;max-width:1200px;margin:auto;padding:32px}h1{font-size:30px}p{line-height:1.8}table{border-collapse:collapse;width:100%;margin:12px 0 30px;background:white}th,td{padding:10px;border:1px solid #d7dfe9;text-align:center}small{display:block;font-size:10px;color:#526070;margin-top:5px}.invalid{background:#e6e8ed;color:#9096a0}.note{padding:18px;background:#fff2d9;border-left:4px solid #d99722}code{overflow-wrap:anywhere}h2{margin-top:44px}</style>
<h1>GLITCHSCOPE · 边缘AI软件候选 v1.0</h1>
<p>用途：辅助容错扫描选择优先实测的格点。三个目标分别建模，真实扫描结果仍由原始证据决定。</p>
<div class="note">以下颜色和数字为未校准的模型分数，不是硬件可靠率或当前实测热力图。训练观测单独标出；“未见训练格点”是插值估计。明确判定覆盖率较低，不能将已回答样本零误判解释为全模型100%准确。</div>
<p>当前学习范围：递增256字节载荷00…ff、单点毛刺、byte20/bit0、route0，已训练d3/d4、s=−1。有效估计限于训练坐标包络；其他合法实验条件可由已声明的规则回退处理。</p>
<p>84条训练、40条验证、30条历史检查，按格点整体留组；数据为公开回顾性开发资料。STM模型不使用B接收器d/s作为预测特征。尚未证明新设备泛化或真实硬件提效。</p>'''
    tail='<h2>交付状态</h2><p>训练、推理、预算选点和反馈队列软件已提供；新反馈训练更新需人工审批。板端时延需运行arm_check.py实测；此报告不授予硬件执行权限。</p><p>模型SHA：<code>'+service.model.model_sha256+'</code></p></html>'
    (out/'report.html').write_text(intro+''.join(sections)+tail,encoding='utf-8')
    (out/'predictions.json').write_bytes(canonical(rows)+b'\n')
    with (out/'scores.csv').open('x',encoding='utf-8-sig',newline='') as f:
        columns=['target','d','s','phase','width','action','prediction','score','support','reason'];w=csv.DictWriter(f,fieldnames=columns);w.writeheader()
        w.writerows({k:r.get(k) for k in columns} for r in rows)
    print('REPORT',out/'report.html');return out/'report.html'

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--output',required=True);a=p.parse_args();render(a.output)
