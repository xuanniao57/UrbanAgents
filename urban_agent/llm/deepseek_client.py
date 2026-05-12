"""DeepSeek LLM client with v4 pro thinking-mode support."""

import os
import logging
import json
from typing import Any, Callable, Dict, List, Optional

# 尝试导入openai库
try:
    from openai import AsyncOpenAI
except ImportError:
    raise ImportError("请安装openai库: pip install openai")

logger = logging.getLogger(__name__)


class DeepSeekClient:
    """OpenAI-compatible DeepSeek client.

    Defaults are tuned for deepseek-v4-pro thinking mode while preserving the
    legacy deepseek-chat/deepseek-reasoner environment variables.
    """
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        client_type: str = "chat",  # kept for backward compatibility
        thinking: Optional[str] = None,
        reasoning_effort: Optional[str] = None,
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
        self.api_key = api_key or os.getenv("DEEPSEEK_API_KEY") or os.getenv("Deepseek_API_KEY")
        self.base_url = (
            base_url
            or os.getenv("DEEPSEEK_BASE_URL")
            or os.getenv("Deepseek_API_BASE")
            or "https://api.deepseek.com"
        )

        legacy_reasoner = os.getenv("DEEPSEEK_REASONER_MODEL") or os.getenv("deepseek_resoner_MODEL")
        self.model = (
            model
            or os.getenv("LLM_MODEL")
            or os.getenv("DEEPSEEK_MODEL")
            or os.getenv("Deepseek_MODEL")
            or (legacy_reasoner if client_type == "reasoner" else None)
            or "deepseek-v4-pro"
        )
        self.thinking = thinking or os.getenv("DEEPSEEK_THINKING", "enabled")
        self.reasoning_effort = reasoning_effort or os.getenv("DEEPSEEK_REASONING_EFFORT", "high")
        self.max_tool_rounds = int(os.getenv("DEEPSEEK_TOOL_MAX_ROUNDS", "8"))
        self.last_reasoning_content: Optional[str] = None
        
        if not self.api_key:
            raise ValueError(f"DeepSeek API Key未设置 (type={client_type})")
        
        # 初始化OpenAI客户端
        self.client = AsyncOpenAI(
            api_key=self.api_key,
            base_url=self.base_url
        )
        
        logger.info("DeepSeek client initialized, type=%s, model=%s, thinking=%s", client_type, self.model, self.thinking)

    def _thinking_enabled(self) -> bool:
        return str(self.thinking).strip().lower() in {"1", "true", "yes", "enabled", "on"}

    def _build_completion_kwargs(
        self,
        *,
        messages: List[Dict[str, Any]],
        temperature: float = 0.7,
        max_tokens: int = 2000,
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        kwargs: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "max_tokens": max_tokens,
        }
        if tools:
            kwargs["tools"] = tools
        if self._thinking_enabled():
            kwargs["reasoning_effort"] = self.reasoning_effort
            kwargs["extra_body"] = {"thinking": {"type": "enabled"}}
        else:
            kwargs["temperature"] = temperature
            kwargs["extra_body"] = {"thinking": {"type": "disabled"}}
        return kwargs

    @staticmethod
    def _message_to_dict(message: Any) -> Dict[str, Any]:
        if hasattr(message, "model_dump"):
            return message.model_dump(exclude_none=True)
        payload = {
            "role": getattr(message, "role", "assistant"),
            "content": getattr(message, "content", None),
            "reasoning_content": getattr(message, "reasoning_content", None),
            "tool_calls": getattr(message, "tool_calls", None),
        }
        return {key: value for key, value in payload.items() if value is not None}

    @staticmethod
    def _tool_call_to_dict(tool_call: Any) -> Dict[str, Any]:
        if hasattr(tool_call, "model_dump"):
            return tool_call.model_dump(exclude_none=True)
        function = getattr(tool_call, "function", None)
        return {
            "id": getattr(tool_call, "id", ""),
            "type": getattr(tool_call, "type", "function"),
            "function": {
                "name": getattr(function, "name", ""),
                "arguments": getattr(function, "arguments", "{}"),
            },
        }
    
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
                **self._build_completion_kwargs(
                    messages=[
                    {"role": "system", "content": "You are a helpful assistant specialized in urban analysis and spatial reasoning."},
                    {"role": "user", "content": prompt}
                    ],
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
            )
            message = response.choices[0].message
            self.last_reasoning_content = getattr(message, "reasoning_content", None)
            return message.content or ""
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
                **self._build_completion_kwargs(
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
            )
            message = response.choices[0].message
            self.last_reasoning_content = getattr(message, "reasoning_content", None)
            return message.content or ""
        except Exception as e:
            logger.error(f"DeepSeek对话失败: {e}")
            return f"Error: {str(e)}"

    async def chat_with_tools(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        tool_handlers: Dict[str, Callable[..., str]],
        temperature: float = 0.7,
        max_tokens: int = 2000,
        max_rounds: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Run a DeepSeek thinking-mode tool loop.

        Assistant messages are appended with reasoning_content intact. DeepSeek
        requires this whenever a thinking-mode turn includes tool calls.
        """
        transcript: List[Dict[str, Any]] = [dict(message) for message in messages]
        rounds = max_rounds or self.max_tool_rounds
        final_content = ""

        for _ in range(rounds):
            response = await self.client.chat.completions.create(
                **self._build_completion_kwargs(
                    messages=transcript,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    tools=tools,
                )
            )
            assistant_message = response.choices[0].message
            assistant_payload = self._message_to_dict(assistant_message)
            transcript.append(assistant_payload)
            self.last_reasoning_content = assistant_payload.get("reasoning_content")
            final_content = assistant_payload.get("content") or ""

            tool_calls = assistant_payload.get("tool_calls") or []
            if not tool_calls:
                return {
                    "content": final_content,
                    "messages": transcript,
                    "reasoning_content": self.last_reasoning_content,
                    "tool_rounds_exhausted": False,
                }

            for raw_tool_call in tool_calls:
                tool_call = raw_tool_call if isinstance(raw_tool_call, dict) else self._tool_call_to_dict(raw_tool_call)
                function = tool_call.get("function", {})
                tool_name = function.get("name")
                arguments_text = function.get("arguments") or "{}"
                try:
                    arguments = json.loads(arguments_text)
                except json.JSONDecodeError:
                    arguments = {"_raw_arguments": arguments_text}
                handler = tool_handlers.get(tool_name)
                if handler is None:
                    tool_result = json.dumps({"success": False, "error": f"No handler for tool '{tool_name}'"})
                else:
                    tool_result = handler(**arguments)
                transcript.append({
                    "role": "tool",
                    "tool_call_id": tool_call.get("id", ""),
                    "content": str(tool_result),
                })

        return {
            "content": final_content,
            "messages": transcript,
            "reasoning_content": self.last_reasoning_content,
            "tool_rounds_exhausted": True,
        }
