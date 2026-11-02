'use strict';
// Source/DOM-contract execution in Node VM. Does not start or control a browser.
const fs=require('fs'),path=require('path'),vm=require('vm'),assert=require('assert');
const nodes=new Map(),node=q=>{if(!nodes.has(q))nodes.set(q,{innerHTML:'',textContent:'',hidden:false,style:{},classList:{toggle(){},remove(){}},showModal(){},close(){}});return nodes.get(q)};
let input={};
const ctx=vm.createContext({console,document:{querySelector:node,querySelectorAll:()=>[],addEventListener(){},body:{classList:{toggle(){},remove(){}}}},window:{addEventListener(){}},location:{hash:'#overview'},fetch:()=>new Promise(()=>{}),setTimeout(){},clearTimeout(){},FormData:function(){return Object.entries(input)},crypto:require('crypto').webcrypto,URL,Blob,Uint8Array,TextEncoder});
vm.runInContext(fs.readFileSync(path.join(__dirname,'web/presentation.js'),'utf8'),ctx);
vm.runInContext(fs.readFileSync(path.join(__dirname,'web/interaction.js'),'utf8'),ctx);
vm.runInContext(fs.readFileSync(path.join(__dirname,'web/authorization.js'),'utf8'),ctx);
vm.runInContext(fs.readFileSync(path.join(__dirname,'web/demo-ui.js'),'utf8'),ctx);
vm.runInContext(fs.readFileSync(path.join(__dirname,'web/app.js'),'utf8'),ctx);
ctx.catalog=JSON.parse(fs.readFileSync(path.join(__dirname,'samples/catalog.json'),'utf8'));
ctx.history=JSON.parse(fs.readFileSync(path.join(__dirname,'samples/c_reference44.json'),'utf8'));
vm.runInContext("S.catalog=catalog;S.status={live_configured:false,assets:[],sessions:[],jobs:[]};S.scanResult=history",ctx);
const checks=[];
for(const route of ['overview','scan','images','evaluate','ai','sessions','reports']){
 ctx.location.hash='#'+route;vm.runInContext('render()',ctx);
 const html=node('#main').innerHTML;assert(html.length>300);assert(!html.includes('UI-S024'));assert(!html.includes('播放演示'));assert(!html.includes('尚未证明比规则更优'));
 checks.push({page:route,rendered:true,characters:html.length});
}
ctx.location.hash='#scan';vm.runInContext('render()',ctx);assert(node('#main').innerHTML.includes('2/3'));
assert(node('#main').innerHTML.includes('data-action="point"'));
ctx.imageReport=JSON.parse(fs.readFileSync(path.join(__dirname,'samples/image49/report.json'),'utf8'));
vm.runInContext("S.imageResults={historical:true,base:'/samples/image49/',exportURL:'/samples/image49_results.zip',result:imageReport}",ctx);
ctx.location.hash='#images';vm.runInContext('render()',ctx);assert(node('#main').innerHTML.includes('/samples/image49/crc_burst_multi/data.png'));assert(node('#main').innerHTML.includes('历史实测回放'));
input={ds:'4,-2',mode:'TYPE3C_CONTIGUOUS',byte:'24',bit:'2',count:'5',points:'7/3 12/6',repeats:'3',limit:'8',target:'B_frame_correct',payload:'incremental',strategy:'sequential',candidates:'5/1',extra:'2'};
const request=JSON.parse(vm.runInContext('JSON.stringify(scanRequest())',ctx));assert.deepStrictEqual(request.request.receiver_B,{d:4,s:-2});assert.strictEqual(request.request.fault.count,5);assert.strictEqual(request.request.payload_hex.length,512);
const html=fs.readFileSync(path.join(__dirname,'web/index.html'),'utf8');assert(!html.includes('studio.js'));assert(!html.includes('reference.css'));assert(!html.includes('data-nav="ai"'));assert(html.includes('presentation.css'));assert(html.includes('ds-native.js'));assert(html.includes('src="app.js"'));assert(!html.includes("connect-src 'none'"));
checks.push({native_ds_no_iframe:!vm.runInContext('renderEvaluation()',ctx).includes('<iframe'),ai_integrated:vm.runInContext('scan()',ctx).includes('data-value="ai"'),configuration_round_trip:true,all_14_profiles:vm.runInContext('LEGAL.length',ctx)===14,original_demo_runtime_not_loaded:true});
ctx.savedPlan=JSON.parse(fs.readFileSync(path.join(__dirname,'checks/regression_saved_plan.json'),'utf8'));
node('#scan-form').elements={namedItem(){return {value:''}}};
vm.runInContext("restoreScanPlan({status:'ACCEPTED',plan:savedPlan});S.status.live_configured=true",ctx);
assert.strictEqual(vm.runInContext('S.scan.plan.sha256',ctx),ctx.savedPlan.sha256);
assert.strictEqual(vm.runInContext("S.forms['scan:scan-form'].mode",ctx),'TYPE3C_CONTIGUOUS');
assert.strictEqual(vm.runInContext("S.forms['scan:scan-form'].limit",ctx),'44');
const pending=vm.runInContext("planView(S.scan,'scan')",ctx);assert(pending.includes('需要本轮额度'));assert(/data-action="live-scan"[^>]*disabled/.test(pending));
checks.push({pending_plan_start_disabled:true,saved_44_record_plan_restored_without_execution:true});
console.log(JSON.stringify({status:'PASS_NODE_UI_CONTRACT',browser_started:false,checks},null,2));
