import {readFile} from 'node:fs/promises';
const env=Object.fromEntries((await readFile('../../.env','utf8')).split(/\r?\n/).flatMap(l=>{const m=l.match(/^\s*(QWEN_API_KEY|QWEN_API_BASE)\s*=\s*(.*?)\s*$/);return m?[[m[1],m[2].replace(/^["']|["']$/g,'')]]:[];}));
const cfg=JSON.parse(await readFile('.pi-agent/models.json','utf8'));
let base=cfg.providers['aliyun-bailian'].baseUrl;
if(base==='$QWEN_API_BASE')base=env.QWEN_API_BASE;
base=base.replace(/\/api\/v1\/?$/,'/compatible-mode/v1').replace(/\/$/,'');
try{const r=await fetch(base+'/models',{headers:{Authorization:`Bearer ${env.QWEN_API_KEY}`},signal:AbortSignal.timeout(15000)});await r.arrayBuffer();console.log(JSON.stringify({host:new URL(base).hostname,status:r.status,connected:true}));}
catch(e){console.log(JSON.stringify({connected:false,name:e.name,code:e.cause?.code,causes:e.cause?.errors?.map(x=>x.code)}));process.exitCode=1;}
