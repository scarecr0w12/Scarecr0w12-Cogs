# Governance and Model Policy

This document describes the governance and budget controls for SkynetV2 along with model allow/deny policy mechanics and admin commands (prefix and slash).

## Overview

- Global defaults are defined in config under [skynetv2/config.py](skynetv2/config.py:154)
  - governance_defaults: 
    - unit: tokens | usd
    - daily caps: tokens, usd
    - thresholds: warn1 (default 0.8), warn2 (default 0.95)
    - reset policy: daily 00:00 UTC
    - notifications: admin_channel_id (optional), dm_admins (boolean)
- Per-guild overrides are defined at [skynetv2/config.py](skynetv2/config.py:220)
  - governance.budget.per_guild.{unit,daily_tokens,daily_usd,thresholds,reset,admin_channel_id}
- Enforced at runtime:
  - Hard reject when budget exceeded via [python.check_over_budget()](skynetv2/governance.py:292) integrated in [python.StatsMixin._check_and_record_usage()](skynetv2/stats.py:15)
  - Usage accounting (tokens, cost) recorded by:
    - [python.record_budget_usage()](skynetv2/governance.py:231) from chat handlers in [skynetv2/skynetv2.py](skynetv2/skynetv2.py:372), [skynetv2/skynetv2.py](skynetv2/skynetv2.py:520), [skynetv2/skynetv2.py](skynetv2/skynetv2.py:1105)
    - USD deltas recorded in [python.SkynetV2._estimate_and_record_cost()](skynetv2/skynetv2.py:172)

## Data Model

- Effective budget resolver: [python.get_effective_budget()](skynetv2/governance.py:60)
- Effective model policy: [python.get_effective_model_policy()](skynetv2/governance.py:22)
- Daily counters and reset:
  - [python.reset_if_needed()](skynetv2/governance.py:143) resets at configured daily time; safe to call frequently
  - [python.get_consumption()](skynetv2/governance.py:186) returns snapshot
- Thresholds:
  - warn1 triggers at or above configured ratio (default 80%)
  - warn2 triggers at or above configured ratio (default 95%)

## Admin Commands

All commands require Manage Guild privileges.

### Prefix

- Model Policy
  - Show:
    - [p]ai modelpolicy show
  - Allow:
    - [p]ai modelpolicy allow add <provider> <model>
    - [p]ai modelpolicy allow remove <provider> <model>
  - Deny:
    - [p]ai modelpolicy deny add <provider> <model>
    - [p]ai modelpolicy deny remove <provider> <model>

- Budget
  - Show current per-guild budget:
    - [p]ai budget show
  - Set budget with unit:
    - [p]ai budget set <amount> [unit=tokens|usd]
      - Examples:
        - [p]ai budget set 100 tokens
        - [p]ai budget set 2.50 usd
  - Reset counters:
    - [p]ai budget reset

### Slash (/skynet …)

- Model Policy
  - /skynet modelpolicy show
  - /skynet modelpolicy allow_add provider:<str> model:<str>
  - /skynet modelpolicy allow_remove provider:<str> model:<str>
  - /skynet modelpolicy deny_add provider:<str> model:<str>
  - /skynet modelpolicy deny_remove provider:<str> model:<str>

- Budget
  - /skynet budget show
  - /skynet budget set amount:<float> unit:(tokens|usd)
  - /skynet budget reset

## Behavior Details

- Unit selection controls which cap is enforced and which threshold ratios trigger warnings (tokens vs USD).
- Accounting:
  - Token usage recorded from provider last_usage totals (prompt + completion)
  - USD cost recorded from pricing table per 1k tokens in [python.SkynetV2._estimate_and_record_cost()](skynetv2/skynetv2.py:172)
- Passive reset:
  - Called on-demand before reads/writes to usage; optionally supplemented by a periodic task in the cog (if enabled)

## Examples

### Configure a USD daily budget of $3.00

- Prefix:
  - [p]ai budget set 3.00 usd
- Slash:
  - /skynet budget set amount:3.00 unit:usd

### Allow and deny specific models

- Allow "gpt-4o-mini" for "openai":
  - [p]ai modelpolicy allow add openai gpt-4o-mini
- Deny experimental model:
  - [p]ai modelpolicy deny add groq experimental-bad

## References

- Config defaults: [skynetv2/config.py](skynetv2/config.py:154)
- Guild overrides: [skynetv2/config.py](skynetv2/config.py:220)
- Governance helpers: 
  - [python.get_effective_budget()](skynetv2/governance.py:60)
  - [python.get_effective_model_policy()](skynetv2/governance.py:22)
  - [python.record_budget_usage()](skynetv2/governance.py:231)
  - [python.reset_if_needed()](skynetv2/governance.py:143)
  - [python.get_consumption()](skynetv2/governance.py:186)
- Runtime integration:
  - [python.SkynetV2._estimate_and_record_cost()](skynetv2/skynetv2.py:172)
  - Chat handlers usage recording in [skynetv2/skynetv2.py](skynetv2/skynetv2.py:372), [skynetv2/skynetv2.py](skynetv2/skynetv2.py:520), [skynetv2/skynetv2.py](skynetv2/skynetv2.py:1105)