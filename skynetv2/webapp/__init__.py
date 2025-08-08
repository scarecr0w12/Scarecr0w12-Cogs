"""Modular web application package for SkynetV2.
Split from monolithic web.py. Provides route registration via init_webapp().
"""
from __future__ import annotations
from aiohttp import web
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..skynetv2 import SkynetV2
    from .base import BaseViews


def init_webapp(webiface: 'WebInterface'):
    """Register routes onto existing aiohttp app using submodules."""
    from . import auth, pages, api  # noqa: F401
    auth.setup(webiface)
    pages.setup(webiface)
    api.setup(webiface)
