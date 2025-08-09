from __future__ import annotations

import asyncio
from typing import Any, AsyncIterator, Dict, List, Optional
import logging

from .base import ChatMessage, ChatParams, Provider, ProviderError
from ..model_capabilities import filter_parameters, get_model_capabilities

log = logging.getLogger("red.skynetv2.api.openai")


class OpenAIProvider(Provider):
    name = "openai"

    def __init__(self, api_key: str):
        super().__init__()
        if not api_key:
            raise ProviderError("Missing OpenAI API key")
        self.api_key = api_key

    async def list_models(self) -> List[str]:
        """List available OpenAI models."""
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
            model_names = [m.id for m in resp.data]
            
            # Sort models to put GPT models first, then others
            def sort_key(model_name: str) -> tuple[int, str]:
                if model_name.startswith('gpt-'):
                    return (0, model_name)
                elif model_name.startswith('o'):
                    return (1, model_name)
                else:
                    return (2, model_name)
            
            return sorted(model_names, key=sort_key)
        except Exception as e:
            log.error(f"Failed to list OpenAI models: {e}")
            # Return a fallback list of common models if the API fails
            return [
                "gpt-4o", "gpt-4o-mini", "gpt-4", "gpt-3.5-turbo",
                "o1", "o1-mini", "gpt-5", "gpt-5-mini", "gpt-5-nano"
            ]

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
        
        # Build initial parameters
        raw_params: Dict[str, Any] = {
            "temperature": (params.temperature if params else 0.7),
        }
        if params and params.max_tokens:
            raw_params["max_tokens"] = params.max_tokens
        if params and params.top_p is not None:
            raw_params["top_p"] = params.top_p
        if params and params.frequency_penalty is not None:
            raw_params["frequency_penalty"] = params.frequency_penalty
        if params and params.presence_penalty is not None:
            raw_params["presence_penalty"] = params.presence_penalty
        
        # Filter parameters based on model capabilities
        filtered_params, adjustments = filter_parameters(raw_params, model, "openai")
        
        # Log parameter adjustments for user awareness
        if adjustments:
            log.info(f"Model {model} parameter adjustments: {'; '.join(adjustments)}")
        
        # Build final payload
        payload: Dict[str, Any] = {
            "model": model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            **filtered_params
        }

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
