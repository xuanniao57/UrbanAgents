"""
Kimi LLM/VLM Client
Moonshot Kimi大模型客户端
"""

import os
import base64
import logging
from typing import Dict, List, Any, Optional
from pathlib import Path

# 尝试导入openai库
try:
    from openai import AsyncOpenAI
except ImportError:
    raise ImportError("请安装openai库: pip install openai")

logger = logging.getLogger(__name__)


class KimiClient:
    """
    Kimi大模型客户端
    支持kimi-k2.5和kimi-for-coding
    """
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        client_type: str = "standard"  # "standard" 或 "coding"
    ):
        """
        初始化Kimi客户端
        
        Args:
            api_key: API密钥
            base_url: API基础URL
            model: 模型名称
            client_type: 客户端类型 ("standard" 使用kimi-k2.5, "coding" 使用kimi-for-coding)
        """
        self.client_type = client_type
        
        # 根据类型选择配置
        if client_type == "coding":
            self.api_key = api_key or os.getenv("KIMI_CODE_API_KEY")
            self.base_url = base_url or os.getenv("KIMI_CODE_API_BASE", "https://api.kimi.com/coding/")
            self.model = model or os.getenv("KIMI_CODE_MODEL", "kimi-for-coding")
        else:
            self.api_key = api_key or os.getenv("KIMI_API_KEY")
            self.base_url = base_url or os.getenv("KIMI_BASE_URL", "https://api.moonshot.cn/v1")
            self.model = model or os.getenv("KIMI_MODEL", "kimi-k2.5")
        
        if not self.api_key:
            raise ValueError(f"Kimi API Key未设置 (type={client_type})")
        
        # 初始化OpenAI客户端
        self.client = AsyncOpenAI(
            api_key=self.api_key,
            base_url=self.base_url
        )
        
        logger.info(f"Kimi客户端初始化完成，类型: {client_type}, 模型: {self.model}")
    
    async def generate(
        self,
        prompt: str,
        temperature: float = 1.0,  # Kimi k2.5 只支持 temperature=1
        max_tokens: int = 2000
    ) -> str:
        """
        文本生成
        
        Args:
            prompt: 提示词
            temperature: 温度参数 (Kimi k2.5 只支持1)
            max_tokens: 最大token数
            
        Returns:
            生成的文本
        """
        try:
            # Kimi k2.5 只支持 temperature=1
            if self.model == "kimi-k2.5":
                temperature = 1.0
            
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are a helpful assistant specialized in urban analysis and spatial reasoning."},
                    {"role": "user", "content": prompt}
                ],
                temperature=temperature,
                max_tokens=max_tokens
            )
            
            return response.choices[0].message.content
        except Exception as e:
            logger.error(f"Kimi生成失败: {e}")
            return f"Error: {str(e)}"
    
    async def analyze_image(
        self,
        image_path: str,
        prompt: str,
        temperature: float = 1.0  # Kimi k2.5 只支持 temperature=1
    ) -> str:
        """
        图像分析（VLM）
        
        Args:
            image_path: 图像路径或base64编码
            prompt: 分析提示词
            temperature: 温度参数 (Kimi k2.5 只支持1)
            
        Returns:
            分析结果
        """
        try:
            # Kimi k2.5 只支持 temperature=1
            if self.model == "kimi-k2.5":
                temperature = 1.0
            
            # 检查是文件路径还是base64
            if Path(image_path).exists():
                # 读取并编码图像
                with open(image_path, "rb") as f:
                    image_base64 = base64.b64encode(f.read()).decode()
            else:
                # 假设已经是base64
                image_base64 = image_path
            
            # 构建消息
            messages = [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{image_base64}"
                            }
                        }
                    ]
                }
            ]
            
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=temperature,
                max_tokens=2000
            )
            
            return response.choices[0].message.content
        except Exception as e:
            logger.error(f"Kimi图像分析失败: {e}")
            return f"Error: {str(e)}"
    
    async def chat(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 1.0,
        max_tokens: int = 2000
    ) -> str:
        """
        对话模式
        
        Args:
            messages: 消息列表
            temperature: 温度参数
            max_tokens: 最大token数
            
        Returns:
            回复文本
        """
        try:
            if self.model == "kimi-k2.5":
                temperature = 1.0

            response = await self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens
            )
            
            return response.choices[0].message.content
        except Exception as e:
            logger.error(f"Kimi对话失败: {e}")
            return f"Error: {str(e)}"
    
    async def code_generate(
        self,
        prompt: str,
        context: Optional[str] = None,
        temperature: float = 0.3
    ) -> str:
        """
        代码生成（专为coding模型优化）
        
        Args:
            prompt: 代码生成提示词
            context: 上下文代码
            temperature: 温度参数（代码生成通常用较低温度）
            
        Returns:
            生成的代码
        """
        system_prompt = """You are an expert programmer. Generate clean, efficient, and well-documented code.
Follow best practices and include appropriate error handling."""
        
        messages = [{"role": "system", "content": system_prompt}]
        
        if context:
            messages.append({"role": "user", "content": f"Context:\n{context}"})
        
        messages.append({"role": "user", "content": prompt})
        
        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=temperature,
                max_tokens=4000
            )
            
            return response.choices[0].message.content
        except Exception as e:
            logger.error(f"Kimi代码生成失败: {e}")
            return f"Error: {str(e)}"


class MultiLLMClient:
    """
    多LLM客户端管理器
    支持动态切换不同模型
    """
    
    def __init__(self):
        self.clients = {}
        self._init_clients()
    
    def _init_clients(self):
        """初始化所有可用的客户端"""
        # Qwen
        try:
            from .qwen_client import QwenClient
            self.clients["qwen"] = QwenClient()
            logger.info("✅ Qwen客户端初始化成功")
        except Exception as e:
            logger.warning(f"⚠️ Qwen客户端初始化失败: {e}")
        
        # Kimi Standard (kimi-k2.5)
        try:
            self.clients["kimi"] = KimiClient(client_type="standard")
            logger.info("✅ Kimi Standard客户端初始化成功")
        except Exception as e:
            logger.warning(f"⚠️ Kimi Standard客户端初始化失败: {e}")
        
        # Kimi Coding (kimi-for-coding)
        try:
            self.clients["kimi-coding"] = KimiClient(client_type="coding")
            logger.info("✅ Kimi Coding客户端初始化成功")
        except Exception as e:
            logger.warning(f"⚠️ Kimi Coding客户端初始化失败: {e}")
    
    def get_client(self, name: str):
        """获取指定客户端"""
        if name in self.clients:
            return self.clients[name]
        raise ValueError(f"未知的客户端: {name}。可用客户端: {list(self.clients.keys())}")
    
    def list_clients(self) -> List[str]:
        """列出所有可用客户端"""
        return list(self.clients.keys())
