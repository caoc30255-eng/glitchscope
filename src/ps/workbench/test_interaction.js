'use strict';
// UI state contracts in Node only. Real historical images, synthetic task states.
const fs=require('fs'),path=require('path'),vm=require('vm'),assert=require('assert');
const nodes=new Map(),listeners={};
const node=q=>{if(!nodes.has(q))nodes.set(q,{id:q.slice(1),innerHTML:'',textContent:'',hidden:false,style:{},classList:{toggle(){},remove(){}},showModal(){},close(){},closest(){return null;},setPointerCapture(id){this.pointer=id;},getBoundingClientRect(){return {left:100,width:400};}});return nodes.get(q);};
const ctx=vm.createContext({console,document:{querySelector:node,querySelectorAll:()=>[],addEventListener(k,f){(listeners[k]??=[]).push(f);},body:{classList:{toggle(){},remove(){}}}},window:{addEventListener(){}},location:{hash:'#overview'},fetch:()=>new Promise(()=>{}),setTimeout(){},clearTimeout(){},FormData:function(){return []},crypto:require('crypto').webcrypto,URL,Blob,Uint8Array,TextEncoder});
for(const name of ['presentation.js','interaction.js','authorization.js','demo-ui.js','app.js'])vm.runInContext(fs.readFileSync(path.join(__dirname,'web',name),'utf8'),ctx);
ctx.catalog=JSON.parse(fs.readFileSync(path.join(__dirname,'samples/catalog.json'),'utf8'));
ctx.imageReport=JSON.parse(fs.readFileSync(path.join(__dirname,'samples/image49/report.json'),'utf8'));
const run=s=>vm.runInContext(s,ctx);
run("S.catalog=catalog;S.status={live_configured:false,assets:[],sessions:[],jobs:[]};S.page='evaluate'");
let html=run('renderEvaluation()');assert(html.includes('还没有分析任务'));assert(!html.includes('data-ds-id="candidate"'));assert(html.includes('id="analysis-config"'));assert(html.includes('open'));
run("S.analysisViewMode='running'");html=run('renderEvaluation()');assert(html.includes('正在分析接收证据'));assert(!html.includes('data-ds-id="candidate"'));
run("S.analysisViewMode='failed';S.analysisError='fixture only'");html=run('renderEvaluation()');assert(html.includes('本次分析已停止'));assert(!html.includes('data-ds-id="candidate"'));
run("S.analysisViewMode='history'");assert(run('renderEvaluation()').includes('载入分析结果'));
run("S.imageResults={base:'/samples/image49/',historical:true,result:imageReport};comparisonPanel(S.imageResults)");
const sources=JSON.parse(run('JSON.stringify(imageSources(S.imageResults))'));assert(sources.length>=7);let pairs=0;
for(const left of sources)for(const right of sources){ctx.left=left.key;ctx.right=right.key;run('S.compare.left=left;S.compare.right=right;updateComparison()');assert.strictEqual(node('#compare-left-image').src,left.url);assert.strictEqual(node('#compare-right-image').src,right.url);pairs++;}
run('setComparePosition(0)');assert.strictEqual(node('#compare-left-layer').style.clipPath,'inset(0 100% 0 0)');
run('setComparePosition(100)');assert.strictEqual(node('#compare-left-layer').style.clipPath,'inset(0 0% 0 0)');
run('setComparePosition(-30)');assert.strictEqual(run('S.compare.position'),0);
run('setComparePosition(140)');assert.strictEqual(run('S.compare.position'),100);
run('setComparePosition(50)');
listeners.pointerdown[0]({target:{closest:()=>node('#comparison-stage')},button:0,pointerId:7,clientX:200,preventDefault(){}});assert.strictEqual(run('S.compare.position'),25);
listeners.pointermove[0]({pointerId:7,clientX:400});assert.strictEqual(run('S.compare.position'),75);listeners.pointerup[0]({pointerId:7});
for(const f of listeners.keydown)f({target:node('#comparison-stage'),key:'ArrowLeft',shiftKey:true,preventDefault(){}});assert.strictEqual(run('S.compare.position'),65);
const job={id:'a'.repeat(32),action:'ds_analysis',state:'RUNNING',events:[{stage:'ANALYZING',completed_records:12,max_records:64}]};ctx.job=job;run('trackJob(job,true);S.dismissedJob=null;updateDock()');assert(!node('#task-dock').hidden);assert(node('#task-dock').innerHTML.includes('12 / 64'));
for(const p of ['overview','scan','images','evaluate','sessions','reports']){ctx.location.hash='#'+p;run('render()');assert(!node('#task-dock').hidden);assert(!node('#main').innerHTML.includes('progress-panel'));}
assert.strictEqual(run('taskProgress(S.job).percent'),18.75);
ctx.unknown={...job,state:'COMPLETE',result:{statistics:{state:'BLOCKED_UNKNOWN'}}};assert(run('taskProgress(unknown).blocked'));
const css=fs.readFileSync(path.join(__dirname,'web/interaction.css'),'utf8');assert(css.includes('position:fixed'));assert(css.includes('z-index:90'));assert(css.includes('aspect-ratio:1'));
const index=fs.readFileSync(path.join(__dirname,'web/index.html'),'utf8');assert(index.indexOf('id="task-dock"')<index.indexOf('<dialog'));assert(index.indexOf('src="interaction.js"')<index.indexOf('src="app.js"'));
console.log(JSON.stringify({status:'PASS_UI_V1_2_INTERACTION',analysis_empty_running_failure_guards:true,comparison_source_pairs:pairs,comparison_pointer_keyboard_and_edges:true,global_dock_across_pages:6,unknown_not_shown_as_success:true,browser_started:false,hardware_access:false},null,2));
