"""DEPRECATED: legacy monolithic web interface.
Kept as a backward-compatible shim. The modular implementation now lives under
`skynetv2/webapp/` with `WebInterface` and is wrapped by `WebServer` in `skynetv2/web/server.py`.
Importing `WebInterface` from here will yield the new implementation.
"""
from __future__ import annotations
try:
    from .webapp.interface import WebInterface as _ModernWebInterface  # type: ignore
except Exception:  # pragma: no cover - if import fails, provide placeholder
    class _ModernWebInterface:  # type: ignore
        def __init__(self, *_, **__):
            raise RuntimeError("Modular web interface not available; installation incomplete.")

__all__ = ["WebInterface"]

class WebInterface(_ModernWebInterface):  # type: ignore
    """Compatibility subclass; no added behavior."""
    pass
