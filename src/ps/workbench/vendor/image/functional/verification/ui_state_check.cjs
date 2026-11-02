// Exercise actual app.js async handlers with deterministic deferred transport.
// This is a JS unit harness, not browser automation; browser proof is separate.
const fs=require('fs'),vm=require('vm'),assert=require('assert');
const root=require('path').resolve(__dirname,'..');
const fixtures=JSON.parse(fs.readFileSync(process.argv[2],'utf8'));
const elements={},storage=new Map([['lab_plan_hash',fixtures.custom.plan_sha256]]);let posts=[],pending=null,mode='defer';
function element(id){return elements[id]||(elements[id]={id,value:'',disabled:false,style:{},options:[{value:'B_frame_correct,STM_business_success'},{value:'B_frame_correct'},{value:'STM_business_success'}],handlers:{},
    addEventListener(event,fn){this.handlers[event]=fn},add(o){this.options.push(o)},replaceChildren(){},appendChild(){},classList:{add(){},toggle(){}}});}
element('imageMethod').value='crc_burst_B';element('seed').value='11';element('unknownRate').value='0';element('strategy').value='grid';
const state={csrf:'test',default_plans:{3:fixtures.default},runs:[],image_metrics:JSON.parse(fs.readFileSync(root+'/results/image_repair/metrics.json')),algorithms:null};
const reply=value=>({ok:true,json:async()=>value});
const context=vm.createContext({console,crypto:{randomUUID:()=>String(Math.random())},Option:function(text,value){this.value=value},
 document:{getElementById:element,querySelectorAll:()=>[],createElement:()=>element('generated')},
 localStorage:{getItem:k=>storage.get(k)||null,setItem:(k,v)=>storage.set(k,v),removeItem:k=>storage.delete(k)},
 setTimeout(){},setInterval(){},window:{open(){}},fetch:async(url,opts)=>{
  if(!opts){if(url==='/api/state')return reply(state);if(url.startsWith('/api/plan'))return reply(fixtures.custom);return reply({cells:[],predictions:[],coverage:{legal:0,measured:0,unknown:0}});}
  posts.push({url,body:JSON.parse(opts.body)});
  if(mode==='reject')return {ok:false,json:async()=>({error:'invalid preview'})};
  return await new Promise(resolve=>pending=resolve);
 }});
vm.runInContext(fs.readFileSync(root+'/web/app.js','utf8'),context);
const drain=()=>new Promise(resolve=>setImmediate(resolve));
(async()=>{
 await drain();await drain();assert.equal(element('d').value,4);assert.equal(element('repeats').value,2);assert.equal(element('budget').value,30);assert.equal(element('target').value,'STM_business_success');
 for(const key of ['s','byte','bit'])assert.equal(element(key).value,fixtures.custom.fixed[key]);
 assert.equal(element('phases').value,fixtures.custom.phases.join(','));assert.equal(element('widths').value,fixtures.custom.widths.join(','));
 assert(element('planSummary').textContent.includes('d=4'));assert(!element('start').disabled);
 element('d').value=3;element('d').handlers.input();assert(element('start').disabled);
 await element('start').onclick();assert.equal(posts.length,0);
 let preview=element('preview').onclick();await drain();assert(element('start').disabled);await element('start').onclick();assert.equal(posts.length,1);
 element('d').value=2;element('d').handlers.input();pending(reply(fixtures.default));await preview;
 assert(element('start').disabled);assert(element('planSummary').textContent.includes('d=4'));
 element('d').value=4;element('d').handlers.input();preview=element('preview').onclick();await drain();pending(reply(fixtures.custom));await preview;assert(!element('start').disabled);
 let start=element('start').onclick();await drain();assert(element('preview').disabled);assert(element('d').disabled);
 await element('start').onclick();await element('preview').onclick();assert.equal(posts.filter(x=>x.url==='/api/start').length,1);
 const run={run_id:'unit-test-run',plan_sha256:fixtures.custom.plan_sha256,state:'RUNNING',used_starts:0,cancelled_unstarted:0};state.runs=[run];pending(reply(run));await start;
 element('budget').value=1;element('budget').handlers.input();mode='reject';await element('preview').onclick();assert(element('start').disabled);
 const report={status:'PASS',full_form_restore:true,dirty_blocks_start:true,pending_preview_blocks_start:true,stale_preview_discarded:true,start_double_click_single_POST:true,start_locks_preview_and_fields:true,failed_preview_stays_blocked:true};
 fs.writeFileSync(process.argv[3],JSON.stringify(report,null,2));console.log(JSON.stringify(report));
})().catch(e=>{console.error(e);process.exitCode=1});
