import test from 'node:test';
import assert from 'node:assert/strict';
import {classifyTurn} from '../src/core/turn-outcome.js';
test('recovered transport errors do not mark a completed answer scientifically correct or failed',()=>{
 const x={failed:false,settled:true,budgetStop:false,messages:[{stopReason:'error'},{stopReason:'stop'}],requests:[{error:'overflow'},{httpStatus:200,finishReason:'stop'}]};
 assert.deepEqual(classifyTurn(x),{outcome:'completed',recoveredErrors:true,scientificStatus:'not_assessed'});
 for(const patch of [{failed:true},{settled:false},{budgetStop:true},{messages:[{stopReason:'length'}]},{requests:[{httpStatus:403}]}]) assert.equal(classifyTurn({...x,...patch}).outcome,'failed');
});
