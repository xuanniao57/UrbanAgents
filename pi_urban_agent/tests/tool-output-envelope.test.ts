import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtemp,readFile} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import envelope from '../src/tool-output-extension.js';
test('large result stored exactly before history, short result unchanged',async()=>{
 const root=await mkdtemp(join(tmpdir(),'envelope-'));process.env.URBAN_PI_WORKSPACE_ROOT=root;
 let handler:any;envelope({on:(_event:any,callback:any)=>{handler=callback;}} as any);
 const body={toolName:'read',content:[{type:'text',text:'source data '.repeat(10000)}],details:{},isError:false};
 const result=await handler(body);
 const pointer=JSON.parse(result.content[0].text);
 assert.ok(pointer.full_result.startsWith('.research-history/'));
 assert.ok(pointer.preview.startsWith('source data'));
 assert.deepEqual(JSON.parse(await readFile(join(root,pointer.full_result),'utf8')).content,body.content);
 assert.equal(await handler({...body,content:[{type:'text',text:'done'}]}),undefined);
 delete process.env.URBAN_PI_WORKSPACE_ROOT;
});
