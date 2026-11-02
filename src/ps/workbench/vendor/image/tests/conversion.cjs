const assert=require('assert'),{grayRGBA,fitRectangle}=require('../web/upload.js');
assert.deepEqual([...grayRGBA(new Uint8Array([255,0,0,255,0,255,0,255,0,0,255,255,0,0,0,0,99,99,99,255]))],[76,150,29,255,99]);
assert.deepEqual(fitRectangle(640,320,'contain'),{x:0,y:32,width:128,height:64});
assert.deepEqual(fitRectangle(640,320,'cover'),{x:-64,y:0,width:256,height:128});
assert.deepEqual(fitRectangle(128,128,'contain'),{x:0,y:0,width:128,height:128});
console.log('PASS: gray conversion, transparency, contain and centered crop; no image or hardware synthesized');
