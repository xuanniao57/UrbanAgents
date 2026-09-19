import { test } from 'node:test';
import assert from 'node:assert/strict';
// @ts-ignore JavaScript runtime helper
import { completeCheckpoint } from '../src/core/summary-completion.mjs';

test('checkpoint retry uses original source, unchanged cap, and includes retry usage', async () => {
  const contexts: any[] = [];
  const source = { systemPrompt: 'Pi summary', messages: [{ role: 'user', content: 'original history' }] };
  const result = await completeCheckpoint(source, { maxTokens: 1000 }, async (context: any, options: any) => {
    contexts.push(context);
    assert.equal(options.maxTokens, 1000);
    assert.equal(context.messages, source.messages);
    return { stopReason: contexts.length === 1 ? 'length' : 'stop', content: [], usage: { input: 50, output: 10 } };
  });
  assert.match(contexts[0].systemPrompt, /450 tokens/);
  assert.match(contexts[1].systemPrompt, /220 tokens/);
  assert.equal(result.usage.input, 100);
  assert.equal(result.usage.output, 20);
  assert.equal(source.systemPrompt, 'Pi summary');
});

test('never accept a truncated checkpoint; retry bounded at two requests', async () => {
  let calls = 0;
  await assert.rejects(completeCheckpoint({ messages: [] }, { maxTokens: 256 }, async () => {
    calls++;
    return { stopReason: 'length', usage: {} };
  }), /original history retained/);
  assert.equal(calls, 2);
});

test('summary source fits by shrinking only checkpoint output, not cutting source', async () => {
  const old = process.env.URBAN_CONTEXT_WINDOW;
  process.env.URBAN_CONTEXT_WINDOW = '4096';
  try {
    const source = { systemPrompt: 'Pi', messages: [{ role: 'user', content: 'a'.repeat(9600) }] };
    await completeCheckpoint(source, { maxTokens: 1000 }, async (context: any, options: any) => {
      assert.equal(context.messages, source.messages);
      assert.ok(options.maxTokens >= 128 && options.maxTokens < 1000);
      return { stopReason: 'stop', content: [], usage: {} };
    });
  } finally {
    if (old === undefined) delete process.env.URBAN_CONTEXT_WINDOW;
    else process.env.URBAN_CONTEXT_WINDOW = old;
  }
});
