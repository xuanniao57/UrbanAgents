import {readFile} from 'node:fs/promises';
const env=await readFile('../../.env','utf8');
const key=env.match(/^\s*kimi_code_apikey\s*=\s*(.+?)\s*$/mi)?.[1].trim().replace(/^['"]|['"]$/g,'');
if(!key)throw Error('kimi_code_apikey missing');
async function request(messages,tools){
 const r=await fetch('https://api.kimi.com/coding/v1/chat/completions',{method:'POST',headers:{Authorization:`Bearer ${key}`,'Content-Type':'application/json','User-Agent':'Urban-Agent-Pi/2.2'},body:JSON.stringify({model:'kimi-for-coding',messages,tools,max_tokens:4096,stream:false}),signal:AbortSignal.timeout(90000)});
 const j=await r.json();
 if(!r.ok){console.log(JSON.stringify({http:r.status,errorType:j.error?.type,errorMessage:j.error?.message}));process.exit(1);}
 return j;
}
const messages=[{role:'system',content:'You are testing a coding agent tool connection. Do not access real files. Call environment_probe once, then report whether its returned ok flag is true.'},{role:'user',content:'Check the provided tool connection.'}];
const tools=[{type:'function',function:{name:'environment_probe',description:'Return a synthetic connection-health record, not research data.',parameters:{type:'object',properties:{},additionalProperties:false}}}];
const first=await request(messages,tools),m=first.choices?.[0]?.message;
console.log(JSON.stringify({step:'tool_call',model:first.model,finish:first.choices?.[0]?.finish_reason,tool:m?.tool_calls?.[0]?.function?.name}));
if(!m?.tool_calls?.length)process.exit(2);
messages.push(m);
for(const call of m.tool_calls)messages.push({role:'tool',tool_call_id:call.id,content:JSON.stringify({ok:true})});
const second=await request(messages,tools);
console.log(JSON.stringify({step:'tool_result_roundtrip',model:second.model,finish:second.choices?.[0]?.finish_reason,answer:second.choices?.[0]?.message?.content}));
