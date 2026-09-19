/** Fresh real-computation smoke matrix. No fixture tree, injected answers or manual compaction. */
import { spawn, spawnSync } from 'node:child_process';
import { mkdir, readFile, writeFile, rename, readdir } from 'node:fs/promises';
import { resolve, join } from 'node:path';
import { createHash } from 'node:crypto';

const root=resolve(process.argv[2] ?? 'evaluation/local_long_budget_20260901');
const sizes=(process.argv[3] ?? '0.8b,2b,4b,9b').split(',');
const conditions=(process.argv[4] ?? 'urban_full,pi_default_compaction').split(',');
const seed=Number(process.argv[5] ?? '42');
const provider=process.argv[6] ?? 'local-ollama';
const baseUrl=process.argv[7] ?? 'http://127.0.0.1:11434/v1';
const localProvider=provider==='local-ollama';
if(!Number.isSafeInteger(seed) || seed<=0)throw Error('seed must be a positive integer');
if(conditions.some(condition=>!['urban_full','pi_default_compaction'].includes(condition)))throw Error(`Unknown condition: ${conditions.join(',')}`);
const runtime=resolve('.'), data=resolve('long_case/data');
const python=resolve('../.venv-section4/Scripts/python.exe');
await mkdir(root,{recursive:true});
const sourceFiles=['src/core/request-budget.mjs','src/pi-extension.ts','src/core/system-prompt.ts','src/core/model-context.ts','src/core/research-store.ts','src/core/types.ts','src/core/tool-policy.ts','src/core/context-bookmark.ts','src/core/human-patch.ts','scripts/long-workflow-session.ts','scripts/run-local-long-budget.ts','scripts/apply-pi-budget-compat-patch.ts','package-lock.json','long_case/data_contract.json'];
const hashes=Object.fromEntries(await Promise.all(sourceFiles.map(async p=>[p,createHash('sha256').update(await readFile(p)).digest('hex')])));
await writeFile(join(root,'plan.json'),JSON.stringify({createdAt:new Date().toISOString(),sizes,conditions,provider,baseUrlHost:new URL(baseUrl).host,window:8192,output:2048,temperature:0,seed,thinking:'off',turnDeadlineSeconds:300,manualCompaction:false,repeats:1,sourceHashes:hashes,
  purpose:'Engineering end-to-end regression; not a replacement for repeated paper ablations',
  protocol:'Same six natural-language requests in both conditions; no gold responses, pre-existing tree or model-generated human messages'},null,2),{flag:'wx'});
await writeFile(join(root,'hardware.txt'),spawnSync('nvidia-smi',[],{encoding:'utf8',windowsHide:true}).stdout);
const pause=(ms:number)=>new Promise(r=>setTimeout(r,ms));
async function readJson(p:string){try{return JSON.parse(await readFile(p,'utf8'));}catch{return null;}}
function routeFamilyReady(state:any){
  if(state?.phase!=='execute' || state?.activeFrontier?.status!=='ready')return false;
  const routes=Object.values(state.nodes ?? {}).filter((node:any)=>node?.nodeType==='model_route') as any[];
  const texts=routes.map(route=>`${route.title ?? ''} ${route.summary ?? ''} ${route.parameters?.analytical_role ?? ''}`.toLowerCase());
  const ols=routes.find((route,index)=>texts[index].includes('ols'));
  const adaptive=routes.find((route,index)=>texts[index].includes('adaptive') || texts[index].includes('自适应'));
  const fixed=routes.find((route,index)=>(texts[index].includes('fixed') || texts[index].includes('固定')) && !texts[index].includes('adaptive') && !texts[index].includes('自适应'));
  // This is only a stage-integrity gate. Scientific and wording quality are
  // scored from the saved trace; negated phrases such as "no p-values" must
  // not be mistaken for a request to calculate them.
  return routes.length>=3 && ols?.status==='active' && fixed?.status==='deferred' && adaptive?.status==='deferred';
}
for(const [index,size] of sizes.entries()) for(const condition of (index%2 ? [...conditions].reverse() : conditions)) {
  const out=join(root,`${size}_${condition}`), research=join(out,'research');
  await mkdir(out,{recursive:true});
  const model=size.includes('qwen') ? size : `qwen3.5:${size}-urban8k`;
  // One model/condition at a time avoids VRAM contention on the 12GB laptop.
  if(localProvider){
    const loaded=await (await fetch('http://127.0.0.1:11434/api/ps')).json() as any;
    for(const m of loaded.models ?? []) await fetch('http://127.0.0.1:11434/api/generate',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({model:m.name,keep_alive:0})});
  }
  // API-hosted Qwen models still need a local tokenizer for the shared 8k
  // request preflight. Without it, the conservative character fallback can
  // reject a valid request before it ever reaches the provider.
  const env={...process.env,URBAN_PI_PYTHON:python,URBAN_TOKENIZER_DIR:resolve('cache/qwen35-tokenizer'),URBAN_BUDGET_LOG_DIR:out};
  const child=spawn(process.execPath,['--import','tsx','scripts/long-workflow-session.ts','--out',out,'--condition',condition,'--data-root',data,'--model',model,'--provider',provider,'--base-url',baseUrl,'--window','8192','--output-tokens','2048','--deadline','300','--seed',String(seed)],{cwd:runtime,env,windowsHide:true,stdio:['ignore','pipe','pipe']});
  let logs=''; child.stdout.on('data',c=>{logs+=c;}); child.stderr.on('data',c=>{logs+=c;});
  const prompts=[
    '我想研究上海街道活力与建成环境的关系怎样随空间尺度改变。工作区提供的是统一口径的两日设备活动聚合表、八个解释变量和米制坐标，不是原始设备轨迹。请比较200到800米、每100米一个尺度，并考虑OLS、固定距离GWR和自适应带宽GWR。这一步只需阅读WORKSPACE.md、data_contract.json和DATA_INVENTORY.md。固定数据合同已经是Research Tree根节点。请把200–800米视为每条分析路线继承的尺度序列，不要为每个尺度建立完整分支；候选路线按分析角色组织，先激活OLS跨尺度基线，另外两类GWR保留为待讨论比较，带宽值暂不臆定。OLS路线只要求样本量、样本内R²和八个系数，不要求p值、显著性或诊断图。请直接调用Research Tree工具提交这个有限路线族，不需要再次向我确认；提交后再给我简明方案，先不要拟合模型。',
    '方案可以继续。现在请根据data_contract.json中的因变量和八个自变量、以及DATA_INVENTORY.md中的真实CSV表头，自己编写一个简短、可复用的Python脚本，由脚本循环读取data/model_ready_{scale}m.csv并实际执行200–800米的OLS基线。使用sklearn LinearRegression；y保持为df[outcome]的一维Series，X严格为df[covariates]。每个尺度先创建row={"scale_m": scale, "n_samples": len(df), "r2": model.score(X,y)}，再用row.update({f"coef_{name}": float(coef) for name,coef in zip(covariates,model.coef_)})，最后results.append(row)；不要用两个dict直接相加。不能用“排除几列后其余全选”的方式；log_stay_count只能作为y。不要计算p值，不要为各尺度吞掉异常。结果表放在outputs/，代码放在work/，至少保存scale_m、n_samples、r2以及八个变量各自的coef列。运行后读回真实结果，告诉我各尺度的样本量和样本内R²，并用urban_commit_run一次性提交脚本和非空结果表，然后停止Worker。固定和自适应GWR都先不要执行，带宽还需要讨论。不要把OLS拟合最高的尺度直接称作最佳尺度。',
    '现在请作为Reviewer审查刚刚提交的OLS脚本和结果表，不重新拟合、不修改文件、不再次提交产物。脚本只读一次；结果宽表用一条只读Python检查列名、行数和尺度集合，不要反复打印全文。核验五项：X是否严格等于合同中的八个解释变量且不含因变量；是否覆盖200–800米七个尺度；结果是否有八个彼此独立的系数列；是否没有执行GWR；是否没有把最高样本内R²解释成最佳尺度。五项都通过时，用urban_record_review记录一次proceed：不要填写路线ID，checks各项使用true或false；否则记录repair并明确唯一需要修复的事项。只有工具返回review ID才算记录成功。完成审核后停止，不代替人类选择路线。',
    '我想澄清一下：800米OLS即使拟合比较高，也只保留为粗尺度对照，不作为唯一主方案。请把这个决定记下来；如果已有相反的主方案批准，要更新它。其他尺度的结果保持不变，GWR仍然没有获准执行。',
    '请回查刚才实际计算的文件。用一条简短的只读Python/pandas查询，只选择scale_m为200、500、800的行，以及scale_m、n_samples、r2、coef_cmab_building_density_per_ha四列；不要靠目测宽CSV对齐列。给我这三个尺度的样本量、样本内R²和建筑密度系数。建筑密度没有取对数，所以系数单位应准确表述为：在其他变量不变时，每增加1栋/ha，log1p(stay_count)改变β；不得解释成百分比弹性。只用最关键的一点说明为什么不能证明800米最佳：这些是在不同聚合支持、不同样本量上得到的样本内R²，不是尺度最优性的独立证据；不要臆测平台、拐点或收敛。现在只读已有结果，不新增分析，也不更改刚才的人类决定。',
    '请从研究记录和产物文件恢复当前进度。先用urban_state核对活动状态，再用一次批量urban_recall核对三条候选路线及已提交产物：哪些模型已真正运行，哪些还没有授权，800米OLS现在是什么角色，Reviewer作了什么判断，下一步需要我决定什么？800米OLS作为粗尺度对照已经确认，不要再次要求确认；下一步只需指出是否开启固定距离GWR、自适应邻居GWR或两者比较，以及相应带宽候选依据尚待人类决定。不要只复述此前的方案，不要把尚未运行的GWR写成已有发现。列出你核对的相对文件位置。'
  ];
  let failure:string|undefined;
  try {
    let turnNumber=0;
    const runPrompt=async(prompt:string)=>{
      const n=turnNumber++;
      const start=Date.now(); let status:any;
      while(true){status=await readJson(join(out,'status.json'));if(status?.stopped||child.exitCode!==null)throw Error(`session stopped: ${status?.error ?? child.exitCode}`);if(status?.idle && status.nextTurn===String(n+1).padStart(3,'0'))break;if(Date.now()-start>350000)throw Error('idle wait timeout');await pause(1000);}
      const path=join(out,'inbox',`${String(n+1).padStart(3,'0')}.json`);
      await writeFile(path+'.tmp',JSON.stringify({message:prompt}));await rename(path+'.tmp',path);
      console.log(JSON.stringify({event:'turn_queued',model,condition,turn:n+1,time:new Date().toISOString()}));
      const begin=Date.now();
      while(!(await readJson(join(out,'turns',String(n+1).padStart(3,'0'),'summary.json')))){
        if(child.exitCode!==null || Date.now()-begin>350000)throw Error('turn completion timeout');await pause(1500);
      }
      const summary=await readJson(join(out,'turns',String(n+1).padStart(3,'0'),'summary.json'));
      console.log(JSON.stringify({event:'turn_finished',model,condition,turn:n+1,outcome:summary.outcome,toolCalls:summary.toolCalls.length,durationMs:summary.durationMs}));
    };
    for(let n=0;n<prompts.length;n++){
      await runPrompt(prompts[n]);
      if(n===0){
        for(let retry=0;retry<2;retry++){
          const state=await readJson(join(research,'research_state.json'));
          if(routeFamilyReady(state))break;
          if(state?.phase!=='plan')throw Error('PLAN produced an incomplete route family; fixed and adaptive GWR must remain distinct candidates');
          await runPrompt('上一轮PLAN会话中断，尚未提交路线族。继续使用已经读到的数据合同，不要执行模型。请用一次urban_commit_route_family提交三条按分析角色组织的候选路线：OLS跨尺度基线为active；固定距离GWR为deferred；自适应邻居GWR为deferred。三条路线都继承200–800米、每100米一个尺度的序列。OLS只要求样本量、样本内R²和八个系数，不要求p值、显著性或诊断图。固定与自适应GWR必须是两条独立候选，带宽值暂不臆定。提交后停止。');
        }
        const state=await readJson(join(research,'research_state.json'));
        if(!routeFamilyReady(state))throw Error('PLAN did not produce OLS, fixed-GWR and adaptive-GWR candidates after two bounded recovery turns');
      }
      // Execution errors often need a fresh context budget. Do not inject the
      // next scientific decision while the active Worker still owes artifacts.
      if(n===1){
        for(let retry=0;retry<2;retry++){
          const state=await readJson(join(research,'research_state.json'));
          if(state?.phase==='review' && state?.activeFrontier?.status==='committed')break;
          await runPrompt('上一轮执行尚未提交完整产物。请保持当前活动路线不变，不要重做方案。读取work/中的现有脚本并用python重现实际报错，然后只做定点修复。y必须为一维df[OUTCOME]；每个尺度先创建row={"scale_m": scale, "n_samples": len(df), "r2": model.score(X,y)}，再用row.update({f"coef_{name}": float(coef) for name,coef in zip(covariates,model.coef_)})并results.append(row)，不要把两个dict相加。X只含data_contract.json中的八个covariates；不要p值、不要逐尺度吞错、不要改用未列出的包。确认结果CSV非空且包含七个尺度及八个独立coef列后，调用urban_commit_run一次性提交脚本和结果表，然后停止。不要开启新路线，也不要提前讨论下一阶段。');
        }
        const state=await readJson(join(research,'research_state.json'));
        if(state?.phase!=='review' || state?.activeFrontier?.status!=='committed'){
          throw Error('execution stage did not commit artifacts after two bounded recovery turns');
        }
      }
      if(n===2){
        let state=await readJson(join(research,'research_state.json'));
        if(!(state?.reviews?.length && state.reviews.at(-1)?.decision==='proceed')){
          await runPrompt('Reviewer记录尚未完成。不要修改、重跑或再次提交分析。脚本只读一次；宽结果表只用一条只读Python检查列名、行数和尺度集合，不要重复打印全文。检查上一条消息列出的五项合同要求后调用urban_record_review一次。不要填写路线ID；checks各项只使用true或false。全部通过才记录proceed，否则记录repair并指出唯一修复项。只有工具返回review ID才算完成。');
          state=await readJson(join(research,'research_state.json'));
        }
        if(!(state?.reviews?.length && state.reviews.at(-1)?.decision==='proceed'))throw Error('Reviewer did not record a proceed gate for the committed OLS artifacts');
      }
      if(n===3){
        const state=await readJson(join(research,'research_state.json'));
        const latest=state?.humanDecisions?.at(-1);
        const target=latest?.branchIds?.[0] ? state.nodes?.[latest.branchIds[0]] : undefined;
        if(latest?.decision!=='retain_sensitivity' || latest?.actorProvenance!=='runtime_authenticated' || target?.status!=='retained_sensitivity'){
          throw Error('Authenticated human correction was not persisted as an OLS retained-sensitivity role');
        }
      }
      if(n>=4){
        const latestTurn=turnNumber;
        const summary=await readJson(join(out,'turns',String(latestTurn).padStart(3,'0'),'summary.json'));
        if(summary?.outcome!=='completed')throw Error(`state recovery turn ${latestTurn} did not complete`);
      }
    }
  }catch(e){failure=String(e);console.log(JSON.stringify({event:'run_failure',model,condition,failure}));}
  finally{
    await writeFile(join(out,'STOP'),'matrix finished');
    for(let i=0;i<15&&child.exitCode===null;i++)await pause(1000);
    if(child.exitCode===null&&child.pid)spawnSync('taskkill',['/PID',String(child.pid),'/T','/F'],{windowsHide:true,stdio:'ignore'});
    await writeFile(join(out,'runner.log'),logs);
    await writeFile(join(out,'runner_result.json'),JSON.stringify({model,condition,seed,failure,endedAt:new Date().toISOString()},null,2));
  }
}
await writeFile(join(root,'complete.json'),JSON.stringify({completedAt:new Date().toISOString()}));
