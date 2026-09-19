import test from 'node:test';
import assert from 'node:assert/strict';
import catalog from '../src/tool-catalog-extension.js';
test('directory discover/load/replace is independent of stage',async()=>{
 let tool:any, active:string[]=[];const handlers:Record<string,any>={};
 const pi:any={getAllTools:()=>['urban_initialize','urban_recall','urban_open_branch','urban_human_decision'].map(name=>({name})),setActiveTools:(names:string[])=>{active=names;},on:(name:string,fn:any)=>{handlers[name]=fn;},registerTool:(value:any)=>{tool=value;}};
 catalog(pi);handlers.session_start();
 const prompt=handlers.before_agent_start({systemPrompt:'Base'}).systemPrompt;
 assert.match(prompt,/urban_recall: Retrieve saved research facts/);
 assert.ok(!prompt.includes('urban_delegate:')); // absent capability stays absent
 assert.deepEqual(active,['read','bash','edit','write','urban_tools']);
 const listed=await tool.execute('',{});
 assert.match(listed.content[0].text,/urban_open_branch/);
 await tool.execute('',{load:['urban_open_branch']});assert.ok(active.includes('urban_open_branch'));
 await tool.execute('',{load:['urban_recall']});assert.ok(!active.includes('urban_open_branch'));
 assert.ok(active.includes('urban_recall'));assert.ok(active.includes('bash'));
 assert.deepEqual(JSON.parse((await tool.execute('',{})).content[0].text).loaded,['urban_recall']);
 await assert.rejects(tool.execute('',{load:['nonexistent']}),/Unavailable/);
});
