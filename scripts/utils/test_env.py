import os
from dotenv import load_dotenv

load_dotenv()

print("Environment variables:")
print(f"KIMI_API_KEY: {os.getenv('KIMI_API_KEY')[:20]}..." if os.getenv('KIMI_API_KEY') else "Not set")
print(f"QWEN_API_KEY: {os.getenv('QWEN_API_KEY')[:20]}..." if os.getenv('QWEN_API_KEY') else "Not set")
