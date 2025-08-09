from __future__ import annotations

import asyncio
from typing import Any, AsyncIterator, Dict, List, Optional

from .base import ChatMessage, ChatParams, Provider, ProviderError


class AnthropicProvider(Provider):
    """Anthropic Claude provider"""
    name = "anthropic"

    def __init__(self, api_key: str):
        super().__init__()
        if not api_key:
            raise ProviderError("Missing Anthropic API key")
        self.api_key = api_key

    async def list_models(self) -> List[str]:
        # Anthropic models are known, no API endpoint for listing
        return [
            "claude-3-5-sonnet-20241022",
            "claude-3-5-haiku-20241022", 
            "claude-3-opus-20240229",
            "claude-3-sonnet-20240229",
            "claude-3-haiku-20240307"
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
            import anthropic
        except Exception as e:
            raise ProviderError(f"Anthropic SDK not available: {e}")

        client = anthropic.Anthropic(api_key=self.api_key)
        
        # Convert messages format
        anthropic_messages = []
        for msg in messages:
            anthropic_messages.append({"role": msg.role, "content": msg.content})

        payload = {
            "model": model,
            "messages": anthropic_messages,
            "max_tokens": params.max_tokens if params else 512,
            "temperature": params.temperature if params else 0.7,
        }

        if tools:
            payload["tools"] = tools

        loop = asyncio.get_running_loop()

        if stream:
            def _call_stream():
                return client.messages.create(stream=True, **payload)

            try:
                stream_resp = await loop.run_in_executor(None, _call_stream)
                
                def _collect_stream():
                    for event in stream_resp:
                        if event.type == "content_block_delta":
                            if hasattr(event.delta, "text"):
                                yield event.delta.text
                
                for part in _collect_stream():
                    yield part
                return
            except Exception as e:
                raise ProviderError(f"Anthropic chat stream error: {e}")

        # Non-streaming
        def _call_once():
            return client.messages.create(**payload)

        try:
            resp = await loop.run_in_executor(None, _call_once)
            usage = getattr(resp, "usage", None)
            if usage:
                prompt = getattr(usage, "input_tokens", 0)
                completion = getattr(usage, "output_tokens", 0)
                self._set_last_usage(prompt=prompt, completion=completion)
            
            text = resp.content[0].text if resp.content else ""
            if text:
                yield text
        except Exception as e:
            raise ProviderError(f"Anthropic chat error: {e}")


class GroqProvider(Provider):
    """Groq fast inference provider"""
    name = "groq"

    def __init__(self, api_key: str):
        super().__init__()
        if not api_key:
            raise ProviderError("Missing Groq API key")
        self.api_key = api_key

    async def list_models(self) -> List[str]:
        try:
            from groq import Groq
        except Exception as e:
            raise ProviderError(f"Groq SDK not available: {e}")
        
        client = Groq(api_key=self.api_key)
        loop = asyncio.get_running_loop()

        def _call_models():
            return client.models.list()

        try:
            resp = await loop.run_in_executor(None, _call_models)
            return [m.id for m in resp.data]
        except Exception as e:
            raise ProviderError(f"Failed to list Groq models: {e}")

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
            from groq import Groq
        except Exception as e:
            raise ProviderError(f"Groq SDK not available: {e}")

        client = Groq(api_key=self.api_key)
        payload = {
            "model": model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "temperature": params.temperature if params else 0.7,
            "max_tokens": params.max_tokens if params else 512,
        }

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
                raise ProviderError(f"Groq chat stream error: {e}")

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
            raise ProviderError(f"Groq chat error: {e}")


class GeminiProvider(Provider):
    """Google Gemini provider"""
    name = "gemini"

    def __init__(self, api_key: str):
        super().__init__()
        if not api_key:
            raise ProviderError("Missing Google Gemini API key")
        self.api_key = api_key

    async def list_models(self) -> List[str]:
        try:
            import google.generativeai as genai
        except Exception as e:
            raise ProviderError(f"Google Generative AI SDK not available: {e}")
        
        genai.configure(api_key=self.api_key)
        loop = asyncio.get_running_loop()

        def _list_models():
            models = genai.list_models()
            return [m.name.replace('models/', '') for m in models if 'generateContent' in m.supported_generation_methods]

        try:
            return await loop.run_in_executor(None, _list_models)
        except Exception as e:
            # Return known models if API call fails
            return [
                "gemini-1.5-pro",
                "gemini-1.5-flash",
                "gemini-1.0-pro",
                "gemini-1.0-pro-vision"
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
            import google.generativeai as genai
        except Exception as e:
            raise ProviderError(f"Google Generative AI SDK not available: {e}")

        genai.configure(api_key=self.api_key)
        
        # Initialize model
        generation_config = {
            "temperature": params.temperature if params else 0.7,
            "max_output_tokens": params.max_tokens if params else 512,
        }
        
        gemini_model = genai.GenerativeModel(model, generation_config=generation_config)
        
        # Convert messages to Gemini format
        # Gemini expects alternating user/model messages
        gemini_messages = []
        system_prompt = ""
        
        for msg in messages:
            if msg.role == "system":
                system_prompt = msg.content
            elif msg.role == "user":
                gemini_messages.append({"role": "user", "parts": [{"text": msg.content}]})
            elif msg.role == "assistant":
                gemini_messages.append({"role": "model", "parts": [{"text": msg.content}]})
        
        # If we have a system prompt, prepend it to the first user message
        if system_prompt and gemini_messages:
            first_user = next((m for m in gemini_messages if m["role"] == "user"), None)
            if first_user:
                first_user["parts"][0]["text"] = f"{system_prompt}\n\n{first_user['parts'][0]['text']}"
        
        # Build prompt text for single generation
        prompt_text = ""
        if system_prompt:
            prompt_text += f"{system_prompt}\n\n"
        
        # Get the last user message as the prompt
        user_messages = [m for m in messages if m.role == "user"]
        if user_messages:
            prompt_text += user_messages[-1].content

        loop = asyncio.get_running_loop()

        if stream:
            def _call_stream():
                response = gemini_model.generate_content(prompt_text, stream=True)
                for chunk in response:
                    if chunk.text:
                        yield chunk.text

            try:
                def _collect_stream():
                    return list(_call_stream())
                
                chunks = await loop.run_in_executor(None, _collect_stream)
                for chunk in chunks:
                    yield chunk
                return
            except Exception as e:
                raise ProviderError(f"Gemini chat stream error: {e}")

        # Non-streaming
        def _call_once():
            return gemini_model.generate_content(prompt_text)

        try:
            response = await loop.run_in_executor(None, _call_once)
            
            # Extract usage info if available
            try:
                if hasattr(response, 'usage_metadata'):
                    usage = response.usage_metadata
                    prompt_tokens = getattr(usage, 'prompt_token_count', 0)
                    completion_tokens = getattr(usage, 'candidates_token_count', 0)
                    total_tokens = getattr(usage, 'total_token_count', prompt_tokens + completion_tokens)
                    self._set_last_usage(prompt=prompt_tokens, completion=completion_tokens, total=total_tokens)
            except Exception:
                pass  # Usage tracking is optional
            
            if response.text:
                yield response.text
        except Exception as e:
            raise ProviderError(f"Gemini chat error: {e}")
