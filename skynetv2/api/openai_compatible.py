from __future__ import annotations

import asyncio
from typing import Any, AsyncIterator, Dict, List, Optional

from .base import ChatMessage, ChatParams, Provider, ProviderError


class OpenAICompatibleProvider(Provider):
    """Generic provider for OpenAI-compatible endpoints (Ollama, LocalAI, LM Studio, etc.)"""
    name = "openai_compatible"

    def __init__(self, api_key: str, base_url: str, name: str = "openai_compatible"):
        super().__init__()
        self.api_key = api_key or "dummy"  # Some servers don't require keys
        self.base_url = base_url.rstrip('/')
        self.name = name

    async def list_models(self) -> List[str]:
        try:
            from openai import OpenAI  # type: ignore
        except Exception as e:
            raise ProviderError(f"OpenAI SDK not available: {e}")
        
        client = OpenAI(api_key=self.api_key, base_url=self.base_url)
        loop = asyncio.get_running_loop()

        def _call_models():
            return client.models.list()

        try:
            resp = await loop.run_in_executor(None, _call_models)
            return [m.id for m in resp.data]
        except Exception as e:
            raise ProviderError(f"Failed to list models from {self.base_url}: {e}")

    async def chat(
        self,
        *,
        model: str,
        messages: List[ChatMessage],
        params: Optional[ChatParams] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
        stream: bool = True,
    ) -> AsyncIterator[str]:
        try:
            from openai import OpenAI  # type: ignore
        except Exception as e:
            raise ProviderError(f"OpenAI SDK not available: {e}")

        client = OpenAI(api_key=self.api_key, base_url=self.base_url)
        payload: Dict[str, Any] = {
            "model": model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "temperature": (params.temperature if params else 0.7),
        }
        if params and params.max_tokens:
            payload["max_tokens"] = params.max_tokens
        if params and params.top_p is not None:
            payload["top_p"] = params.top_p

        # Add tools if supported
        if tools:
            payload["tools"] = tools

        loop = asyncio.get_running_loop()

        if stream:
            def _call_stream():
                return client.chat.completions.create(stream=True, **payload)

            try:
                stream_resp = await loop.run_in_executor(None, _call_stream)
                
                def _collect_stream():
                    for chunk in stream_resp:
                        try:
                            choice = chunk.choices[0]
                            delta = getattr(choice, "delta", None)
                            if delta and getattr(delta, "content", None):
                                yield delta.content
                        except Exception:
                            continue
                
                for part in _collect_stream():
                    yield part
                return
            except Exception as e:
                raise ProviderError(f"OpenAI-compatible chat stream error from {self.base_url}: {e}")

        # Non-streaming
        def _call_once():
            return client.chat.completions.create(**payload)

        try:
            resp = await loop.run_in_executor(None, _call_once)
            usage = getattr(resp, "usage", None)
            if usage:
                prompt = getattr(usage, "prompt_tokens", 0)
                completion = getattr(usage, "completion_tokens", 0)
                total = getattr(usage, "total_tokens", None)
                self._set_last_usage(prompt=prompt, completion=completion, total=total)
            
            text = resp.choices[0].message.content or ""
            if text:
                yield text
        except Exception as e:
            raise ProviderError(f"OpenAI-compatible chat error from {self.base_url}: {e}")
