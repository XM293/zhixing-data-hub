from zhixing_api.actor_context import ActorContext
from zhixing_api.database import Database
from zhixing_api.errors import ApiProblem
from zhixing_api.scope_context import build_scope_context


def require_selected_data_scope(database: Database, actor: ActorContext, scope_key: str) -> None:
    selection = actor.scope_selection
    if not selection:
        return
    scope = build_scope_context(database, actor)
    if scope_key == "enterprise":
        allowed = (
            scope.scope_level == "enterprise"
            and scope.selected_enterprise_ids == (actor.enterprise_id,)
            and not any(selection.get(key) for key in (
                "business_unit_ids", "store_ids", "warehouse_ids",
            ))
        )
    else:
        allowed = scope_key in scope.store_ids
    if not allowed:
        raise ApiProblem(status_code=403, code="scope.selection_denied",
                         message="查询范围超出当前选择，请选择对应的数据范围")
