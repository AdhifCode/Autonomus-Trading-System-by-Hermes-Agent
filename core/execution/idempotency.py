"""Idempotency and Client Order ID Management.

Generates unique client order IDs (TRD-YYYYMMDD-NNNNNN) and prevents duplicate
order submissions across local SQLite database and in-flight memory.

See architecture §13 and implementation_spec §8.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from core.errors import DuplicateOrderError
from core.logging import get_logger

if TYPE_CHECKING:
    from adapters.repositories.sqlite_repos import OrderRepository

logger = get_logger(__name__)


class IdempotencyManager:
    """Manages unique client order ID generation and duplicate submission prevention."""

    def __init__(self) -> None:
        self._seen_ids: set[str] = set()
        self._daily_counters: dict[str, int] = {}

    def generate_client_order_id(self, date: datetime | None = None) -> str:
        """Generate deterministic client_order_id in format TRD-YYYYMMDD-NNNNNN."""
        now = date or datetime.now(tz=UTC)
        date_key = now.strftime("%Y%m%d")

        counter = self._daily_counters.get(date_key, 0) + 1
        self._daily_counters[date_key] = counter

        client_order_id = f"TRD-{date_key}-{counter:06d}"
        return client_order_id

    def check_and_register(
        self,
        client_order_id: str,
        order_repo: OrderRepository | None = None,
    ) -> None:
        """Check whether client_order_id has already been processed.

        Checks both in-memory cache and persistent SQLite repository.

        Raises:
            DuplicateOrderError: If client_order_id was already registered or exists in DB.
        """
        if client_order_id in self._seen_ids:
            logger.error(
                "Duplicate order submission blocked by in-memory idempotency check: %s",
                client_order_id,
            )
            raise DuplicateOrderError(client_order_id)

        if order_repo is not None:
            try:
                existing_order = order_repo.get_by_id(client_order_id)
                if existing_order is not None:
                    logger.error(
                        "Duplicate order submission blocked by SQLite check: %s",
                        client_order_id,
                    )
                    self._seen_ids.add(client_order_id)
                    raise DuplicateOrderError(client_order_id)
            except Exception as e:
                # Import RecordNotFoundError locally to catch non-existence
                from core.errors import RecordNotFoundError

                if isinstance(e, DuplicateOrderError):
                    raise
                if not isinstance(e, RecordNotFoundError):
                    raise

        # Register in in-memory cache
        self._seen_ids.add(client_order_id)
        logger.debug(f"Client order ID registered: {client_order_id}")

    def clear(self) -> None:
        """Clear memory cache (primarily for unit tests)."""
        self._seen_ids.clear()
        self._daily_counters.clear()


__all__ = ["IdempotencyManager"]
