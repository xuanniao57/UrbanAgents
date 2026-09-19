import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';
import { callPython } from '../src/bridge/python-bridge.js';
import extension from '../src/pi-extension.js';

test('Python bridge rejects malformed arguments, preserves CLI tokens, and reports process failure', async () => {
  const root = await mkdtemp(join(tmpdir(), 'urban-python-'));
  const script = join(root, 'analysis with spaces.py');
  await writeFile(script, 'import argparse,json,os\np=argparse.ArgumentParser()\np.add_argument("--action",required=True)\np.add_argument("--label")\na=p.parse_args()\nprint(json.dumps({"action":a.action,"label":a.label,"cwd":os.getcwd()}))\n');
  const options = { repositoryRoot: root, runDir: root };
  const run = (args: Record<string, unknown>) => callPython('run_script', args, options);
  const success = await run({ script, args: ['--action', 'inventory', '--label', 'a b; no shell'], cwd: root });
  assert.equal(success.success, true);
  assert.equal(success.result?.exit_code, 0);
  assert.deepEqual(JSON.parse(String(success.result?.stdout_preview)), { action: 'inventory', label: 'a b; no shell', cwd: root });
  for (const args of [{ script, action: 'inventory' }, { script, args: '--action inventory' }, { script, args: [42] }, { path: script }, { script, timeout_seconds: -1 }]) {
    const result = await run(args);
    assert.equal(result.success, false, JSON.stringify(args));
    assert.match(result.error!, /Unexpected|requires|array of strings|integer/);
  }
  const command = await run({ script: `${script} --action inventory` });
  assert.equal(command.success, false);
  assert.match(command.error!, /one existing Python file/);
  const failure = await run({ script });
  assert.equal(failure.success, false);
  assert.equal(failure.result?.exit_code, 2);
  assert.match(failure.error!, /code 2.*[\s\S]*--action/);
  assert.match(String(failure.result?.stderr_preview), /required/);
  const csv = join(root, 'data.csv'); await writeFile(csv, 'id,value\na,2\nb,3\n');
  const inspected = await callPython('inspect_csv', { path: csv, limit: 1 }, options);
  assert.equal(inspected.success, true);
  assert.equal(inspected.result?.preview_rows, 1);
  assert.equal((await callPython('inspect_csv', { path: csv, script }, options)).success, false);
});

for (const mode of ['hybrid_recall', 'pi_default']) test(`shared extension declares Python arguments and throws on nonzero exit (${mode})`, async () => {
  const old = process.env.URBAN_CONTEXT_MODE;
  const tools = new Map<string, any>();
  try {
    process.env.URBAN_CONTEXT_MODE = mode;
    extension({ on() {}, registerTool(t: any) { tools.set(t.name, t); } } as any);
  } finally { if (old === undefined) delete process.env.URBAN_CONTEXT_MODE; else process.env.URBAN_CONTEXT_MODE = old; }
  const tool = tools.get('urban_python');
  const shape = tool.parameters.properties.arguments;
  assert.equal(shape.additionalProperties, false);
  assert.equal(shape.properties.args.type, 'array');
  assert.equal(shape.properties.args.items.type, 'string');
  assert.ok(shape.properties.script.description.includes('file path'));
  await assert.rejects(tool.execute('bad-cli', { method: 'run_script', arguments: { script: resolve('python/urban_tool_server.py'), args: ['--bad-argument'] } }), /Python script exited with code 1/);
});

test('read-only file access works before initialization and JSON envelopes survive result hooks',async()=>{
  const tools=new Map<string,any>(), handlers=new Map<string,any[]>();
  extension({on(name:string,cb:any){handlers.set(name,[...(handlers.get(name)??[]),cb]);},registerTool(t:any){tools.set(t.name,t);}} as any);
  for(const hook of handlers.get('before_agent_start')??[]){
    const result=await hook({prompt:'Read the supplied data first.'},{model:{contextWindow:8192,maxTokens:2048}});
    assert.equal(result.message,undefined,'Runtime instructions must not impersonate a new human message');
    assert.match(result.systemPrompt,/No Research Tree exists/);
  }
  const ctx={abort(){throw Error('should not abort');}};
  for(const hook of handlers.get('tool_call')??[]) {
    const result=await hook({toolName:'urban_read',input:{method:'inspect_text',path:resolve('long_case/data_contract.json')}},ctx);
    assert.ok(!result?.block);
  }
  const read=await tools.get('urban_read').execute('read', {path:resolve('long_case/data_contract.json'),limit:4000});
  let event={toolName:'urban_read',content:read.content,details:read.details,isError:false};
  for(const hook of handlers.get('tool_result')??[]) event={...event,...await hook(event,ctx)};
  assert.doesNotThrow(()=>JSON.parse(event.content[0].text));
  assert.equal(event.content[0].text,read.content[0].text);
  assert.ok(JSON.parse(event.content[0].text).path.endsWith('data_contract.json'));
});
