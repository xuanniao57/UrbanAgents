/** Local-only interactive bridge to the production Pi runtime; not an evaluation harness. */
import {createServer} from 'node:http';
import {spawn} from 'node:child_process';
import {readFile,writeFile,mkdir,appendFile} from 'node:fs/promises';
import {resolve,dirname,delimiter} from 'node:path';
import {fileURLToPath} from 'node:url';
import {randomUUID} from 'node:crypto';
import {prepareSharedEnvironment} from '../src/core/shared-environment.js';
import {workspaceShellPrefix} from '../src/core/workspace-shell.js';
import {resolveCompactionSettings} from '../src/core/model-context.js';
const root=resolve(dirname(fileURLToPath(import.meta.url)),'..');
const run=resolve(process.env.URBAN_WEB_WORKSPACE || resolve(root,'.local-workspaces',new Date().toISOString().replace(/[:.]/g,'-')));
const port=Number(process.env.URBAN_WEB_PORT || 8018);
const token=randomUUID();
for(const folder of ['data','work','outputs','research','runtime','sessions'])await mkdir(resolve(run,folder),{recursive:true});
// Credentials remain in process environment, never in browser responses or source files.
for(const path of [resolve(root,'../.env'),resolve(root,'../../.env')]){
 try{for(const line of (await readFile(path,'utf8')).split(/\r?\n/)){
  const m=line.match(/^\s*(kimi_code_apikey|KIMI_CODE_API_KEY)\s*=\s*(.*?)\s*$/i);if(m)process.env.KIMI_CODE_API_KEY=m[2].replace(/^['"]|['"]$/g,'');
 }}catch{}
}
if(!process.env.KIMI_CODE_API_KEY)throw Error('Configure KIMI_CODE_API_KEY in your environment or repository .env');
const python=process.env.URBAN_PI_PYTHON || resolve(root,'../.venv-section4/Scripts/python.exe');
await prepareSharedEnvironment(run,python);
await writeFile(resolve(run,'WORKSPACE.md'),`# Interactive research workspace\n\nHuman-driven session. Read DATA_GUIDE.md and ENVIRONMENT.md. Inputs go in data/, scripts in work/, outputs in outputs/. No input data is preloaded: ask the researcher to place their data here and describe its meaning. Do not invent data or inherit an experiment task.\n`);
const config={providers:{'kimi-code':{baseUrl:'https://api.kimi.com/coding/v1',api:'openai-completions',apiKey:'$KIMI_CODE_API_KEY',headers:{'User-Agent':'Urban-Agent-Pi/2.2'},models:[{id:'kimi-for-coding',name:'Kimi Code',reasoning:true,input:['text'],contextWindow:262144,maxTokens:16384,compat:{supportsDeveloperRole:false,supportsReasoningEffort:false,maxTokensField:'max_tokens'},cost:{input:0,output:0,cacheRead:0,cacheWrite:0}}]}}};
await writeFile(resolve(run,'runtime/models.json'),JSON.stringify(config));
await writeFile(resolve(run,'runtime/settings.json'),JSON.stringify({compaction:resolveCompactionSettings(262144,16384),shellCommandPrefix:workspaceShellPrefix(python)}));
const env={...process.env,PATH:dirname(python)+delimiter+process.env.PATH,PI_CODING_AGENT_DIR:resolve(run,'runtime'),PI_OFFLINE:'1',PYTHONUTF8:'1',PYTHONIOENCODING:'utf-8',URBAN_PI_RUN_DIR:resolve(run,'research'),URBAN_PI_WORKSPACE_ROOT:run,URBAN_PI_REPOSITORY_ROOT:run,URBAN_DATA_ROOT:resolve(run,'data'),URBAN_PI_PYTHON:python,URBAN_CONTEXT_MODE:'hybrid_recall',URBAN_EVAL_CONDITION:'urban_full_v2',URBAN_AUTHENTICATED_ACTOR:'local-human',URBAN_AGENT_ROLE:'planner',URBAN_PI_PROVIDER:'kimi-code',URBAN_PI_MODEL:'kimi-for-coding',URBAN_PI_THINKING:'high',URBAN_DELEGATION_LOG_DIR:resolve(run,'outputs/delegations'),NODE_USE_ENV_PROXY:'0'};
for(const key of Object.keys(env))if(/^(https?|all)_proxy$/i.test(key))delete (env as Record<string,unknown>)[key];
const args=[resolve(root,'node_modules/@earendil-works/pi-coding-agent/dist/cli.js'),'-a','-e',resolve(root,'src/shared-environment-extension.ts'),'-e',resolve(root,'src/four-condition-extension.ts'),'--no-extensions','--no-skills','--no-prompt-templates','--no-context-files','--offline','--mode','rpc','--thinking','high','--provider','kimi-code','--model','kimi-for-coding','--session',resolve(run,'sessions/interactive.jsonl')];
const child=spawn(process.execPath,args,{cwd:run,env,windowsHide:true,stdio:'pipe'});
const events:any[]=[];let buffer='',alive=true,busy=false,ready=false;
function record(event:any){events.push({...event,time:new Date().toISOString()});void appendFile(resolve(run,'ui-events.jsonl'),JSON.stringify(events.at(-1))+'\n');}
child.stdout.setEncoding('utf8');child.stdout.on('data',(chunk:string)=>{buffer+=chunk;const lines=buffer.split('\n');buffer=lines.pop()||'';for(const line of lines){try{const e=JSON.parse(line);if(e.type==='agent_start')busy=true;if(e.type==='agent_end')busy=false;if(e.type==='response'&&e.command==='get_state')ready=e.success;
 // Display observable answers and tool events, not private reasoning tokens.
 if(e.type==='message_end'&&e.message?.role==='assistant')record({type:'answer',text:(e.message.content||[]).filter((c:any)=>c.type==='text').map((c:any)=>c.text).join('\n'),error:e.message.errorMessage});
 else if(['tool_execution_start','tool_execution_end','auto_compaction_start','auto_compaction_end'].includes(e.type))record({type:e.type,tool:e.toolName,id:e.toolCallId,isError:e.isError});
 else if(e.type==='response'&&!e.success)record({type:'error',text:e.error});
 }catch{}}});
child.stderr.on('data',chunk=>void appendFile(resolve(run,'stderr.log'),chunk));
child.on('exit',code=>{alive=false;busy=false;record({type:'error',text:`Runtime exited: ${code}`});});
child.on('error',error=>{alive=false;record({type:'error',text:error.message});});
child.stdin.on('error',()=>{alive=false;});
child.stdin.write(JSON.stringify({type:'get_state',id:'startup'})+'\n');
const server=createServer(async(req,res)=>{try{
 if(req.headers.host!==`127.0.0.1:${port}`&&req.headers.host!==`localhost:${port}`){res.writeHead(403).end();return;}
 const url=new URL(req.url||'/',`http://127.0.0.1:${port}`);
 if(req.method==='GET'&&url.pathname==='/'){res.setHeader('Content-Type','text/html; charset=utf-8');res.end((await readFile(resolve(root,'web/index.html'),'utf8')).replace('__TOKEN__',token));return;}
 if(req.headers['x-workspace-token']!==token){res.writeHead(403).end();return;}
 res.setHeader('Content-Type','application/json');res.setHeader('Cache-Control','no-store');
 if(req.method==='GET'&&url.pathname==='/state'){let tree=null;try{tree=JSON.parse(await readFile(resolve(run,'research/research_state.json'),'utf8'));}catch{}res.end(JSON.stringify({ready,alive,busy,workspace:run,model:'kimi-for-coding',events,tree}));return;}
 if(req.method==='POST'&&['/message','/abort'].includes(url.pathname)){
  if(!ready||!alive){res.writeHead(503).end(JSON.stringify({error:'Runtime not ready'}));return;}
  let body='';for await(const chunk of req){body+=chunk;if(Buffer.byteLength(body)>65536){res.writeHead(413).end();return;}}
  if(url.pathname==='/abort'){child.stdin.write(JSON.stringify({type:'abort'})+'\n');res.end('{}');return;}
  const {message}=JSON.parse(body);if(typeof message!=='string'||!message.trim()){res.writeHead(400).end('{}');return;}
  record({type:'human',text:message});child.stdin.write(JSON.stringify({type:'prompt',id:randomUUID(),message,streamingBehavior:'steer'})+'\n');busy=true;res.end('{}');return;
 }
 res.writeHead(404).end('{}');
 }catch(error){res.writeHead(500).end(JSON.stringify({error:String(error)}));}});
server.listen(port,'127.0.0.1',()=>console.log(JSON.stringify({url:`http://127.0.0.1:${port}`,workspace:run})));
function stop(){child.kill();server.close();}process.on('SIGINT',stop);process.on('SIGTERM',stop);
