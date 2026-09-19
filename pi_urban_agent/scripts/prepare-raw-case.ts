/** Copy retained event-level samples and vector sources, never aggregate. */
import { mkdir, copyFile, readFile, writeFile, stat } from 'node:fs/promises';
import { resolve } from 'node:path';
import { createHash } from 'node:crypto';
const root = process.cwd();
const target = resolve(root, 'raw_case/data');
await mkdir(target, {recursive:true});
const layers = resolve(root, '../experiments/case2_uuid10_multiroute_rerun_20260528_095026/data_canvas/layers');
const events = resolve(root, '../experiments/case2_age_aware_rerun_20260528_005956/partial_outputs');
const names = ['aoi_inner_ring.geojson','cmab_buildings_inner_ring.geojson','osm_points_inner_ring.geojson','osm_roads_inner_ring.geojson','sampled_stays_weekday_2024-09-19.csv','sampled_stays_weekend_2024-09-21.csv'];
const manifest = [];
for (const name of names) {
 const source = resolve(name.endsWith('.csv') ? events : layers, name);
 await copyFile(source, resolve(target,name));
 const sha256 = createHash('sha256').update(await readFile(source)).digest('hex');
 manifest.push({name,source,sha256,bytes:(await stat(source)).size});
}
await writeFile(resolve(root,'raw_case/source_manifest.json'),JSON.stringify(manifest,null,2));
await writeFile(resolve(target,'raw_data_contract.json'),JSON.stringify({
 research_question:'上海内环建成环境与观测活动的关系如何随空间尺度变化？',
 data_level:'Event-level retained samples and vector source features, not grid aggregates. These are existing sampled stays, not the complete original LBS database.',
 population:'Observed device stays in retained event-level samples on 2024-09-19 and 2024-09-21, at most 200000 sampled stays per day; not the resident population or the complete LBS database.',
 time_window:'2024-09-19 and 2024-09-21; at most 200000 sampled stays per day',
 aoi:'aoi_inner_ring.geojson', crs:'Inspect each source CRS; use an appropriate metric projection for areas/distances.',
 analysis_scope:'Propose feasible spatial supports and OLS/GWR comparisons. No prescribed scale list or route count. Obtain human approval before fitting. Build comparable observations from source geometries and events.',
 data_files:names,
 outcome:'Construct an explicit comparable observed-activity measure from sampled stays, not resident population. Explain transformations.',
 covariates:'Use interpretable building, POI and road measures supported by actual attributes. Keep their definitions comparable across scales. Inspect metadata rather than guessing units or fields.',
 sample_handling:'Distinguish absent sampled events from missing values. Describe sample coverage. Do not claim an existing suppression rule has already been applied to newly generated grids.',
 geometry:'Ensure event aggregation and covariate aggregation refer to the same spatial support within AOI.',
 privacy:'Local research only. Do not print device identifiers or expose event rows in reports. Aggregate outputs for reporting.'
},null,2));
console.log(JSON.stringify(manifest.map(({name,bytes})=>({name,bytes})),null,2));
