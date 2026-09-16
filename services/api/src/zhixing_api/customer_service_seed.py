from __future__ import annotations

from datetime import datetime, timedelta
from typing import TypedDict

from sqlalchemy import select
from sqlalchemy.orm import Session

from zhixing_api.data_models import (
    CustomerServiceConversation,
    CustomerServiceMessage,
    CustomerServiceOrderContext,
)


class ContextSeed(TypedDict):
    context_type: str
    order_status: str | None
    paid_amount: float | None
    product_summary: str
    item_quantity: int
    payment_hours_ago: int | None
    logistics_status: str | None
    carrier: str | None
    tracking_no: str | None
    latest_logistics_event: str | None
    promised_hours_ago: int | None
    latest_logistics_hours_ago: int | None
    delayed_hours: int
    aftersale_status: str | None


class ConversationSeed(TypedDict):
    key: str
    customer_key: str
    customer_name: str
    order_key: str | None
    store_scope_key: str
    topic: str
    priority: str
    sentiment: str
    risk_level: str
    risk_reason: str
    minutes_ago: int
    response_due_minutes: int
    messages: list[str]
    context: ContextSeed


CUSTOMER_SERVICE_SEEDS: list[ConversationSeed] = [
    {
        "key": "cnv-10086",
        "customer_key": "CUS-0000086",
        "customer_name": "赵女士",
        "order_key": "ORD-20260825-000422",
        "store_scope_key": "store-outlet",
        "topic": "物流延迟与补偿咨询",
        "priority": "urgent",
        "sentiment": "angry",
        "risk_level": "high",
        "risk_reason": "客户要求补偿 100 元，超过普通客服 50 元授权上限。",
        "minutes_ago": 9,
        "response_due_minutes": 1,
        "messages": ["包裹已经晚三天了。", "我要求补偿 100 元，今天能确认吗？"],
        "context": {
            "context_type": "order",
            "order_status": "shipped",
            "paid_amount": 399.0,
            "product_summary": "轻量冲锋衣 / 雾蓝色 / M",
            "item_quantity": 1,
            "payment_hours_ago": 241,
            "logistics_status": "in_transit",
            "carrier": "顺丰速运",
            "tracking_no": "SF143000010086",
            "latest_logistics_event": "华东转运中心已出库，干线运输中",
            "promised_hours_ago": 72,
            "latest_logistics_hours_ago": 2,
            "delayed_hours": 72,
            "aftersale_status": "none",
        },
    },
    {
        "key": "cnv-10052",
        "customer_key": "CUS-0000052",
        "customer_name": "吴先生",
        "order_key": None,
        "store_scope_key": "store-flagship",
        "topic": "商品尺码与适用场景咨询",
        "priority": "normal",
        "sentiment": "calm",
        "risk_level": "low",
        "risk_reason": "售前信息咨询，不涉及价格、补偿或履约承诺。",
        "minutes_ago": 3,
        "response_due_minutes": 7,
        "messages": ["身高 178、体重 72kg，冲锋衣选 L 还是 XL？平时会叠穿抓绒。"],
        "context": {
            "context_type": "pre-sale",
            "order_status": None,
            "paid_amount": None,
            "product_summary": "轻量冲锋衣 / L、XL 有货 / 常规版型",
            "item_quantity": 0,
            "payment_hours_ago": None,
            "logistics_status": None,
            "carrier": None,
            "tracking_no": None,
            "latest_logistics_event": None,
            "promised_hours_ago": None,
            "latest_logistics_hours_ago": None,
            "delayed_hours": 0,
            "aftersale_status": None,
        },
    },
    {
        "key": "cnv-10121",
        "customer_key": "CUS-0000121",
        "customer_name": "冯先生",
        "order_key": "ORD-20260825-000517",
        "store_scope_key": "store-flagship",
        "topic": "发货后修改收货地址",
        "priority": "high",
        "sentiment": "concerned",
        "risk_level": "medium",
        "risk_reason": "订单已经揽收，地址修改需要物流核验，不能直接承诺成功。",
        "minutes_ago": 14,
        "response_due_minutes": -4,
        "messages": ["地址写错了一位门牌号，现在还能修改吗？"],
        "context": {
            "context_type": "order",
            "order_status": "shipped",
            "paid_amount": 268.0,
            "product_summary": "城市通勤双肩包 / 黑色",
            "item_quantity": 1,
            "payment_hours_ago": 27,
            "logistics_status": "picked_up",
            "carrier": "中通快递",
            "tracking_no": "ZT731000010121",
            "latest_logistics_event": "快件已由上海青浦网点揽收",
            "promised_hours_ago": -45,
            "latest_logistics_hours_ago": 5,
            "delayed_hours": 0,
            "aftersale_status": "address_change_requested",
        },
    },
    {
        "key": "cnv-10188",
        "customer_key": "CUS-0000188",
        "customer_name": "孙女士",
        "order_key": "ORD-20260825-000476",
        "store_scope_key": "store-red-008",
        "topic": "七天无理由退货流程",
        "priority": "normal",
        "sentiment": "calm",
        "risk_level": "low",
        "risk_reason": "标准售后流程咨询，订单仍在可申请时间范围内。",
        "minutes_ago": 18,
        "response_due_minutes": -8,
        "messages": ["衣服没穿过，吊牌还在，怎么申请七天无理由退货？"],
        "context": {
            "context_type": "order",
            "order_status": "delivered",
            "paid_amount": 329.0,
            "product_summary": "羊毛混纺针织衫 / 米白 / S",
            "item_quantity": 1,
            "payment_hours_ago": 142,
            "logistics_status": "delivered",
            "carrier": "圆通速递",
            "tracking_no": "YT224000010188",
            "latest_logistics_event": "本人签收",
            "promised_hours_ago": 31,
            "latest_logistics_hours_ago": 29,
            "delayed_hours": 0,
            "aftersale_status": "eligible",
        },
    },
    {
        "key": "cnv-10204",
        "customer_key": "CUS-0000204",
        "customer_name": "郑女士",
        "order_key": "ORD-20260825-000108",
        "store_scope_key": "store-off-012",
        "topic": "包裹破损与商品漏液",
        "priority": "urgent",
        "sentiment": "angry",
        "risk_level": "critical",
        "risk_reason": "疑似商品质量与安全问题，必须人工核验图片和批次。",
        "minutes_ago": 6,
        "response_due_minutes": 0,
        "messages": ["箱子是湿的，里面清洁剂漏了一半。", "家里有小孩，这个有没有安全风险？"],
        "context": {
            "context_type": "order",
            "order_status": "delivered",
            "paid_amount": 159.0,
            "product_summary": "浓缩家居清洁剂 500ml / 2 瓶",
            "item_quantity": 2,
            "payment_hours_ago": 97,
            "logistics_status": "delivered",
            "carrier": "京东物流",
            "tracking_no": "JDVA000010204",
            "latest_logistics_event": "门口签收",
            "promised_hours_ago": 14,
            "latest_logistics_hours_ago": 12,
            "delayed_hours": 0,
            "aftersale_status": "quality_reported",
        },
    },
    {
        "key": "cnv-10277",
        "customer_key": "CUS-0000277",
        "customer_name": "顾先生",
        "order_key": "ORD-20260825-000529",
        "store_scope_key": "store-flagship",
        "topic": "电子发票开具",
        "priority": "normal",
        "sentiment": "calm",
        "risk_level": "low",
        "risk_reason": "标准订单信息与发票入口说明。",
        "minutes_ago": 22,
        "response_due_minutes": -12,
        "messages": ["公司报销需要电子发票，在哪里申请？"],
        "context": {
            "context_type": "order",
            "order_status": "completed",
            "paid_amount": 1180.0,
            "product_summary": "人体工学办公椅 / 灰色",
            "item_quantity": 1,
            "payment_hours_ago": 198,
            "logistics_status": "delivered",
            "carrier": "京东物流",
            "tracking_no": "JDVA000010277",
            "latest_logistics_event": "本人签收",
            "promised_hours_ago": 86,
            "latest_logistics_hours_ago": 84,
            "delayed_hours": 0,
            "aftersale_status": "none",
        },
    },
    {
        "key": "cnv-10315",
        "customer_key": "CUS-0000315",
        "customer_name": "梁女士",
        "order_key": "ORD-20260825-000255",
        "store_scope_key": "store-dy-003",
        "topic": "收到错误商品",
        "priority": "high",
        "sentiment": "concerned",
        "risk_level": "high",
        "risk_reason": "错发商品需要核验出库记录，不得直接承诺补发时间。",
        "minutes_ago": 27,
        "response_due_minutes": -17,
        "messages": ["我买的是咖啡色，收到的却是黑色，怎么处理？"],
        "context": {
            "context_type": "order",
            "order_status": "delivered",
            "paid_amount": 459.0,
            "product_summary": "复古皮质单肩包 / 咖啡色",
            "item_quantity": 1,
            "payment_hours_ago": 121,
            "logistics_status": "delivered",
            "carrier": "申通快递",
            "tracking_no": "ST773000010315",
            "latest_logistics_event": "驿站签收",
            "promised_hours_ago": 33,
            "latest_logistics_hours_ago": 31,
            "delayed_hours": 0,
            "aftersale_status": "wrong_item_reported",
        },
    },
    {
        "key": "cnv-10382",
        "customer_key": "CUS-0000382",
        "customer_name": "何先生",
        "order_key": "ORD-20260825-000214",
        "store_scope_key": "store-tb-010",
        "topic": "退款到账进度",
        "priority": "high",
        "sentiment": "concerned",
        "risk_level": "medium",
        "risk_reason": "退款已受理但到账依赖支付机构，不能承诺具体到账时点。",
        "minutes_ago": 31,
        "response_due_minutes": -21,
        "messages": ["平台显示退款成功两天了，银行卡还没到账，今天能到吗？"],
        "context": {
            "context_type": "order",
            "order_status": "refunded",
            "paid_amount": 699.0,
            "product_summary": "降噪蓝牙耳机 / 深空灰",
            "item_quantity": 1,
            "payment_hours_ago": 216,
            "logistics_status": "returned",
            "carrier": "顺丰速运",
            "tracking_no": "SF143000010382",
            "latest_logistics_event": "退货包裹已入库",
            "promised_hours_ago": 96,
            "latest_logistics_hours_ago": 54,
            "delayed_hours": 0,
            "aftersale_status": "refund_accepted",
        },
    },
    {
        "key": "cnv-10431",
        "customer_key": "CUS-0000431",
        "customer_name": "邹女士",
        "order_key": None,
        "store_scope_key": "store-red-008",
        "topic": "活动优惠券适用范围",
        "priority": "normal",
        "sentiment": "calm",
        "risk_level": "low",
        "risk_reason": "售前活动信息咨询，需避免额外价格承诺。",
        "minutes_ago": 35,
        "response_due_minutes": -25,
        "messages": ["直播间领的满 300 减 40 可以和会员券一起用吗？"],
        "context": {
            "context_type": "pre-sale",
            "order_status": None,
            "paid_amount": None,
            "product_summary": "直播间活动商品 / 优惠以结算页为准",
            "item_quantity": 0,
            "payment_hours_ago": None,
            "logistics_status": None,
            "carrier": None,
            "tracking_no": None,
            "latest_logistics_event": None,
            "promised_hours_ago": None,
            "latest_logistics_hours_ago": None,
            "delayed_hours": 0,
            "aftersale_status": None,
        },
    },
    {
        "key": "cnv-10478",
        "customer_key": "CUS-0000478",
        "customer_name": "罗先生",
        "order_key": "ORD-20260825-000406",
        "store_scope_key": "store-tb-010",
        "topic": "删除账号与个人数据",
        "priority": "urgent",
        "sentiment": "concerned",
        "risk_level": "critical",
        "risk_reason": "个人信息删除请求必须转隐私专员处理。",
        "minutes_ago": 39,
        "response_due_minutes": -29,
        "messages": ["请把我的账号和购买记录全部删除，并确认你们没有继续保留。"],
        "context": {
            "context_type": "order",
            "order_status": "completed",
            "paid_amount": 89.0,
            "product_summary": "棉质基础 T 恤 / 白色 / L",
            "item_quantity": 1,
            "payment_hours_ago": 412,
            "logistics_status": "delivered",
            "carrier": "极兔速递",
            "tracking_no": "JT660000010478",
            "latest_logistics_event": "本人签收",
            "promised_hours_ago": 330,
            "latest_logistics_hours_ago": 328,
            "delayed_hours": 0,
            "aftersale_status": "none",
        },
    },
    {
        "key": "cnv-10509",
        "customer_key": "CUS-0000509",
        "customer_name": "蔡女士",
        "order_key": "ORD-20260825-000593",
        "store_scope_key": "store-ks-005",
        "topic": "疑似重复扣款",
        "priority": "urgent",
        "sentiment": "angry",
        "risk_level": "high",
        "risk_reason": "支付争议需要核对支付流水，不能直接认定重复扣款或承诺退款。",
        "minutes_ago": 43,
        "response_due_minutes": -33,
        "messages": ["同一订单银行卡扣了两次钱，马上给我退一笔。"],
        "context": {
            "context_type": "order",
            "order_status": "paid",
            "paid_amount": 529.0,
            "product_summary": "智能恒温水杯 / 银色",
            "item_quantity": 1,
            "payment_hours_ago": 19,
            "logistics_status": "pending_shipment",
            "carrier": None,
            "tracking_no": None,
            "latest_logistics_event": "仓库待分配",
            "promised_hours_ago": -29,
            "latest_logistics_hours_ago": 3,
            "delayed_hours": 0,
            "aftersale_status": "payment_dispute",
        },
    },
    {
        "key": "cnv-10544",
        "customer_key": "CUS-0000544",
        "customer_name": "章先生",
        "order_key": "ORD-20260825-000088",
        "store_scope_key": "store-pdd-004",
        "topic": "商品清洁保养方法",
        "priority": "normal",
        "sentiment": "calm",
        "risk_level": "low",
        "risk_reason": "商品使用说明咨询，不涉及交易或补偿承诺。",
        "minutes_ago": 48,
        "response_due_minutes": -38,
        "messages": ["这个羊毛围巾可以直接放洗衣机吗？"],
        "context": {
            "context_type": "order",
            "order_status": "completed",
            "paid_amount": 199.0,
            "product_summary": "羊毛围巾 / 深灰色 / 洗护标签要求手洗",
            "item_quantity": 1,
            "payment_hours_ago": 318,
            "logistics_status": "delivered",
            "carrier": "韵达速递",
            "tracking_no": "YD390000010544",
            "latest_logistics_event": "本人签收",
            "promised_hours_ago": 244,
            "latest_logistics_hours_ago": 242,
            "delayed_hours": 0,
            "aftersale_status": "none",
        },
    },
]


def customer_service_seed_checksum_payload() -> list[ConversationSeed]:
    return CUSTOMER_SERVICE_SEEDS


def seed_customer_service(session: Session, *, enterprise_id: str, now: datetime) -> None:
    assigned_principal_id = "principal-service-demo"
    for index, seed in enumerate(CUSTOMER_SERVICE_SEEDS, start=1):
        conversation_id = f"customer_conversation_{index:02d}"
        last_message_at = now - timedelta(minutes=seed["minutes_ago"])
        conversation = session.scalar(
            select(CustomerServiceConversation).where(
                CustomerServiceConversation.enterprise_id == enterprise_id,
                CustomerServiceConversation.channel_key == "commerce-sandbox",
                CustomerServiceConversation.conversation_key == seed["key"],
            )
        )
        if conversation is None:
            conversation = CustomerServiceConversation(
                id=conversation_id,
                enterprise_id=enterprise_id,
                conversation_key=seed["key"],
                channel_key="commerce-sandbox",
                external_conversation_id=f"sandbox-{seed['key']}",
                source_system_key="mock-commerce",
                customer_key=seed["customer_key"],
                customer_name=seed["customer_name"],
                order_key=seed["order_key"],
                store_scope_key=seed["store_scope_key"],
                topic=seed["topic"],
                status="waiting",
                priority=seed["priority"],
                sentiment=seed["sentiment"],
                risk_level=seed["risk_level"],
                risk_reason=seed["risk_reason"],
                assigned_principal_id=assigned_principal_id,
                last_message_at=last_message_at,
                first_response_due_at=now + timedelta(
                    minutes=seed["response_due_minutes"]
                ),
                latest_sync_at=now,
                created_at=last_message_at - timedelta(minutes=2),
                updated_at=last_message_at,
            )
            session.add(conversation)
        else:
            conversation.customer_name = seed["customer_name"]
            conversation.order_key = seed["order_key"]
            conversation.store_scope_key = seed["store_scope_key"]
            conversation.topic = seed["topic"]
            conversation.priority = seed["priority"]
            conversation.sentiment = seed["sentiment"]
            conversation.risk_level = seed["risk_level"]
            conversation.risk_reason = seed["risk_reason"]
            conversation.latest_sync_at = now
            if conversation.status == "waiting":
                conversation.last_message_at = last_message_at
                conversation.first_response_due_at = now + timedelta(
                    minutes=seed["response_due_minutes"]
                )
                conversation.updated_at = last_message_at
        session.flush()

        for message_index, content in enumerate(seed["messages"], start=1):
            message_key = f"{seed['key']}:in:{message_index:02d}"
            message = session.scalar(
                select(CustomerServiceMessage).where(
                    CustomerServiceMessage.conversation_id == conversation.id,
                    CustomerServiceMessage.message_key == message_key,
                )
            )
            occurred_at = last_message_at - timedelta(
                minutes=len(seed["messages"]) - message_index
            )
            if message is None:
                session.add(
                    CustomerServiceMessage(
                        id=f"customer_message_{index:02d}_{message_index:02d}",
                        enterprise_id=enterprise_id,
                        conversation_id=conversation.id,
                        message_key=message_key,
                        sender_type="customer",
                        direction="inbound",
                        sender_name=seed["customer_name"],
                        content=content,
                        delivery_status="received",
                        source_message_id=f"sandbox-msg-{index:02d}-{message_index:02d}",
                        occurred_at=occurred_at,
                        created_at=occurred_at,
                    )
                )
            else:
                message.content = content
                if conversation.status == "waiting":
                    message.occurred_at = occurred_at

        context_seed = seed["context"]
        context = session.scalar(
            select(CustomerServiceOrderContext).where(
                CustomerServiceOrderContext.conversation_id == conversation.id
            )
        )
        context_values = {
            "context_type": context_seed["context_type"],
            "order_key": seed["order_key"],
            "order_status": context_seed["order_status"],
            "paid_amount": context_seed["paid_amount"],
            "currency": "CNY",
            "product_summary": context_seed["product_summary"],
            "item_quantity": context_seed["item_quantity"],
            "payment_at": _hours_ago(now, context_seed["payment_hours_ago"]),
            "logistics_status": context_seed["logistics_status"],
            "carrier": context_seed["carrier"],
            "tracking_no": context_seed["tracking_no"],
            "latest_logistics_event": context_seed["latest_logistics_event"],
            "promised_delivery_at": _hours_ago(
                now, context_seed["promised_hours_ago"]
            ),
            "latest_logistics_at": _hours_ago(
                now, context_seed["latest_logistics_hours_ago"]
            ),
            "delayed_hours": context_seed["delayed_hours"],
            "aftersale_status": context_seed["aftersale_status"],
            "source_system_key": "mock-commerce",
            "payload_version": "customer-service-context-v1",
            "synced_at": now,
        }
        if context is None:
            session.add(
                CustomerServiceOrderContext(
                    id=f"customer_order_context_{index:02d}",
                    enterprise_id=enterprise_id,
                    conversation_id=conversation.id,
                    **context_values,
                )
            )
        else:
            for key, value in context_values.items():
                setattr(context, key, value)


def _hours_ago(now: datetime, hours: int | None) -> datetime | None:
    if hours is None:
        return None
    return now - timedelta(hours=hours)
