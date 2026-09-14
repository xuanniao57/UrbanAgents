/** Transport-only replay. Summary is a stub: this DOES NOT score summary fidelity. */
import { readdir,readFile,mkdir,writeFile } from 'node:fs/promises';
import { resolve,join } from 'node:path';
// @ts-expect-error Shared JS runtime used by Pi SDK.
import {streamWithBudget,countContext,requestLimits} from '../src/core/request-budget.mjs';
const source=resolve(process.argv[2]??'evaluation/long27_toolsfix_20260831');
const out=resolve(process.argv[3]??'evaluation/local_long_budget_v4_20260901/replay');
process.env.URBAN_BUDGET_LOG_DIR=out;
process.env.URBAN_TOKENIZER_DIR=resolve('cache/qwen35-tokenizer');
await mkdir(out,{recursive:true});
const candidates:string[]=[];
async function walk(dir:string){for(const e of await readdir(dir,{withFileTypes:true})){const p=join(dir,e.name);if(e.isDirectory())await walk(p);else if(e.name==='summary.json')candidates.push(p);}}
await walk(source);
const records:any[]=[];
for(const path of candidates){
  const old=JSON.parse(await readFile(path,'utf8'));
  if(!(old.httpStatus>=400))continue;
  let payload:any;try{payload=JSON.parse(await readFile(join(path,'../request.json'),'utf8'));}catch{continue;}
  const messages=payload.messages.filter((m:any)=>!['system','developer'].includes(m.role)).map((m:any,i:number)=>{
    if(m.role==='tool')return {role:'toolResult',toolCallId:m.tool_call_id,toolName:'archived-tool',content:[{type:'text',text:m.content}],timestamp:i+1};
    if(m.role==='assistant')return {role:'assistant',content:[...(typeof m.content==='string'?[{type:'text',text:m.content}]:m.content??[]),...(m.tool_calls??[]).map((t:any)=>({type:'toolCall',id:t.id,name:t.function.name,arguments:JSON.parse(t.function.arguments)}))],timestamp:i+1};
    return {...m,timestamp:i+1};
  });
  const context={systemPrompt:payload.messages.filter((m:any)=>['system','developer'].includes(m.role)).map((m:any)=>m.content).join('\n'),messages,tools:(payload.tools??[]).map((t:any)=>t.function)};
  let sent=0,input=0,error:string|undefined,summaries=0;
  try{await streamWithBudget({contextWindow:8192,maxTokens:2048},context,{maxTokens:2048},async(_m:any,c:any,o:any)=>{
    sent++;input=await countContext(c);if(input+o.maxTokens+requestLimits(8192,o.maxTokens).margin>8192)throw Error('INVALID SEND');
    return {result:async()=>({stopReason:'stop',content:[{type:'text',text:'Transport-only summary stub.'}]})};
  },async()=>{summaries++;return 'Transport-only summary stub. Full historical evidence remains archived. This is not a semantic evaluation.';});}catch(e){error=String(e);}
  records.push({source:path,oldHttp:old.httpStatus,oldMaxTokens:payload.max_tokens,input,sent,summaries,error});
}
await writeFile(join(out,'replay_results.json'),JSON.stringify({summaryIsStub:true,semanticClaims:false,records},null,2));
console.log(JSON.stringify({replayed:records.length,fitted:records.filter(r=>r.sent&&!r.error).length,refused:records.filter(r=>r.error).length},null,2));
