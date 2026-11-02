"use strict";
const assert=require('node:assert/strict'),fs=require('node:fs');
const v=require('./viewer.js');
assert.equal(v.expand([[0,0],[5,1]])[4],0);assert.equal(v.expand([[0,0],[5,1]])[5],1);
assert(v.expand(null).every(x=>x===null));
assert.equal(v.esc('</script>'),'&lt;/script&gt;');
const frame=[20,100,1100,0xa5,0,[]],copy=JSON.stringify(frame);
const a=v.reconstruct([frame]);assert.equal(a[99],null);assert.equal(a[100],0);assert.equal(a[200],1);assert.equal(a[300],0);assert.equal(a[1000],1);assert.equal(a[1100],null);assert.equal(JSON.stringify(frame),copy);
const item={profiles:[{d:4,s:-2,scenarios:[[7,true,0,0,[frame]]]}]};
assert.equal(v.options(item,'4,-2')[0][0],7);assert.deepEqual(v.options(item,'3,-1'),[]);
assert(v.svg(a,0,4095,'#123456').includes('<svg'));
if(process.argv[2]){
 const html=fs.readFileSync(process.argv[2],'utf8');
 const payload=JSON.parse(html.match(/<script id="payload" type="application\/json">([\s\S]*?)<\/script>/)[1]);
 assert.equal(payload.items.length,64);
 for(const item of payload.items){
  if(item.raw){assert.equal(v.expand(item.raw).length,4096);assert(v.expand(item.raw).every(x=>x===0||x===1));}
  for(const p of item.profiles||[])for(const s of p.scenarios){
   if(!s[1])continue;
   for(const f of s[4])for(const vote of f[5]){
    assert.equal(vote[7],Number(vote[4]+vote[5]+vote[6]>=2));
    const raw=v.expand(item.raw);assert.deepEqual(vote.slice(4,7),vote.slice(1,4).map(i=>raw[i]));
   }
  }
 }
 console.log('PASS_VIEWER_DATA64_AND_VOTE_LINKAGE_NO_BROWSER_AUTOMATION');
}
console.log('PASS_PURE_VIEWER_HELPERS_NO_BROWSER_AUTOMATION');
