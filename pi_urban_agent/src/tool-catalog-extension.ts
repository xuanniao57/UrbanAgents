import type {ExtensionAPI} from '@earendil-works/pi-coding-agent';
import {Type} from 'typebox';

const BASE=['read','bash','edit','write','urban_tools'];
const CATALOG:Record<string,string>={
 urban_initialize:'Create research record from source metadata and proposed design',
 urban_state:'Inspect current research status',urban_recall:'Retrieve saved research facts',
 urban_set_phase:'Change work focus; planning can be revisited',
 urban_open_branch:'Create an alternative research branch',
 urban_commit_route_family:'Record a group of proposed routes',
 urban_commit_run:'Attach executed script and result evidence',
 urban_record_review:'Record evidence checks and repairs requested',
 urban_human_decision:'Apply an authenticated human decision',
 urban_finalize:'Save final reviewed conclusions',
 urban_delegate:'Assign a fresh-context Worker or Reviewer',
};
export default function catalog(pi:ExtensionAPI) {
 let loaded:string[]=[];
 const available=()=>pi.getAllTools().filter(t=>CATALOG[t.name]);
 pi.on('session_start',()=>{loaded=[];pi.setActiveTools(BASE);});
 pi.on('before_agent_start',event=>({systemPrompt: event.systemPrompt+
  '\nResearch capability directory (names and purposes only):\n'+
  available().map(t=>`${t.name}: ${CATALOG[t.name]}`).join('\n')+
  '\nLoad the tools needed for your next action using urban_tools({load:[names]}). This changes available schemas, not permissions. No fixed number of branches or delegations is required.'+
  (available().some(t=>t.name==='urban_initialize')?' Handoffs: after inspecting metadata, initialize your proposed design before fitting; when the human narrows the task, record that scope on the active route; after execution, attach evidence before presenting it as reviewed. The source contract describes available data, not necessarily the subset used by a route. Files alone are not a Research Tree.':'')}));
 pi.registerTool({name:'urban_tools',label:'Research tool directory',
 description:'List available research tools, or load named tools into context. All roles can inspect the directory. Loading replaces previously loaded research schemas; files remain available. The directory is not research memory.',
 parameters:Type.Object({load:Type.Optional(Type.Array(Type.String()))}),
 async execute(_id,p){
  const tools=available();
  if(p.load){
   const unknown=p.load.filter(n=>!tools.some(t=>t.name===n));
   if(unknown.length)throw new Error(`Unavailable tools: ${unknown.join(', ')}. Inspect directory first.`);
   loaded=[...new Set(p.load)];pi.setActiveTools([...BASE,...loaded]);
  }
  return {content:[{type:'text',text:JSON.stringify({tools:tools.map(t=>({name:t.name,purpose:CATALOG[t.name]})),loaded,note:'Load the capabilities needed for your next action. Human authorization and valid-state checks still apply.'})}],details:{}};
 }});
}
