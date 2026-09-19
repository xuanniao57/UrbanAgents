import {readFile,writeFile,readdir} from 'node:fs/promises';
import {join} from 'node:path';
import {spawnSync} from 'node:child_process';
export async function prepareSharedEnvironment(cwd:string,python:string){
 const probe=spawnSync(python,['-c',`import json,sys,importlib.metadata as m
names=['numpy','pandas','scipy','scikit-learn','geopandas','shapely','pyproj','pyogrio','statsmodels','mgwr','matplotlib','fiona','rtree']
v={}
for n in names:
 try: v[n]=m.version(n)
 except m.PackageNotFoundError: v[n]='not installed'
print(json.dumps({'python':sys.version.split()[0],'packages':v}))`],{encoding:'utf8',windowsHide:true});
 if(probe.status!==0)throw Error('Environment inventory failed: '+probe.stderr);
 await writeFile(join(cwd,'ENVIRONMENT.md'),'# Verified environment\n\n'+probe.stdout+'\nUse python from the workspace root. Do not install packages during a run. GeoPandas can use pyogrio; fiona is not required.\n');
 const entries:string[]=[];
 for(const name of await readdir(join(cwd,'data'))){
  if(name.endsWith('.geojson')){
   const d=JSON.parse(await readFile(join(cwd,'data',name),'utf8'));
   entries.push(`## data/${name}\nFormat: ${d.type}; features: ${d.features.length}; CRS metadata: ${JSON.stringify(d.crs)}.\nGeometry types: ${[...new Set(d.features.map((f:any)=>f.geometry?.type))].join(', ')}.\nAttribute keys: ${Object.keys(d.features[0]?.properties??{}).join(', ')}.\nFeatureCollection has a features array; each feature has geometry and properties. Read with geopandas.read_file rather than assuming top-level attributes.\n`);
  }else if(name.endsWith('.csv')){
   const header=(await readFile(join(cwd,'data',name),'utf8')).split(/\r?\n/,1)[0];
   entries.push(`## data/${name}\nCSV fields: ${header}.\nInspect types and missingness without displaying device IDs or event rows. lon/lat are coordinate fields; verify their CRS against source documentation. grid_id is a legacy identifier, not proof of the current analysis resolution. Rows are sampled stays, not necessarily unique people.\n`);
  }
 }
 await writeFile(join(cwd,'DATA_GUIDE.md'),'# Source structure (automatically inspected, no aggregation)\n\n'+entries.join('\n')+'\nDo not infer undocumented category meanings, units or missing-value sentinels from column names. Inspect distributions and ask when uncertain. Building attributes Height/Function/Age/Quality are source attributes, not automatically valid covariates; inspect them before use. Spatial lengths/areas require a suitable metric CRS.\n');
 await writeFile(join(cwd,'GIS_REFERENCE.md'),`# Optional API reference — not an analysis recipe

Read only the operation you need. Paths below are placeholders. Choose scientific definitions yourself.

- Read vectors: gdf = geopandas.read_file('data/file.geojson', engine='pyogrio'). Inspect gdf.crs, gdf.columns, gdf.geom_type, gdf.total_bounds.
- Reproject: projected = gdf.to_crs(chosen_metric_crs). set_crs labels coordinates; it does not transform them. A Shapely Polygon is geometry only and has no GeoDataFrame-style CRS or transform method.
- CSV points: geopandas.GeoDataFrame(df, geometry=geopandas.points_from_xy(df.lon, df.lat), crs=verified_source_crs). Then to_crs as required.
- Geometry measures: projected.geometry.area and projected.geometry.length; no totalLength method. Sum only when the intended measure calls for it.
- Spatial join: geopandas.sjoin(left_gdf, right_gdf, how='left', predicate='within'). Both arguments must be GeoDataFrames in matching CRS. Choose predicates based on boundary semantics; within and intersects are not interchangeable. A join does not clip lengths or areas.
- Geometry intersection: geopandas.overlay(left_gdf, right_gdf, how='intersection') produces intersected geometry. Inspect empty/invalid geometries and boundary cases.
- Tables: inspect df.columns and dtypes before selecting fields. Plain pandas DataFrames do not have a CRS or spatial-join method.
- Paths: run python work/script.py from the root; inside it use data/file and outputs/file. No cd work required.

These operations do not determine grids, predictors, model specification, bandwidth or interpretation. Verify saved results yourself.
`);
}
