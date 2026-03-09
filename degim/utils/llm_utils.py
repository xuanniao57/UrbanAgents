import os
import json
import requests
from dotenv import load_dotenv

load_dotenv()

class LLMClient:
    def __init__(self):
        self.provider = os.getenv("LLM_PROVIDER", "openai").lower()
        if self.provider == "qwen":
            self.api_key = os.getenv("QWEN_API_KEY") or os.getenv("DASHSCOPE_API_KEY")
            self.api_base = os.getenv("QWEN_API_BASE", "https://dashscope.aliyuncs.com/compatible-mode/v1")
            self.model = os.getenv("QWEN_MODEL", "qwen-vl-plus")
        else:
            self.api_key = os.getenv("OPENAI_API_KEY")
            self.api_base = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
            self.model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

    def chat(self, prompt, system_prompt="You are a helpful assistant."):
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        data = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt}
            ],
            "response_format": {"type": "json_object"} if "json" in prompt.lower() else None
        }
        
        try:
            response = requests.post(f"{self.api_base}/chat/completions", headers=headers, json=data)
            response.raise_for_status()
            result = response.json()
            return result["choices"][0]["message"]["content"]
        except Exception as e:
            print(f"Error calling LLM: {e}")
            return None

client = LLMClient()

def get_llm_response(prompt, system_prompt="You are a helpful assistant."):
    return client.chat(prompt, system_prompt)
