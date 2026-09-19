/** Transport completion is distinct from scientific correctness. */
export function classifyTurn(input: { failed: boolean; settled: boolean; budgetStop: unknown; messages: Array<{stopReason?: string}>; requests: Array<Record<string, any>> }) {
  const terminal=input.messages.at(-1)?.stopReason;
  const last=input.requests.at(-1);
  const requestFailed=(r:Record<string,any>)=>Boolean(r.error||r.providerError||r.httpStatus>=400||r.incomplete);
  const completed=!input.failed && input.settled && !input.budgetStop && terminal==='stop' && !(last && (requestFailed(last)||last.finishReason==='length'));
  const hadErrors=input.messages.some(m=>['error','aborted','length'].includes(m.stopReason??''))||input.requests.some(requestFailed);
  return {outcome:completed?'completed':'failed',recoveredErrors:completed&&hadErrors,scientificStatus:'not_assessed'};
}
