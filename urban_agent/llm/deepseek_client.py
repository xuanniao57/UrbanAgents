"""
DeepSeek LLM Client
DeepSeek大模型客户端 (支持chat和reasoner模型)
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


class DeepSeekClient:
    """
    DeepSeek大模型客户端
    支持deepseek-chat和deepseek-reasoner
    """
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        client_type: str = "chat"  # "chat" 或 "reasoner"
    ):
        """
        初始化DeepSeek客户端
        
        Args:
            api_key: API密钥
            base_url: API基础URL
            model: 模型名称
            client_type: 客户端类型 ("chat" 使用deepseek-chat, "reasoner" 使用deepseek-reasoner)
        """
        self.client_type = client_type
        
        # 根据类型选择配置
        if client_type == "reasoner":
            self.api_key = api_key or os.getenv("Deepseek_API_KEY") or os.getenv("DEEPSEEK_API_KEY")
            self.base_url = base_url or os.getenv("Deepseek_API_BASE", "https://api.deepseek.com")
            self.model = model or os.getenv("DEEPSEEK_REASONER_MODEL") or os.getenv("deepseek_resoner_MODEL", "deepseek-reasoner")
        else:
            self.api_key = api_key or os.getenv("Deepseek_API_KEY") or os.getenv("DEEPSEEK_API_KEY")
            self.base_url = base_url or os.getenv("Deepseek_API_BASE", "https://api.deepseek.com")
            self.model = model or os.getenv("Deepseek_MODEL", "deepseek-chat")
        
        if not self.api_key:
            raise ValueError(f"DeepSeek API Key未设置 (type={client_type})")
        
        # 初始化OpenAI客户端
        self.client = AsyncOpenAI(
            api_key=self.api_key,
            base_url=self.base_url
        )
        
        logger.info(f"DeepSeek客户端初始化完成，类型: {client_type}, 模型: {self.model}")
    
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
            logger.error(f"DeepSeek生成失败: {e}")
            return f"Error: {str(e)}"
    
    async def analyze_image(
        self,
        image_path: str,
        prompt: str,
        temperature: float = 0.7,
        max_tokens: int = 2000
    ) -> str:
        """
        图像分析 (DeepSeek目前不支持直接图像输入，使用文本描述方式)
        
        Args:
            image_path: 图像路径
            prompt: 分析提示词
            temperature: 温度参数
            max_tokens: 最大token数
            
        Returns:
            分析结果
        """
        # DeepSeek不支持视觉，返回提示信息
        logger.warning("DeepSeek不支持直接图像分析，使用文本模式")
        
        # 构建一个模拟的图像分析提示
        enhanced_prompt = f"[图像分析任务] {prompt}\n\n注意：这是一个图像分析任务，但当前模型不支持直接图像输入。请基于以下上下文回答：图像路径为 {image_path}"
        
        return await self.generate(enhanced_prompt, temperature, max_tokens)
    
    async def chat(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 2000
    ) -> str:
        """
        多轮对话
        
        Args:
            messages: 消息列表
            temperature: 温度参数
            max_tokens: 最大token数
            
        Returns:
            回复内容
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
            logger.error(f"DeepSeek对话失败: {e}")
            return f"Error: {str(e)}"
