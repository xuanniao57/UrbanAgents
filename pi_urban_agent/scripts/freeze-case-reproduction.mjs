// Explicit allowlist: no credentials, model config, or previous research answers.
import { readdir, readFile, mkdir, copyFile, writeFile } from 'node:fs/promises';
import { resolve, relative, dirname } from 'node:path';
import { createHash } from 'node:crypto';
const root=process.cwd();
const experiment=process.argv[2] ?? 'evaluation/case_reproduction_20260916';
const dataRoot=process.argv[3] ?? 'evaluation/case_reproduction_20260916/data';
const dest=resolve(root,experiment,'frozen');
await mkdir(dest,{recursive:false});
const records=[];
async function capture(path, copy=true){
  const bytes=await readFile(path);const name=relative(root,path).replaceAll('\\','/');
  records.push({path:name,bytes:bytes.length,sha256:createHash('sha256').update(bytes).digest('hex'),copied:copy});
  if(copy){const target=resolve(dest,name);await mkdir(dirname(target),{recursive:true});await copyFile(path,target);}
}
async function walk(path,copy=true){for(const e of await readdir(path,{withFileTypes:true})){const p=resolve(path,e.name);if(e.isDirectory())await walk(p,copy);else if(e.isFile())await capture(p,copy);}}
for(const name of ['src','scripts','tests'])await walk(resolve(root,name));
for(const name of ['package.json','package-lock.json','tsconfig.json'])await capture(resolve(root,name));
await capture(resolve(root,experiment,'PROTOCOL.md'));
await walk(resolve(root,dataRoot),false);
for(const name of ['dist/core/agent-session.js','dist/core/compaction/compaction.js','dist/core/sdk.js','node_modules/@earendil-works/pi-ai/dist/api/simple-options.js'])await capture(resolve(root,'node_modules/@earendil-works/pi-coding-agent',name));
await writeFile(resolve(dest,'manifest.json'),JSON.stringify({frozenAt:new Date().toISOString(),piVersion:'0.84.2',experiment,dataRoot,purpose:'See frozen PROTOCOL.md for scope, conditions and limits',records},null,2));
console.log(JSON.stringify({snapshot:dest,files:records.length}));
