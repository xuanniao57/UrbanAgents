import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile, readdir, mkdtemp } from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
// @ts-expect-error shared runtime JS
import { countContext, estimateTextTokens, inputUsageRatio, streamWithBudget } from '../src/core/request-guard.mjs';

test('provider calibration includes cached input, excludes output and survives a changed history',async()=>{
 assert.equal(inputUsageRatio({input:100,cacheRead:200,cacheWrite:50,output:9000},700),.5);
 assert.equal(inputUsageRatio({input:0,output:9000},700),undefined);
 const dir=await mkdtemp(join(tmpdir(),'calibration-'));process.env.URBAN_BUDGET_LOG_DIR=dir;
 const model={provider:'fixture',id:'model',contextWindow:8192,maxTokens:2048};
 for(const n of [3000,4000]) {
   const c={messages:[{role:'user',content:'word '.repeat(n/5)}]};
   const estimate=await countContext(c);
   await streamWithBudget(model,c,{},()=>({result:()=>Promise.resolve({stopReason:'stop',usage:{input:estimate*.6,cacheRead:estimate*.1,output:9999}})}));
 }
 // Raw estimate exceeds the budget; actual-provider calibrated input fits.
 // This represents a rebuilt post-compaction context, NOT old absolute usage.
 let sent=false;
 await streamWithBudget(model,{messages:[{role:'user',content:'word '.repeat(4000)}]}, {},()=>{sent=true;});
 assert.equal(sent,true);
 const last=JSON.parse((await readFile(join(dir,'request-budget/events.jsonl'),'utf8')).trim().split('\n').at(-1)!);
 assert.equal(last.countMode,'provider_calibrated_estimate');
 assert.ok(last.before>last.input);assert.ok(last.inputTokens<last.input);
 await assert.rejects(streamWithBudget(model,{messages:[{role:'user',content:'word '.repeat(10000)}]}, {},()=>{}),/Context window exceeded/);
 delete process.env.URBAN_BUDGET_LOG_DIR;
});

test('unknown-vocabulary fallback is mixed-text token estimation, not bytes',()=>{
 assert.equal(estimateTextTokens('a'.repeat(300)),100);
 assert.equal(estimateTextTokens('中'.repeat(100)),150);
 assert.equal(estimateTextTokens('a'.repeat(300)+'中'.repeat(100)),250);
});

test('saved API wire requests do not reproduce the byte-as-token false overflow',async t=>{
 const root='evaluation/four_framework_qwen38_20260917/runs/urban_full_v2/requests';
 let dirs:string[];try{dirs=await readdir(root);}catch{t.skip('local recorded requests unavailable');return;}
 let checked=0;const ratios:number[]=[];
 for(const d of dirs){
  const summary=JSON.parse(await readFile(`${root}/${d}/summary.json`,'utf8'));
  if(!summary.usage?.prompt_tokens)continue;
  const wire=JSON.parse(await readFile(`${root}/${d}/request.json`,'utf8'));
  const estimated=await countContext({systemPrompt:wire.messages.filter((m:any)=>m.role==='system').map((m:any)=>m.content).join('\n'),tools:wire.tools,messages:wire.messages.filter((m:any)=>m.role!=='system').map((m:any)=>({role:m.role,content:[{type:'text',text:typeof m.content==='string'?m.content:JSON.stringify(m.content??'')},...(m.tool_calls??[]).map((c:any)=>({type:'toolCall',name:c.function.name,arguments:JSON.parse(c.function.arguments)})),...(m.reasoning_content?[{type:'thinking',thinking:m.reasoning_content}]:[])]}))});
  assert.ok(estimated < 22609,`recorded ${d}: old false overflow must fit`);
  ratios.push(estimated/summary.usage.prompt_tokens);checked++;
 }
 assert.ok(checked>=8);
 // This fixture is English-rich code/tools plus Chinese requests, not a claim
 // of exact counting for every tokenizer. Keep provider usage as the reference.
 assert.ok(Math.max(...ratios)<1.8,JSON.stringify(ratios));
 t.diagnostic(JSON.stringify({checked,minRatio:Math.min(...ratios),maxRatio:Math.max(...ratios)}));
});
