from __future__ import annotations

from .openai_compatible import OpenAICompatibleProvider


class OllamaProvider(OpenAICompatibleProvider):
    """Ollama local AI provider"""
    name = "ollama"

    def __init__(self, base_url: str = "http://localhost:11434/v1"):
        super().__init__(
            api_key="ollama",  # Ollama doesn't require real keys
            base_url=base_url,
            name="ollama"
        )


class LMStudioProvider(OpenAICompatibleProvider):
    """LM Studio local AI provider"""
    name = "lmstudio"

    def __init__(self, base_url: str = "http://localhost:1234/v1"):
        super().__init__(
            api_key="lm-studio",  # LM Studio doesn't require real keys
            base_url=base_url,
            name="lmstudio"
        )


class LocalAIProvider(OpenAICompatibleProvider):
    """LocalAI self-hosted provider"""
    name = "localai"

    def __init__(self, base_url: str, api_key: str = ""):
        super().__init__(
            api_key=api_key or "localai",
            base_url=base_url,
            name="localai"
        )


class TextGenerationWebUIProvider(OpenAICompatibleProvider):
    """Text Generation WebUI (oobabooga) provider"""
    name = "text_generation_webui"

    def __init__(self, base_url: str = "http://localhost:5000/v1"):
        super().__init__(
            api_key="text-gen-webui",
            base_url=base_url,
            name="text_generation_webui"
        )


class VLLMProvider(OpenAICompatibleProvider):
    """vLLM OpenAI-compatible server provider"""
    name = "vllm"

    def __init__(self, base_url: str, api_key: str = ""):
        super().__init__(
            api_key=api_key or "vllm",
            base_url=base_url,
            name="vllm"
        )
