"""
运行对比测试 - 手动加载环境变量
"""

import os
import sys
from pathlib import Path

# 手动加载.env文件
env_path = Path(__file__).parent / ".env"
if env_path.exists():
    with open(env_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                key = key.strip()
                value = value.strip()
                if key and value:
                    os.environ[key] = value
                    print(f"Loaded: {key}={value[:20]}..." if len(value) > 20 else f"Loaded: {key}={value}")

print(f"\nKIMI_API_KEY: {os.getenv('KIMI_API_KEY')[:20]}..." if os.getenv('KIMI_API_KEY') else "KIMI_API_KEY: Not set")

# 现在运行主测试
import asyncio
from test_comprehensive_comparison import run_all_tests

if __name__ == "__main__":
    asyncio.run(run_all_tests())
