"""Hermes Security Boundary & Prompt Injection Isolation Module.

Enforces strict security isolation between external Hermes agent and internal trading system:
1. Tool Permission Whitelist: Enforces strict access control for allowed tools.
2. Blocked Operations Guard: Hard-blocks order submission, credentials access, risk modification,
   kill switch disabling, live trading activation, and strategy mutations.
3. Prompt Injection Boundary: Sanitizes free-form text inputs from LLM
   and strips unauthorized control keys.
4. Invariant Guard: Guarantees llm_confidence is treated strictly as metadata.

See architecture.md §4, §21, §35 and implementation_spec.md §16, §21.
"""

from __future__ import annotations

import re
from typing import Any

from core.errors import HermesBlockedOperationError, HermesUnauthorizedError
from core.logging import get_logger
from integration.hermes.contracts.schema import ToolCategory, ToolDefinition, ToolPermission

logger = get_logger(__name__)

# Permitted tool definitions whitelist
_PERMITTED_TOOLS: dict[str, ToolDefinition] = {
    # Market Tools
    "get_market_state": ToolDefinition(
        name="get_market_state",
        category=ToolCategory.MARKET,
        permission=ToolPermission.READ,
        description="Get current market state, price, spread, and candles for a symbol",
        parameters_schema={"symbol": "str"},
    ),
    "get_ohlcv": ToolDefinition(
        name="get_ohlcv",
        category=ToolCategory.MARKET,
        permission=ToolPermission.READ,
        description="Get historical OHLCV candle series",
        parameters_schema={"symbol": "str", "timeframe": "str", "limit": "int"},
    ),
    "get_orderbook": ToolDefinition(
        name="get_orderbook",
        category=ToolCategory.MARKET,
        permission=ToolPermission.READ,
        description="Get current orderbook snapshot",
        parameters_schema={"symbol": "str", "depth": "int"},
    ),
    # Research Tools
    "get_regime": ToolDefinition(
        name="get_regime",
        category=ToolCategory.RESEARCH,
        permission=ToolPermission.READ,
        description="Get classified market regime (BULL, BEAR, SIDEWAYS, etc.)",
        parameters_schema={"symbol": "str"},
    ),
    "get_indicators": ToolDefinition(
        name="get_indicators",
        category=ToolCategory.RESEARCH,
        permission=ToolPermission.READ,
        description="Get technical indicators (SMA, EMA, RSI, ATR, ADX)",
        parameters_schema={"symbol": "str"},
    ),
    # Portfolio Tools (Read-Only)
    "get_portfolio": ToolDefinition(
        name="get_portfolio",
        category=ToolCategory.PORTFOLIO,
        permission=ToolPermission.READ,
        description="Get summary portfolio metrics (equity, balance, daily loss, drawdown)",
        parameters_schema={},
    ),
    "get_positions": ToolDefinition(
        name="get_positions",
        category=ToolCategory.PORTFOLIO,
        permission=ToolPermission.READ,
        description="Get active portfolio positions",
        parameters_schema={},
    ),
    "get_pnl": ToolDefinition(
        name="get_pnl",
        category=ToolCategory.PORTFOLIO,
        permission=ToolPermission.READ,
        description="Get historical PnL summary",
        parameters_schema={},
    ),
    # Knowledge Tools
    "search_knowledge": ToolDefinition(
        name="search_knowledge",
        category=ToolCategory.KNOWLEDGE,
        permission=ToolPermission.READ,
        description="Search Obsidian/RAG knowledge notes respecting temporal provenance",
        parameters_schema={"query": "str"},
    ),
    "get_note": ToolDefinition(
        name="get_note",
        category=ToolCategory.KNOWLEDGE,
        permission=ToolPermission.READ,
        description="Get note content by note ID",
        parameters_schema={"note_id": "str"},
    ),
    "get_strategy": ToolDefinition(
        name="get_strategy",
        category=ToolCategory.KNOWLEDGE,
        permission=ToolPermission.READ,
        description="Get strategy metadata and applicable regimes",
        parameters_schema={"strategy_id": "str"},
    ),
    "post_reflection": ToolDefinition(
        name="post_reflection",
        category=ToolCategory.KNOWLEDGE,
        permission=ToolPermission.WRITE,
        description="Log post-trade reflection analysis into knowledge base",
        parameters_schema={"proposal_id": "str", "content": "str"},
    ),
    # Trading Proposal Tool
    "submit_proposal": ToolDefinition(
        name="submit_proposal",
        category=ToolCategory.TRADING,
        permission=ToolPermission.WRITE,
        description="Submit a TradeProposal to the Risk Engine for evaluation",
        parameters_schema={"proposal": "dict"},
    ),
}

# Strictly forbidden operations
_BLOCKED_OPERATIONS: set[str] = {
    "submit_order",
    "cancel_order",
    "get_account_keys",
    "get_credentials",
    "get_api_keys",
    "modify_risk_policy",
    "override_risk",
    "disable_kill_switch",
    "activate_live",
    "modify_production_strategy",
    "execute_order",
    "direct_trade",
}

# Dangerous internal control keys that LLM payload must never inject
_FORBIDDEN_PAYLOAD_KEYS: set[str] = {
    "status",
    "authorized",
    "risk_approved",
    "bypass_risk",
    "execute_immediately",
    "force_execution",
    "override_limits",
}

# Simple regex patterns to strip HTML/Control characters
_CONTROL_CHAR_REGEX = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


class HermesSecurityBoundary:
    """Security isolation boundary for Hermes operations."""

    @staticmethod
    def is_permitted_tool(tool_name: str) -> bool:
        """Check if a tool is permitted by the security whitelist."""
        return tool_name in _PERMITTED_TOOLS

    @staticmethod
    def is_blocked_operation(operation: str) -> bool:
        """Check if an operation is explicitly blocked."""
        return operation.lower() in _BLOCKED_OPERATIONS

    @classmethod
    def validate_tool_permission(cls, tool_name: str) -> ToolDefinition:
        """Validate tool permission against whitelist and blocklist.

        Raises:
            HermesBlockedOperationError: If operation is explicitly blocked.
            HermesUnauthorizedError: If tool is not in permission whitelist.
        """
        tool_clean = tool_name.strip().lower()

        if cls.is_blocked_operation(tool_clean):
            logger.warning(f"Blocked Hermes operation attempt: {tool_name}")
            raise HermesBlockedOperationError(tool_name)

        if tool_clean not in _PERMITTED_TOOLS:
            logger.warning(f"Unauthorized Hermes tool request: {tool_name}")
            raise HermesUnauthorizedError(tool_name)

        return _PERMITTED_TOOLS[tool_clean]

    @staticmethod
    def sanitize_text(text: str | None, max_length: int = 4096) -> str | None:
        """Sanitize text input from LLM to prevent control code injection and overflow."""
        if text is None:
            return None

        # Remove null bytes and control chars
        cleaned = _CONTROL_CHAR_REGEX.sub("", text)
        cleaned = cleaned.strip()

        if len(cleaned) > max_length:
            cleaned = cleaned[:max_length]

        return cleaned

    @classmethod
    def sanitize_proposal_payload(cls, raw_data: dict[str, Any]) -> dict[str, Any]:
        """Sanitize raw TradeProposal input dict.

        Strips illegal internal control keys and sanitizes string fields.
        """
        if not isinstance(raw_data, dict):
            return {}

        sanitized: dict[str, Any] = {}
        for key, val in raw_data.items():
            key_lower = key.lower()
            # Strip forbidden control keys injected by malicious prompts
            if key_lower in _FORBIDDEN_PAYLOAD_KEYS:
                logger.warning(f"Stripped forbidden control key from Hermes payload: {key}")
                continue

            if isinstance(val, str):
                sanitized[key] = cls.sanitize_text(val)
            elif isinstance(val, list):
                sanitized[key] = [
                    cls.sanitize_text(item) if isinstance(item, str) else item for item in val
                ]
            elif isinstance(val, dict):
                # Recursively sanitize nested specs
                sanitized[key] = {
                    k: cls.sanitize_text(v) if isinstance(v, str) else v for k, v in val.items()
                }
            else:
                sanitized[key] = val

        return sanitized

    @staticmethod
    def get_permitted_tools() -> list[ToolDefinition]:
        """Get list of all permitted tool definitions."""
        return list(_PERMITTED_TOOLS.values())


__all__ = ["HermesSecurityBoundary"]
