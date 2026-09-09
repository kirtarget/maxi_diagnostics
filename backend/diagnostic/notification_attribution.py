"""Attribute a delivered reminder link to its authenticated recipient."""

import hashlib
import hmac
import logging
import re
from datetime import datetime
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from diagnostic.db import funnel
from diagnostic.db.core import get_pool


logger = logging.getLogger(__name__)
_TOKEN = re.compile(r"([1-9][0-9]{0,18})\.([0-9]{1,12})\.([0-9a-f]{32})", re.ASCII)


def _signature(secret: str, user_id: int, identifier: str) -> str:
    return hmac.new(secret.encode(), f"notification-v1/{user_id}/{identifier}".encode(), hashlib.sha256).hexdigest()[:32]


def notification_url(url: str, secret: str, user_id: int, notification_id: int, due_at: datetime) -> str:
    identifier = f"{notification_id}.{int(due_at.timestamp())}"
    token = f"{identifier}.{_signature(secret, user_id, identifier)}"
    parts = urlsplit(url)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query["n"] = token
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


def verify_token(token: str, secret: str, user_id: int) -> tuple[int, int] | None:
    match = _TOKEN.fullmatch(token)
    if match is None:
        return None
    notification_id, due_at, signature = match.groups()
    if not hmac.compare_digest(signature, _signature(secret, user_id, f"{notification_id}.{due_at}")):
        return None
    return int(notification_id), int(due_at)


async def record_open(token: str | None, secret: str, user_id: int) -> bool:
    if not token:
        return False
    verified = verify_token(token, secret, user_id)
    if verified is None:
        return False
    notification_id, due_at = verified
    try:
        pool = await get_pool()
        async with pool.acquire() as connection:
            delivered = await connection.fetchval(
                """
                SELECT EXISTS (
                    SELECT 1 FROM diagnostic_notifications
                     WHERE id=$1 AND user_id=$2 AND status='sent'
                       AND floor(extract(epoch FROM due_at))::bigint=$3
                )
                """, notification_id, user_id, due_at,
            )
        if not delivered:
            return False
        return await funnel.record_event(
            application_secret=secret, user_id=user_id, action="notification_opened",
            dedupe_key=f"{notification_id}/{due_at}",
        )
    except Exception as exc:
        logger.warning("notification_attribution_failed error=%s", type(exc).__name__)
        return False
