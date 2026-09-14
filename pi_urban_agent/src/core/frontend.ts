import type { WorkflowState } from "./types.js";

export function buildStandaloneViewer(state: WorkflowState): string {
  const embedded = JSON.stringify(state).replaceAll("<", "\\u003c");
  return `<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Urban Agent · ${escapeHtml(state.runId)}</title>
<style>
:root{--ink:#121826;--teal:#0f766e;--orange:#e76518;--paper:#fff;--line:#d8dee8}*{box-sizing:border-box}
body{margin:0;background:#f7f8fa;color:var(--ink);font:15px/1.45 Arial,"Microsoft YaHei",sans-serif}header{padding:22px 28px;background:var(--paper);border-bottom:1px solid var(--line)}
h1{margin:0 0 5px;font-size:25px}.meta{color:#516071}.layout{display:grid;grid-template-columns:minmax(0,1fr) 380px;gap:16px;padding:18px}.panel{background:#fff;border:1px solid var(--line);border-radius:12px;padding:16px;overflow:auto}
.tree{display:flex;gap:18px;align-items:flex-start;min-width:max-content}.node{width:245px;border:2px solid var(--ink);border-radius:10px;padding:12px;background:#fff}.node[data-status="selected"],.node[data-status="complete"]{border-color:var(--teal)}.node[data-status="blocked"],.node[data-status="repair_required"]{border-color:var(--orange)}
.node h3{margin:0 0 7px;font-size:15px}.tag{font-size:11px;letter-spacing:.05em;text-transform:uppercase;color:#657286}.status{font-weight:700}.arrow{font-size:27px;margin-top:43px}.section{margin-bottom:18px}.section h2{font-size:15px;margin:0 0 8px}.item{padding:9px 0;border-top:1px solid var(--line)}code{font-size:12px;word-break:break-all}.metric{display:inline-block;margin:3px 4px 0 0;padding:2px 6px;background:#eef7f6;border-radius:5px}@media(max-width:900px){.layout{grid-template-columns:1fr}}
</style></head><body><header><h1>Urban Agent research record</h1><div class="meta" id="meta"></div></header><main class="layout"><section class="panel"><div class="tree" id="tree"></div></section><aside class="panel" id="detail"></aside></main>
<script>const state=${embedded};
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
document.getElementById('meta').textContent=state.runId+' · '+state.phase+' · contract '+state.contractHash.slice(0,12);
const nodes=Object.values(state.nodes);const depth={};function d(n){if(depth[n.nodeId]!=null)return depth[n.nodeId];return depth[n.nodeId]=n.parentIds.length?1+Math.max(...n.parentIds.map(p=>d(state.nodes[p]))):0}nodes.forEach(d);
const groups=Object.groupBy?Object.groupBy(nodes,n=>d(n)):nodes.reduce((a,n)=>((a[d(n)]??=[]).push(n),a),{});const tree=document.getElementById('tree');Object.keys(groups).sort((a,b)=>+a-+b).forEach((key,i)=>{if(i){const a=document.createElement('div');a.className='arrow';a.textContent='→';tree.append(a)}const col=document.createElement('div');groups[key].forEach(n=>{const el=document.createElement('article');el.className='node';el.dataset.status=n.status;el.innerHTML='<div class="tag">'+esc(n.nodeType)+'</div><h3>'+esc(n.title)+'</h3><div class="status">'+esc(n.status)+'</div><div>'+esc(n.summary)+'</div>';el.onclick=()=>show(n);col.append(el)});tree.append(col)});
function show(n){const arts=n.artifactIds.map(id=>state.artifacts[id]).filter(Boolean);const rev=state.reviews.filter(r=>r.branchId===n.nodeId);document.getElementById('detail').innerHTML='<div class="section"><h2>'+esc(n.title)+'</h2><div>'+esc(n.decisionQuestion)+'</div><p><b>Claim boundary</b><br>'+esc(n.claimBoundary)+'</p><pre>'+esc(JSON.stringify(n.parameters,null,2))+'</pre></div><div class="section"><h2>Evidence</h2>'+arts.map(a=>'<div class="item"><b>'+esc(a.role)+'</b><br>'+esc(a.summary)+'<br><code>'+esc(a.sha256)+'</code>'+Object.entries(a.metrics||{}).map(([k,v])=>'<span class="metric">'+esc(k)+': '+esc(v)+'</span>').join('')+'</div>').join('')+'</div><div class="section"><h2>Review</h2>'+rev.map(r=>'<div class="item"><b>'+esc(r.decision)+'</b><br>'+esc(r.rationale)+'</div>').join('')+'</div>'}show(nodes.find(n=>n.nodeId===state.activeBranchId)||nodes[0]);
</script></body></html>`;
}

function escapeHtml(value: string): string {
  return value.replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;").replaceAll('"', "&quot;");
}
