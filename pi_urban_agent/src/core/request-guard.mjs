/** Transport only. Pi owns all historical summarization and cut points. */
import { readFile, mkdir, appendFile } from 'node:fs/promises';
import { resolve } from 'node:path';
import { Tokenizer } from '@huggingface/tokenizers';
const tokenizers = new Map();
const usageRatios = new Map();
// Learn only input-token ratios from successful provider responses. Never use
// an old absolute usage count after compaction (it includes removed history).
export function inputUsageRatio(usage, estimate) {
  const actual = Number(usage?.input ?? 0) + Number(usage?.cacheRead ?? 0) + Number(usage?.cacheWrite ?? 0);
  return actual > 0 && estimate > 0 && Number.isFinite(actual) ? actual / estimate : undefined;
}
// Unknown provider vocabulary: conservative mixed-text estimate, NOT bytes.
// A configured tokenizer is preferred. The request margin covers chat-template
// overhead; neither mode claims to reproduce a provider's private tokenizer.
export function estimateTextTokens(text) {
  const ascii = text.match(/[\x00-\x7f]/g)?.length ?? 0;
  return Math.ceil(ascii / 3 + Buffer.byteLength(text.replace(/[\x00-\x7f]/g, ''), 'utf8') / 2);
}
export async function countText(text) {
  const dir = process.env.URBAN_TOKENIZER_DIR;
  if (!dir) return estimateTextTokens(text);
  const key = resolve(dir);
  if (!tokenizers.has(key)) tokenizers.set(key, Promise.all(['tokenizer.json','tokenizer_config.json'].map(f=>readFile(resolve(key,f),'utf8').then(JSON.parse))).then(([m,c])=>new Tokenizer(m,c)));
  return (await tokenizers.get(key)).encode(text).ids.length;
}
export function requestLimits(window, output) {
  if (!Number.isFinite(window) || window < 1024) throw new Error('Invalid deployed context window');
  const margin=Math.max(256,Math.ceil(window*.06));
  output=Math.floor(output);
  if(!Number.isFinite(output)||output<128||output+margin>=window)throw new Error('Invalid output budget');
  return {window,output,margin,input:window-output-margin};
}
export async function countContext(context) {
  let n=32+await countText(context.systemPrompt??'');
  if(context.tools?.length)n+=128+await countText(JSON.stringify(context.tools));
  for(const m of context.messages) {
    n+=32+await countText([m.role,m.toolCallId,m.toolName].filter(Boolean).join(' '));
    // Text is tokenized as text, not as JSON-escaped copies of scripts/results.
    // This remains an estimate (the provider owns its chat template).
    if(typeof m.content==='string') n+=await countText(m.content);
    else for(const b of m.content??[]) {
      n+=16;
      if(b.type==='text') n+=await countText(b.text??'');
      else if(b.type==='thinking') n+=await countText(b.thinking??'');
      else n+=await countText(JSON.stringify(b));
    }
  }
  return n;
}
export async function streamWithBudget(model, original, options, send) {
  const window=Number(process.env.URBAN_CONTEXT_WINDOW??model.contextWindow);
  const cap=Number(process.env.URBAN_MAX_OUTPUT_TOKENS??model.maxTokens);
  const limits=requestLimits(window,Math.min(options?.maxTokens??cap,cap));
  const context={...original,messages:original.messages.map(m=>({...m}))};
  const before=await countContext(context);
  const base=resolve(process.env.URBAN_PI_WORKSPACE_ROOT??process.env.URBAN_BUDGET_LOG_DIR??'.');
  // Tool envelopes were already persisted. Never rewrite history at send time.
  const key=JSON.stringify([base,model.provider,model.id,context.tools?.length?'agent':'summary']);
  const ratios=usageRatios.get(key)??[];
  // Known local tokenizer remains unchanged. Unknown-vocabulary estimates use
  // the highest of the last eight observed ratios, plus the existing margin.
  // Keep the conservative fallback until two observations are available.
  const scale=!process.env.URBAN_TOKENIZER_DIR && ratios.length>=2 ? Math.max(...ratios) : 1;
  const input=Math.ceil(before*scale);
  const output=limits.output;
  const log=resolve(process.env.URBAN_BUDGET_LOG_DIR??base,'request-budget');await mkdir(log,{recursive:true});
  await appendFile(resolve(log,'events.jsonl'),JSON.stringify({time:new Date().toISOString(),event:'request_check',policy:'pi_only_compaction_v5',countMode:process.env.URBAN_TOKENIZER_DIR?'configured_tokenizer':ratios.length>=2?'provider_calibrated_estimate':'mixed_text_estimate',calibrationScale:scale,calibrationSamples:ratios.length,before,inputTokens:input,...limits,actualOutput:output,accepted:input<=limits.input})+'\n');
  if(input>limits.input)throw new Error(`Context window exceeded: request input exceeds the context window budget: input=${input}, window=${window}, reservedOutput=${output}. Request NOT sent; Pi must compact the session.`);
  const stream=await send(model,context,{...options,maxTokens:output,urbanPreflightChecked:true});
  // result() is Pi's shared final-result promise, not a second stream consumer.
  if (!process.env.URBAN_TOKENIZER_DIR && typeof stream?.result==='function') {
    void stream.result().then(message=>{
      if(message.stopReason==='error'||message.stopReason==='aborted')return;
      const ratio=inputUsageRatio(message.usage,before);
      if(ratio!==undefined)usageRatios.set(key,[...(usageRatios.get(key)??[]),ratio].slice(-8));
    }).catch(()=>{});
  }
  return stream;
}
