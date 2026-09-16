from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from typing import Literal
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from zhixing_api.actor_context import ActorContext
from zhixing_api.channel_identity_schemas import (
    ChannelIdentityAccountView,
    ChannelIdentityAdminResponse,
    ChannelIdentityConfigureRequest,
    ChannelIdentityEventView,
    ChannelIdentityMutationResponse,
    ChannelIdentityStats,
    ChannelIdentityView,
)
from zhixing_api.data_models import (
    ChannelIdentity,
    ChannelIdentityEvent,
    Membership,
    OrgUnit,
    Position,
    Principal,
    UserAccount,
)
from zhixing_api.database import Database
from zhixing_api.errors import ApiProblem

CHANNEL_LABELS = {"feishu": "飞书", "wecom": "企业微信", "wechat": "微信"}


def channel_identity_admin_overview(
    database: Database,
    *,
    enterprise_id: str,
) -> ChannelIdentityAdminResponse:
    now = datetime.now(UTC)
    with database.session() as session:
        identities = list(
            session.scalars(
                select(ChannelIdentity)
                .where(ChannelIdentity.enterprise_id == enterprise_id)
                .order_by(ChannelIdentity.last_seen_at.desc(), ChannelIdentity.id)
            )
        )
        events = list(
            session.scalars(
                select(ChannelIdentityEvent)
                .where(ChannelIdentityEvent.enterprise_id == enterprise_id)
                .order_by(ChannelIdentityEvent.occurred_at.desc(), ChannelIdentityEvent.id.desc())
                .limit(100)
            )
        )
        principal_ids = {
            value
            for value in [
                *(item.principal_id for item in identities),
                *(item.actor_principal_id for item in events),
                *(item.before_principal_id for item in events),
                *(item.after_principal_id for item in events),
            ]
            if value
        }
        principals = (
            {
                item.id: item
                for item in session.scalars(
                    select(Principal).where(
                        Principal.enterprise_id == enterprise_id,
                        Principal.id.in_(principal_ids),
                    )
                )
            }
            if principal_ids
            else {}
        )
        accounts = {
            item.principal_id: item
            for item in session.scalars(
                select(UserAccount).where(UserAccount.enterprise_id == enterprise_id)
            )
        }
        account_views = _account_views(session, enterprise_id=enterprise_id)

    views = [_identity_view(item, principals, accounts) for item in identities]
    return ChannelIdentityAdminResponse(
        enterprise_id=enterprise_id,
        stats=ChannelIdentityStats(
            total=len(views),
            bound=sum(item.binding_status == "bound" for item in views),
            unknown=sum(item.binding_status == "unknown" for item in views),
            suspended=sum(item.binding_status == "suspended" for item in views),
            seen_last_24h=sum(
                _as_utc(item.last_seen_at) >= now - timedelta(hours=24) for item in views
            ),
            channel_count=len({item.channel_key for item in views}),
        ),
        accounts=account_views,
        items=views,
        recent_events=[
            ChannelIdentityEventView(
                id=item.id,
                event_type=item.event_type,
                channel_identity_id=item.channel_identity_id,
                actor_name=(
                    principals[item.actor_principal_id].display_name
                    if item.actor_principal_id in principals
                    else "系统"
                ),
                before_status=item.before_status,
                after_status=item.after_status,
                before_principal_name=(
                    principals[item.before_principal_id].display_name
                    if item.before_principal_id in principals
                    else None
                ),
                after_principal_name=(
                    principals[item.after_principal_id].display_name
                    if item.after_principal_id in principals
                    else None
                ),
                reason=item.reason,
                request_id=item.request_id,
                run_id=item.run_id,
                occurred_at=_as_utc(item.occurred_at),
            )
            for item in events
        ],
        generated_at=now,
    )


def configure_channel_identity(
    database: Database,
    *,
    actor: ActorContext,
    identity_id: str,
    payload: ChannelIdentityConfigureRequest,
) -> ChannelIdentityMutationResponse:
    payload_hash = _payload_hash(payload.model_dump(mode="json"))
    now = datetime.now(UTC)
    with database.session() as session:
        replay = session.scalar(
            select(ChannelIdentityEvent).where(
                ChannelIdentityEvent.enterprise_id == actor.enterprise_id,
                ChannelIdentityEvent.idempotency_key == payload.client_request_key,
            )
        )
        if replay is not None:
            if replay.payload_hash != payload_hash or replay.channel_identity_id != identity_id:
                raise ApiProblem(
                    status_code=409,
                    code="identity.channel_idempotency_conflict",
                    message="该渠道身份请求键已用于不同配置",
                )
            return _mutation_response(
                database,
                enterprise_id=actor.enterprise_id,
                identity_id=identity_id,
                event_id=replay.id,
                replayed=True,
            )

        identity = session.scalar(
            select(ChannelIdentity).where(
                ChannelIdentity.enterprise_id == actor.enterprise_id,
                ChannelIdentity.id == identity_id,
            )
        )
        if identity is None:
            raise ApiProblem(
                status_code=404,
                code="identity.channel_identity_not_found",
                message="渠道身份不存在",
            )
        if identity.version != payload.expected_version:
            raise ApiProblem(
                status_code=409,
                code="identity.channel_version_conflict",
                message="渠道身份已被其他管理操作更新，请刷新后重试",
                details={
                    "expected_version": payload.expected_version,
                    "actual_version": identity.version,
                },
            )

        target_principal = _resolve_target_principal(
            session,
            enterprise_id=actor.enterprise_id,
            principal_id=payload.principal_id,
        )
        if target_principal is not None:
            duplicate = session.scalar(
                select(ChannelIdentity).where(
                    ChannelIdentity.enterprise_id == actor.enterprise_id,
                    ChannelIdentity.channel_key == identity.channel_key,
                    ChannelIdentity.external_tenant_key == identity.external_tenant_key,
                    ChannelIdentity.principal_id == target_principal.id,
                    ChannelIdentity.id != identity.id,
                )
            )
            if duplicate is not None:
                raise ApiProblem(
                    status_code=409,
                    code="identity.channel_principal_conflict",
                    message="该内部账号已绑定同一渠道租户中的其他身份",
                    details={"channel_identity_id": duplicate.id},
                )

        before_principal_id = identity.principal_id
        before_binding_status = _binding_status(identity)
        after_principal_id = target_principal.id if target_principal else None
        after_binding_status = _binding_status_values(payload.status, after_principal_id)
        if (
            before_principal_id == after_principal_id
            and before_binding_status == after_binding_status
        ):
            raise ApiProblem(
                status_code=409,
                code="identity.channel_configuration_unchanged",
                message="渠道身份配置没有发生变化",
            )

        identity.principal_id = after_principal_id
        identity.status = payload.status
        identity.version += 1
        identity.updated_at = now
        if before_principal_id != after_principal_id:
            identity.bound_at = now if after_principal_id else None
            identity.unbound_at = now if before_principal_id and not after_principal_id else None
        event = ChannelIdentityEvent(
            id=f"channel_identity_event_{uuid4().hex}",
            enterprise_id=actor.enterprise_id,
            channel_identity_id=identity.id,
            event_type=_event_type(
                before_principal_id=before_principal_id,
                after_principal_id=after_principal_id,
                before_status=before_binding_status,
                after_status=after_binding_status,
            ),
            actor_principal_id=actor.principal_id,
            before_principal_id=before_principal_id,
            after_principal_id=after_principal_id,
            before_status=before_binding_status,
            after_status=after_binding_status,
            reason=payload.reason,
            idempotency_key=payload.client_request_key,
            payload_hash=payload_hash,
            request_id=actor.request_id,
            run_id=actor.run_id,
            occurred_at=now,
        )
        session.add(event)
        session.commit()

    return _mutation_response(
        database,
        enterprise_id=actor.enterprise_id,
        identity_id=identity_id,
        event_id=event.id,
        replayed=False,
    )


def resolve_channel_principal(
    database: Database,
    *,
    enterprise_id: str,
    channel_key: str,
    external_tenant_key: str,
    external_identity_key: str,
) -> str | None:
    identity_hash = sha256(external_identity_key.encode()).hexdigest()
    with database.session() as session:
        identity = session.scalar(
            select(ChannelIdentity).where(
                ChannelIdentity.enterprise_id == enterprise_id,
                ChannelIdentity.channel_key == channel_key,
                ChannelIdentity.external_tenant_key == external_tenant_key,
                ChannelIdentity.external_identity_hash == identity_hash,
                ChannelIdentity.status == "active",
            )
        )
        if identity is None or identity.principal_id is None:
            return None
        principal = session.get(Principal, identity.principal_id)
        account = session.scalar(
            select(UserAccount).where(
                UserAccount.enterprise_id == enterprise_id,
                UserAccount.principal_id == identity.principal_id,
                UserAccount.status == "active",
            )
        )
        if principal is None or principal.status != "active" or account is None:
            return None
        return identity.principal_id


def _account_views(session: Session, *, enterprise_id: str) -> list[ChannelIdentityAccountView]:
    rows = session.execute(
        select(UserAccount, Principal, OrgUnit, Position)
        .join(Principal, Principal.id == UserAccount.principal_id)
        .join(
            Membership,
            (Membership.principal_id == Principal.id)
            & (Membership.enterprise_id == enterprise_id)
            & Membership.is_primary.is_(True)
            & (Membership.status == "active"),
        )
        .join(OrgUnit, OrgUnit.id == Membership.org_unit_id)
        .join(Position, Position.id == Membership.position_id)
        .where(
            UserAccount.enterprise_id == enterprise_id,
            UserAccount.status == "active",
            Principal.status == "active",
            Principal.principal_type == "human",
        )
        .order_by(OrgUnit.name, Position.name, Principal.display_name)
    )
    return [
        ChannelIdentityAccountView(
            principal_id=principal.id,
            account_key=account.account_key,
            display_name=principal.display_name,
            login_name=account.local_login_name,
            organization=org.name,
            position=position.name,
        )
        for account, principal, org, position in rows
    ]


def _identity_view(
    identity: ChannelIdentity,
    principals: dict[str, Principal],
    accounts: dict[str, UserAccount],
) -> ChannelIdentityView:
    principal = principals.get(identity.principal_id or "")
    account = accounts.get(identity.principal_id or "")
    return ChannelIdentityView(
        id=identity.id,
        channel_key=identity.channel_key,
        channel_label=CHANNEL_LABELS.get(identity.channel_key, identity.channel_key),
        external_tenant_key=identity.external_tenant_key,
        external_identity_hint=identity.external_identity_hint,
        external_identity_fingerprint=identity.external_identity_hash[:12],
        observed_display_name=identity.observed_display_name,
        principal_id=identity.principal_id,
        principal_name=principal.display_name if principal else None,
        principal_account_key=account.account_key if account else None,
        binding_status=_binding_status(identity),
        version=identity.version,
        first_seen_at=_as_utc(identity.first_seen_at),
        last_seen_at=_as_utc(identity.last_seen_at),
        updated_at=_as_utc(identity.updated_at),
    )


def _resolve_target_principal(
    session: Session,
    *,
    enterprise_id: str,
    principal_id: str | None,
) -> Principal | None:
    if principal_id is None:
        return None
    principal = session.scalar(
        select(Principal).where(
            Principal.enterprise_id == enterprise_id,
            Principal.id == principal_id,
            Principal.status == "active",
            Principal.principal_type == "human",
        )
    )
    account = session.scalar(
        select(UserAccount).where(
            UserAccount.enterprise_id == enterprise_id,
            UserAccount.principal_id == principal_id,
            UserAccount.status == "active",
        )
    )
    if principal is None or account is None:
        raise ApiProblem(
            status_code=422,
            code="identity.channel_target_invalid",
            message="目标内部账号不存在或未生效",
        )
    return principal


def _binding_status(
    identity: ChannelIdentity,
) -> Literal["unknown", "bound", "suspended"]:
    return _binding_status_values(identity.status, identity.principal_id)


def _binding_status_values(
    status: str,
    principal_id: str | None,
) -> Literal["unknown", "bound", "suspended"]:
    if status == "suspended":
        return "suspended"
    return "bound" if principal_id else "unknown"


def _event_type(
    *,
    before_principal_id: str | None,
    after_principal_id: str | None,
    before_status: str,
    after_status: str,
) -> str:
    if before_status != "suspended" and after_status == "suspended":
        return "channel.identity.suspended"
    if before_status == "suspended" and after_status != "suspended":
        return "channel.identity.reactivated"
    if before_principal_id is None and after_principal_id is not None:
        return "channel.identity.bound"
    if before_principal_id is not None and after_principal_id is None:
        return "channel.identity.unbound"
    if before_principal_id != after_principal_id:
        return "channel.identity.rebound"
    return "channel.identity.configured"


def _mutation_response(
    database: Database,
    *,
    enterprise_id: str,
    identity_id: str,
    event_id: str,
    replayed: bool,
) -> ChannelIdentityMutationResponse:
    overview = channel_identity_admin_overview(database, enterprise_id=enterprise_id)
    identity = next((item for item in overview.items if item.id == identity_id), None)
    if identity is None:
        raise ApiProblem(
            status_code=500,
            code="identity.channel_mutation_result_missing",
            message="渠道身份配置已保存，但无法重建结果视图",
        )
    return ChannelIdentityMutationResponse(identity=identity, event_id=event_id, replayed=replayed)


def _payload_hash(payload: dict[str, object]) -> str:
    material = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return sha256(material.encode()).hexdigest()


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
