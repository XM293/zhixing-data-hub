from __future__ import annotations

from datetime import datetime
from hashlib import sha256

from sqlalchemy import select
from sqlalchemy.orm import Session

from zhixing_api.data_models import ApprovedMemory, MemoryCandidate, RoleTwinProfile, TwinMeeting

MEMORY_SEEDS: list[dict[str, object]] = [
    {
        "key": "ceo-conclusion-first",
        "twin_key": "twin-ceo",
        "category": "communication-style",
        "content": "管理讨论先给结论，再给关键证据、责任人、期限和停止条件。",
        "source_type": "meeting-minutes",
        "source_ref": "模拟管理会议纪要 / 2026-Q2",
        "confidence": 0.96,
        "conflict_status": "clear",
        "conflict_ref": None,
        "status": "active",
        "reviewer": "林知远",
    },
    {
        "key": "ceo-policy-priority",
        "twin_key": "twin-ceo",
        "category": "decision-rule",
        "content": "历史聊天与正式制度冲突时，以当前生效制度为准并显式指出版本差异。",
        "source_type": "manual-rule",
        "source_ref": "角色分身配置 v1",
        "confidence": 1.0,
        "conflict_status": "clear",
        "conflict_ref": None,
        "status": "active",
        "reviewer": "林知远",
    },
    {
        "key": "ops-small-experiment",
        "twin_key": "twin-ops",
        "category": "operating-rule",
        "content": "投放异常先做小范围素材和人群试验，明确观察周期、预算上限和库存约束后再扩量。",
        "source_type": "decision-record",
        "source_ref": "旗舰店广告预算与库存联动研判",
        "confidence": 0.94,
        "conflict_status": "clear",
        "conflict_ref": None,
        "status": "active",
        "reviewer": "周岚",
    },
    {
        "key": "finance-stop-condition",
        "twin_key": "twin-finance",
        "category": "risk-rule",
        "content": "新增预算必须同时给出预算上限、监控口径、停止阈值和审批责任人。",
        "source_type": "decision-record",
        "source_ref": "预算审批复盘 / 2026-08",
        "confidence": 0.97,
        "conflict_status": "clear",
        "conflict_ref": None,
        "status": "active",
        "reviewer": "陈硕",
    },
    {
        "key": "ceo-old-refund-weight",
        "twin_key": "twin-ceo",
        "category": "historical-chat",
        "content": "退款率权重仍按 15% 执行。",
        "source_type": "chat-import",
        "source_ref": "模拟管理群聊天 / 2026-07-14",
        "confidence": 0.83,
        "conflict_status": "conflicted",
        "conflict_ref": "电商运营绩效考核制度 v3",
        "status": "rejected",
        "reviewer": "制度管理员",
    },
    {
        "key": "ops-new-campaign-preference",
        "twin_key": "twin-ops",
        "category": "historical-chat",
        "content": "大促前倾向优先保障旗舰店新品素材测试资源。",
        "source_type": "chat-import",
        "source_ref": "模拟运营群聊天 / 2026-08-26",
        "confidence": 0.68,
        "conflict_status": "unverified",
        "conflict_ref": None,
        "status": "candidate",
        "reviewer": None,
    },
]


def seed_decision_runtime(
    session: Session,
    *,
    enterprise_id: str,
    meeting_id: str,
    now: datetime,
) -> None:
    profiles = {
        profile.twin_key: profile
        for profile in session.scalars(
            select(RoleTwinProfile).where(RoleTwinProfile.enterprise_id == enterprise_id)
        )
    }
    for index, seed in enumerate(MEMORY_SEEDS, start=1):
        profile = profiles.get(str(seed["twin_key"]))
        if profile is None:
            raise RuntimeError(f"missing role twin profile for {seed['twin_key']}")
        candidate = session.scalar(
            select(MemoryCandidate).where(
                MemoryCandidate.enterprise_id == enterprise_id,
                MemoryCandidate.candidate_key == seed["key"],
            )
        )
        content = str(seed["content"])
        reviewed_at = now if seed["reviewer"] else None
        effective_from = now if seed["status"] == "active" else None
        if candidate is None:
            candidate = MemoryCandidate(
                id=f"memory_candidate_{index:02d}",
                enterprise_id=enterprise_id,
                twin_profile_id=profile.id,
                candidate_key=str(seed["key"]),
                category=str(seed["category"]),
                content=content,
                source_type=str(seed["source_type"]),
                source_ref=str(seed["source_ref"]),
                normalized_hash=sha256(content.encode("utf-8")).hexdigest(),
                confidence=float(str(seed["confidence"])),
                conflict_status=str(seed["conflict_status"]),
                conflict_ref=str(seed["conflict_ref"]) if seed["conflict_ref"] else None,
                status=str(seed["status"]),
                reviewer=str(seed["reviewer"]) if seed["reviewer"] else None,
                reviewed_at=reviewed_at,
                effective_from=effective_from,
                created_at=now,
                updated_at=now,
                evidence_refs=[
                    {
                        "type": str(seed["source_type"]),
                        "ref": str(seed["source_ref"]),
                        "excerpt": content,
                    }
                ],
                review_reason=(
                    "开发种子中的已审核角色记忆" if seed["reviewer"] else None
                ),
                retired_at=None,
                source_import_run_id=None,
            )
            session.add(candidate)
        else:
            candidate.twin_profile_id = profile.id
            candidate.category = str(seed["category"])
            candidate.content = content
            candidate.source_type = str(seed["source_type"])
            candidate.source_ref = str(seed["source_ref"])
            candidate.normalized_hash = sha256(content.encode("utf-8")).hexdigest()
            candidate.confidence = float(str(seed["confidence"]))
            candidate.conflict_status = str(seed["conflict_status"])
            candidate.conflict_ref = (
                str(seed["conflict_ref"]) if seed["conflict_ref"] else None
            )
            candidate.status = str(seed["status"])
            candidate.reviewer = str(seed["reviewer"]) if seed["reviewer"] else None
            candidate.review_reason = (
                "开发种子中的已审核角色记忆" if seed["reviewer"] else None
            )
            candidate.reviewed_at = reviewed_at
            candidate.effective_from = effective_from
            candidate.retired_at = None
            candidate.evidence_refs = [
                {
                    "type": str(seed["source_type"]),
                    "ref": str(seed["source_ref"]),
                    "excerpt": content,
                }
            ]
            candidate.updated_at = now

    session.flush()
    approver_by_twin = {
        "twin-ceo": "principal-ceo-lin",
        "twin-ops": "principal-ops-manager-zhou",
        "twin-finance": "principal-finance-chen",
    }
    for candidate in session.scalars(
        select(MemoryCandidate).where(
            MemoryCandidate.enterprise_id == enterprise_id,
            MemoryCandidate.status == "active",
        )
    ):
        profile = session.get(RoleTwinProfile, candidate.twin_profile_id)
        if profile is None:
            continue
        approved = session.scalar(
            select(ApprovedMemory).where(
                ApprovedMemory.enterprise_id == enterprise_id,
                ApprovedMemory.memory_key == candidate.candidate_key,
                ApprovedMemory.version_number == 1,
            )
        )
        if approved is None:
            approved = ApprovedMemory(
                id=f"approved_{candidate.id}",
                enterprise_id=enterprise_id,
                twin_profile_id=candidate.twin_profile_id,
                candidate_id=candidate.id,
                memory_key=candidate.candidate_key,
                version_number=1,
                category=candidate.category,
                content=candidate.content,
                normalized_hash=candidate.normalized_hash,
                source_type=candidate.source_type,
                source_ref=candidate.source_ref,
                evidence_refs=candidate.evidence_refs,
                status="active",
                approved_by_principal_id=approver_by_twin[profile.twin_key],
                approved_at=candidate.reviewed_at or now,
                effective_from=candidate.effective_from or now,
                effective_until=None,
                created_at=now,
            )
            session.add(approved)
        else:
            approved.twin_profile_id = candidate.twin_profile_id
            approved.candidate_id = candidate.id
            approved.category = candidate.category
            approved.content = candidate.content
            approved.normalized_hash = candidate.normalized_hash
            approved.source_type = candidate.source_type
            approved.source_ref = candidate.source_ref
            approved.evidence_refs = candidate.evidence_refs
            approved.status = "active"
            approved.effective_until = None

    meeting = session.get(TwinMeeting, meeting_id)
    if meeting is None:
        raise RuntimeError("missing decision meeting seed")
    if meeting.protocol_status not in {
        "independent_analysis",
        "cross_examination",
        "risk_review",
        "decision_drafted",
        "human_confirmed",
    }:
        meeting.protocol_status = "draft"
    meeting.template_key = "budget-inventory-review"
    meeting.decision_owner = "林知远 / CEO"
    meeting.success_metric = "7 天试验期内广告 ROI 不低于 2.5，重点 SKU 库存覆盖保持可履约"


def decision_seed_checksum_payload() -> dict[str, object]:
    return {"memories": MEMORY_SEEDS}
