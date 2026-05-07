"""Append-only audit log helper.

A row in :class:`AuditLog` is the only side effect of every privileged action
(login, key creation, domain verification). Routers always commit through the
session's per-request transaction so an audit row is durable iff its action
also succeeded.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from ..db.models import AuditLog


async def write_audit(
    session: AsyncSession,
    *,
    action: str,
    actor_user_id: uuid.UUID | None = None,
    actor_ip: str | None = None,
    target_type: str | None = None,
    target_id: str | None = None,
    detail: dict[str, Any] | None = None,
) -> None:
    session.add(
        AuditLog(
            actor_user_id=actor_user_id,
            actor_ip=actor_ip,
            action=action,
            target_type=target_type,
            target_id=target_id,
            detail=detail,
        )
    )
