import test from 'node:test';
import assert from 'node:assert/strict';
import {existsSync} from 'node:fs';
import {resolve} from 'node:path';
import {pathToFileURL} from 'node:url';
import {workspaceShellPrefix} from '../src/core/workspace-shell.js';

const sdkRoot=resolve('node_modules/@earendil-works/pi-coding-agent');
test('Pi recognizes the preflight error as context overflow',async()=>{
 const {isContextOverflow}=await import(pathToFileURL(resolve(sdkRoot,'node_modules/@earendil-works/pi-ai/dist/utils/overflow.js')).href);
 assert.equal(isContextOverflow({stopReason:'error',errorMessage:'Context window exceeded: request input exceeds the context window budget',usage:{input:0,output:0,cacheRead:0,cacheWrite:0}},32768),true);
});
test('checked requests retain output cap; unchecked native requests still clamp',async()=>{
 const {buildBaseOptions}=await import(pathToFileURL(resolve(sdkRoot,'node_modules/@earendil-works/pi-ai/dist/api/simple-options.js')).href);
 const model={contextWindow:4096,maxTokens:1024};
 const context={systemPrompt:'x'.repeat(24000),messages:[]};
 assert.equal(buildBaseOptions(model,context,{maxTokens:1024,urbanPreflightChecked:true}).maxTokens,1024);
 assert.ok(buildBaseOptions(model,context,{maxTokens:1024}).maxTokens<1024);
});
const python=process.env.URBAN_PI_PYTHON??resolve('../.venv-section4/Scripts/python.exe');
test('actual run shell binds both Python commands and propagates piped failure',{skip:!existsSync(python)},async()=>{
 const {createBashTool}=await import(pathToFileURL(resolve(sdkRoot,'dist/core/tools/bash.js')).href);
 const tool=createBashTool(process.cwd(),{commandPrefix:workspaceShellPrefix(python)});
 const result=await tool.execute('env',{command:`python -c "import sys; print(sys.executable)"; python3 -c "import sys; print(sys.executable)"`});
 const text=result.content.map((b:any)=>b.text??'').join('\n');
 const paths=text.trim().split(/\r?\n/);
 assert.equal(paths.length,2);assert.equal(paths[0],paths[1]);assert.equal(resolve(paths[0]).toLowerCase(),resolve(python).toLowerCase());
 await assert.rejects(tool.execute('failure',{command:`python -c "import sys; sys.exit(7)" | cat`}),/code 7/);
});
