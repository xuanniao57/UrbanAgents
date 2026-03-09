from pathlib import Path

env_path = Path(__file__).parent / ".env"
print(f"Reading: {env_path}")

# 用二进制模式读取
with open(env_path, 'rb') as f:
    content = f.read()
    print(f"Total bytes: {len(content)}")
    print(f"Content:\n{content.decode('utf-8')}")
