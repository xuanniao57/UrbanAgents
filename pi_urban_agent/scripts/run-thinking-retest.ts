/** Bounded two-turn rerun. Local models are serial; API runs concurrently. */
import {spawn} from 'node:child_process';
import {mkdir,readFile,writeFile,rename,access} from 'node:fs/promises';
import {resolve} from 'node:path';
const root=process.cwd(), run='thinking_on_20260916_r01';
const exists=async(p:string)=>{try{await access(p);return true;}catch{return false;}};
const sleep=()=>new Promise(r=>setTimeout(r,2000));
const first=JSON.parse(await readFile('evaluation/raw_api_20260915/qwen3.5-plus/raw_full_r01/inbox/001.json','utf8'));
const second={message:'方案先收窄为500米和1000米两种方格，其他尺度保留后续比较。先用工作日样本，以单位面积停留次数为因变量，解释变量用建筑覆盖率、平均建筑高度、POI密度和道路密度，在两种尺度保持定义一致。现在授权你实际完成这两组OLS，保存代码、结果并检查后告诉我具体数值。原始坐标重新聚合，不沿用已有grid_id，也不能仅凭编号推断其尺度；停留次数不是去重设备人数。GWR保留在后续比较中，这一步暂不执行。实际网格数和样本数请从结果核验。'};
async function execute(model:string,local:boolean){
 const out=resolve(local?`evaluation/raw_local_20260915/${model}/${run}`:`evaluation/raw_api_20260915/${model}/${run}`);
 if(await exists(resolve(out,'manifest.json')))throw new Error('Refuse reuse '+out);
 await mkdir(resolve(out,'inbox'),{recursive:true});
 await writeFile(resolve(out,'inbox/001.json'),JSON.stringify(first));
 const args=local?['-File','scripts/start-raw-local.ps1','-Size',model,'-Run',run,'-Window','32768','-OutputTokens','8192','-Sampling','qwen-coding-compatible','-Thinking','low']:['-File','scripts/start-raw-api.ps1','-Model',model,'-Run',run,'-Thinking','xhigh'];
 const child=spawn('powershell.exe',['-NoProfile','-ExecutionPolicy','Bypass',...args],{cwd:root,windowsHide:true,stdio:['ignore','pipe','pipe']});
 let stdout='',stderr='';child.stdout.on('data',x=>stdout+=x);child.stderr.on('data',x=>stderr+=x);
 const ended=new Promise<void>(r=>child.once('close',()=>r()));
 const started=Date.now();let queued=false,stop=false;
 try{
  while(child.exitCode===null&&child.signalCode===null){
   let status:any;try{status=JSON.parse(await readFile(resolve(out,'status.json'),'utf8'));}catch{}
   if(status?.stopped)break;
   if(!queued&&status?.idle&&status.turn===1){
    await writeFile(resolve(out,'inbox/002.pending'),JSON.stringify(second));
    await rename(resolve(out,'inbox/002.pending'),resolve(out,'inbox/002.json'));queued=true;
   }
   if(!stop&&status?.turn===2){await writeFile(resolve(out,'STOP'),'Stop after this bounded second turn.');stop=true;}
   if(Date.now()-started>25*60*1000){
    await writeFile(resolve(out,'STOP'),'Supervisor timeout.');
    await new Promise<void>(r=>spawn('taskkill',['/PID',String(child.pid),'/T','/F'],{windowsHide:true,stdio:'ignore'}).once('close',()=>r()));
    throw new Error('Supervisor timeout: '+model);
   }
   await sleep();
  }
  await ended;
 }finally{
  await writeFile(resolve(out,'launcher.stdout.log'),stdout);await writeFile(resolve(out,'launcher.stderr.log'),stderr);
  if(local)await fetch('http://127.0.0.1:11434/api/generate',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({model:`qwen3.5:${model}-urban32k`,keep_alive:0})}).catch(()=>{});
 }
 console.log(JSON.stringify({model,out,finished:true,code:child.exitCode}));
}
await Promise.all([execute('qwen3.8-max',false),(async()=>{await execute('4b',true);await execute('9b',true);})()]);
