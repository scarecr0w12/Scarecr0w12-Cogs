from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import AsyncGenerator, AsyncIterator, Dict, List, Optional, Any
import logging

log = logging.getLogger("red.skynetv2.api.base")


@dataclass
class ChatMessage:
    role: str
    content: str


@dataclass
class ChatParams:
    temperature: float = 0.7
    max_tokens: int = 512
    top_p: float = 1.0
    frequency_penalty: float = 0.0
    presence_penalty: float = 0.0


class ProviderError(Exception):
    pass


class Provider:
    name: str

    def __init__(self) -> None:
        self._last_usage: Optional[Dict[str, int]] = None

    async def list_models(self) -> List[str]:
        """
        List available models from this provider.
        
        Returns:
            List of model names available from this provider
        """
        raise NotImplementedError("Subclasses must implement list_models")
    
    async def chat(
        self,
        model: str,
        messages: List[ChatMessage],
        **params: Any
    ) -> AsyncIterator[str]:
        """Yield chunks of text for streaming responses for the given model."""
        raise NotImplementedError

    def get_last_usage(self) -> Optional[Dict[str, int]]:
        return self._last_usage

    def _set_last_usage(self, prompt: int = 0, completion: int = 0, total: Optional[int] = None) -> None:
        t = total if total is not None else (prompt + completion)
        self._last_usage = {"prompt": int(prompt), "completion": int(completion), "total": int(t)}
