"""Hermes Integration Gateway Module.

Implements the canonical integration gateway boundary between the external Hermes runtime
and the internal trading system:
1. Tool Dispatcher: Validates tool requests, checks permission whitelists, routes execution to
   read-only tools, and logs audit events.
2. Proposal Pipeline: Validates raw TradeProposal schemas, attaches model version metadata,
   sanitizes prompt inputs, and routes proposals through the Risk Engine.

CRITICAL INVARIANTS:
- Hermes can ONLY propose trade hypotheses via submit_proposal.
- Risk Engine AUTHORIZES trading. Hermes cannot bypass risk evaluation or execute directly.
- Direct exchange SDK access, credentials access, or order placement is strictly impossible.

See architecture.md §4, §39 and implementation_spec.md §16.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import ValidationError

from adapters.repositories.sqlite_repos import SystemEventRepository
from core.domain.enums import EventType, KillSwitchState, RiskDecisionType, Severity, TradingMode
from core.domain.events import AuditEvent
from core.domain.market_state import MarketState
from core.domain.portfolio import PortfolioState
from core.domain.risk import RiskPolicy
from core.domain.system_state import SystemState
from core.domain.trade_proposal import TradeProposal
from core.errors import HermesBlockedOperationError, HermesUnauthorizedError
from core.logging import get_logger
from core.risk.engine import RiskEngine
from integration.hermes.contracts.schema import (
    ProposalSubmissionRequest,
    ProposalSubmissionResponse,
    ToolRequest,
    ToolResponse,
)
from integration.hermes.security import HermesSecurityBoundary
from integration.hermes.tools import KnowledgeTools, MarketTools, PortfolioTools, ResearchTools

logger = get_logger(__name__)


class HermesGateway:
    """Canonical Hermes Integration Gateway."""

    def __init__(
        self,
        risk_engine: RiskEngine | None = None,
        system_event_repo: SystemEventRepository | None = None,
        market_tools: MarketTools | None = None,
        research_tools: ResearchTools | None = None,
        portfolio_tools: PortfolioTools | None = None,
        knowledge_tools: KnowledgeTools | None = None,
    ) -> None:
        self.risk_engine = risk_engine or RiskEngine(policy=RiskPolicy(policy_version="v1.0.0"))
        self.event_repo = system_event_repo
        self.market_tools = market_tools or MarketTools()
        self.research_tools = research_tools or ResearchTools()
        self.portfolio_tools = portfolio_tools or PortfolioTools()
        self.knowledge_tools = knowledge_tools or KnowledgeTools()
        self.security = HermesSecurityBoundary()

    def _log_audit_event(
        self,
        event_type: EventType,
        summary: str,
        details: dict[str, Any],
        severity: Severity = Severity.INFO,
    ) -> None:
        """Record an audit log event in the database if repository is configured."""
        if self.event_repo is None:
            return

        event = AuditEvent(
            event_id=f"EVT-HERMES-{int(datetime.now(UTC).timestamp() * 1000)}",
            timestamp=datetime.now(UTC),
            event_type=event_type,
            severity=severity,
            source="HermesGateway",
            message=summary,
            metadata=details,
        )
        try:
            self.event_repo.save(event)
        except Exception as exc:
            logger.error(f"Failed to record Hermes audit event: {exc}")

    def execute_tool(self, request_payload: ToolRequest | dict[str, Any]) -> ToolResponse:
        """Validate, authorize, and execute a Hermes tool call."""
        # 1. Parse and validate ToolRequest structure
        try:
            if isinstance(request_payload, dict):
                req = ToolRequest.model_validate(request_payload)
            else:
                req = request_payload
        except ValidationError as val_err:
            logger.warning(f"Malformed Hermes tool request: {val_err}")
            return ToolResponse(
                request_id=request_payload.get("request_id", "UNKNOWN")
                if isinstance(request_payload, dict)
                else "UNKNOWN",
                tool_name=request_payload.get("tool_name", "UNKNOWN")
                if isinstance(request_payload, dict)
                else "UNKNOWN",
                success=False,
                error=f"Malformed request schema: {val_err}",
                error_code="HERMES_MALFORMED_REQUEST",
            )

        # 2. Check security permission whitelist & blocked operations
        try:
            tool_def = self.security.validate_tool_permission(req.tool_name)
        except (HermesBlockedOperationError, HermesUnauthorizedError) as sec_err:
            self._log_audit_event(
                event_type=EventType.HERMES_TOOL_DISPATCHED,
                summary=f"Blocked/Unauthorized tool request: {req.tool_name}",
                details={"request_id": req.request_id, "error": str(sec_err)},
                severity=Severity.WARNING,
            )
            err_code = (
                sec_err.code.value
                if (hasattr(sec_err, "code") and sec_err.code is not None)
                else "HERMES_UNAUTHORIZED"
            )
            return ToolResponse(
                request_id=req.request_id,
                tool_name=req.tool_name,
                success=False,
                error=str(sec_err),
                error_code=err_code,
            )

        # 3. Route to target tool handler
        try:
            data: Any = None
            params = req.parameters

            if req.tool_name == "get_market_state":
                data = self.market_tools.get_market_state(symbol=params.get("symbol", "BTCUSDT"))
            elif req.tool_name == "get_ohlcv":
                data = self.market_tools.get_ohlcv(
                    symbol=params.get("symbol", "BTCUSDT"),
                    timeframe=params.get("timeframe", "1h"),
                    limit=params.get("limit", 100),
                )
            elif req.tool_name == "get_orderbook":
                data = self.market_tools.get_orderbook(
                    symbol=params.get("symbol", "BTCUSDT"),
                    depth=params.get("depth", 20),
                )
            elif req.tool_name == "get_regime":
                data = self.research_tools.get_regime(symbol=params.get("symbol", "BTCUSDT"))
            elif req.tool_name == "get_indicators":
                data = self.research_tools.get_indicators(symbol=params.get("symbol", "BTCUSDT"))
            elif req.tool_name == "get_portfolio":
                data = self.portfolio_tools.get_portfolio()
            elif req.tool_name == "get_positions":
                data = self.portfolio_tools.get_positions()
            elif req.tool_name == "get_pnl":
                data = self.portfolio_tools.get_pnl()
            elif req.tool_name == "search_knowledge":
                data = self.knowledge_tools.search_knowledge(query=params.get("query", ""))
            elif req.tool_name == "get_note":
                data = self.knowledge_tools.get_note(note_id=params.get("note_id", ""))
            elif req.tool_name == "get_strategy":
                data = self.knowledge_tools.get_strategy(strategy_id=params.get("strategy_id", ""))
            elif req.tool_name == "post_reflection":
                data = self.knowledge_tools.post_reflection(
                    proposal_id=params.get("proposal_id", ""),
                    content=params.get("content", ""),
                )
            else:
                raise HermesUnauthorizedError(req.tool_name)

            self._log_audit_event(
                event_type=EventType.HERMES_TOOL_DISPATCHED,
                summary=f"Executed tool: {req.tool_name}",
                details={"request_id": req.request_id, "category": tool_def.category.value},
            )

            return ToolResponse(
                request_id=req.request_id,
                tool_name=req.tool_name,
                success=True,
                data=data,
            )

        except Exception as exc:
            logger.error(f"Error executing Hermes tool {req.tool_name}: {exc}")
            return ToolResponse(
                request_id=req.request_id,
                tool_name=req.tool_name,
                success=False,
                error=str(exc),
                error_code="HERMES_TOOL_EXECUTION_ERROR",
            )

    def submit_proposal(
        self,
        submission_payload: ProposalSubmissionRequest | dict[str, Any],
        market_state: MarketState | None = None,
        portfolio: PortfolioState | None = None,
        risk_policy: RiskPolicy | None = None,
        system_state: SystemState | None = None,
    ) -> ProposalSubmissionResponse:
        """Validate raw TradeProposal and submit to Risk Engine for decision.

        Execution pipeline:
        Hermes -> TradeProposal -> Validation -> Risk Engine -> Authorization -> Response
        """
        now = datetime.now(UTC)

        # 1. Parse ProposalSubmissionRequest
        try:
            if isinstance(submission_payload, dict):
                submission = ProposalSubmissionRequest.model_validate(submission_payload)
            else:
                submission = submission_payload
        except ValidationError as val_err:
            logger.warning(f"Malformed proposal submission contract: {val_err}")
            self._log_audit_event(
                event_type=EventType.HERMES_PROPOSAL_RECEIVED,
                summary="Malformed proposal submission contract received",
                details={"errors": str(val_err)},
                severity=Severity.WARNING,
            )
            return ProposalSubmissionResponse(
                status="VALIDATION_FAILED",
                validation_errors=[f"Submission payload error: {val_err}"],
            )

        # 2. Sanitize payload against prompt injection & forbidden control keys
        sanitized_proposal_data = self.security.sanitize_proposal_payload(submission.proposal_data)

        # Ensure model_version is set on the proposal data
        has_version = bool(sanitized_proposal_data.get("model_version"))
        if not has_version:
            sanitized_proposal_data["model_version"] = submission.model_version

        # 3. Validate TradeProposal domain schema strictly
        try:
            proposal = TradeProposal.model_validate(sanitized_proposal_data)
        except ValidationError as schema_err:
            error_msgs = [f"{e['loc']}: {e['msg']}" for e in schema_err.errors()]
            logger.warning(f"TradeProposal schema validation failed: {error_msgs}")
            self._log_audit_event(
                event_type=EventType.HERMES_PROPOSAL_RECEIVED,
                summary="TradeProposal failed schema validation",
                details={"errors": error_msgs},
                severity=Severity.WARNING,
            )
            return ProposalSubmissionResponse(
                status="VALIDATION_FAILED",
                validation_errors=error_msgs,
            )

        self._log_audit_event(
            event_type=EventType.HERMES_PROPOSAL_RECEIVED,
            summary=f"Received TradeProposal {proposal.proposal_id} for {proposal.symbol}",
            details={
                "proposal_id": proposal.proposal_id,
                "symbol": proposal.symbol,
                "model_version": proposal.model_version,
                "llm_confidence": proposal.llm_confidence,
            },
        )

        # 4. Construct default contextual state inputs if not provided
        m_state = market_state or MarketState(
            symbol=proposal.symbol,
            price=proposal.entry.price,
            bid=proposal.entry.price - 1.0,
            ask=proposal.entry.price + 1.0,
            volume_24h=1000000.0,
            spread=2.0,
            timestamp=now,
            data_age_seconds=1.0,
        )

        p_state = portfolio or PortfolioState(
            balance=85000.0,
            equity=100000.0,
            available_margin=85000.0,
            exposure=15000.0,
            positions=[],
            open_orders=[],
            timestamp=now,
        )

        r_policy = risk_policy or RiskPolicy(policy_version="v1.0.0")

        s_state = system_state or SystemState(
            trading_mode=TradingMode.PAPER,
            kill_switch=KillSwitchState.ACTIVE,
            exchange_connected=True,
            data_healthy=True,
            last_heartbeat=now,
        )

        # 5. Route to Risk Engine (INVARIANT: Risk Engine evaluates; llm_confidence cannot override)
        engine = RiskEngine(policy=r_policy) if risk_policy is not None else self.risk_engine
        risk_decision = engine.evaluate(
            proposal=proposal,
            market=m_state,
            portfolio=p_state,
            system=s_state,
        )

        status_str = (
            "ACCEPTED" if risk_decision.decision == RiskDecisionType.APPROVED else "REJECTED"
        )

        self._log_audit_event(
            event_type=EventType.RISK_EVALUATED,
            summary=f"Risk evaluation result for proposal {proposal.proposal_id}: {status_str}",
            details={
                "proposal_id": proposal.proposal_id,
                "decision": risk_decision.decision.value,
                "violations_count": len(risk_decision.violations),
            },
            severity=Severity.INFO if status_str == "ACCEPTED" else Severity.WARNING,
        )

        return ProposalSubmissionResponse(
            proposal_id=proposal.proposal_id,
            status=status_str,
            risk_decision=risk_decision.model_dump(),
        )


__all__ = ["HermesGateway"]
