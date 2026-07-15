"""Shared HTTP 429 (Too Many Requests) handling."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Mapping

logger = logging.getLogger(__name__)


class RateLimitError(Exception):
    """Raised when an HTTP API returns 429 Too Many Requests."""

    def __init__(
        self,
        retry_after: float | None = None,
        message: str = "Rate limit exceeded",
    ) -> None:
        self.retry_after = retry_after
        super().__init__(message)


def parse_retry_after(headers: Mapping[str, str]) -> float | None:
    """Parse Retry-After header as seconds. Returns None if missing/invalid."""
    value = headers.get("Retry-After") or headers.get("retry-after")
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


async def raise_for_rate_limit(
    status_code: int,
    headers: Mapping[str, str],
    *,
    context: str = "",
) -> None:
    """
    If status is 429: log, honor Retry-After when present, then raise RateLimitError.

    Callers should wrap the request in tenacity retry on RateLimitError
    (exponential backoff: 1s → 2s → 4s → 8s).
    """
    if status_code != 429:
        return

    wait_time = parse_retry_after(headers)
    suffix = f" ({context})" if context else ""
    logger.warning(
        "HTTP 429 Too Many Requests%s, retry_after=%s",
        suffix,
        wait_time,
    )
    if wait_time and wait_time > 0:
        await asyncio.sleep(wait_time)
    raise RateLimitError(wait_time)
