from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from zhixing_api.customer_service_schemas import (
    CustomerServiceCanonicalFactView,
    CustomerServiceReconciliationDifferenceView,
)
from zhixing_api.data_models import (
    CommerceOrderFact,
    CommerceRefundFact,
    CustomerServiceConversation,
    CustomerServiceOrderContext,
    DataScopeMapping,
    ExternalSystem,
)


@dataclass(frozen=True, slots=True)
class CustomerServiceReconciliationSummary:
    conversation_count: int
    order_conversation_count: int
    matched_count: int
    consistent_count: int
    conflict_count: int
    missing_count: int
    scope_mismatch_count: int
    context_missing_count: int
    not_applicable_count: int
    issues: tuple[dict[str, object], ...]

    @property
    def affected_records(self) -> int:
        return (
            self.conflict_count
            + self.missing_count
            + self.scope_mismatch_count
            + self.context_missing_count
        )

    @property
    def result_status(self) -> Literal["passed", "warning", "failed"]:
        if self.conflict_count:
            return "failed"
        if self.affected_records:
            return "warning"
        return "passed"

    @property
    def observed_value(self) -> str:
        return (
            f"{self.consistent_count}/{self.order_conversation_count} 个订单会话一致；"
            f"{self.conflict_count} 个冲突；{self.affected_records} 个待处理"
        )

    def details(self) -> dict[str, object]:
        return {
            "conversation_count": self.conversation_count,
            "order_conversation_count": self.order_conversation_count,
            "matched_count": self.matched_count,
            "consistent_count": self.consistent_count,
            "conflict_count": self.conflict_count,
            "missing_count": self.missing_count,
            "scope_mismatch_count": self.scope_mismatch_count,
            "context_missing_count": self.context_missing_count,
            "not_applicable_count": self.not_applicable_count,
            "issues": list(self.issues),
        }


def build_customer_service_canonical_fact(
    session: Session,
    conversation: CustomerServiceConversation,
    context: CustomerServiceOrderContext,
) -> CustomerServiceCanonicalFactView:
    if context.context_type == "pre-sale" or not context.order_key:
        return _unmatched_canonical_fact(
            conversation,
            status="not_applicable",
            reason="售前咨询没有订单，不需要执行交易事实对账。",
        )

    order = session.scalar(
        select(CommerceOrderFact).where(
            CommerceOrderFact.enterprise_id == conversation.enterprise_id,
            CommerceOrderFact.order_key == context.order_key,
        )
    )
    if order is None:
        return _unmatched_canonical_fact(
            conversation,
            status="missing",
            reason="数据中心尚未同步到该订单，草稿只可使用客服履约上下文与制度证据。",
        )

    mapping = session.scalar(
        select(DataScopeMapping)
        .where(
            DataScopeMapping.enterprise_id == conversation.enterprise_id,
            DataScopeMapping.external_system_id == order.external_system_id,
            DataScopeMapping.scope_type == "store",
            DataScopeMapping.scope_key == conversation.store_scope_key,
            DataScopeMapping.external_scope_key == order.store_key,
            DataScopeMapping.status == "active",
        )
        .order_by(DataScopeMapping.updated_at.desc())
    )
    if mapping is None or order.customer_key != conversation.customer_key:
        return _unmatched_canonical_fact(
            conversation,
            status="scope_mismatch",
            reason="订单、客户或门店范围未通过当前映射校验，系统不会向草稿暴露该交易事实。",
        )

    refunds = list(
        session.scalars(
            select(CommerceRefundFact).where(
                CommerceRefundFact.enterprise_id == conversation.enterprise_id,
                CommerceRefundFact.order_key == order.order_key,
                CommerceRefundFact.store_key == order.store_key,
            )
        )
    )
    source = session.get(ExternalSystem, order.external_system_id)
    sync_run_ids = sorted({order.sync_run_id, *(item.sync_run_id for item in refunds)})
    paid_amount = _fen_to_yuan(order.paid_amount_fen)
    cost_amount = _fen_to_yuan(order.cost_amount_fen)
    gross_margin_rate = (
        round((order.paid_amount_fen - order.cost_amount_fen) / order.paid_amount_fen, 4)
        if order.paid_amount_fen
        else None
    )
    refund_statuses = sorted({item.status for item in refunds})
    differences = reconcile_order_context(
        context,
        order_status=order.status,
        paid_amount=paid_amount,
        item_count=order.item_count,
        refund_count=len(refunds),
        refund_statuses=refund_statuses,
    )
    material_conflict = any(item.severity == "critical" for item in differences)
    return CustomerServiceCanonicalFactView(
        match_status="matched",
        match_reason="订单、客户与门店范围均通过规范映射校验，已建立事实关联。",
        consistency_status="conflict" if differences else "consistent",
        consistency_reason=(
            f"发现 {len(differences)} 项跨源差异，生成或发送回复前必须人工核验。"
            if differences
            else "客服业务上下文与数据中心规范事实一致。"
        ),
        material_conflict=material_conflict,
        differences=differences,
        order_key=order.order_key,
        customer_key=order.customer_key,
        store_scope_key=conversation.store_scope_key,
        external_store_key=order.store_key,
        order_status=order.status,
        paid_amount=paid_amount,
        cost_amount=cost_amount,
        gross_margin_rate=gross_margin_rate,
        currency="CNY",
        item_count=order.item_count,
        refund_count=len(refunds),
        refund_amount=_fen_to_yuan(sum(item.refund_amount_fen for item in refunds)),
        refund_statuses=refund_statuses,
        business_date=order.business_date,
        paid_at=order.paid_at,
        source_system_key=source.system_key if source is not None else None,
        sync_run_ids=sync_run_ids,
        scope_mapping_id=mapping.id,
        mapping_version=mapping.mapping_version,
    )


def summarize_customer_service_reconciliation(
    session: Session,
    *,
    enterprise_id: str,
) -> CustomerServiceReconciliationSummary:
    conversations = list(
        session.scalars(
            select(CustomerServiceConversation).where(
                CustomerServiceConversation.enterprise_id == enterprise_id
            )
        )
    )
    contexts = {
        item.conversation_id: item
        for item in session.scalars(
            select(CustomerServiceOrderContext).where(
                CustomerServiceOrderContext.enterprise_id == enterprise_id
            )
        )
    }
    counts = {
        "order": 0,
        "matched": 0,
        "consistent": 0,
        "conflict": 0,
        "missing": 0,
        "scope_mismatch": 0,
        "context_missing": 0,
        "not_applicable": 0,
    }
    issues: list[dict[str, object]] = []
    for conversation in conversations:
        context = contexts.get(conversation.id)
        if context is None:
            counts["context_missing"] += 1
            issues.append(_quality_issue(conversation, "context_missing", [], True))
            continue
        if context.context_type == "order":
            counts["order"] += 1
        fact = build_customer_service_canonical_fact(session, conversation, context)
        if fact.match_status == "not_applicable":
            counts["not_applicable"] += 1
            continue
        if fact.match_status == "missing":
            counts["missing"] += 1
            issues.append(_quality_issue(conversation, "missing", [], False))
            continue
        if fact.match_status == "scope_mismatch":
            counts["scope_mismatch"] += 1
            issues.append(_quality_issue(conversation, "scope_mismatch", [], True))
            continue
        counts["matched"] += 1
        counts[fact.consistency_status] += 1
        if fact.consistency_status == "conflict":
            issues.append(
                _quality_issue(
                    conversation,
                    "conflict",
                    [item.field for item in fact.differences],
                    fact.material_conflict,
                )
            )
    return CustomerServiceReconciliationSummary(
        conversation_count=len(conversations),
        order_conversation_count=counts["order"],
        matched_count=counts["matched"],
        consistent_count=counts["consistent"],
        conflict_count=counts["conflict"],
        missing_count=counts["missing"],
        scope_mismatch_count=counts["scope_mismatch"],
        context_missing_count=counts["context_missing"],
        not_applicable_count=counts["not_applicable"],
        issues=tuple(issues),
    )


def reconcile_order_context(
    context: CustomerServiceOrderContext,
    *,
    order_status: str,
    paid_amount: float,
    item_count: int,
    refund_count: int,
    refund_statuses: list[str],
) -> list[CustomerServiceReconciliationDifferenceView]:
    differences: list[CustomerServiceReconciliationDifferenceView] = []
    context_status = (context.order_status or "").casefold()
    canonical_status = order_status.casefold()
    compatible_statuses = {("delivered", "completed"), ("completed", "delivered")}
    if context_status != canonical_status and (
        context_status,
        canonical_status,
    ) not in compatible_statuses:
        differences.append(
            CustomerServiceReconciliationDifferenceView(
                field="order_status",
                severity="critical",
                context_value=context.order_status,
                canonical_value=order_status,
                message=(
                    f"订单状态不一致：客服上下文为 {context.order_status or '未记录'}，"
                    f"数据中心为 {order_status}。"
                ),
            )
        )
    if context.paid_amount is None or abs(context.paid_amount - paid_amount) > 0.01:
        differences.append(
            CustomerServiceReconciliationDifferenceView(
                field="paid_amount",
                severity="critical",
                context_value=(
                    None if context.paid_amount is None else f"{context.paid_amount:.2f} CNY"
                ),
                canonical_value=f"{paid_amount:.2f} CNY",
                message=(
                    "实付金额不一致：客服上下文为 "
                    f"{context.paid_amount if context.paid_amount is not None else '未记录'} CNY，"
                    f"数据中心为 {paid_amount:.2f} CNY。"
                ),
            )
        )
    if context.item_quantity != item_count:
        differences.append(
            CustomerServiceReconciliationDifferenceView(
                field="item_count",
                severity="critical",
                context_value=str(context.item_quantity),
                canonical_value=str(item_count),
                message=(
                    f"商品件数不一致：客服上下文为 {context.item_quantity}，"
                    f"数据中心为 {item_count}。"
                ),
            )
        )
    aftersale_status = (context.aftersale_status or "none").casefold()
    expects_refund = aftersale_status in {
        "refund_accepted",
        "refund_approved",
        "refunding",
        "refunded",
    }
    excludes_refund = aftersale_status in {
        "none",
        "eligible",
        "address_change_requested",
        "quality_reported",
        "wrong_item_reported",
        "payment_dispute",
    }
    if (refund_count > 0 and excludes_refund) or (refund_count == 0 and expects_refund):
        canonical_refund = (
            f"{refund_count} 笔 / {','.join(refund_statuses)}" if refund_count else "无退款事实"
        )
        differences.append(
            CustomerServiceReconciliationDifferenceView(
                field="refund_state",
                severity="critical",
                context_value=context.aftersale_status or "none",
                canonical_value=canonical_refund,
                message=(
                    f"退款状态不一致：客服上下文为 {context.aftersale_status or 'none'}，"
                    f"数据中心为 {canonical_refund}。"
                ),
            )
        )
    return differences


def _quality_issue(
    conversation: CustomerServiceConversation,
    issue_type: str,
    difference_fields: list[str],
    material: bool,
) -> dict[str, object]:
    return {
        "conversation_key": conversation.conversation_key,
        "customer_name": conversation.customer_name,
        "order_key": conversation.order_key,
        "store_scope_key": conversation.store_scope_key,
        "topic": conversation.topic,
        "issue_type": issue_type,
        "difference_fields": difference_fields,
        "material": material,
        "href": f"/console/customer-service/conversations/{conversation.conversation_key}",
    }


def _unmatched_canonical_fact(
    conversation: CustomerServiceConversation,
    *,
    status: Literal["not_applicable", "missing", "scope_mismatch"],
    reason: str,
) -> CustomerServiceCanonicalFactView:
    return CustomerServiceCanonicalFactView(
        match_status=status,
        match_reason=reason,
        consistency_status="not_checked",
        consistency_reason="只有通过订单、客户与门店映射后才执行字段级对账。",
        material_conflict=False,
        differences=[],
        order_key=conversation.order_key,
        customer_key=None,
        store_scope_key=conversation.store_scope_key,
        external_store_key=None,
        order_status=None,
        paid_amount=None,
        cost_amount=None,
        gross_margin_rate=None,
        currency="CNY",
        item_count=None,
        refund_count=0,
        refund_amount=0,
        refund_statuses=[],
        business_date=None,
        paid_at=None,
        source_system_key=None,
        sync_run_ids=[],
        scope_mapping_id=None,
        mapping_version=None,
    )


def _fen_to_yuan(value: int) -> float:
    return round(value / 100, 2)
