import test from 'node:test';
import assert from 'node:assert/strict';
import {executionBudget} from '../src/core/execution-budget.js';
test('execution ceilings retain historical defaults and accept generous experiment ceilings',()=>{
 assert.deepEqual(executionBudget({}),{requestsPerTurn:64,toolCallsPerTurn:32,consecutiveToolErrors:4});
 assert.deepEqual(executionBudget({URBAN_TURN_REQUEST_LIMIT:'512',URBAN_TOOL_CALL_BUDGET:'512',URBAN_TOOL_ERROR_BUDGET:'16'}),{requestsPerTurn:512,toolCallsPerTurn:512,consecutiveToolErrors:16});
 assert.throws(()=>executionBudget({URBAN_TOOL_CALL_BUDGET:'NaN'}));
 assert.throws(()=>executionBudget({URBAN_TURN_REQUEST_LIMIT:'0'}));
});
