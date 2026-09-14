import {readFile,writeFile} from 'node:fs/promises';
import {resolve,join} from 'node:path';
const root=resolve(process.argv[2]);
const rows=JSON.parse(await readFile(join(root,'separated_results.json'),'utf8'));
const mapping=JSON.parse(await readFile(join(root,'blind_mapping_private.json'),'utf8'));
const safe=async(p:string)=>{try{return JSON.parse(await readFile(p,'utf8'));}catch{return null;}};
for(const r of rows){
  const judged=await safe(join(root,'judge_outputs',`${r.bundleId}.validated.json`));
  r.qualityScore=judged?.score??null;r.qualityStatus=judged?.status??'awaiting_judge';r.judgeItems=judged?.response?.items??null;
  r.recoverySemanticScore=r.task==='context'&&r.judgeItems?r.judgeItems.filter((i:any)=>['C1','C2'].includes(i.id)).reduce((s:number,i:any)=>s+i.score,0):null;
  r.patchAnswerScore=r.task==='context'&&r.judgeItems?r.judgeItems.filter((i:any)=>['C3','C4'].includes(i.id)).reduce((s:number,i:any)=>s+i.score,0):null;
  const s=mapping.find((m:any)=>m.runId===r.id&&m.kind==='summary');const sj=s?await safe(join(root,'judge_outputs',`${s.id}.validated.json`)):null;
  r.summaryFidelityScore=sj?.score??null;
}
const groups:any[]=[];
for(const r of rows){let g=groups.find(g=>g.size===r.size&&g.task===r.task&&g.condition===r.condition&&g.track===r.track);if(!g){g={size:r.size,task:r.task,condition:r.condition,track:r.track,runs:[]};groups.push(g);}g.runs.push(r);}
const avg=(a:number[])=>a.length?a.reduce((x,y)=>x+y,0)/a.length:null;
const summary=groups.map(g=>({size:g.size,task:g.task,condition:g.condition,track:g.track,n:g.runs.length,judged:g.runs.filter((r:any)=>r.qualityScore!==null).length,qualityMean:avg(g.runs.filter((r:any)=>r.qualityScore!==null).map((r:any)=>r.qualityScore)),patchApplied:g.task==='context'?g.runs.filter((r:any)=>r.execution?.patchApplied).length:null,patchFullyConsistent:g.task==='context'?g.runs.filter((r:any)=>{const x=r.execution;return x?.patchApplied&&x.identityProvenance&&x.ingressBeforeDecision&&x.oldApprovalInvalidated&&x.pendingQuestionsCleared&&x.artifactsUnchanged&&x.otherRouteRolesUnchanged&&x.otherNodeStatusesUnchanged&&x.unrequestedDecisionWrites===0&&x.finalClaimAbsent;}).length:null,completeMetricDelivery:g.task==='context'?g.runs.filter((r:any)=>r.delivery.filter((d:any)=>d.r2Delivered!==null).every((d:any)=>d.r2Delivered)).length:null,readOnlyRecovery:g.task==='context'?g.runs.filter((r:any)=>r.execution?.recoveryReadOnly).length:null,compactionRuns:g.runs.filter((r:any)=>r.compactions.length).length,naturalThresholdRuns:g.runs.filter((r:any)=>r.compactions.some((c:any)=>c.reason==='threshold')).length,summaryMean:avg(g.runs.filter((r:any)=>r.summaryFidelityScore!==null).map((r:any)=>r.summaryFidelityScore)),meanSeconds:avg(g.runs.map((r:any)=>r.runtimeSeconds)),meanInputTokens:avg(g.runs.map((r:any)=>r.inputTokens)),meanOutputTokens:avg(g.runs.map((r:any)=>r.outputTokens)),toolErrors:g.runs.reduce((n:number,r:any)=>n+r.toolErrors,0),guardStops:g.runs.reduce((n:number,r:any)=>n+r.guardStops,0)}));
await writeFile(join(root,'scored_runs.json'),JSON.stringify(rows,null,2));await writeFile(join(root,'group_summary.json'),JSON.stringify(summary,null,2));
const csv=(items:any[])=>{const keys=Object.keys(items[0]??{});const esc=(x:any)=>'"'+String(x??'').replaceAll('"','""')+'"';return '\uFEFF'+keys.map(esc).join(',')+'\n'+items.map(r=>keys.map(k=>esc(r[k])).join(',')).join('\n')+'\n';};
await writeFile(join(root,'group_summary.csv'),csv(summary));
await writeFile(join(root,'run_results_long.csv'),csv(rows.map((r:any)=>({id:r.id,model:r.model,task:r.task,condition:r.condition,track:r.track,repeat:r.repeat,qualityScore:r.qualityScore,qualityMaximum:8,qualityStatus:r.qualityStatus,summaryScore:r.summaryFidelityScore,summaryMaximum:2,patchApplied:r.execution?.patchApplied,identityProvenance:r.execution?.identityProvenance,pendingQuestionsCleared:r.execution?.pendingQuestionsCleared,readOnlyRecovery:r.execution?.recoveryReadOnly,metricRoutesDelivered:r.delivery?.filter((d:any)=>d.r2Delivered===true).length,metricRoutesExpected:r.delivery?.filter((d:any)=>d.r2Delivered!==null).length,toolCalls:r.toolCalls,toolErrors:r.toolErrors,guardStops:r.guardStops,seconds:r.runtimeSeconds,inputTokens:r.inputTokens,outputTokens:r.outputTokens,compactions:r.compactions.length,timedOut:r.timedOut,diagnosticFailure:r.diagnosticFailure?.message??''}))));
const fmt=(x:any)=>x===null?'待评':Number(x).toFixed(2);
let md='# 4.3 本地重跑结果（语义分为本地9B初评）\n\n运行数 '+rows.length+'；评分来源与原始日志均保留。三次重置是同一受控任务的重复，不是独立研究样本。\n\n';
for(const track of ['primary','natural_threshold']){
  md+=`## ${track}\n\n|模型|模块|条件|n|研究质量 /8|补丁完整执行|指标完整送达|摘要 /2|秒|输入 tokens|输出 tokens|\n|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|\n`;
  for(const g of summary.filter(g=>g.track===track))md+=`|${g.size}|${g.task}|${g.condition}|${g.n}|${fmt(g.qualityMean)}|${g.patchFullyConsistent??'—'}|${g.completeMetricDelivery??'—'}|${fmt(g.summaryMean)}|${fmt(g.meanSeconds)}|${fmt(g.meanInputTokens)}|${fmt(g.meanOutputTokens)}|\n`;
}
md+='\n语义分不是外部专家金标准。状态、身份、审批与待办清理由前后文件核对；证据送达不等于理解正确。资源统计包括模型调用与工具执行，不能在完成量不同的条件之间直接解读为效率排名。\n';
await writeFile(join(root,'RESULT_TABLES_CN.md'),md);
console.log(JSON.stringify(summary));
