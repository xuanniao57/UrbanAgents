import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtemp} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
// @ts-expect-error runtime JS module
import {streamWithBudget,countContext,requestLimits} from '../src/core/request-guard.mjs';

test('multiline text is not charged for JSON escaping; tool arguments remain counted',async()=>{
 const script='print("value")\n'.repeat(100);
 const actual=await countContext({messages:[{role:'user',content:[{type:'text',text:script}]}]});
 assert.ok(actual<Buffer.byteLength(JSON.stringify(script),'utf8'));
 const call=await countContext({messages:[{role:'assistant',content:[{type:'toolCall',name:'write',arguments:{content:script}}]}]});
 assert.ok(call>actual);
});
test('guard never invokes a second history summarizer',async()=>{
 process.env.URBAN_BUDGET_LOG_DIR=await mkdtemp(join(tmpdir(),'pi-only-'));
 let summaries=0;
 await assert.rejects(streamWithBudget({contextWindow:8192,maxTokens:2048},{systemPrompt:'',messages:[{role:'user',content:'x'.repeat(27000)}]}, {},()=>{},()=>{summaries++;}),/exceeds the context window/);
 assert.equal(summaries,0);
});
test('full output reserve is preserved; insufficient space never sends a partial budget',async()=>{
 for(const window of [4096,8192,16384]) {
  const model={contextWindow:window,maxTokens:1024};
  const latest={role:'user',content:'x'.repeat(requestLimits(window,1024).input*3)};
  let sent:any;
  await assert.rejects(streamWithBudget(model,{systemPrompt:'',messages:[latest]}, {},async()=>{sent=true;}),/Context window exceeded/);
  assert.equal(sent,undefined);
  const short={role:'user',content:'Continue the authorized analysis'};
  let accepted:any;
  await streamWithBudget(model,{systemPrompt:'',messages:[short]}, {},async(_m:any,c:any,o:any)=>{accepted={c,o};});
  assert.deepEqual(accepted.c.messages[0],short);assert.equal(accepted.o.maxTokens,1024);
  assert.equal(accepted.o.urbanPreflightChecked,true);
 }
});

test('send-time guard preserves tool evidence instead of replacing it with new pointers',async()=>{
 const evidence={role:'toolResult',toolName:'bash',toolCallId:'1',content:[{type:'text',text:'measurement '.repeat(500)}]};
 let sent:any;
 await streamWithBudget({contextWindow:16384,maxTokens:2048},{systemPrompt:'',messages:[evidence]}, {},async(_m:any,c:any)=>{sent=c;});
 assert.deepEqual(sent.messages[0],evidence);
});
