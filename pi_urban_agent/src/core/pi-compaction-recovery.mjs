import { countContext, countText, requestLimits } from './request-guard.mjs';

/** Allocate ONE joint summary budget after accounting for the kept suffix.
 * Pi still selects legal cuts, generates the summary and persists it. */
export async function fitCompactionBudget(preparation, entries, settings, model, state, prepare, estimate, buildContext, convert) {
  if (!preparation) return preparation;
  const window=Number(process.env.URBAN_CONTEXT_WINDOW??model.contextWindow);
  const output=Number(process.env.URBAN_MAX_OUTPUT_TOKENS??model.maxTokens);
  if (!Number.isFinite(window)||!state?.tools) return preparation; // legacy test doubles
  const limits=requestLimits(window,output);
  for(const fraction of [1,.5,.25,0]) {
    const p=fraction===1?preparation:prepareOverflowCompaction(entries,{...settings,keepRecentTokens:Math.floor(settings.keepRecentTokens*fraction)},prepare,estimate);
    if(!p)continue;
    const preview={id:'budget-preview',parentId:entries.at(-1)?.id,type:'compaction',timestamp:new Date().toISOString(),firstKeptEntryId:p.firstKeptEntryId,summary:'',tokensBefore:p.tokensBefore};
    const messages=await convert(buildContext([...entries,preview],preview.id).messages);
    const kept=await countContext({systemPrompt:state.systemPrompt,tools:state.tools,messages});
    const fileTokens=await countText([...p.fileOps.read,...p.fileOps.written,...p.fileOps.edited].join('\n'))+256;
    // Leave room for the next tool result, rather than refilling the window.
    const progress=Math.max(256,Math.floor(limits.input*.1));
    const allowance=Math.floor(window*.1);
    if(limits.input-kept-fileTokens-progress<allowance)continue;
    // Pi's split-turn path concatenates .8*reserve history + .5*reserve prefix.
    const split=p.isSplitTurn&&p.turnPrefixMessages.length>0;
    const multiplier=split?((p.messagesToSummarize.length>0||p.previousSummary)?.8:0)+.5:.8;
    const reserve=Math.min(p.settings.reserveTokens,Math.floor(allowance/multiplier));
    if(Math.floor(reserve*(split?.5:.8))<128)continue;
    return {...p,settings:{...p.settings,reserveTokens:reserve}};
  }
  throw new Error('Context overflow: static context and the minimum legal retained suffix leave no room for a summary.');
}

/** Overflow-only cut-point recovery. Pi still creates and persists the summary. */
export function prepareOverflowCompaction(entries, settings, prepare, estimate) {
  const original = prepare(entries, settings);
  if (original) return original;
  // Bounded local searches, not model calls. Keep Pi's tool-pair-safe cut logic.
  for (const fraction of [0.5, 0.25, 0]) {
    const preparation = prepare(entries, { ...settings, keepRecentTokens: Math.floor(settings.keepRecentTokens * fraction) });
    if (preparation) return preparation;
  }
  const previous = entries.findLast(entry => entry.type === 'compaction');
  if (!previous?.summary || !entries.some(entry => entry.id === previous.firstKeptEntryId)) return undefined;
  // A summary can itself fill the window even when no new history is eligible.
  // Retain exactly the same suffix and ask Pi to condense only its old summary.
  const summaryTokens = estimate({ role: 'user', content: previous.summary, timestamp: 0 });
  if (summaryTokens < 512) return undefined;
  return {
    firstKeptEntryId: previous.firstKeptEntryId,
    messagesToSummarize: [], turnPrefixMessages: [], isSplitTurn: false,
    tokensBefore: previous.tokensBefore,
    previousSummary: previous.summary,
    fileOps: {
      read: new Set(previous.details?.readFiles ?? []),
      written: new Set(previous.details?.modifiedFiles ?? []),
      edited: new Set(),
    },
    settings: { ...settings, reserveTokens: Math.min(settings.reserveTokens, Math.floor(summaryTokens / 2 / 0.8)) },
    overflowSummaryOnly: true,
  };
}
