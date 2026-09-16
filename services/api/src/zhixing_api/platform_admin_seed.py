from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from zhixing_api.data_models import (
    DomainEvent,
    Notification,
    NotificationDelivery,
    PlatformDictionaryItem,
    PlatformDictionaryType,
    PlatformParameter,
)

PARAMETERS = [
    (
        "platform.business-timezone",
        "platform",
        "企业业务时区",
        "string",
        "Asia/Shanghai",
    ),
    (
        "agent.default-evidence-limit",
        "agent",
        "默认证据数量",
        "integer",
        12,
    ),
    (
        "notification.feishu-enabled",
        "notification",
        "飞书通知",
        "boolean",
        False,
    ),
    (
        "file.max-upload-mb",
        "file",
        "单文件大小上限",
        "integer",
        10,
    ),
]

DICTIONARIES = [
    (
        "business-severity",
        "业务严重程度",
        [
            ("info", "提示", "info", 10),
            ("warning", "预警", "warning", 20),
            ("critical", "严重", "critical", 30),
        ],
    ),
    (
        "file-category",
        "文件分类",
        [
            ("knowledge", "知识原件", "knowledge", 10),
            ("exchange", "批量交换", "exchange", 20),
            ("evidence", "业务证据", "evidence", 30),
        ],
    ),
    (
        "notification-category",
        "通知分类",
        [
            ("approval", "审批", "approval", 10),
            ("data-quality", "数据质量", "data-quality", 20),
            ("system", "平台运行", "system", 30),
        ],
    ),
]


def platform_admin_seed_checksum_payload() -> dict[str, object]:
    return {"parameters": PARAMETERS, "dictionaries": DICTIONARIES}


def seed_platform_admin(session: Session, *, enterprise_id: str, now: datetime) -> None:
    for index, (key, group, label, value_type, value) in enumerate(PARAMETERS):
        item = session.scalar(
            select(PlatformParameter).where(
                PlatformParameter.enterprise_id == enterprise_id,
                PlatformParameter.parameter_key == key,
            )
        )
        if item is None:
            session.add(
                PlatformParameter(
                    id=f"platform_parameter_{index:02d}",
                    enterprise_id=enterprise_id,
                    parameter_key=key,
                    group_key=group,
                    label=label,
                    value_type=value_type,
                    value=value,
                    status="active",
                    revision=1,
                    updated_by_principal_id="principal-platform-admin",
                    updated_at=now,
                )
            )

    for type_index, (dictionary_key, name, items) in enumerate(DICTIONARIES):
        dictionary = session.scalar(
            select(PlatformDictionaryType).where(
                PlatformDictionaryType.enterprise_id == enterprise_id,
                PlatformDictionaryType.dictionary_key == dictionary_key,
            )
        )
        if dictionary is None:
            dictionary = PlatformDictionaryType(
                id=f"platform_dictionary_{type_index:02d}",
                enterprise_id=enterprise_id,
                dictionary_key=dictionary_key,
                name=name,
                status="active",
                revision=1,
                updated_at=now,
            )
            session.add(dictionary)
            session.flush()
        existing = set(
            session.scalars(
                select(PlatformDictionaryItem.item_key).where(
                    PlatformDictionaryItem.dictionary_type_id == dictionary.id
                )
            )
        )
        for item_index, (item_key, label, value, sort_order) in enumerate(items):
            if item_key in existing:
                continue
            session.add(
                PlatformDictionaryItem(
                    id=f"platform_dictionary_item_{type_index:02d}_{item_index:02d}",
                    enterprise_id=enterprise_id,
                    dictionary_type_id=dictionary.id,
                    item_key=item_key,
                    label=label,
                    value=value,
                    sort_order=sort_order,
                    status="active",
                    revision=1,
                    updated_at=now,
                )
            )

    event = session.get(DomainEvent, "domain_event_platform_controls_ready")
    if event is None:
        event = DomainEvent(
            id="domain_event_platform_controls_ready",
            enterprise_id=enterprise_id,
            event_key="platform-controls-ready",
            event_type="platform.controls.ready",
            aggregate_type="platform",
            aggregate_id=enterprise_id,
            payload={"revision": "0044"},
            status="published",
            occurred_at=now,
            published_at=now,
        )
        session.add(event)
        session.flush()
    for principal_id, suffix in (
        ("principal-ceo-lin", "ceo"),
        ("principal-platform-admin", "admin"),
    ):
        notification_id = f"notification_platform_controls_ready_{suffix}"
        if session.get(Notification, notification_id) is not None:
            continue
        notification = Notification(
            id=notification_id,
            enterprise_id=enterprise_id,
            principal_id=principal_id,
            source_event_id=event.id,
            category="system",
            title="平台控制面已更新",
            body="后台任务、参数字典、通知、文件、批量交换和访问委托已就绪。",
            severity="success",
            status="unread",
            action_route="/console/admin/jobs" if suffix == "admin" else "/console/inbox",
            created_at=now,
            read_at=None,
        )
        session.add(notification)
        session.add(
            NotificationDelivery(
                id=f"notification_delivery_platform_controls_ready_{suffix}",
                notification_id=notification.id,
                channel="inbox",
                status="delivered",
                attempt_count=1,
                last_error=None,
                delivered_at=now,
            )
        )
