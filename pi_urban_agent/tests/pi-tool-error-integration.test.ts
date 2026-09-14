import test from 'node:test';
import assert from 'node:assert/strict';
import { createServer } from 'node:http';
import { spawn } from 'node:child_process';
import { mkdtemp, mkdir, readFile, readdir, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';
import { ResearchStore } from '../src/core/research-store.js';
import { CONTRACT } from './fixtures.js';

// Real Pi RPC/SDK/tools/hooks/session storage, with deterministic model responses.
// No GPU or external API is used, and the model never supplies an actor.
for (const mode of ['hybrid_recall', 'pi_default']) test(`Pi propagates rejected writes and recovers (${mode})`, { timeout: 30000 }, async () => {
  const root = await mkdtemp(join(tmpdir(), 'urban-sdk-error-'));
  const run = join(root, 'research');
  const store = await ResearchStore.initialize(run, CONTRACT);
  await store.openBranch({ nodeId: 'route_a', nodeType: 'model_route', title: 'Sensitivity candidate', parentIds: ['research_object'], decisionQuestion: 'Retain?', parameters: { support_m: 500 }, claimBoundary: 'Association only.' });
  const previous = await store.recordHumanDecision({ branchIds: ['route_a'], decision: 'defer', rationale: 'Await review', actor: 'fixture_expert' });
  await store.setPhase('human', 'route_a');
  const before = await store.load();
  let request = 0; const payloads: any[] = []; const intermediate: any[] = [];
  const server = createServer(async (req, res) => {
    try {
      const chunks: Buffer[] = []; for await (const chunk of req) chunks.push(chunk);
      payloads.push(JSON.parse(Buffer.concat(chunks).toString()));
      intermediate.push(await store.load());
      request++;
      const tool = request <= 2 ? { name: 'urban_human_decision', arguments: JSON.stringify(request === 2 ? { rationale: 'Human requested sensitivity, not a universal scale.' } : {}) }
        : request === 3 ? { name: 'urban_state', arguments: '{}' } : null;
      res.writeHead(200, { 'Content-Type': 'text/event-stream' });
      const chunk = (delta: unknown, finish: string | null) => `data: ${JSON.stringify({ id: `fake_${request}`, object: 'chat.completion.chunk', created: 1, model: 'fixture-model', choices: [{ index: 0, delta, finish_reason: finish }] })}\n\n`;
      res.write(chunk({ role: 'assistant', ...(tool ? { tool_calls: [{ index: 0, id: `call_${request}`, type: 'function', function: tool }] } : { content: 'State read back; sensitivity retained.' }) }, null));
      res.write(chunk({}, tool ? 'tool_calls' : 'stop'));
      res.end('data: [DONE]\n\n');
    } catch (error) { res.writeHead(500); res.end(String(error)); }
  });
  await new Promise<void>(yes => server.listen(0, '127.0.0.1', yes));
  const port = (server.address() as {port:number}).port;
  const cfg = join(root, 'runtime'); await mkdir(cfg);
  await writeFile(join(cfg, 'models.json'), JSON.stringify({ providers: { fixture: { api: 'openai-completions', apiKey: 'test-only', baseUrl: `http://127.0.0.1:${port}/v1`, models: [{ id: 'fixture-model', name: 'fixture-model', reasoning: false, input: ['text'], cost: {input:0,output:0,cacheRead:0,cacheWrite:0}, contextWindow: 32768, maxTokens: 1024 }] } } }));
  await writeFile(join(cfg, 'settings.json'), JSON.stringify({ compaction: {enabled:false}, retry: {enabled:false} }));
  const sessionDir = join(root, 'sessions'); await mkdir(sessionDir);
  const child = spawn(process.execPath, ['node_modules/@earendil-works/pi-coding-agent/dist/cli.js', '-a', '-e', '.pi/extensions/urban-agent.ts', '--no-extensions', '--no-skills', '--no-prompt-templates', '--no-context-files', '--offline', '--mode', 'rpc', '--thinking', 'off', '--provider', 'fixture', '--model', 'fixture-model', '--session-dir', sessionDir], {
    cwd: resolve('.'), windowsHide: true, env: {...process.env, PI_CODING_AGENT_DIR:cfg, PI_OFFLINE:'1', URBAN_PI_RUN_DIR:run, URBAN_CONTEXT_MODE:mode, URBAN_EVAL_CONDITION:mode==='pi_default'?'pi_default_compaction':'urban_full', URBAN_AUTHENTICATED_ACTOR:'integration_expert', URBAN_DISABLED_TOOLS:'', URBAN_TOOL_ERROR_BUDGET:'4', URBAN_TOOL_CALL_BUDGET:'16'}
  });
  const events: any[] = []; let tail = ''; let stderr = '';
  const done = new Promise<void>((yes, no) => {
    child.stderr.on('data', c => { stderr += c; });
    child.on('error', no);
    child.on('exit', code => { if (!events.some(e => e.type==='agent_settled')) no(new Error(`Pi exited ${code}: ${stderr}`)); });
    child.stdout.on('data', c => {
      tail += c; const lines = tail.split('\n'); tail=lines.pop()!;
      for(const line of lines) if(line.trim()) {
        const e=JSON.parse(line); events.push(e);
        if(e.type==='agent_settled') yes();
        if(e.type==='response' && !e.success) no(new Error(JSON.stringify(e)));
      }
    });
  });
  let timer: NodeJS.Timeout | undefined;
  try {
    child.stdin.write(JSON.stringify({id:'test',type:'prompt',message:'Retain route_a as sensitivity evidence, not the main route. Record this decision and read the state back. Do not claim a unique correct scale.'})+'\n');
    await Promise.race([done,new Promise<never>((_,no)=>{timer=setTimeout(()=>no(new Error('Pi integration timeout')),25000);})]);
    const ends=events.filter(e=>e.type==='tool_execution_end');
    assert.deepEqual(ends.map(e=>e.isError),[true,false,false]);
    assert.match(ends[0].result.content[0].text,/Recovery guard: 3 tool-error attempt/);
    assert.deepEqual(intermediate[1].humanDecisions,before.humanDecisions,'rejected write must not persist');
    assert.deepEqual(intermediate[1].nodes,before.nodes);
    assert.match(payloads[1].messages.filter((m:any)=>m.role==='tool').at(-1).content,/requires rationale/);
    const final=await store.load();
    assert.equal(final.humanDecisions.length,before.humanDecisions.length+1);
    assert.equal(final.humanDecisions.at(-1)?.actor,'integration_expert');
    assert.equal(final.humanDecisions.at(-1)?.decision,'retain_sensitivity');
    assert.equal(JSON.parse(ends[2].result.content[0].text).inspected_node.human_evidence_role,'retain_sensitivity');
    const message=events.find(e=>e.type==='message_end' && e.message?.role==='toolResult');
    assert.equal(message.message.isError,true);
    const files=(await readdir(sessionDir)).filter(f=>f.endsWith('.jsonl'));
    assert.equal(files.length,1);
    const persisted=(await readFile(join(sessionDir,files[0]),'utf8')).trim().split(/\r?\n/).map(line=>JSON.parse(line));
    assert.equal(persisted.find(e=>e.type==='message' && e.message?.role==='toolResult').message.isError,true);
  } finally {
    clearTimeout(timer); child.stdin.end(); child.kill(); server.closeAllConnections(); server.close();
  }
});
