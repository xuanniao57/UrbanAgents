import test from 'node:test';
import assert from 'node:assert/strict';
import { evidenceDelivery, adjudicatedRoutes, contextExecution, makeContextJudgeBundle } from '../src/core/separated-context-evaluation.js';

const state:any={nodes:{alpha:{parameters:{model:'OLS',analysis_support_m:600},artifactIds:['a'],status:'complete',claimBoundary:'Association'},beta:{parameters:{model:'GWR'},artifactIds:[],status:'deferred'}},artifacts:{a:{metrics:{oof_r2:0.12345}}},humanDecisions:[{decisionId:'d1',branchIds:['alpha'],decision:'select_main'},{decisionId:'d2',branchIds:['beta'],decision:'defer'}],phase:'human',activeBranchId:'beta',pendingQuestions:['Retain beta?']};
test('delivery is separate from understanding and does not require four fixed routes',()=>{
  assert.equal(adjudicatedRoutes(state).length,2);
  const delivery=evidenceDelivery(state,[{messages:[{role:'tool',content:JSON.stringify({records:[{nodeId:'alpha',metrics:{oof_r2:0.12345}}]})}]}]);
  assert.equal(delivery[0].r2Delivered,true);
  assert.equal(delivery[1].r2Delivered,null);
  const execution=contextExecution(state,state,state,'Retain beta as sensitivity evidence.','beta');
  assert.equal(execution.patchApplied,false); assert.equal(execution.identityProvenance,null);
  const b=makeContextJudgeBundle({recoveryPrompt:'Recover',humanPrompt:'Retain beta',recoveryAnswer:'I do not know.',humanAnswer:'Done',expectedRoutes:adjudicatedRoutes(state),execution});
  assert.ok(!('taskQualityScore' in b));
  assert.ok(!JSON.stringify(b).includes('r2Delivered'));
  assert.equal(b.execution.patchApplied,false);
});
test('matching a metric on the wrong route is not evidence delivery',()=>{
  const delivery=evidenceDelivery(state,[{messages:[{role:'assistant',content:'alpha 0.12345'},{role:'tool',content:JSON.stringify({records:[{nodeId:'beta',metrics:{oof_r2:0.12345}}]})}]}]);
  assert.equal(delivery[0].r2Delivered,false);
});
test('a role-only index cannot receive metric credit; read-only phase changes fail',()=>{
  const delivery=evidenceDelivery(state,[{messages:[{role:'tool',content:JSON.stringify({records:[{nodeId:'alpha',humanRole:'select_main'}]})}]}]);
  assert.equal(delivery[0].indexDelivered,true); assert.equal(delivery[0].r2Delivered,false);
  assert.equal(contextExecution(state,{...state,phase:'plan'},state,'','beta').recoveryReadOnly,false);
});
