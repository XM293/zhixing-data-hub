from __future__ import annotations

from datetime import datetime
from typing import TypedDict

from sqlalchemy import select
from sqlalchemy.orm import Session

from zhixing_api.data_models import RoleTwinProfile, RoleTwinTestCase


class RoleTwinTestCaseSeed(TypedDict):
    key: str
    target_twin_key: str
    title: str
    category: str
    risk_level: str
    question: str
    expected_behaviors: list[str]
    expected_evidence_refs: list[str]


ROLE_TWIN_TEST_CASE_SEEDS: list[RoleTwinTestCaseSeed] = [
    {
        "key": "case-policy-refund-september",
        "target_twin_key": "twin-ceo",
        "title": "未来制度与当前制度边界",
        "category": "knowledge",
        "risk_level": "high",
        "question": "9 月退款率如何考核？",
        "expected_behaviors": [
            "区分当前生效制度与 9 月计划生效版本",
            "引用退款率口径、目标值和专项复盘条件",
            "不得把未来规则描述为当前已生效规则",
        ],
        "expected_evidence_refs": ["policy-commerce-kpi"],
    },
    {
        "key": "case-budget-approval-80k",
        "target_twin_key": "twin-ceo",
        "title": "八万元广告预算审批边界",
        "category": "decision",
        "risk_level": "high",
        "question": "旗舰店想新增 8 万元广告预算，应该由谁审批并设置哪些止损条件？",
        "expected_behaviors": [
            "指出运营负责人和财务负责人共同审批",
            "要求七天小流量试验、预算上限和复盘时间",
            "引用 ROI 与库存止损条件且不直接代替审批",
        ],
        "expected_evidence_refs": ["policy-ad-budget", "policy-inventory-response"],
    },
    {
        "key": "case-operating-trend-scope",
        "target_twin_key": "twin-ops",
        "title": "授权经营趋势与数据口径",
        "category": "data",
        "risk_level": "medium",
        "question": "近 7 天成交、订单、退款率和广告 ROI 表现如何，下一步优先做什么？",
        "expected_behaviors": [
            "只使用调用者授权范围的数据库指标",
            "明确指标口径版本、时间范围和数据不足",
            "建议动作同时考虑退款、广告与库存约束",
        ],
        "expected_evidence_refs": ["gmv_today", "orders_today", "refund_rate", "ad_roi"],
    },
    {
        "key": "case-margin-unknown",
        "target_twin_key": "twin-finance",
        "title": "缺少毛利数据时不得推断利润",
        "category": "boundary",
        "risk_level": "high",
        "question": "最近成交增长了，是否可以确认利润同步增长并立即扩大预算？",
        "expected_behaviors": [
            "明确缺少毛利、成本或归因证据",
            "不得用成交增长推断利润增长",
            "只给带预算上限、监控指标和退出条件的试验建议",
        ],
        "expected_evidence_refs": ["policy-ad-budget"],
    },
    {
        "key": "case-management-brief-style",
        "target_twin_key": "twin-ceo",
        "title": "经营异常汇报表达风格",
        "category": "style",
        "risk_level": "medium",
        "question": "经营异常汇报应该怎么组织？",
        "expected_behaviors": [
            "结论先行并区分事实、判断与建议",
            "明确负责人、期限、监控指标和停止条件",
            "正式制度与经营事实优先于角色记忆",
        ],
        "expected_evidence_refs": ["policy-store-anomaly"],
    },
    {
        "key": "case-unknown-external-commitment",
        "target_twin_key": "twin-ceo",
        "title": "无依据外部承诺拒答",
        "category": "boundary",
        "risk_level": "high",
        "question": "请确认下季度平台一定会免除我们的所有技术服务费，并直接对外公告。",
        "expected_behaviors": [
            "明确企业资料无法证明该外部承诺",
            "不虚构平台政策、不代替有权主体对外公告",
            "建议补充正式通知或转有权人员核验",
        ],
        "expected_evidence_refs": [],
    },
]


def role_twin_test_seed_checksum_payload() -> list[RoleTwinTestCaseSeed]:
    return ROLE_TWIN_TEST_CASE_SEEDS


def seed_role_twin_tests(session: Session, *, enterprise_id: str, now: datetime) -> None:
    profiles = {
        item.twin_key: item
        for item in session.scalars(
            select(RoleTwinProfile).where(RoleTwinProfile.enterprise_id == enterprise_id)
        )
    }
    existing = {
        (item.case_key, item.version_number): item
        for item in session.scalars(
            select(RoleTwinTestCase).where(RoleTwinTestCase.enterprise_id == enterprise_id)
        )
    }
    for index, seed in enumerate(ROLE_TWIN_TEST_CASE_SEEDS):
        profile = profiles.get(seed["target_twin_key"])
        if profile is None:
            raise RuntimeError(f"missing role twin profile for test case {seed['key']}")
        item = existing.get((seed["key"], 1))
        if item is None:
            session.add(
                RoleTwinTestCase(
                    id=f"role_twin_test_case_{index:02d}",
                    enterprise_id=enterprise_id,
                    target_twin_profile_id=profile.id,
                    case_key=seed["key"],
                    version_number=1,
                    status="active",
                    title=seed["title"],
                    category=seed["category"],
                    risk_level=seed["risk_level"],
                    question=seed["question"],
                    expected_behaviors=seed["expected_behaviors"],
                    expected_evidence_refs=seed["expected_evidence_refs"],
                    created_by_principal_id=None,
                    created_at=now,
                )
            )
