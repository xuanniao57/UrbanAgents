import { readdir,readFile,writeFile } from 'node:fs/promises';
import { resolve,join } from 'node:path';
const root=resolve(process.argv[2] || 'evaluation/framework_full_20260914');
const files=[];
async function walk(p){for(const f of await readdir(p,{withFileTypes:true})){const q=join(p,f.name);if(f.isDirectory())await walk(q);else if(f.name==='manifest.json')files.push(q);}}
await walk(root);
const rows=[];
for(const file of files){
  const dir=resolve(file,'..'); const m=JSON.parse(await readFile(file,'utf8'));
  if(m.protocol!=='framework-ablation-v1')continue;
  let status={};try{status=JSON.parse(await readFile(join(dir,'status.json'),'utf8'));}catch{}
  let summaries=[];
  for(const f of await readdir(join(dir,'turns'),{withFileTypes:true})){
    if(!f.isDirectory())continue;
    try{summaries.push(JSON.parse(await readFile(join(dir,'turns',f.name,'summary.json'),'utf8')));}catch{}
  }
  const usage=summaries.reduce((a,s)=>{const u=s.requestUsageTotals||{}; for(const k of Object.keys(a))a[k]+=u[k]||0;return a;},{promptTokens:0,completionTokens:0,totalTokens:0,requestsWithUsage:0});
  rows.push({model:m.model,condition:m.condition,seed:m.seed,currentTurn:status.turn,stopped:status.stopped,phase:status.phase,turnsWithSavedSummaries:summaries.length,turnOutcomes:summaries.map(s=>s.outcome),usageOfCompletedTurns:usage,scientificScore:null,judgeStatus:'pending',path:dir});
}
await writeFile(join(root,'PROGRESS.json'),JSON.stringify({updatedAt:new Date().toISOString(),note:'Execution status only, not scientific success. Usage covers completed turns only.',runs:rows},null,2));
console.log(JSON.stringify(rows.map(r=>({model:r.model,condition:r.condition,turn:r.currentTurn,stopped:r.stopped,savedTurns:r.turnsWithSavedSummaries,judge:r.judgeStatus})),null,2));
