import { readFile, readdir, mkdir, writeFile } from 'node:fs/promises';
import { resolve } from 'node:path';

// Counterfactual first-response probes only; no generated tool call is executed.
const source = resolve(process.argv[2]); const out = resolve(process.argv[3]);
await mkdir(out, {recursive:true});
await writeFile(resolve(out,'diagnostic.lock'),new Date().toISOString(),{flag:'wx'});
const events = (await readFile(resolve(source,'timeline.jsonl'),'utf8')).trim().split(/\r?\n/).map(JSON.parse as any) as any[];
const recovery = events.find(e => e.event === 'request_start' && e.stage === 'recovery');
const natural = events.filter(e => e.event === 'request_start' && /^natural_/.test(e.stage) && e.messageCount > 2).at(-1);
const recovered = JSON.parse(await readFile(resolve(source,`request_${recovery.id}.json`),'utf8'));
const before = JSON.parse(await readFile(resolve(source,`request_${natural.id}.json`),'utf8'));
for (const payload of [recovered,before]) payload.messages = payload.messages.map((m:any) => ({...m,content:Array.isArray(m.content) ? m.content.map((c:any)=>c.text??'').join('\n') : m.content}));
const latest = recovered.messages.at(-1);
if (!latest.content.includes('Read-only recovery:')) throw new Error('Wrong source recovery message');
const system = recovered.messages.filter((m:any) => m.role==='system');
const history = [...before.messages.filter((m:any) => m.role!=='system'),{role:'assistant',content:'ACK'}];
const compressed = recovered.messages.filter((m:any) => m.role!=='system').slice(0,-1);
function soften(messages:any[], changeAnswers:boolean) {
  return messages.map(m => ({...m,content: typeof m.content !== 'string' ? m.content :
    m.role==='assistant' && changeAnswers && m.content.trim()==='ACK' ? 'These notes remain provisional.' :
    m.content.replace(/Do not call tools or change state\. Reply only ACK\./gi,'For this archival turn, briefly note that these are provisional alternatives.')
      .replace(/^.*(?:reply.*(?:only.*ACK|ACK only)|do not call.*tools).*$/gim,'[Prior-turn archival instruction omitted for this diagnostic.]') }));
}
const variants = [
  {name:'fresh',messages:[...system,latest]},
  {name:'one_ack_turn',messages:[...system,...history.slice(0,2),latest]},
  {name:'five_ack_turns',messages:[...system,...history.slice(0,10),latest]},
  {name:'ten_ack_turns',messages:[...system,...history,latest]},
  {name:'ten_no_ack_order',messages:[...system,...soften(history,false),latest]},
  {name:'ten_neutral_history',messages:[...system,...soften(history,true),latest]},
  {name:'compressed_original',messages:recovered.messages},
  {name:'compressed_no_ack_order',messages:[...system,...soften(compressed,false),latest]},
  {name:'compressed_neutral_history',messages:[...system,...soften(compressed,true),latest]},
  {name:'compressed_explicit_transition',messages:[...system,...compressed,{...latest,content:'The previous archive-only task has ended. Now carry out this new task:\n'+latest.content}]},
];
const rows:any[]=[];
for (const v of variants) for(let repeat=1;repeat<=2;repeat++) {
  const request={...recovered,messages:v.messages,temperature:0,max_tokens:256,stream:false}; delete request.stream_options;
  const start=Date.now();
  try {
    const r=await fetch('http://127.0.0.1:11434/v1/chat/completions',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(request),signal:AbortSignal.timeout(120000)});
    const response=await r.json(); const m=response.choices?.[0]?.message;
    const row={name:v.name,repeat,status:r.status,ms:Date.now()-start,tokens:response.usage,finish:response.choices?.[0]?.finish_reason,text:m?.content,toolCalls:m?.tool_calls,ackOnly:/^ACK[.!]?$/i.test(m?.content?.trim()??'')&&!m?.tool_calls?.length};
    rows.push(row); await writeFile(resolve(out,`${v.name}_r${repeat}.json`),JSON.stringify({request,response},null,2));
    console.log(JSON.stringify(row));
  } catch(e) { const row={name:v.name,repeat,error:String(e)}; rows.push(row); console.log(JSON.stringify(row)); }
}
await writeFile(resolve(out,'probe_summary.json'),JSON.stringify({kind:'synthetic_history_first_response_only',source,rows},null,2));
