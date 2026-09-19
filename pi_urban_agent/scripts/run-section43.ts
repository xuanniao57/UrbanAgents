import { spawn, spawnSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import { mkdir, readFile, readdir, writeFile } from 'node:fs/promises';
import { resolve, join } from 'node:path';

const root=resolve(process.argv[2]??'evaluation/section43_20260831');
const resume=process.argv.includes('--resume');
await mkdir(root,{recursive:true});
async function sourceHashes() {
  const files:string[]=[];
  async function walk(dir:string){for(const e of await readdir(dir,{withFileTypes:true})){const p=join(dir,e.name); if(e.isDirectory()) await walk(p); else if(e.name.endsWith('.ts')) files.push(p);}}
  await walk('src'); await walk('.pi/extensions');
  files.push('scripts/diagnose-context-stages.ts','scripts/prepare-module-ablation-fixture.ts','scripts/prepare-context-ablation-session.ts','package-lock.json');
  return Object.fromEntries(await Promise.all(files.sort().map(async p=>[p,createHash('sha256').update(await readFile(p)).digest('hex')])));
}
const models=['0.8b','2b','4b','9b'];
const specs:any[]=[];
for(const size of models) {
  const model=`qwen3.5:${size}-urban8k`;
  for(let repeat=1;repeat<=3;repeat++) for(const task of ['plan','reviewer','context']) {
    const pair=task==='context'?['urban_full','pi_default_compaction']:['urban_full',task==='plan'?'urban_no_planner':'urban_no_reviewer'];
    if(repeat%2===0) pair.reverse();
    for(const condition of pair) specs.push({id:`${size}_${task}_${condition}_r${repeat}`,model,size,task,condition,repeat,mode:task==='context'?'all':'fresh',track:'primary'});
  }
  for(const condition of ['urban_full','pi_default_compaction']) specs.push({id:`${size}_natural_${condition}`,model,size,task:'context',condition,repeat:1,mode:'natural',track:'natural_threshold'});
}
const hashes=await sourceHashes();
const planPath=join(root,'experiment_plan.json');
let plan:any;
if(resume){plan=JSON.parse(await readFile(planPath,'utf8')); if(JSON.stringify(plan.sourceHashes)!==JSON.stringify(hashes))throw new Error('Frozen sources changed; use a new experiment root');}
else {
  plan={protocol:'section43-separated-v1',createdAt:new Date().toISOString(),sourceHashes:hashes,specs,settings:{window:8192,maxOutputTokens:2048,thinking:'off',temperature:0,seeds:[42,43,44],stageDeadlineSeconds:300,wholeRunDeadlineSeconds:900,toolCalls:16,consecutiveToolErrors:4,retry:false},notes:['Three reset repeats per primary model-condition; deterministic-temperature replay, not independent cities or diverse tasks.','Context fixture is a historical authoritative-state recovery test, not new case model estimates.','Natural discussion uses no ACK-only instruction and is a separate stress track.','Research quality is judged from assistant text, execution from state, and delivered evidence from actual model requests; no global hard cap.','Prepared history is manually compacted; only the separate natural track establishes threshold-triggered compaction.','Both context conditions share the same external research state, tools, Pi version, and error-propagation fix.'],judge:{model:'qwen3.5:9b-urban16k',mode:'separate-context blinded preliminary assessment',limitations:'Judge receives no condition/model labels; same family and the 9B candidate overlap. Scores require human audit and are not an external-expert gold standard.'}};
  await writeFile(planPath,JSON.stringify(plan,null,2),{flag:'wx'});
  await writeFile(join(root,'model_versions.json'),JSON.stringify(await (await fetch('http://127.0.0.1:11434/api/tags')).json(),null,2));
  const gpu=spawnSync('nvidia-smi',['--query-gpu=name,driver_version,memory.total,power.limit','--format=csv'],{windowsHide:true,encoding:'utf8'});
  await writeFile(join(root,'hardware.txt'),gpu.stdout+gpu.stderr);
}
for(const spec of plan.specs) {
  const out=join(root,'runs',spec.id);
  try {await readFile(join(out,'run_manifest.json')); if(!resume)throw new Error('Run exists without --resume'); console.log(JSON.stringify({skip:spec.id})); continue;} catch(e:any){if(e.code!=='ENOENT')throw e;}
  if(JSON.stringify(await sourceHashes())!==JSON.stringify(plan.sourceHashes))throw new Error('Sources changed during matrix; stopped before next condition');
  spawnSync('ollama',['stop',spec.model],{windowsHide:true,stdio:'ignore',timeout:30000});
  const started=Date.now(); let code:number|null=null; let timedOut=false;
  const child=spawn(process.execPath,['--import','tsx','scripts/diagnose-context-stages.ts','--out',out,'--task',spec.task,'--model',spec.model,'--condition',spec.condition,'--mode',spec.mode,'--history-style','neutral','--thinking','off','--temperature','0','--seed',String(41+spec.repeat),'--timeout','300'],{windowsHide:true,stdio:['ignore','pipe','pipe']});
  let stdout='',stderr=''; child.stdout.on('data',c=>{stdout+=c;});child.stderr.on('data',c=>{stderr+=c;});
  const timer=setTimeout(()=>{timedOut=true;if(process.platform==='win32'&&child.pid)spawnSync('taskkill',['/PID',String(child.pid),'/T','/F'],{windowsHide:true,stdio:'ignore'});else child.kill('SIGKILL');},900000);
  try{code=await new Promise<number|null>((yes,no)=>{child.once('exit',yes);child.once('error',no);});}finally{clearTimeout(timer);spawnSync('ollama',['stop',spec.model],{windowsHide:true,stdio:'ignore',timeout:30000});}
  await mkdir(out,{recursive:true});
  let diagnostic:any=null;try{diagnostic=JSON.parse(await readFile(join(out,'diagnostic_summary.json'),'utf8'));}catch{}
  const manifest={...spec,protocol:spec.task==='context'?'context-separated-v1':'task-semantic-v1',settings:plan.settings,startedAt:new Date(started).toISOString(),runtimeSeconds:(Date.now()-started)/1000,processExitCode:code,timedOut,diagnosticFailure:diagnostic?.stages?.find((s:any)=>s.event==='diagnostic_failure')??null,diagnosticRecorded:!!diagnostic};
  await writeFile(join(out,'run_manifest.json'),JSON.stringify(manifest,null,2));
  await writeFile(join(out,'runner_output.txt'),stdout+stderr);
  console.log(JSON.stringify({finished:spec.id,seconds:manifest.runtimeSeconds,code,diagnosticFailure:manifest.diagnosticFailure}));
}
await writeFile(join(root,'matrix_complete.json'),JSON.stringify({completedAt:new Date().toISOString(),runs:plan.specs.length,sourceHashes:await sourceHashes()},null,2));
