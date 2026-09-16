from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select

from zhixing_api.actor_context import ActorContext, require_permission
from zhixing_api.data_models import AgentSkill, AgentSkillVersion, ToolDefinition
from zhixing_api.database import Database
from zhixing_api.errors import ApiProblem


@dataclass(frozen=True, slots=True)
class RuntimeSkillSelection:
    skill_key: str
    version_number: int
    instructions: str
    tool_keys: tuple[str, ...]


def select_runtime_skill(
    database: Database,
    actor: ActorContext,
    *,
    skill_key: str,
    required_tool_keys: set[str] | None = None,
) -> RuntimeSkillSelection:
    """Resolve a published Skill and intersect it with current tool authorization."""
    with database.session() as session:
        skill = session.scalar(
            select(AgentSkill).where(
                AgentSkill.enterprise_id == actor.enterprise_id,
                AgentSkill.skill_key == skill_key,
                AgentSkill.status == "published",
            )
        )
        if skill is None or skill.current_version_number is None:
            raise ApiProblem(
                status_code=409,
                code="skill.runtime_unavailable",
                message="Skill 没有可运行的已发布版本",
                details={"skill_key": skill_key},
            )
        version = session.scalar(
            select(AgentSkillVersion).where(
                AgentSkillVersion.skill_id == skill.id,
                AgentSkillVersion.version_number == skill.current_version_number,
                AgentSkillVersion.status == "published",
            )
        )
        if version is None:
            raise ApiProblem(
                status_code=409,
                code="skill.runtime_version_unavailable",
                message="Skill 当前版本不可运行",
                details={"skill_key": skill_key},
            )
        available = set(
            session.scalars(
                select(ToolDefinition.tool_key).where(
                    ToolDefinition.enterprise_id == actor.enterprise_id,
                    ToolDefinition.status == "active",
                )
            )
        )
        declared = set(version.tool_keys)
        if not declared.issubset(available):
            raise ApiProblem(
                status_code=409,
                code="skill.runtime_tool_unavailable",
                message="Skill 引用的工具当前不可用",
                details={"skill_key": skill_key, "tool_keys": sorted(declared - available)},
            )
        allowed = declared & required_tool_keys if required_tool_keys is not None else declared
        if not allowed:
            raise ApiProblem(
                status_code=403,
                code="skill.runtime_tool_denied",
                message="当前主体没有 Skill 所需的可用工具",
                details={"skill_key": skill_key},
            )
    require_permission(
        actor,
        "role-twin.invoke",
        database,
        resource_type="agent-skill-runtime",
        resource_key=skill_key,
        scope_type="enterprise",
        scope_id=actor.enterprise_id,
    )
    return RuntimeSkillSelection(
        skill_key=skill_key,
        version_number=version.version_number,
        instructions=version.instructions,
        tool_keys=tuple(sorted(allowed)),
    )
