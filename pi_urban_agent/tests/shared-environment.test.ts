import test from 'node:test';
import assert from 'node:assert/strict';
import extension,{ENVIRONMENT_ENTRY} from '../src/shared-environment-extension.js';
import urban from '../src/pi-extension.js';
test('shared environment entry is role-neutral and reapplied without full documentation',()=>{
 let handler:any;extension({on:(_event:any,h:any)=>handler=h} as any);
 const result=handler({systemPrompt:'Base'});
 assert.equal(result.systemPrompt,'Base\n'+ENVIRONMENT_ENTRY);
 for(const name of ['WORKSPACE.md','DATA_GUIDE.md','ENVIRONMENT.md','GIS_REFERENCE.md','python work/script.py'])assert.ok(result.systemPrompt.includes(name));
 assert.ok(!/urban_initialize|urban_recall|Reviewer/.test(result.systemPrompt));
});
test('Urban bootstrap preserves the incoming Pi and environment prompt',async()=>{
 const handlers:any[]=[];
 const api={on:(name:string,h:any)=>{if(name==='before_agent_start')handlers.push(h);},registerTool(){},setActiveTools(){}};
 extension(api as any);urban(api as any);
 let prompt='Pi native instructions';
 for(const handler of handlers){const result=await handler({systemPrompt:prompt,prompt:'Inspect data'},{});if(result?.systemPrompt)prompt=result.systemPrompt;}
 assert.ok(prompt.includes('Pi native instructions'));
 assert.ok(prompt.includes(ENVIRONMENT_ENTRY));
 assert.ok(prompt.includes('No Research Tree exists yet'));
});
