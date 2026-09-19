import test from 'node:test';
import assert from 'node:assert/strict';
import {bashBoundaryError} from '../src/core/workspace-command.js';
test('Python labels followed by escaped newlines are not drive paths',()=>{
 assert.equal(bashBoundaryError("python << 'EOF'\nprint(f'Sample rows:\\n{stays.head()}')\nEOF"),undefined);
 assert.equal(bashBoundaryError('python work/inspect.py'),undefined);
});
test('actual out-of-workspace paths remain rejected',()=>{
 for(const command of ['cd ..','ls /','python C:/private/a.py','python "D:\\private\\a.py"','python ../a.py','pip install unknown']) assert.ok(bashBoundaryError(command),command);
});
test('literal downward navigation is allowed, escapes and dynamic cd are not',()=>{
 for(const c of ['cd data && python inspect.py','cd "work"; python a.py','cd outputs/sub && ls'])assert.equal(bashBoundaryError(c),undefined);
 for(const c of ['cd data && cd ..','cd data/../../private','cd $TARGET','cd /tmp','cd data; python ../x.py'])assert.ok(bashBoundaryError(c),c);
});
