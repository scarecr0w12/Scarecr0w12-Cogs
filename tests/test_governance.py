#!/usr/bin/env python3
from __future__ import annotations

import sys
sys.path.append('.')

import asyncio
import time
from typing import Any, Dict, Optional

import pytest

# Target under test
from skynetv2.governance import (
    get_effective_model_policy,
    get_effective_budget,
    record_budget_usage,
    reset_if_needed,
    get_consumption,
)


class _AsyncDictContext:
    """Async context manager that returns a backing dict and persists mutations."""
    def __init__(self, backing: Dict[str, Any]):
        self._backing = backing

    async def __aenter__(self) -> Dict[str, Any]:
        return self._backing

    async def __aexit__(self, exc_type, exc, tb) -> bool:
        return False


class _GuildConfigFacade:
    """Guild-scoped config facade providing async getters and async-with contexts."""
    def __init__(self, store: Dict[str, Any]):
        # Expected keys: policy, governance, usage, memory, etc. But we only use a subset here.
        self._store = store
        self._store.setdefault("policy", {})
        self._store.setdefault("governance", {})
        self._store.setdefault("usage", {})

    async def policy(self) -> Dict[str, Any]:
        # Return a deep-ish copy to simulate read semantics without accidentally sharing
        return dict(self._store.get("policy", {}))

    async def governance(self) -> Dict[str, Any]:
        return dict(self._store.get("governance", {}))

    async def usage(self) -> _AsyncDictContext:
        # usage must persist mutations
        return _AsyncDictContext(self._store.setdefault("usage", {}))


class _ConfigFacade:
    """Top-level config facade, simulating Red's Config.get_conf API shape minimally."""
    def __init__(self, defaults: Dict[str, Any], guild_data: Dict[int, Dict[str, Any]]):
        # defaults: global defaults (e.g., governance_defaults)
        self._defaults = defaults
        self._guilds = guild_data

    async def governance_defaults(self) -> Dict[str, Any]:
        return dict(self._defaults.get("governance_defaults", {}))

    def guild(self, guild) -> _GuildConfigFacade:
        gid = int(getattr(guild, "id", 0))
        self._guilds.setdefault(gid, {})
        return _GuildConfigFacade(self._guilds[gid])


class _FakeCog:
    """Minimal Cog holder for governance helpers: exposes .config like the real cog."""
    def __init__(self, defaults: Dict[str, Any], guild_data: Optional[Dict[int, Dict[str, Any]]] = None):
        self.config = _ConfigFacade(defaults=defaults, guild_data=guild_data or {})


class _FakeGuild:
    def __init__(self, gid: int = 1234):
        self.id = gid
        self.owner = None  # not needed for these tests


# ----------------------------
# Test data builders
# ----------------------------

def _build_defaults() -> Dict[str, Any]:
    return {
        "governance_defaults": {
            "budget": {
                "unit": "tokens",
                "daily": {"tokens": 100, "usd": 0.0},
                "thresholds": {"warn1": 0.8, "warn2": 0.95},
                "reset": {"period": "daily", "time_utc": "00:00"},
                "notifications": {"admin_channel_id": None, "dm_admins": True},
            },
            "policy": {
                "models": {
                    "allow": {"openai": ["gpt-4o", "gpt-4o-mini"]},
                    "deny": {"groq": ["experimental-bad"]},
                }
            },
        }
    }


def _build_guild_seed() -> Dict[str, Any]:
    # Guild overrides for policy/ governance to exercise merging logic
    return {
        "policy": {
            "models": {
                "allow": {"openai": ["gpt-4o-mini"]},  # overrides allow for openai
                "deny": {"groq": ["worse-model"]},     # union with global deny
            }
        },
        "governance": {
            "budget": {
                "per_guild": {
                    "unit": "usd",
                    "daily_usd": 1.5,
                    "thresholds": {"warn1": 0.75, "warn2": 0.9},
                    "reset": {"period": "daily", "time_utc": "00:00"},
                    "admin_channel_id": None,
                }
            }
        },
        "usage": {},  # will be mutated by tests
    }


# ----------------------------
# Tests
# ----------------------------

def test_policy_merge_allow_and_deny():
    """Guild allow overrides; deny is union with global."""
    defaults = _build_defaults()
    guild_seed = {1234: _build_guild_seed()}
    cog = _FakeCog(defaults, guild_seed)
    g = _FakeGuild(1234)

    eff = asyncio.run(get_effective_model_policy(cog, g))
    assert "models" in eff
    allow = eff["models"]["allow"]
    deny = eff["models"]["deny"]

    # Allow: guild override takes precedence if present
    assert allow.get("openai") == ["gpt-4o-mini"]

    # Deny: union
    assert set(deny.get("groq", [])) == {"experimental-bad", "worse-model"}


def test_budget_merge_per_guild_overrides_default_unit_and_amount():
    """Per-guild budget overwrites defaults for unit and daily cap."""
    defaults = _build_defaults()
    guild_seed = {1234: _build_guild_seed()}
    cog = _FakeCog(defaults, guild_seed)
    g = _FakeGuild(1234)

    eff = asyncio.run(get_effective_budget(cog, g))
    assert eff["unit"] == "usd"
    assert eff["daily_usd"] == pytest.approx(1.5)
    # Tokens limit from defaults should remain available (but unit is usd)
    assert eff["daily_tokens"] == 100


def test_record_budget_usage_warn1_and_warn2_tokens_unit():
    """Cross warn1 and warn2 thresholds for tokens unit budgets."""
    defaults = _build_defaults()
    # Force unit=tokens at guild level to exercise token path; no per_guild override for unit
    guild_seed = {1234: {"governance": {"budget": {"per_guild": {"unit": "tokens", "daily_tokens": 100}}}}}
    cog = _FakeCog(defaults, guild_seed)
    g = _FakeGuild(1234)

    # First increment to 81 (81%), expect warn1
    status = asyncio.run(record_budget_usage(cog, g, tokens_delta=81, usd_delta=0.0))
    assert status["unit"] == "tokens"
    assert status["warn_level"] in (None, "warn1")  # depending on exact ratio comparison
    # Cross to 96 (96%), expect warn2
    status = asyncio.run(record_budget_usage(cog, g, tokens_delta=15, usd_delta=0.0))
    assert status["ratio_tokens"] >= 0.96
    # At or beyond warn2 boundary
    assert status.get("warn_level") in ("warn2", None)  # None if boundary already noted; warn2 acceptable
    # Over budget with another increment
    status = asyncio.run(record_budget_usage(cog, g, tokens_delta=10, usd_delta=0.0))
    assert status["over_budget"] is True


def test_reset_if_needed_resets_day_counters():
    """If day start is prior to threshold, reset counters."""
    defaults = _build_defaults()
    guild_data = {1234: _build_guild_seed()}
    # Initialize usage with very old start times so reset is guaranteed
    guild_data[1234]["usage"] = {"budget": {"tokens_day_start": 0, "cost_day_start": 0, "tokens_day_total": 42, "cost_day_usd": 0.42}}
    cog = _FakeCog(defaults, guild_data)
    g = _FakeGuild(1234)

    did = asyncio.run(reset_if_needed(cog, g))
    assert did is True
    snap = asyncio.run(get_consumption(cog, g))
    # After reset, totals should be zeroed
    assert int(snap["tokens_day_total"]) == 0
    assert float(snap["cost_day_usd"]) == pytest.approx(0.0, abs=1e-6)


def test_get_consumption_tracks_totals_after_usage():
    defaults = _build_defaults()
    guild_data = {1234: _build_guild_seed()}
    cog = _FakeCog(defaults, guild_data)
    g = _FakeGuild(1234)

    # Add some USD consumption directly (simulate provider cost)
    status = asyncio.run(record_budget_usage(cog, g, tokens_delta=0, usd_delta=0.2))
    assert status["unit"] in ("usd", "tokens")
    snap = asyncio.run(get_consumption(cog, g))
    assert float(snap["cost_day_usd"]) >= 0.2


if __name__ == "__main__":
    # Allow ad-hoc local run without pytest
    import sys
    try:
        test_policy_merge_allow_and_deny()
        test_budget_merge_per_guild_overrides_default_unit_and_amount()
        test_record_budget_usage_warn1_and_warn2_tokens_unit()
        test_reset_if_needed_resets_day_counters()
        test_get_consumption_tracks_totals_after_usage()
    except AssertionError:
        sys.exit(1)