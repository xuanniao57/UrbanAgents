import os
import json
import time
from degim.engine.degim_engine import DeGIMEngine

def run_batch():
    test_sites = [
        {"name": "Tianzifang, Shanghai", "address": "Tianzifang, Shanghai"},
        {"name": "Marais, Paris", "address": "Place des Vosges, Paris"},
        {"name": "Hengfu, Shanghai", "address": "Wukang Road, Shanghai"}
    ]
    
    task = "Design a community micro-regeneration plan focusing on porous boundaries, social interaction, and green infrastructure."
    
    engine = DeGIMEngine()
    
    output_base_dir = "outputs/batch_validation"
    if not os.path.exists(output_base_dir):
        os.makedirs(output_base_dir)
    
    summary_report = []

    for site in test_sites:
        print(f"\n" + "!"*60)
        print(f"VALIDATING SITE: {site['name']}")
        print("!"*60)
        
        try:
            result = engine.run(task, address=site['address'])
            
            # Save individual results
            site_slug = site['name'].lower().replace(", ", "_").replace(" ", "_")
            site_dir = os.path.join(output_base_dir, site_slug)
            if not os.path.exists(site_dir):
                os.makedirs(site_dir)
            
            # Save SVG
            svg_path = os.path.join(site_dir, "spatial_topology.svg")
            with open(svg_path, "w", encoding="utf-8") as f:
                f.write(result["svg_xml"])
                
            # Save JSON
            json_path = os.path.join(site_dir, "report.json")
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(result, f, indent=2, ensure_ascii=False)
            
            # Extract spatial deliberation for terminal display
            delib = result["spatial_metadata"].get("spatial_deliberation", {})
            print(f"\n[Spatial Deliberation - {site['name']}]")
            print(f"Inspector Critique: {delib.get('inspector_critique', 'N/A')}")
            
            summary_report.append({
                "site": site['name'],
                "metrics": result["metrics"],
                "status": "success",
                "output_dir": site_dir
            })
            
        except Exception as e:
            print(f"Error validating {site['name']}: {e}")
            summary_report.append({
                "site": site['name'],
                "status": "error",
                "error": str(e)
            })
        
        print(f"Finished {site['name']}. Sleeping to avoid rate limits...")
        time.sleep(2)

    # Save summary
    with open(os.path.join(output_base_dir, "batch_summary.json"), "w", encoding="utf-8") as f:
        json.dump(summary_report, f, indent=2, ensure_ascii=False)
    
    print("\n" + "="*50)
    print("BATCH VALIDATION COMPLETED")
    for s in summary_report:
        if s['status'] == 'success':
            print(f"- {s['site']}: CD={s['metrics']['CD']:.2f}, CS={s['metrics']['CS']:.2f}")
    print("="*50)

if __name__ == "__main__":
    run_batch()
