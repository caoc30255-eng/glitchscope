'use strict';
// Execute the actual native controller against all 64 real historical items.
// Minimal DOM contract only; no browser or computer-use session is launched.
const fs=require('fs'),path=require('path'),assert=require('assert');
class Element{
 constructor(){this._html='';this.textContent='';this._value='';this.options=[];this.dataset={};}
 set innerHTML(s){this._html=s;this.options=[...s.matchAll(/<option value="([^"]*)"/g)].map(m=>({value:m[1]}));if(this.options.length)this._value=this.options[0].value;}
 get innerHTML(){return this._html;}
 set value(v){this._value=String(v);}get value(){return this._value;}
 querySelectorAll(q){if(q!=='button')return [];return [...this._html.matchAll(/<button([^>]*)>/g)].map(m=>{const e=new Element();for(const a of m[1].matchAll(/data-([\w-]+)="([^"]*)"/g))e.dataset[a[1]]=a[2];return e;});}
 querySelector(q){if(q==='svg')return {innerHTML:this._html.replace(/^<svg[^>]*>/,'').replace(/<\/svg>$/,'')};return null;}
}
const map=new Map(),root={querySelector(q){const id=q.match(/data-ds-id="([^"]+)"/)[1];if(!map.has(id))map.set(id,new Element());return map.get(id);}};
const data=JSON.parse(fs.readFileSync(path.join(__dirname,'samples/ds64/viewer_data.json'),'utf8'));
const {GlitchDS,DSView}=require('./web/ds-native.js');GlitchDS.mount(root,data);
assert(map.get('candidate').textContent.includes('d4'));assert(map.get('grid').innerHTML.includes('data-ds="4,-2"'));assert.strictEqual(map.get('items').querySelectorAll('button').length,64);
let cases=0;
for(const p of data.summary.profiles){map.get('profile').value=DSView.key(p);map.get('profile').onchange();for(let i=0;i<64;i++){map.get('item').value=i;map.get('item').onchange();assert(map.get('ideal').innerHTML.includes('<svg'));assert(map.get('actual').innerHTML.includes('<svg'));assert(map.get('reconstructed').innerHTML.includes('<svg'));assert(map.get('votes').innerHTML.includes('<tr>'));cases++;}}
assert.strictEqual(cases,896);
console.log(JSON.stringify({status:'PASS_NATIVE_DS_CONTROLLER',real_item_profile_cases:cases,items:64,profiles:14,summary_candidate:data.summary.global_minimax_candidate_set,all_three_traces_populated:true,browser_started:false,hardware_access:false},null,2));
