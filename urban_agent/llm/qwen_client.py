"""
Qwen LLM/VLM Client
通义千问大模型客户端
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


class QwenClient:
    """
    Qwen大模型客户端
    支持文本生成和视觉理解
    """
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None
    ):
        # 从环境变量或参数获取配置
        self.api_key = api_key or os.getenv("QWEN_API_KEY")
        self.base_url = base_url or os.getenv("QWEN_API_BASE", "https://dashscope.aliyuncs.com/compatible-mode/v1")
        self.model = model or os.getenv("QWEN_MODEL", "qwen-vl-plus")
        
        if not self.api_key:
            raise ValueError("Qwen API Key未设置")
        
        # 初始化OpenAI客户端
        self.client = AsyncOpenAI(
            api_key=self.api_key,
            base_url=self.base_url
        )
        
        logger.info(f"Qwen客户端初始化完成，模型: {self.model}")
    
    async def generate(
        self,
        prompt: str,
        temperature: float = 0.7,
        max_tokens: int = 2000
    ) -> str:
        """
        文本生成
        
        Args:
            prompt: 提示词
            temperature: 温度参数
            max_tokens: 最大token数
            
        Returns:
            生成的文本
        """
        try:
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
            logger.error(f"Qwen生成失败: {e}")
            return f"Error: {str(e)}"
    
    async def analyze_image(
        self,
        image_path: str,
        prompt: str,
        temperature: float = 0.7
    ) -> str:
        """
        图像分析（VLM）
        
        Args:
            image_path: 图像路径或base64编码
            prompt: 分析提示词
            temperature: 温度参数
            
        Returns:
            分析结果
        """
        try:
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
            logger.error(f"Qwen图像分析失败: {e}")
            return f"Error: {str(e)}"
    
    async def chat(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
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
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens
            )
            
            return response.choices[0].message.content
        except Exception as e:
            logger.error(f"Qwen对话失败: {e}")
            return f"Error: {str(e)}"
