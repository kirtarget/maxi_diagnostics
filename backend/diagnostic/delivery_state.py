"""Cancellation-safe reconciliation for post-send database finalizers."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass


@dataclass(frozen=True)
class SentFinalizerResult:
    sent: bool
    uncertain: bool
    cancelled: bool
    error: Exception | None


async def reconcile_sent_finalizer(
    finalizer: asyncio.Task[bool],
    verify_sent: Callable[[], Awaitable[bool]],
) -> SentFinalizerResult:
    """Finish a shielded finalizer and verify ambiguous database responses."""
    cancelled = False
    error: Exception | None = None
    try:
        sent = bool(await asyncio.shield(finalizer))
    except asyncio.CancelledError:
        cancelled = True
        try:
            sent = bool(await asyncio.shield(finalizer))
        except Exception as exc:
            error = exc
            sent = False
    except Exception as exc:
        error = exc
        sent = False

    if error is not None:
        verification = asyncio.create_task(verify_sent())
        try:
            sent = bool(await asyncio.shield(verification))
        except asyncio.CancelledError:
            cancelled = True
            try:
                sent = bool(await asyncio.shield(verification))
            except Exception:
                return SentFinalizerResult(False, True, cancelled, error)
        except Exception:
            return SentFinalizerResult(False, True, cancelled, error)
    return SentFinalizerResult(sent, False, cancelled, error)
