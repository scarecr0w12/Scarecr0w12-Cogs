from __future__ import annotations

import asyncio
from typing import Any, AsyncIterator, Dict, List, Optional

from .base import ChatMessage, ChatParams, Provider, ProviderError


class OpenAIProvider(Provider):
    name = "openai"

    def __init__(self, api_key: str):
        super().__init__()
        if not api_key:
            raise ProviderError("Missing OpenAI API key")
        self.api_key = api_key

    async def list_models(self) -> List[str]:
        # Lazy import to avoid hard dependency at load time
        try:
            from openai import OpenAI  # type: ignore
        except Exception as e:
            raise ProviderError(f"OpenAI SDK not available: {e}")
        client = OpenAI(api_key=self.api_key)
        loop = asyncio.get_running_loop()

        def _call_models():
            return client.models.list()

        try:
            resp = await loop.run_in_executor(None, _call_models)
            return [m.id for m in resp.data]
        except Exception as e:
            raise ProviderError(f"Failed to list models: {e}")

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

        client = OpenAI(api_key=self.api_key)
        payload: Dict[str, Any] = {
            "model": model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "temperature": (params.temperature if params else 0.7),
        }
        if params and params.max_tokens:
            payload["max_tokens"] = params.max_tokens
        if params and params.top_p is not None:
            payload["top_p"] = params.top_p

        loop = asyncio.get_running_loop()

        if stream:
            def _call_stream():
                return client.chat.completions.create(stream=True, **payload)

            try:
                stream_resp = await loop.run_in_executor(None, _call_stream)
                # Iterate stream on a worker thread to avoid blocking loop
                def _collect_stream():
                    for chunk in stream_resp:
                        try:
                            choice = chunk.choices[0]
                            delta = getattr(choice, "delta", None)
                            if delta and getattr(delta, "content", None):
                                yield delta.content
                        except Exception:
                            continue
                # Bridge generator to async iterator
                for part in _collect_stream():
                    yield part
                # Note: token usage may not be provided in streaming; leave last_usage as-is
                return
            except Exception as e:
                raise ProviderError(f"OpenAI chat stream error: {e}")

        # Non-streaming one-shot
        def _call_once():
            resp = client.chat.completions.create(**payload)
            return resp

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
            raise ProviderError(f"OpenAI chat error: {e}")
