import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, readFile, writeFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { contractPopulation } from '../src/core/contract-population.js';
import extension from '../src/pi-extension.js';
import { ResearchStore } from '../src/core/research-store.js';

test('sample scope: canonical, legacy, explicit proposal, and actionable missing-data error', () => {
  assert.equal(contractPopulation({population:'observed stays'},'invented'), 'observed stays');
  assert.equal(contractPopulation({sampling:'sample',eligibility:'eligible'}), 'sample eligible');
  assert.equal(contractPopulation({},' observed device sample '), 'observed device sample');
  assert.throws(()=>contractPopulation({data_level:'vector files'},' '), /supply population to urban_initialize/);
});

test('real raw contract initializes through public tool; old raw metadata has a legal repair path', async () => {
  const dir = await mkdtemp(join(tmpdir(),'urban-raw-init-'));
  const keys=['URBAN_PI_RUN_DIR','URBAN_PI_WORKSPACE_ROOT'] as const;
  const old=Object.fromEntries(keys.map(k=>[k,process.env[k]]));
  try {
    const source={research_question:'How do observed urban relationships vary across spatial supports?',aoi:'synthetic-study-boundary',time_window:'synthetic observation window',outcome:'observed activity',analysis_scope:'Compare OLS and GWR with human review.',population:'Observed device stays in a sampled dataset, not the resident population.',data_level:'Event samples and vector source features; no predefined analytical grids.'};
    for(const legacyRaw of [false,true]) {
      const contract:Record<string,unknown>={...source};
      if(legacyRaw) delete contract.population;
      await writeFile(join(dir,'data_contract.json'),JSON.stringify(contract));
      process.env.URBAN_PI_WORKSPACE_ROOT=dir;
      process.env.URBAN_PI_RUN_DIR=join(dir,legacyRaw?'legacy':'canonical');
      const registered:any[]=[];
      extension({on(){},registerTool(t:any){registered.push(t);},appendEntry(){},setActiveTools(){},setSessionName(){}} as any);
      const tool=registered.find(t=>t.name==='urban_initialize');
      assert.ok(tool.parameters.properties.population);
      assert.equal(tool.parameters.additionalProperties,false);
      const args={research_question:source.research_question,intended_claim:source.analysis_scope,prohibited_claims:['resident-population inference'],candidate_supports:['500 m','1000 m'],covariates:['building coverage','mean height','POI density','road density']};
      if(legacyRaw) await assert.rejects(tool.execute('',args),/supply population to urban_initialize/);
      await tool.execute('',legacyRaw?{...args,population:source.population}:args);
      const state=await new ResearchStore(process.env.URBAN_PI_RUN_DIR!).load();
      assert.equal(state.phase,'plan');
      assert.match(JSON.stringify(state),/Observed device stays/);
      assert.ok(!JSON.stringify(state).includes('>=10'));
      const family=registered.find(t=>t.name==='urban_commit_route_family');
      await family.execute('',{title:'Scale comparison',decision_dimension:'spatial support',candidates:[{label:'OLS',analytical_role:'global baseline',analysis_scope:'Weekday only; stay count per area; four common predictors'},{label:'GWR',analytical_role:'deferred local comparison',analysis_scope:'Not authorized to fit'}],active_candidate:'OLS',stop_condition:'Save and inspect results'});
      const after=await new ResearchStore(process.env.URBAN_PI_RUN_DIR!).load();
      assert.equal(after.contract.population,source.population);
      assert.ok(Object.values(after.nodes).some(n=>n.parameters.analysis_scope==='Weekday only; stay count per area; four common predictors'));
      const checkpoint=registered.find(t=>t.name==='urban_human_decision');
      assert.equal(checkpoint.parameters.properties.actor,undefined);
      const beforeCheckpoint=JSON.stringify(after);
      const receipt=await checkpoint.execute('',{rationale:'The human asked to run OLS, not approve its findings.'});
      assert.ok(!receipt.isError);
      assert.match(JSON.stringify(receipt),/no_pending_evidence_role_decision/);
      assert.equal(JSON.stringify(await new ResearchStore(process.env.URBAN_PI_RUN_DIR!).load()),beforeCheckpoint,'Execution instruction must not create a claim approval or mutate research state');
    }
  } finally {
    for(const key of keys) {if(old[key]===undefined) delete process.env[key];else process.env[key]=old[key];}
    await rm(dir,{recursive:true,force:true});
  }
});
