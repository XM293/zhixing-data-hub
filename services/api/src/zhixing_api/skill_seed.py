from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from zhixing_api.data_models import AgentSkill, AgentSkillVersion

SKILL_SEEDS: tuple[dict[str, Any], ...] = (
    {
        "key": "policy-grounded-answer",
        "name": "制度证据问答",
        "description": "优先读取当前生效制度与企业知识，再形成带来源的回答。",
        "instructions": (
            "先检索当前生效制度和企业知识；只使用工具返回的证据；"
            "回答必须区分事实、判断和未知，并给出来源定位。"
        ),
        "tool_keys": ["read_policy", "search_knowledge"],
        "input_schema": {
            "type": "object",
            "properties": {"question": {"type": "string", "minLength": 2}},
            "required": ["question"],
            "additionalProperties": False,
        },
        "output_schema": {
            "type": "object",
            "properties": {
                "answer": {"type": "string"},
                "evidence": {"type": "array"},
            },
            "required": ["answer", "evidence"],
            "additionalProperties": False,
        },
        "change_summary": "首版制度证据问答 Skill",
    },
    {
        "key": "store-performance-brief",
        "name": "店铺经营简报",
        "description": "读取授权范围经营指标和经营事实，输出可复核的店铺简报。",
        "instructions": (
            "先确认当前授权范围和时间窗口，再读取经营指标与经营事实；"
            "不得猜测指标口径；输出异常、证据和下一步建议。"
        ),
        "tool_keys": ["get_metric", "query_commerce_facts"],
        "input_schema": {
            "type": "object",
            "properties": {
                "scope_key": {"type": "string", "minLength": 1},
                "days": {"type": "integer", "minimum": 1, "maximum": 90},
            },
            "required": ["scope_key"],
            "additionalProperties": False,
        },
        "output_schema": {
            "type": "object",
            "properties": {
                "summary": {"type": "string"},
                "metrics": {"type": "array"},
                "exceptions": {"type": "array"},
            },
            "required": ["summary", "metrics", "exceptions"],
            "additionalProperties": False,
        },
        "change_summary": "首版店铺经营简报 Skill",
    },
)


def seed_skill_registry(session: Session, *, enterprise_id: str, now: datetime) -> None:
    for seed in SKILL_SEEDS:
        skill_key = str(seed["key"])
        skill = session.scalar(
            select(AgentSkill).where(
                AgentSkill.enterprise_id == enterprise_id,
                AgentSkill.skill_key == skill_key,
            )
        )
        if skill is None:
            skill = AgentSkill(
                id=f"agent_skill_{skill_key.replace('-', '_')}",
                enterprise_id=enterprise_id,
                skill_key=skill_key,
                name=str(seed["name"]),
                description=str(seed["description"]),
                status="published",
                current_version_number=1,
                created_by_principal_id="principal-platform-admin",
                created_at=now,
                updated_at=now,
            )
            session.add(skill)
            session.flush()
        else:
            skill.name = str(seed["name"])
            skill.description = str(seed["description"])
            skill.status = "published"
            skill.current_version_number = 1
            skill.updated_at = now

        version = session.scalar(
            select(AgentSkillVersion).where(
                AgentSkillVersion.skill_id == skill.id,
                AgentSkillVersion.version_number == 1,
            )
        )
        if version is None:
            session.add(
                AgentSkillVersion(
                    id=f"agent_skill_version_{skill_key.replace('-', '_')}_v1",
                    enterprise_id=enterprise_id,
                    skill_id=skill.id,
                    version_number=1,
                    status="published",
                    instructions=str(seed["instructions"]),
                    tool_keys=list(seed["tool_keys"]),
                    input_schema=dict(seed["input_schema"]),
                    output_schema=dict(seed["output_schema"]),
                    change_summary=str(seed["change_summary"]),
                    created_by_principal_id="principal-platform-admin",
                    created_at=now,
                    published_at=now,
                )
            )
