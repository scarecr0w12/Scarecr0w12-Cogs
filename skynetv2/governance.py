from __future__ import annotations

from typing import Optional, Tuple, Dict, Any
from datetime import datetime, timezone, time as dtime
import inspect


def _parse_time_utc(hhmm: str) -> Tuple[int, int]:
    try:
        parts = hhmm.split(":")
        return int(parts[0]), int(parts[1] if len(parts) > 1 else 0)
    except Exception:
        return 0, 0


def _today_reset_dt_utc(now: datetime, reset_cfg: Dict[str, Any]) -> datetime:
    # Only daily period for now
    hh, mm = _parse_time_utc(str(reset_cfg.get("time_utc", "00:00")))
    return datetime.combine(now.date(), dtime(hour=hh, minute=mm, tzinfo=timezone.utc))


async def get_effective_model_policy(cog, guild) -> Dict[str, Any]:
    """
    Merge model policy with precedence:
      guild.policy.models.* overrides global governance_defaults.policy.models.*
    Shape:
      {
        "models": { "allow": {provider: [models...]}, "deny": {provider: [models...]} }
      }
    """
    g = await cog.config.guild(guild).policy()
    g_models = (g or {}).get("models", {}) if g else {}
    g_allow = g_models.get("allow", {}) or {}
    g_deny = g_models.get("deny", {}) or {}

    defaults = await cog.config.governance_defaults()
    d_models = (defaults or {}).get("policy", {}).get("models", {}) if defaults else {}
    d_allow = d_models.get("allow", {}) or {}
    d_deny = d_models.get("deny", {}) or {}

    # Guild allow overrides global allow when present; otherwise fallback to global
    eff_allow: Dict[str, list] = {}
    providers = set(d_allow.keys()) | set(g_allow.keys())
    for p in providers:
        ga = g_allow.get(p, [])
        da = d_allow.get(p, [])
        eff_allow[p] = list(ga) if ga else list(da)

    # Deny is union (global + guild)
    eff_deny: Dict[str, list] = {}
    providers = set(d_deny.keys()) | set(g_deny.keys())
    for p in providers:
        dd = set(d_deny.get(p, []) or [])
        gd = set(g_deny.get(p, []) or [])
        eff_deny[p] = sorted(list(dd | gd))

    return {"models": {"allow": eff_allow, "deny": eff_deny}}


async def get_effective_budget(cog, guild) -> Dict[str, Any]:
    """
    Merge budget defaults with per-guild overrides.

    Returns:
      {
        "unit": "tokens" | "usd",
        "daily_tokens": int,
        "daily_usd": float,
        "thresholds": {"warn1": float, "warn2": float},
        "reset": {"period": "daily", "time_utc": "HH:MM"},
        "admin_channel_id": int | None
      }
    """
    defaults = await cog.config.governance_defaults()
    d_budget = (defaults or {}).get("budget", {}) if defaults else {}
    d_unit = str(d_budget.get("unit", "tokens"))
    d_daily = d_budget.get("daily", {}) or {}
    d_tokens = int(d_daily.get("tokens", 0) or 0)
    d_usd = float(d_daily.get("usd", 0.0) or 0.0)
    d_thresholds = d_budget.get("thresholds", {}) or {"warn1": 0.8, "warn2": 0.95}
    d_reset = d_budget.get("reset", {}) or {"period": "daily", "time_utc": "00:00"}
    d_admin_chan = (d_budget.get("notifications", {}) or {}).get("admin_channel_id")

    gov = await cog.config.guild(guild).governance()
    g_budget = (gov or {}).get("budget", {}) if gov else {}
    g_per_guild = g_budget.get("per_guild", {}) or {}

    unit = str(g_per_guild.get("unit", d_unit))
    daily_tokens = int(g_per_guild.get("daily_tokens", d_tokens) or 0)
    daily_usd = float(g_per_guild.get("daily_usd", d_usd) or 0.0)
    thresholds = g_per_guild.get("thresholds", {}) or d_thresholds
    reset = g_per_guild.get("reset", {}) or d_reset
    admin_channel_id = g_per_guild.get("admin_channel_id", d_admin_chan)

    return {
        "unit": unit,
        "daily_tokens": max(0, int(daily_tokens)),
        "daily_usd": max(0.0, float(daily_usd)),
        "thresholds": {
            "warn1": float(thresholds.get("warn1", 0.8)),
            "warn2": float(thresholds.get("warn2", 0.95)),
        },
        "reset": {"period": str(reset.get("period", "daily")), "time_utc": str(reset.get("time_utc", "00:00"))},
        "admin_channel_id": admin_channel_id,
    }


async def _open_usage_cm(cog, guild):
    """Return an async context-manager for usage."""
    # Always return the context manager object; callers do:
    #   usage_cm = await _open_usage_cm(...); async with usage_cm as usage:
    return cog.config.guild(guild).usage()

async def _get_or_init_budget_usage(cog, guild) -> Dict[str, Any]:
    """
    Ensure usage.budget block exists and return it:
      {
        "tokens_day_start": int,
        "tokens_day_total": int,
        "cost_day_start": int,
        "cost_day_usd": float,
        "last_warn_level": str | None
      }
    """
    usage_cm = await _open_usage_cm(cog, guild)
    async with usage_cm as usage:
        b = usage.setdefault("budget", {})
        now = int(datetime.now(tz=timezone.utc).timestamp())
        if "tokens_day_start" not in b:
            b["tokens_day_start"] = now
        if "tokens_day_total" not in b:
            b["tokens_day_total"] = 0
        if "cost_day_start" not in b:
            b["cost_day_start"] = now
        if "cost_day_usd" not in b:
            b["cost_day_usd"] = 0.0
        if "last_warn_level" not in b:
            b["last_warn_level"] = None
        return b


async def reset_if_needed(cog, guild) -> bool:
    """
    Reset daily counters at configured reset time. Returns True if reset performed.
    """
    eff = await get_effective_budget(cog, guild)
    reset_cfg = eff.get("reset", {}) or {"period": "daily", "time_utc": "00:00"}

    now = datetime.now(tz=timezone.utc)
    today_reset = _today_reset_dt_utc(now, reset_cfg)
    if now < today_reset:
        # Before today's reset time, compare against yesterday's reset
        yesterday = today_reset.replace(day=today_reset.day - 1)
        threshold_ts = int(yesterday.timestamp())
    else:
        threshold_ts = int(today_reset.timestamp())

    did_reset = False
    usage_cm = await _open_usage_cm(cog, guild)
    async with usage_cm as usage:
        b = usage.setdefault("budget", {})
        # Initialize keys if missing
        for k, v in {
            "tokens_day_start": threshold_ts,
            "tokens_day_total": 0,
            "cost_day_start": threshold_ts,
            "cost_day_usd": 0.0,
            "last_warn_level": None,
        }.items():
            if k not in b:
                b[k] = v

        # If day_start earlier than threshold (older window), reset
        if int(b.get("tokens_day_start", 0)) < threshold_ts or int(b.get("cost_day_start", 0)) < threshold_ts:
            b["tokens_day_start"] = threshold_ts
            b["tokens_day_total"] = 0
            b["cost_day_start"] = threshold_ts
            b["cost_day_usd"] = 0.0
            b["last_warn_level"] = None
            did_reset = True

    return did_reset


async def get_consumption(cog, guild) -> Dict[str, Any]:
    """
    Return current daily consumption snapshot:
      {
        "tokens_day_total": int,
        "cost_day_usd": float,
        "tokens_day_start": int,
        "cost_day_start": int,
        "last_warn_level": str | None
      }
    """
    await reset_if_needed(cog, guild)
    usage_cm = await _open_usage_cm(cog, guild)
    async with usage_cm as usage:
        b = usage.get("budget", {}) or {}
        return {
            "tokens_day_total": int(b.get("tokens_day_total", 0)),
            "cost_day_usd": float(b.get("cost_day_usd", 0.0)),
            "tokens_day_start": int(b.get("tokens_day_start", 0)),
            "cost_day_start": int(b.get("cost_day_start", 0)),
            "last_warn_level": b.get("last_warn_level"),
        }


def _compute_ratios(consumed_tokens: int, consumed_usd: float, limit_tokens: int, limit_usd: float) -> Tuple[float, float]:
    r_tokens = (consumed_tokens / limit_tokens) if limit_tokens > 0 else 0.0
    r_usd = (consumed_usd / limit_usd) if limit_usd > 0.0 else 0.0
    return r_tokens, r_usd


def _crossed_threshold(prev_ratio: float, new_ratio: float, t1: float, t2: float) -> Optional[str]:
    """
    Determine if we crossed any threshold going from prev_ratio -> new_ratio.
    Returns "warn1" or "warn2" or None.
    """
    # Normalize
    prev_ratio = max(0.0, prev_ratio)
    new_ratio = max(0.0, new_ratio)
    # Only increasing crossings considered
    if new_ratio >= t2 and prev_ratio < t2:
        return "warn2"
    if new_ratio >= t1 and prev_ratio < t1:
        return "warn1"
    return None


async def record_budget_usage(cog, guild, tokens_delta: int = 0, usd_delta: float = 0.0) -> Dict[str, Any]:
    """
    Increment daily consumption and return status:
      {
        "unit": "tokens" | "usd",
        "limit_tokens": int,
        "limit_usd": float,
        "ratio_tokens": float,
        "ratio_usd": float,
        "warn_level": "warn1" | "warn2" | None,
        "over_budget": bool
      }
    """
    eff = await get_effective_budget(cog, guild)
    await reset_if_needed(cog, guild)

    # Update usage
    usage_cm = await _open_usage_cm(cog, guild)
    async with usage_cm as usage:
        b = usage.setdefault("budget", {})
        prev_tokens = int(b.get("tokens_day_total", 0))
        prev_usd = float(b.get("cost_day_usd", 0.0))
        new_tokens = max(0, prev_tokens + int(tokens_delta or 0))
        new_usd = max(0.0, prev_usd + float(usd_delta or 0.0))
        b["tokens_day_total"] = new_tokens
        b["cost_day_usd"] = new_usd

        # Ratios and threshold crossing
        t1 = float(eff["thresholds"]["warn1"])
        t2 = float(eff["thresholds"]["warn2"])
        r_tok_prev, r_usd_prev = _compute_ratios(prev_tokens, prev_usd, eff["daily_tokens"], eff["daily_usd"])
        r_tok_new, r_usd_new = _compute_ratios(new_tokens, new_usd, eff["daily_tokens"], eff["daily_usd"])

        trig = None
        # Only check the chosen unit for warning by default; compute both for reporting
        if eff["unit"] == "tokens" and eff["daily_tokens"] > 0:
            trig = _crossed_threshold(r_tok_prev, r_tok_new, t1, t2)
        elif eff["unit"] == "usd" and eff["daily_usd"] > 0.0:
            trig = _crossed_threshold(r_usd_prev, r_usd_new, t1, t2)

        if trig:
            b["last_warn_level"] = trig

        # Over budget if chosen unit exceeded limit
        over = False
        if eff["unit"] == "tokens" and eff["daily_tokens"] > 0 and new_tokens >= eff["daily_tokens"]:
            over = True
        if eff["unit"] == "usd" and eff["daily_usd"] > 0.0 and new_usd >= eff["daily_usd"]:
            over = True

    return {
        "unit": eff["unit"],
        "limit_tokens": int(eff["daily_tokens"]),
        "limit_usd": float(eff["daily_usd"]),
        "ratio_tokens": (new_tokens / eff["daily_tokens"]) if eff["daily_tokens"] > 0 else 0.0,  # type: ignore[name-defined]
        "ratio_usd": (new_usd / eff["daily_usd"]) if eff["daily_usd"] > 0 else 0.0,              # type: ignore[name-defined]
        "warn_level": trig,
        "over_budget": over,
    }


async def check_over_budget(cog, guild) -> Optional[str]:
    """
    Check current consumption against effective budget.
    Returns a user-safe error string when budget exceeded, else None.
    """
    eff = await get_effective_budget(cog, guild)
    snap = await get_consumption(cog, guild)

    if eff["unit"] == "tokens":
        limit = int(eff["daily_tokens"])
        if limit > 0 and int(snap["tokens_day_total"]) >= limit:
            return "Daily token budget reached for this server. Try again after the reset."
    else:
        limit = float(eff["daily_usd"])
        if limit > 0.0 and float(snap["cost_day_usd"]) >= limit:
            return "Daily cost budget reached for this server. Try again after the reset."
    return None