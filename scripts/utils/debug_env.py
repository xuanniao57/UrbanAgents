from pathlib import Path

env_path = Path(__file__).parent / ".env"
print(f"Reading: {env_path}")
print(f"Exists: {env_path.exists()}")

if env_path.exists():
    with open(env_path, 'r', encoding='utf-8') as f:
        content = f.read()
        print(f"\nFile content:\n{content}")
        
    print("\n--- Parsing ---")
    with open(env_path, 'r', encoding='utf-8') as f:
        for i, line in enumerate(f, 1):
            line = line.strip()
            print(f"Line {i}: '{line}'")
            if line and not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                key = key.strip()
                value = value.strip()
                print(f"  -> key='{key}', value='{value[:30]}...'" if len(value) > 30 else f"  -> key='{key}', value='{value}'")
