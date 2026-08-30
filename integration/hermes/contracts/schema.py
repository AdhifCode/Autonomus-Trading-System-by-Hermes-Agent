"""Hermes Integration Schemas and Contracts Module.

Defines strict request/response data contracts for:
- Tool discovery and tool invocation (Market, Research, Portfolio, Knowledge)
- Proposal submissions from Hermes to Risk Engine
- Model versioning metadata tracking

See architecture.md §4, §21 and implementation_spec.md §16.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class ToolCategory(StrEnum):
    """Categorization of permitted Hermes tools."""

    MARKET = "MARKET"
    RESEARCH = "RESEARCH"
    PORTFOLIO = "PORTFOLIO"
    KNOWLEDGE = "KNOWLEDGE"
    TRADING = "TRADING"


class ToolPermission(StrEnum):
    """Access control permission levels."""

    READ = "READ"
    WRITE = "WRITE"


class ToolDefinition(BaseModel):
    """Schema metadata describing a Hermes tool."""

    name: str = Field(min_length=1)
    category: ToolCategory
    permission: ToolPermission
    description: str
    parameters_schema: dict[str, Any] = Field(default_factory=dict)


class ToolRequest(BaseModel):
    """Standardized tool invocation payload from Hermes."""

    request_id: str = Field(min_length=1, description="Unique tool request identifier")
    tool_name: str = Field(min_length=1, description="Target tool name")
    parameters: dict[str, Any] = Field(default_factory=dict, description="Tool argument payload")
    caller_id: str = Field(default="hermes", description="Caller identifier")
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="Invocation timestamp",
    )


class ToolResponse(BaseModel):
    """Standardized response returned to Hermes after tool execution."""

    request_id: str
    tool_name: str
    success: bool
    data: Any = None
    error: str | None = None
    error_code: str | None = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ProposalSubmissionRequest(BaseModel):
    """Hermes trade proposal submission contract with model provenance metadata."""

    proposal_data: dict[str, Any] = Field(description="Raw TradeProposal payload")
    model_version: str = Field(min_length=1, description="LLM model version string")
    model_name: str = Field(default="hermes", description="Model family name")
    prompt_hash: str | None = Field(default=None, description="SHA-256 hash of system prompt")
    reasoning_summary: str | None = Field(
        default=None, description="LLM reasoning summary (metadata only)"
    )


class ProposalSubmissionResponse(BaseModel):
    """System response returned to Hermes following proposal evaluation."""

    proposal_id: str | None = None
    status: str = Field(
        description="Evaluation result: ACCEPTED, REJECTED, VALIDATION_FAILED, or SECURITY_BLOCKED"
    )
    validation_errors: list[str] = Field(default_factory=list)
    risk_decision: dict[str, Any] | None = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))


__all__ = [
    "ProposalSubmissionRequest",
    "ProposalSubmissionResponse",
    "ToolCategory",
    "ToolDefinition",
    "ToolPermission",
    "ToolRequest",
    "ToolResponse",
]
