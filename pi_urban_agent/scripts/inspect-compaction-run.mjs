import {readFile,readdir} from 'node:fs/promises';
import {resolve} from 'node:path';
const root=resolve(process.argv[2]);
const json=async p=>JSON.parse(await readFile(resolve(root,p),'utf8'));
const lines=async p=>{try{return (await readFile(resolve(root,p),'utf8')).trim().split('\n').filter(Boolean).flatMap(l=>{try{return [JSON.parse(l)];}catch{return [];}});}catch{return [];}};
const events=await lines('pi_events.jsonl');
const guard=await lines('request-budget/events.jsonl');
const requests=[];
for(const d of await readdir(resolve(root,'requests'))){try{requests.push(await json(`requests/${d}/summary.json`));}catch{}}
const compactions=events.filter(e=>e.type==='compaction_start'||e.type==='compaction_end').map(e=>({type:e.type,reason:e.reason,willRetry:e.willRetry,aborted:e.aborted,error:e.errorMessage,summaryChars:e.result?.summary?.length}));
const toolErrors=events.filter(e=>e.type==='tool_execution_end'&&e.isError).map(e=>({tool:e.toolName,text:e.result?.content?.filter(b=>b.type==='text').map(b=>b.text).join('\n').slice(-400)}));
console.log(JSON.stringify({root,status:await json('status.json'),requests:requests.length,lastRequest:requests.at(-1),guardChecks:guard.length,rejections:guard.filter(e=>!e.accepted).map(e=>({time:e.time,input:e.inputTokens,limit:e.input})),compactions,toolErrors},null,2));
