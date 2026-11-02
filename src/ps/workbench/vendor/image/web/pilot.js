const $=id=>document.getElementById(id);let current=null,busy=false,loading=false;
const pretty=v=>JSON.stringify(v,null,2),label=v=>v===true?'正确':v===false?'不正确':'— / UNKNOWN';
function err(e){$('error').textContent=e.message||String(e);$('error').style.display='block'}
function controls(){let s=current?.pilot?.state;$('pilotStart').disabled=busy||!current?.linked||s!=='READY';$('pilotStop').disabled=busy||!current?.linked||!['READY','RUNNING','STOPPING'].includes(s)}
function operationKey(action,p){let name='pynq_fixed_pilot_'+p.session+'_'+p.plan_sha256+'_'+action;let k=localStorage.getItem(name);if(!k){k=crypto.randomUUID();localStorage.setItem(name,k)}return k}
async function refresh(){if(loading)return;loading=true;try{let r=await fetch('/api/pilot');if(!r.ok)throw Error('连接状态读取失败');current=await r.json();
 $('connection').textContent=current.linked?'已连接真实板卡执行器':'未连接真实板卡执行器';
 $('mode').textContent=current.linked?'当前为新采集固定四条联调；历史回放和模拟有独立入口':'当前可体验模拟与历史回放；真实启动按钮不可用';
 if(!current.linked){$('pilotState').textContent='NOT_LINKED · 不会访问板卡';return}
 let p=current.pilot;$('pilotState').textContent=p.session+' · '+p.state+(p.inflight?' · 当前记录处理中':'');
 $('progress').textContent='已尝试 '+p.attempts+' / 4；已核验 '+p.completed_records+' / 4'+(p.stop_requested?'；已请求停止剩余项':'');
 $('plan').textContent=pretty({plan_sha256:p.plan_sha256,plan:p.plan});$('details').textContent=pretty(p);
 $('records').replaceChildren();for(let row of p.results){let r=row.result,f=row.feedback,tr=document.createElement('tr');
 for(let text of [r.record_id,r.kind,'d='+r.actual_receiver_B.d+', s='+r.actual_receiver_B.s,label(r.receiver_A_frame_correct),label(r.receiver_B_frame_correct),label(r.STM_business_success),f.strict_retirement_verified===true?'已核验':'未核验']){let td=document.createElement('td');td.textContent=text;tr.appendChild(td)}$('records').appendChild(tr)}
 $('export').hidden=!['COMPLETE','STOPPED','BLOCKED_ERROR','BLOCKED_UNKNOWN','BLOCKED_STORAGE'].includes(p.state);
 }catch(e){err(e);current=null}finally{loading=false;controls()}}
async function command(action){if(busy||!current?.linked)return;let p=current.pilot;if(action==='start'&&p.state!=='READY')return;
 busy=true;controls();try{let r=await fetch('/api/pilot/'+action,{method:'POST',headers:{'Content-Type':'application/json','X-Lab-Token':current.csrf},body:JSON.stringify({idempotency_key:operationKey(action,p),plan_sha256:p.plan_sha256})});let v=await r.json();if(!r.ok)throw Error(v.error||'命令未接受');await refresh()}catch(e){err(e)}finally{busy=false;controls()}}
window.addEventListener('unhandledrejection',e=>err(e.reason));$('pilotStart').onclick=()=>command('start');$('pilotStop').onclick=()=>command('stop');refresh();setInterval(refresh,1200);
