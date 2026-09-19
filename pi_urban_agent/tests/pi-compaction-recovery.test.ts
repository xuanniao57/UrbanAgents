import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile, readdir} from 'node:fs/promises';
// @ts-ignore shared JS compatibility shim
import {prepareOverflowCompaction,fitCompactionBudget} from '../src/core/pi-compaction-recovery.mjs';
// @ts-ignore runtime package exports
import {buildSessionContext} from '../node_modules/@earendil-works/pi-coding-agent/dist/core/session-manager.js';
// @ts-ignore runtime package exports
import {convertToLlm} from '../node_modules/@earendil-works/pi-coding-agent/dist/core/messages.js';
// @ts-ignore exercise the actual installed Pi implementation, not a reimplementation
import {prepareCompaction, estimateTokens, compact} from '../node_modules/@earendil-works/pi-coding-agent/dist/core/compaction/compaction.js';
// @ts-ignore installed Pi prototype exercises the patched production entry point
import {AgentSession} from '../node_modules/@earendil-works/pi-coding-agent/dist/core/agent-session.js';
const settings={enabled:true,reserveTokens:8192,keepRecentTokens:6553};
const response=(text:string)=>({result:async()=>({content:[{type:'text',text}],stopReason:'stop',usage:{input:1,output:1,cacheRead:0,cacheWrite:0,totalTokens:2,cost:{input:0,output:0,cacheRead:0,cacheWrite:0,total:0}}})});

test('history and split-turn summaries share one allowance with retained context',async()=>{
 const entries=[{id:'u',parentId:null,type:'message',message:{role:'user',content:'Execute OLS only',timestamp:0}}];
 const prep={firstKeptEntryId:'u',messagesToSummarize:[],turnPrefixMessages:[entries[0].message],isSplitTurn:true,tokensBefore:14000,previousSummary:'Human authorized OLS only.',fileOps:{read:new Set(['data_contract.json']),written:new Set(),edited:new Set()},settings};
 const fitted=await fitCompactionBudget(prep,entries,settings,{contextWindow:16384,maxTokens:4096},{systemPrompt:'Research environment.',tools:[]},prepareCompaction,estimateTokens,buildSessionContext,convertToLlm);
 const caps:number[]=[];
 const result=await compact(fitted,{contextWindow:16384,maxTokens:4096,reasoning:true} as any,'unused',undefined,undefined,undefined,'xhigh',((_m:any,_c:any,o:any)=>{assert.equal(o.reasoning,undefined,'checkpoint writing does not inherit research thinking');caps.push(o.maxTokens);return response('Human authorized OLS only.');}) as any);
 assert.equal(caps.length,2);
 assert.ok(caps.reduce((a,b)=>a+b,0)<=1638,'combined cap, not one full cap per subsummary');
 assert.ok(result.summary.includes('Human authorized OLS only.'));
 assert.equal(result.firstKeptEntryId,'u');
});

test('recorded 9B tiny-budget failure chooses a legal earlier cut, not a sub-128 request',async t=>{
 const root='evaluation/compaction_repair_20260917/r3/9b/urban_full_v2';
 let names:string[];try{names=await readdir(`${root}/session`);}catch{t.skip('local failed-run fixture unavailable');return;}
 const all=(await readFile(`${root}/session/${names.find(n=>n.endsWith('.jsonl'))}`,'utf8')).trim().split('\n').map(l=>JSON.parse(l));
 const byId=new Map(all.map(e=>[e.id,e]));
 let leaf:any=[...all].reverse().find(e=>e.type==='message'&&e.message?.stopReason==='error');
 const branch:any[]=[];while(leaf){branch.unshift(leaf);leaf=byId.get(leaf.parentId);}
 let wire:any;
 for(const d of (await readdir(`${root}/requests`)).sort().reverse()){
   const candidate=JSON.parse(await readFile(`${root}/requests/${d}/request.json`,'utf8'));
   if(candidate.tools?.length){wire=candidate;break;}
 }
 const original=process.env.URBAN_TOKENIZER_DIR;
 process.env.URBAN_TOKENIZER_DIR='cache/qwen35-tokenizer';
 try{
   const s={enabled:true,reserveTokens:5080,keepRecentTokens:3276};
   const p=prepareOverflowCompaction(branch,s,prepareCompaction,estimateTokens);
   const fitted=await fitCompactionBudget(p,branch,s,{contextWindow:16384,maxTokens:4096},{systemPrompt:wire.messages.filter((m:any)=>m.role==='system').map((m:any)=>m.content).join('\n'),tools:wire.tools.map((x:any)=>x.function)},prepareCompaction,estimateTokens,buildSessionContext,convertToLlm);
   assert.ok(fitted);
   assert.ok(Math.floor(fitted.settings.reserveTokens*.5)>=128);
   assert.ok(fitted.settings.reserveTokens>=1000,'do not squeeze a checkpoint into a tiny unusable allowance');
 }finally{if(original===undefined)delete process.env.URBAN_TOKENIZER_DIR;else process.env.URBAN_TOKENIZER_DIR=original;}
});

test('real 9B failed recovery receives a smaller joint summary budget',async t=>{
 const dir='evaluation/compaction_repair_20260917/r1/9b/urban_full_v2/session';
 let names:string[];try{names=await readdir(dir);}catch{t.skip('local failed-run fixture unavailable');return;}
 const all= (await readFile(`${dir}/${names.find(n=>n.endsWith('.jsonl'))}`,'utf8')).trim().split('\n').map(l=>JSON.parse(l));
 const byId=new Map(all.map(e=>[e.id,e]));
 const leaf=[...all].reverse().find((e:any)=>e.type==='message'&&e.message?.stopReason==='error');
 const branch:any[]=[];let e:any=leaf;while(e){branch.unshift(e);e=byId.get(e.parentId);}
 const localSettings={enabled:true,reserveTokens:5080,keepRecentTokens:3276};
 const preparation=prepareOverflowCompaction(branch,localSettings,prepareCompaction,estimateTokens);
 assert.ok(preparation);
 const fitted=await fitCompactionBudget(preparation,branch,localSettings,{contextWindow:16384,maxTokens:4096},{systemPrompt:'Research tools and environment. '.repeat(200),tools:[]},prepareCompaction,estimateTokens,buildSessionContext,convertToLlm);
 assert.ok(fitted.settings.reserveTokens<localSettings.reserveTokens);
 assert.ok(fitted.firstKeptEntryId);
});
test('recovery preserves an available native preparation unchanged',()=>{
 const original={test:true};let calls=0;
 assert.equal(prepareOverflowCompaction([],settings,()=>{calls++;return original;},estimateTokens),original);
 assert.equal(calls,1);
});
test('empty history has a bounded four local searches and no recovery',()=>{
 let calls=0;
 assert.equal(prepareOverflowCompaction([],settings,()=>{calls++;},estimateTokens),undefined);
 assert.equal(calls,4);
});
test('summary-only preparation retains suffix and uses Pi summarizer with smaller output',async()=>{
 const entries=[{id:'u',type:'message',message:{role:'user',content:'Keep the latest authorization',timestamp:0}},
 {id:'c',type:'compaction',firstKeptEntryId:'u',summary:'Prior research constraints. '.repeat(600),tokensBefore:9000,details:{readFiles:['data/a.csv'],modifiedFiles:['work/fit.py']}}];
 const p=prepareOverflowCompaction(entries,settings,prepareCompaction,estimateTokens);
 assert.equal(p.overflowSummaryOnly,true);assert.equal(p.firstKeptEntryId,'u');assert.ok(p.settings.reserveTokens<8192);
 let prompt='';let cap=0;
 const result=await compact(p,{maxTokens:8192} as any,'unused',undefined,undefined,undefined,'off',((_m:any,c:any,o:any)=>{
   prompt=JSON.stringify(c);cap=o.maxTokens;
   return {result:async()=>({content:[{type:'text',text:'Prior research constraints retained.'}],stopReason:'stop',usage:{input:1,output:1,cacheRead:0,cacheWrite:0,totalTokens:2,cost:{input:0,output:0,cacheRead:0,cacheWrite:0,total:0}}})};
 }) as any);
 assert.ok(prompt.includes(entries[1].summary!));assert.ok(cap<8192);assert.equal(result.firstKeptEntryId,'u');
 assert.deepEqual(result.details,{readFiles:['data/a.csv'],modifiedFiles:['work/fit.py']});
});
test('Pi split-turn summary keeps earlier human authorization when no new history exists',async()=>{
 const prompts:string[]=[];
 const preparation={firstKeptEntryId:'u',messagesToSummarize:[],turnPrefixMessages:[{role:'user',content:'Current question',timestamp:0}],isSplitTurn:true,tokensBefore:5000,previousSummary:'Human authorized executing OLS.',fileOps:{read:new Set(),written:new Set(),edited:new Set()},settings};
 const result=await compact(preparation as any,{maxTokens:8192} as any,'unused',undefined,undefined,undefined,'off',((_m:any,c:any)=>{
   const prompt=JSON.stringify(c);prompts.push(prompt);return response(prompt.includes('Human authorized')?'Human authorized executing OLS.':'Current question context');
 }) as any);
 assert.equal(prompts.length,2);assert.ok(result.summary.includes('Human authorized executing OLS.'));assert.ok(result.summary.includes('Current question context'));
});
test('installed auto-compaction emits explicit failure and does not persist a non-shrinking summary',async()=>{
 const events:any[]=[];let appended=false;
 const old='Previous constraints. '.repeat(600);
 const entries=[{id:'u',type:'message',message:{role:'user',content:'Current task',timestamp:0}},{id:'c',type:'compaction',firstKeptEntryId:'u',summary:old,tokensBefore:9000}];
 const fake:any={model:{maxTokens:8192},settingsManager:{getCompactionSettings:()=>settings,getRetrySettings:()=>undefined},
   _getSummarizationRequestAuth:async()=>({model:{maxTokens:8192},apiKey:'unused'}),
   sessionManager:{getBranch:()=>entries,appendCompaction:()=>{appended=true;}},
   _extensionRunner:{hasHandlers:()=>false},_emit:(e:any)=>events.push(e),
   _summarizationRetryCallbacks:()=>undefined,thinkingLevel:'off',agent:{streamFunction:()=>response(old)}};
 const continued=await (AgentSession.prototype as any)._runAutoCompaction.call(fake,'overflow',true);
 assert.equal(continued,false);assert.equal(appended,false);assert.equal(events[0].type,'compaction_start');
 assert.match(events.at(-1).errorMessage,/did not reduce/);assert.equal(events.at(-1).willRetry,false);
});
test('installed threshold path still returns without overflow recovery on summary-only input',async()=>{
 let called=false;
 const entries=[{id:'u',type:'message',message:{role:'user',content:'Current task',timestamp:0}},{id:'c',type:'compaction',firstKeptEntryId:'u',summary:'old '.repeat(3000),tokensBefore:9000}];
 const fake:any={model:{maxTokens:8192},settingsManager:{getCompactionSettings:()=>settings},_getSummarizationRequestAuth:async()=>({model:{maxTokens:8192}}),sessionManager:{getBranch:()=>entries},_emit:()=>{called=true;}};
 assert.equal(await (AgentSession.prototype as any)._runAutoCompaction.call(fake,'threshold',false),false);assert.equal(called,false);
});
test('saved Qwen session replays overflow cut-point failure without modifying session',async t=>{
 const dir='evaluation/raw_api_20260915/qwen3.8-max/subagent_tester_20260916_r1/session';
 let files:string[];try{files=await readdir(dir);}catch{t.skip('local diagnostic fixture unavailable');return;}
 const raw=await readFile(`${dir}/${files.find(f=>f.endsWith('.jsonl'))}`,'utf8');
 const all:any[]=raw.trim().split('\n').map(line=>JSON.parse(line));let recovered=0;
 const byId=new Map(all.filter((x:any)=>x.id).map((x:any)=>[x.id,x]));
 for(const leaf of all){
   if(leaf.type!=='message'||leaf.message?.role!=='assistant'||leaf.message?.stopReason!=='error')continue;
   const branch:any[]=[];let current:any=leaf;
   while(current){branch.unshift(current);current=byId.get(current.parentId);}
   if(branch.filter(e=>e.type==='compaction').length<6)continue;
   if(prepareCompaction(branch,settings))continue;
   const preparation=prepareOverflowCompaction(branch,settings,prepareCompaction,estimateTokens);
   assert.ok(preparation);assert.ok(preparation.settings.keepRecentTokens<6553||preparation.overflowSummaryOnly);recovered++;
 }
 assert.ok(recovered>0,'reproduce at least one actual seventh-compaction failure');
 assert.equal(await readFile(`${dir}/${files.find(f=>f.endsWith('.jsonl'))}`,'utf8'),raw);
});
