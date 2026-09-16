from __future__ import annotations

from datetime import datetime, timedelta
from hashlib import sha256

from sqlalchemy import select
from sqlalchemy.orm import Session

from zhixing_api.data_models import ChannelIdentity

CHANNEL_IDENTITY_SEEDS = [
    (
        "channel_identity_feishu_ceo",
        "feishu",
        "tenant-zhixing-sandbox",
        "ou_ceo_demo",
        "林知远",
        "principal-ceo-lin",
        "active",
        4,
    ),
    (
        "channel_identity_feishu_unknown_31",
        "feishu",
        "tenant-zhixing-sandbox",
        "ou_unknown_31",
        "陈璐",
        None,
        "active",
        18,
    ),
    (
        "channel_identity_feishu_unknown_47",
        "feishu",
        "tenant-zhixing-sandbox",
        "ou_unknown_47",
        "徐航",
        None,
        "active",
        67,
    ),
]


def channel_identity_seed_checksum_payload() -> list[
    tuple[str, str, str, str, str, str | None, str, int]
]:
    return CHANNEL_IDENTITY_SEEDS


def seed_channel_identities(
    session: Session,
    *,
    enterprise_id: str,
    now: datetime,
) -> None:
    for (
        identity_id,
        channel_key,
        tenant_key,
        external_identity,
        observed_name,
        principal_id,
        status,
        minutes_ago,
    ) in CHANNEL_IDENTITY_SEEDS:
        existing = session.scalar(select(ChannelIdentity).where(ChannelIdentity.id == identity_id))
        if existing is not None:
            continue
        observed_at = now - timedelta(minutes=minutes_ago)
        session.add(
            ChannelIdentity(
                id=identity_id,
                enterprise_id=enterprise_id,
                channel_key=channel_key,
                external_tenant_key=tenant_key,
                external_identity_hash=_identity_hash(external_identity),
                external_identity_hint=_identity_hint(external_identity),
                observed_display_name=observed_name,
                principal_id=principal_id,
                status=status,
                version=1,
                first_seen_at=observed_at - timedelta(days=7),
                last_seen_at=observed_at,
                bound_at=observed_at - timedelta(days=6) if principal_id else None,
                unbound_at=None,
                updated_at=observed_at,
            )
        )


def _identity_hash(value: str) -> str:
    return sha256(value.encode()).hexdigest()


def _identity_hint(value: str) -> str:
    return f"{value[:3]}...{value[-4:]}" if len(value) > 8 else f"***{value[-4:]}"
