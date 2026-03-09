import os
import json
from degim.engine.degim_engine import DeGIMEngine

def main():
    # Example task
    task = "Design a community micro-regeneration plan for a historical neighborhood in Shanghai, focusing on social interaction and green infrastructure."
    address = "Tianzifang, Shanghai" # REAL LOCATION
    
    engine = DeGIMEngine()
    result = engine.run(task, address=address)
    
    # Save results
    output_dir = "outputs"
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    
    # Save JSON report
    with open(os.path.join(output_dir, "degim_report.json"), "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    
    # Save SVG
    with open(os.path.join(output_dir, "spatial_topology.svg"), "w", encoding="utf-8") as f:
        f.write(result["svg_xml"])
    
    print("\n" + "="*50)
    print("DeGIM RESULTS SUMMARY")
    print(f"Task: {result['task']}")
    print(f"Consensus Degree (CD): {result['metrics']['CD']:.2f}")
    print(f"Coherence Score (CS): {result['metrics']['CS']:.2f}")
    print(f"Paradigm Diversity (PD): {result['metrics']['PD']:.2f}")
    print(f"Cross-Layer Consistency (CLC): {result['metrics']['CLC']:.2f}")
    print("="*50)
    print(f"Shared Narrative: {result['shared_narrative']}")
    print("="*50)
    print(f"Results saved to '{output_dir}/' directory.")

if __name__ == "__main__":
    main()
