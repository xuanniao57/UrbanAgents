/** Frozen local matrix; conditional simulated-human prompts, never a scientific judge. */
import {spawn} from 'node:child_process';
import {mkdir,readFile,writeFile,rename,readdir} from 'node:fs/promises';
import {resolve,join} from 'node:path';
import {createHash} from 'node:crypto';
const root=process.cwd(), batchName=process.env.URBAN_BATCH_NAME||'approved_20260916_v2',batch=resolve('evaluation/'+batchName);
const sizes=(process.env.URBAN_BATCH_MODELS||'4b,9b').split(',');
const repetitions=Number(process.env.URBAN_BATCH_REPETITIONS||3);
if(!/^[a-zA-Z0-9_]+$/.test(batchName)||sizes.some(s=>!['4b','9b'].includes(s))||!Number.isInteger(repetitions)||repetitions<1||repetitions>3)throw Error('Invalid batch configuration');
const conditions=['urban_full_v2','urban_single_v2','urban_no_memory_v2','pi_native_v2'];
const prompts=[
 '我想看看上海内环里建筑、周边设施和道路与活动分布的关系，会不会随着分析尺度变化。这里有工作日和周末的设备停留样本，以及建筑、POI、道路和边界，尚未按网格汇总。请先看数据说明，提出一个能完成的尺度比较方案，并实际做一组不同尺度的OLS分析，保存代码和结果，检查后告诉我发现。尺度和变量你根据数据建议，各尺度的定义要可比；局部关系我们下一步再讨论。不要展示设备编号或逐条位置记录。',
 '现在我希望进一步看不同地方的关系。请以已经完成的整体分析为基础，补充固定距离带宽的GWR比较，选择数据支持且能完成的范围；如果你已经做了自适应GWR，保留它，不要覆盖。若已做了固定距离GWR，核查它和OLS是否使用一致的空间单元与变量定义，必要时补充比较。请实际执行并核验结果。如果前面的OLS尚未完成，先完成它再推进，不能把计划当结果。',
 '结合刚才的调整，哪些关系比较稳定，哪些随尺度改变？请用实际结果解释可能的城市意义，并说清楚哪些旧结果需要重新计算或重新解释。请提供代码与结果文件的位置；没有完成的部分如实说明，不要用计划代替发现。'
];
await mkdir(batch,{recursive:true});
async function hashTree(dir:string):Promise<any[]> {let out:any[]=[];for(const e of await readdir(dir,{withFileTypes:true})){const p=join(dir,e.name);if(e.isDirectory())out.push(...await hashTree(p));else out.push({path:p.slice(root.length+1),sha256:createHash('sha256').update(await readFile(p)).digest('hex')});}return out;}
await writeFile(join(batch,'frozen_manifest.json'),JSON.stringify({created:new Date().toISOString(),conditions,models:sizes,repetitions,prompts,thinking:'on (Ollama boolean)',window:32768,output:8192,sessionRequests:128,perTurnRequests:64,perTurnTools:32,consecutiveToolErrors:4,wallMinutes:30,perTurnSeconds:600,tester:'Conditional scripted simulator; not a human participant or independent scientific judge',source:await hashTree(resolve('src')),scripts:await hashTree(resolve('scripts')),data:await hashTree(resolve('raw_case/data'))},null,2));
async function readJson(p:string){try{return JSON.parse(await readFile(p,'utf8'));}catch{return null;}}
async function run(size:string,condition:string,repeat:number){
 const name=`${batchName}_${condition}_r${repeat}`,out=resolve(`evaluation/raw_local_20260915/${size}/${name}`);
 await mkdir(join(out,'inbox'),{recursive:true});
 if(await readJson(join(out,'manifest.json')))throw Error('Refuse reuse '+out);
 async function publish(n:number,message:string,basis:string){const p=join(out,'inbox',String(n).padStart(3,'0'));await writeFile(join(out,`tester_${n}.json`),JSON.stringify({message,basis}));await writeFile(p+'.pending',JSON.stringify({message}));await rename(p+'.pending',p+'.json');}
 await publish(1,prompts[0],'Common initial request');
 const child=spawn('powershell.exe',['-NoProfile','-ExecutionPolicy','Bypass','-File','scripts/start-raw-local.ps1','-Size',size,'-Run',name,'-Condition',condition,'-Window','32768','-OutputTokens','8192','-Sampling','qwen-coding-compatible','-Thinking','low'],{cwd:root,windowsHide:true,env:{...process.env,URBAN_SESSION_REQUEST_LIMIT:'128'},stdio:['ignore','pipe','pipe']});
 let stdout='',stderr='';child.stdout.on('data',x=>stdout+=x);child.stderr.on('data',x=>stderr+=x);
 const ended=new Promise<void>(r=>child.once('close',()=>r()));
 const start=Date.now();let sent=1,stage=0,clarifications=0;
 await writeFile(join(batch,'current.json'),JSON.stringify({size,condition,repeat,out,pid:child.pid,started:new Date().toISOString()}));
 while(child.exitCode===null&&child.signalCode===null){
  const s=await readJson(join(out,'status.json'));
  if(s?.stopped)break;
  if(Date.now()-start>=30*60*1000){await writeFile(join(out,'STOP'),'Protocol wall-time limit');await new Promise<void>(r=>spawn('taskkill',['/PID',String(child.pid),'/T','/F'],{windowsHide:true,stdio:'ignore'}).once('close',()=>r()));break;}
  if(s?.idle&&s.turn===sent){
   const summary=await readJson(join(out,'turns',String(sent).padStart(3,'0'),'summary.json'));
   if(!summary){await new Promise(r=>setTimeout(r,2000));continue;}
   if(!summary.promptSubmitted) {await writeFile(join(out,'STOP'),'Infrastructure failure: prompt not submitted');throw Error('Prompt submission failed; pause matrix: '+out);}
   if(stage===2){await writeFile(join(out,'STOP'),'Protocol conversation complete');break;}
   if(summary.outcome!=='completed'&&clarifications<2){
    clarifications++;await publish(++sent,'这一步还没有形成完整交付。请先检查你已经保存的代码和产物，收拢到当前能够完成的比较，不要继续扩大范围。先完成并核验刚才要求的分析；若有具体的数据或研究范围问题需要我决定，请直接说明。','Previous transport turn incomplete; no scientific judgement or code supplied');
   }else{stage++;await publish(++sent,prompts[stage],'Advance research question; instruction explicitly requires checking actual progress, transport completion is not scientific success');}
  }
  await new Promise(r=>setTimeout(r,2000));
 }
 await ended;
 await writeFile(join(out,'launcher.stdout.log'),stdout);await writeFile(join(out,'launcher.stderr.log'),stderr);
 await fetch('http://127.0.0.1:11434/api/generate',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({model:`qwen3.5:${size}-urban32k`,keep_alive:0})}).catch(()=>{});
 console.log(JSON.stringify({size,condition,repeat,out,elapsed:Date.now()-start,exit:child.exitCode}));
}
for(let repeat=1;repeat<=repetitions;repeat++)for(const size of sizes)for(let i=0;i<conditions.length;i++)await run(size,conditions[(i+repeat-1)%conditions.length],repeat);
await writeFile(join(batch,'DONE'),new Date().toISOString());
