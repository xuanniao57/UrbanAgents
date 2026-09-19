/** Shared transport envelope, applied before Pi persists tool results. */
import {mkdir,writeFile} from 'node:fs/promises';
import {resolve} from 'node:path';
import {createHash} from 'node:crypto';
import type {ExtensionAPI} from '@earendil-works/pi-coding-agent';
// @ts-expect-error runtime JS
import {countText} from './core/request-guard.mjs';
export default function outputEnvelope(pi:ExtensionAPI) {
 pi.on('tool_result',async(event)=>{
  const body=JSON.stringify({content:event.content,details:event.details,isError:event.isError});
  const limit=Math.max(768,Math.min(1600,Math.floor(Number(process.env.URBAN_CONTEXT_WINDOW??8192)*.04)));
  if(await countText(body)<=limit)return;
  const root=resolve(process.env.URBAN_PI_WORKSPACE_ROOT??process.cwd());
  const path='.research-history/'+createHash('sha256').update(body).digest('hex')+'.json';
  await mkdir(resolve(root,'.research-history'),{recursive:true});await writeFile(resolve(root,path),body);
  const original=event.content.filter(b=>b.type==='text').map(b=>b.text).join('\n');
  let chars=limit*2, text='';
  do {
   let head=original.slice(0,chars);
   if(head.includes('\n'))head=head.slice(0,head.lastIndexOf('\n')+1);
   const source=event.toolName==='read'?event.input?.path:undefined;
   const view={tool:event.toolName,isError:event.isError??false,full_result:path,source_file:source,
    preview:head,tail:event.toolName==='bash'?original.slice(-Math.floor(chars/3)):undefined,
    next_read_offset:source?Number(event.input?.offset??1)+(head.match(/\n/g)?.length??0):undefined,
    note:'Partial verbatim preview; full tool result is archived. For code, read the source at the needed line with offset/limit. For one-line JSON use Python to inspect needed fields.'};
   text=JSON.stringify(view);chars=Math.floor(chars/2);
  } while(await countText(text)>limit && chars>0);
  return {content:[{type:'text' as const,text}],details:{full_result:path},isError:event.isError};
 });
}
