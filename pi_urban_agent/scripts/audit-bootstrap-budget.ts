import {readFile} from 'node:fs/promises';
import {bootstrapTools} from '../src/core/tool-policy.js';
// @ts-expect-error JS tokenizer
import {countText} from '../src/core/request-guard.mjs';
process.env.URBAN_TOKENIZER_DIR='cache/qwen35-tokenizer';
const r=JSON.parse(await readFile('evaluation/raw_local_20260915/9b/pi_only_r04/requests/000001/request.json','utf8'));
const kept=r.tools.filter((t:any)=>bootstrapTools(true).includes(t.function.name));
console.log(JSON.stringify({oldToolCount:r.tools.length,newToolCount:kept.length,oldSchemaTokens:await countText(JSON.stringify(r.tools)),newSchemaTokens:await countText(JSON.stringify(kept)),systemTokens:await countText(JSON.stringify(r.messages.filter((m:any)=>m.role==='system')))},null,2));
