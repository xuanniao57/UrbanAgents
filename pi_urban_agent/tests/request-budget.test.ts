import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, readFile, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
// @ts-expect-error The runtime module is also loaded directly by the patched Pi SDK.
import { streamWithBudget, countContext, requestLimits } from '../src/core/request-budget.mjs';
import { callPython } from '../src/bridge/python-bridge.js';

test('near-limit summary is retained with a readable workspace-relative archive',async()=>{
  const workspace=await mkdtemp(join(tmpdir(),'urban-recovery-workspace-'));
  process.env.URBAN_PI_WORKSPACE_ROOT=workspace;
  process.env.URBAN_BUDGET_LOG_DIR=await mkdtemp(join(tmpdir(),'urban-recovery-log-'));
  let sent:any;
  try {
    await streamWithBudget({contextWindow:8192,maxTokens:2048},{systemPrompt:'Research',messages:[
      {role:'assistant',content:'old '.repeat(12000),timestamp:1},
      {role:'user',content:'OLS only; GWR not authorized.',timestamp:2}
    ]},{},async(_m:any,c:any)=>{sent=c;return {};},async(_p:any,cap:number)=>'A'.repeat(cap));
    const text=sent.messages[0].content[0].text;
    assert.match(text,/summary_status=possibly_incomplete/);
    assert.match(text,/AAAA/);
    const path=text.match(/full_history=([^;]+)/)[1];
    assert.ok(path.startsWith('.research-history/'));
    assert.ok(JSON.parse(await readFile(join(workspace,path),'utf8')).length>0);
    assert.ok(await countContext(sent)<=requestLimits(8192,2048).input);
  } finally { delete process.env.URBAN_PI_WORKSPACE_ROOT; }
});

test('budget is checked for the whole request and never returns one output token', async () => {
  const out = await mkdtemp(join(tmpdir(),'urban-budget-')); process.env.URBAN_BUDGET_LOG_DIR=out;
  const model={contextWindow:8192,maxTokens:1024}; let sent:any;
  const context:any={systemPrompt:'Research',tools:[],messages:[{role:'user',content:'先执行OLS，GWR暂不执行。',timestamp:1},
    {role:'assistant',content:[{type:'toolCall',id:'1',name:'urban_python',arguments:{}}],timestamp:2},
    {role:'toolResult',toolCallId:'1',toolName:'urban_python',content:[{type:'text',text:JSON.stringify({manifest_path:'/evidence/manifest.json',stdout_preview:'long row '.repeat(10000)})}],timestamp:3}]};
  await streamWithBudget(model,context,{},async (_m:any,c:any,o:any)=>{sent={c,o};return {};},async()=>{throw Error('not needed');});
  assert.ok(await countContext(sent.c)<=requestLimits(8192,1024).input);
  assert.equal(sent.o.maxTokens,1024);
  assert.equal(sent.c.messages[0].content,context.messages[0].content);
  assert.equal(sent.c.messages[1].content[0].id,sent.c.messages[2].toolCallId);
  assert.match(sent.c.messages[2].content[0].text,/manifest.json/);
  const pointer=JSON.parse(sent.c.messages[2].content[0].text).archived_tool_result;
  assert.equal(JSON.parse(await readFile(pointer,'utf8')).content[0].text,context.messages[2].content[0].text);
});

test('oversized old history uses summary callback, preserving latest human correction exactly',async()=>{
  const latest={role:'user',content:'Actually execute OLS now; GWR remains unapproved.',timestamp:3};
  const context={systemPrompt:'Research',messages:[{role:'user',content:'Old research request',timestamp:1},{role:'assistant',content:[{type:'text',text:'old history '.repeat(6000)}],timestamp:2},latest]};
  let summaries=0, sent:any;
  await streamWithBudget({contextWindow:8192,maxTokens:1024},context,{},async(_m:any,c:any)=>{sent=c;return {};},async()=>{summaries++;return 'Earlier plan recorded; no GWR authorization.';});
  assert.equal(summaries,1); assert.deepEqual(sent.messages.at(-1),latest);
});

test('several individually valid tool results share one aggregate request budget',async()=>{
  process.env.URBAN_BUDGET_LOG_DIR=await mkdtemp(join(tmpdir(),'urban-batch-budget-'));
  const model={contextWindow:8192,maxTokens:2048};
  const human={role:'user',content:'Compare only the returned artifacts; GWR is not authorized.',timestamp:1};
  const tool=(id:string,body:string)=>({role:'toolResult',toolCallId:id,toolName:'urban_read',content:[{type:'text',text:JSON.stringify({path:`/evidence/${id}.csv`,body})}],timestamp:3});
  let body='grid coefficient '.repeat(1000);
  while(await countContext({systemPrompt:'Research',messages:[human,tool('a',body)]})>requestLimits(8192,2048).input/2)body=body.slice(0,Math.floor(body.length/2));
  const ids=['a','b','c','d','e','f'];
  const context:any={systemPrompt:'Research',messages:[human,{role:'assistant',content:ids.map(id=>({type:'toolCall',id,name:'urban_read',arguments:{path:`/evidence/${id}.csv`}})),timestamp:2},...ids.map(id=>tool(id,body))]};
  assert.ok(await countContext(context)>requestLimits(8192,2048).input);
  let sent:any;
  await streamWithBudget(model,context,{},async(_m:any,c:any)=>{sent=c;return {};},async()=>{throw Error('Tool archival alone should suffice');});
  assert.ok(await countContext(sent)<=requestLimits(8192,2048).input);
  assert.deepEqual(sent.messages.slice(2).map((m:any)=>m.toolCallId),ids);
  assert.equal(sent.messages.length,context.messages.length);
  assert.ok(sent.messages.slice(2).some((m:any)=>JSON.parse(m.content[0].text).archived_tool_result));
});

test('oversized Pi summary is chunked and every subrequest fits',async()=>{
  let calls=0;
  const send=async(_m:any,c:any,o:any)=>{calls++;assert.ok(await countContext(c)+o.maxTokens+492<=8192);return {result:async()=>({stopReason:'stop',content:[{type:'text',text:'Preserved decision and file path.'}]})};};
  await streamWithBudget({contextWindow:8192,maxTokens:1024},{systemPrompt:'You are a context summarization assistant.',messages:[{role:'user',content:`<conversation>\n${'source data '.repeat(4000)}\n</conversation>\nSummarize.`}]},{},send,async()=>{throw Error('not main');});
  assert.ok(calls>2);
});

test('unshrinkable request fails locally without sending or cutting latest user',async()=>{
  let calls=0;
  await assert.rejects(streamWithBudget({contextWindow:8192,maxTokens:1024},{systemPrompt:'x'.repeat(90000),messages:[{role:'user',content:'latest'}]},{},async()=>{calls++;},async()=>''),/Budget configuration/);
  assert.equal(calls,0);
});

test('large summary requests use a model-window-relative output cap and reject unusable fan-out',async()=>{
  process.env.URBAN_BUDGET_LOG_DIR=await mkdtemp(join(tmpdir(),'urban-summary-total-'));
  let calls=0;
  const send=async(_m:any,c:any,o:any)=>{
    calls++;
    assert.ok(o.maxTokens<=Math.floor(8192*.05));
    assert.ok(await countContext(c)<=requestLimits(8192,o.maxTokens).input);
    return {result:async()=>({stopReason:'stop',content:[{type:'text',text:'x '.repeat(Math.max(1,o.maxTokens-16))}]})};
  };
  await assert.rejects(streamWithBudget({contextWindow:8192,maxTokens:1024},
    {systemPrompt:'You are a context summarization assistant.',messages:[{role:'user',content:`<conversation>\n${'source data '.repeat(30000)}\n</conversation>\nSummarize.`}]},
    {},send,async()=>{throw Error('not main');}),/too many source chunks/);
  assert.equal(calls,0);
});

test('long Python stdout keeps manifest, complete logs and paged artifact discovery',async()=>{
  const root=await mkdtemp(join(tmpdir(),'urban-manifest-'));
  const script=join(root,'compute.py');
  await writeFile(script,'from pathlib import Path\nimport sys\nout=Path(sys.argv[2]);out.mkdir()\n(out/"metric.csv").write_text("scale,r2\\n800,0.6\\n")\nprint("large preview "*3000)\nprint(str(out/"metric.csv"))\n');
  const options={repositoryRoot:root,runDir:root};
  const result=await callPython('run_script',{script,args:['--out',join(root,'results')]},options);
  assert.equal(result.success,true);
  const manifest=JSON.parse(await readFile(String(result.result?.manifest_path),'utf8'));
  assert.ok(manifest.files[0].endsWith('metric.csv'));
  assert.ok((await readFile(manifest.stdout_path,'utf8')).length>10000);
  const page=await callPython('inspect_text',{path:manifest.stdout_path,limit:100},options);
  assert.equal(page.result?.next_offset,100);
  const second=await callPython('inspect_text',{path:manifest.stdout_path,limit:100,offset:100},options);
  assert.equal(second.result?.next_offset,200);
  const list=await callPython('list_directory',{path:join(root,'results')},options);
  assert.equal(list.success,true);
});
