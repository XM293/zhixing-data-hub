"""Generate the non-secret DAT-011 manual review and provider access ledger."""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "packages/connectors/src/zhixing_connectors/lingxing_official_registry.json"
ALLOWLIST = (
    ROOT / "packages/connectors/src/zhixing_connectors/lingxing_official_readonly_allowlist.json")
WORKLIST = ROOT / "contracts/data/lingxing-official-rollout-worklist.json"
PARAMETER_POLICIES = (
    ROOT / "packages/connectors/src/zhixing_connectors/lingxing_parameter_policies.json")
TARGET = ROOT / "docs/reports/dat-011-lingxing-manual-review-and-access-gaps.md"


def _load(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _cell(value: object) -> str:
    return str(value or "—").replace("|", "\\|").replace("\n", " ")


def _operation_maps() -> tuple[dict[str, dict[str, object]], dict[str, dict[str, object]]]:
    registry = _load(REGISTRY)
    by_id = {str(item["id"]): item for item in registry["operations"]}
    by_resource: dict[str, dict[str, object]] = {}
    for operation in registry["operations"]:
        for key in operation.get("resource_keys") or []:
            by_resource[str(key)] = operation
        operation_id = str(operation["id"])
        if operation_id.startswith("lingxing_op_"):
            operation_id = operation_id[len("lingxing_op_"):]
        by_resource[f"official_{operation_id}"] = operation
    return by_id, by_resource


def _resource_row(resource_key: str, operation: dict[str, object], detail: str,
                  action: str) -> str:
    link = f"[官方文档]({operation['documentation_url']})"
    return "| " + " | ".join(map(_cell, (
        operation.get("wave"), resource_key, operation.get("title"),
        operation.get("path"), detail, action, link,
    ))) + " |"


def build(validation: dict[str, object],
          dependency_status: dict[str, object] | None = None) -> str:
    by_id, by_resource = _operation_maps()
    allowlist = _load(ALLOWLIST)
    worklist = _load(WORKLIST)
    parameter_policies = _load(PARAMETER_POLICIES)
    decisions = {str(item["operation_id"]): str(item["decision"])
                 for item in allowlist["entries"]}
    work_items = list(worklist["items"])
    runtime_keys = {str(item["resource_key"]) for item in work_items}
    multiplatform = [item for item in work_items
                     if item.get("scope_namespace") == "multiplatform"]
    multiplatform_keys = {str(item["resource_key"]) for item in multiplatform}
    failures = list(validation.get("items") or [])
    provider_failures = [item for item in failures
                         if str(item.get("error_code", "")).startswith("sync.external_business.")]
    provider_failures = [item for item in provider_failures
                         if str(item["resource_key"]) not in multiplatform_keys]
    structural = [item for item in failures
                  if item.get("error_code") == "source.read_only_review_blocked"
                  and str(item["resource_key"]) not in runtime_keys
                  and str(item["resource_key"]) not in {
                      "official_72d2c55bdbc031ea"}]
    warehouse = [item for item in work_items
                 if item.get("rollout_state") == "blocked_binding_approval"]
    policy_by_resource = {str(item["resource_key"]): item
                          for item in parameter_policies["resources"]}
    manual_parameters = [item for item in work_items
                         if policy_by_resource.get(str(item["resource_key"]), {}).get("status")
                         == "manual_required"]
    automatic_parameter_resources = [item for item in parameter_policies["resources"]
                                     if item["status"] == "ready_for_bounded_fanout"]
    strategy_counts = Counter(
        str(rule["strategy"])
        for item in parameter_policies["resources"] for rule in item["rules"]
    )
    unreviewed = [operation for operation_id, operation in by_id.items()
                  if operation_id not in decisions]
    errors = Counter(str(item["error_code"]) for item in provider_failures)
    dependency_waiting = [item for item in (dependency_status or {}).get("pending", [])
                          if item.get("waiting_code")]

    lines = [
        "# DAT-011 领星人工核对与接口权限清单",
        "",
        "> 状态：持续维护（2026-09-11）。本清单只保存官方契约标识、错误分类和"
        "待确认事项；不保存密钥、Token、Cookie、真实响应、客户字段值或店铺名称。",
        "",
        "本清单是 DAT-011 唯一的人工核对入口。代码能够确定的分页、时间窗口、枚举和"
        "上游 ID 依赖继续由系统实现；只有当前证据不足或必须由领星/业务人员确认的事项"
        "列为人工输入。任何条目在收到答复后仍需在隔离候选库复测，不能直接改成已接入。",
        "",
        "## 当前人工阻断摘要",
        "",
        f"- 候选账号接口返回需核对：{len(provider_failures)} 个；错误分类："
        + "、".join(f"`{key}` × {value}" for key, value in sorted(errors.items())) + "。",
        f"- 仓库范围归属待审核：{len(warehouse)} 个运行时资源；没有获批仓库映射前保持停用。",
        f"- 多平台店铺归属待审核：{len(multiplatform)} 个运行时资源；Amazon SID 不得用于"
        "多平台接口。",
        f"- 参数语义需人工给出：{len(manual_parameters)} 个资源；其余必填参数由"
        "官方枚举、日期策略或 Raw 依赖值生成。",
        f"- 上游业务数据依赖等待：{len(dependency_waiting)} 个资源；先由历史来源资源"
        "补充受控标识，若全历史仍无记录，再由业务确认无数据或不适用。",
        f"- 已完成自动参数策略：{len(automatic_parameter_resources)} 个资源，版本"
        f" `{parameter_policies['policy_version']}`；其中同一 Raw 行复合键策略 2 个，"
        "不会使用笛卡尔积拼接无效标识。",
        f"- 已确认只读但请求扇出结构仍需专项规则：{len(structural)} 个资源。",
        f"- 尚未完成只读语义审查的官方操作：{len(unreviewed)} 个；这些操作保持 metadata-only。",
        "- 已知写操作 `official_72d2c55bdbc031ea` 永久阻断，不属于申请权限或放行范围。",
        "- 非“星云”店铺共 260 家，按已确认业务规则保持未分配并排除在星云项目指标"
        "之外；只有项目范围变化时才重新审核。",
        "",
        "## 人工回复与关闭规则",
        "",
        "人工核对人员只需提交业务结论和官方权限信息，不要提交 App ID、AppSecret、"
        "Token、Cookie、数据库密码或真实响应。每条回复至少包含：`事项类型`、`资源键或"
        "操作 ID`、`结论`、`依据`、`核对人`、`核对日期`。接口权限结论使用“应可访问 / "
        "不适用 / 尚未开通”；归属结论使用“批准 / 拒绝”；口径结论必须写明版本和生效日期。",
        "",
        "收到回复后，实施方按固定顺序关闭条目：更新版本化契约或映射规则、补失败测试、"
        "在隔离候选库单页复测、再更新本清单状态。口头确认、截图或一次 HTTP 成功均不能"
        "直接替代契约与隔离回归。",
        "",
        "## 正式组织与经营口径待确认",
        "",
        "| 事项 | 当前状态 | 需要提供 | 放行影响 |",
        "|---|---|---|---|",
        "| 集团 | 已确认：领航集团 | 无 | 作为集团治理主体 |",
        "| 法人 | 暂用：星云项目主体（暂定） | 法定名称、内部编码、默认本位币、"
        "默认时区 | 正式组织初始化、财务与业务日期口径 |",
        "| 业务单元 | 已确认：星云铁皮柜 | 无；范围变化时重新核对 | 来源与规范事实的项目范围 |",
        "| 正式管理员 | 隔离验证账号不可作为正式账号 | 至少两名正式管理员的账号标识"
        "及职责分工；不在本清单填写密码 | 生产登录、权限交接与演示账号退场 |",
        "| 店铺范围 | 已按名称含“星云”的既定规则批准 6 家，260 家保持未分配 | "
        "范围变化时提供店铺外部 ID 的批准/拒绝清单 | 订单、售后、广告、财务和指标范围 |",
        "| 多平台店铺范围 | 未批准；现有 6 家仅来自 Amazon 店铺目录 | 按平台提供"
        " `multiplatform_shops` 外部 ID 的批准/拒绝清单 | Walmart、TikTok、Temu、"
        "Lazada、Shein、Shopify 等多平台资源 |",
        "| 仓库范围 | 未批准 | 仓库外部 ID 到法人及星云业务单元的批准/拒绝清单 | "
        "库存、履约、采购和仓储报表 |",
        "| 汇率与合并 | 未确认 | 汇率方向、来源、版本、生效日期、内部抵销规则和"
        "合并口径版本 | 本位币金额与集团财务汇总 |",
        "| 历史边界 | 用户要求领星可提供的全部历史；最早日期未获官方证据 | "
        "按资源/模块提供最早可查询日期或官方保留期 | 全量回填完成判定 |",
        "| 对账基线 | 未签字 | 同范围、同日期、同币种的订单/退款/库存/采购/广告/"
        "财务抽样基线 | 真实功能与数据正确性验收 |",
        "",
        "## 领星账号或接口权限核对",
        "",
        "请领星管理员按资源逐项确认：当前应用是否已获对应模块的只读权限、该账号是否购买/启用对应产品、该站点或平台是否适用，以及错误码的官方含义。不要提供密钥值；只需回复资源键、是否应可访问、所需权限名称或不适用原因。",
        "",
        "| 波次 | 资源键 | 官方名称 | 路径 | 候选证据 | 需要提供 | 文档 |",
        "|---|---|---|---|---|---|---|",
    ]
    for item in sorted(provider_failures, key=lambda value: (
            str(value["error_code"]), str(value["resource_key"]))):
        key = str(item["resource_key"])
        operation = by_resource[key]
        code = str(item["error_code"])
        action = ("确认应用只读权限、模块开通和适用平台"
                  if code.endswith(".403") else
                  "向领星确认错误码含义、账号前置条件和接口适用性")
        lines.append(_resource_row(key, operation, f"隔离候选单页请求返回 `{code}`", action))

    lines += [
        "",
        "## 业务参数与归属规则核对",
        "",
        "| 波次 | 资源键 | 官方名称 | 路径 | 待确认字段 | 需要提供 | 文档 |",
        "|---|---|---|---|---|---|---|",
    ]
    for item in sorted(manual_parameters, key=lambda value: (
            str(value["wave"]), str(value["resource_key"]))):
        key = str(item["resource_key"])
        policy = policy_by_resource[key]
        fields = sorted(str(rule["field"]) for rule in policy["rules"]
                        if rule["strategy"] == "manual")
        requests = {
            "mids": "国家 ID 的合法值及星云项目应覆盖的国家集合",
            "productType": "该接口商品类型的合法值、全量含义及项目适用值",
            "region": "六家已审核店铺到 `na/eu/fe` 的确认映射",
        }
        action = "；".join(requests[field] for field in fields)
        lines.append(_resource_row(key, by_resource[key], ", ".join(fields), action))

    lines += [
        "",
        "### 上游业务数据依赖",
        "",
        "以下资源的参数必须来自同一来源、当前项目范围内已经落地的 Raw 数据。候选库"
        "当前没有发现这些标识，因此保持等待；不能使用合成值或跨项目标识发起真实请求。",
        "",
        "| 波次 | 资源键 | 官方名称 | 路径 | 等待字段 | 后续核对 | 文档 |",
        "|---|---|---|---|---|---|---|",
    ]
    for item in sorted(dependency_waiting, key=lambda value: str(value["resource_key"])):
        key = str(item["resource_key"])
        fields = ", ".join(map(str, item.get("dependency_types") or []))
        lines.append(_resource_row(
            key, by_resource[key], fields,
            "等待上游历史资源产生标识；全历史仍为零时由业务确认无数据或不适用"))

    lines += [
        "",
        "### 仓库范围",
        "",
        "需要业务人员在系统归属审核中确认星云项目可使用的领星仓库；请提供仓库外部 "
        "ID 与项目归属，不要从名称自动推断。批准前以下资源不会执行。",
        "",
        "| 波次 | 资源键 | 官方名称 | 路径 | 当前状态 | 需要提供 | 文档 |",
        "|---|---|---|---|---|---|---|",
    ]
    for item in sorted(warehouse, key=lambda value: str(value["resource_key"])):
        key = str(item["resource_key"])
        lines.append(_resource_row(
            key, by_resource[key], "blocked_binding_approval",
            "审核仓库到法人和星云业务单元的归属；拒绝或批准均需留痕"))

    lines += [
        "",
        "### 多平台店铺范围",
        "",
        "以下接口要求多平台店铺来源键 `store:multiplatform:{store_id}`。当前六家已审核"
        "店铺来自 Amazon 目录，不能复用；请按平台审核多平台店铺外部 ID。批准前不发请求，"
        "此前跨命名空间的空结果或权限错误不作为接口证据。",
        "",
        "| 波次 | 资源键 | 官方名称 | 路径 | 当前状态 | 需要提供 | 文档 |",
        "|---|---|---|---|---|---|---|",
    ]
    for item in sorted(multiplatform, key=lambda value: (
            str(value["wave"]), str(value["resource_key"]))):
        key = str(item["resource_key"])
        lines.append(_resource_row(
            key, by_resource[key], "blocked_platform_store_approval",
            "审核对应平台的多平台店铺外部 ID；不得填写 Amazon SID"))

    lines += [
        "",
        "## 已确认只读但仍需请求结构规则",
        "",
        "以下资源已通过只读语义审查，但请求包含非范围数组或数组对象。需要接口人员确认数组元素来源、最大批量、组合关系和空集合语义；在规则明确前不进入运行时目录。",
        "",
        "| 波次 | 资源键 | 官方名称 | 路径 | 当前状态 | 需要提供 | 文档 |",
        "|---|---|---|---|---|---|---|",
    ]
    for item in sorted(structural, key=lambda value: str(value["resource_key"])):
        key = str(item["resource_key"])
        lines.append(_resource_row(
            key, by_resource[key], "read_only_reviewed / runtime blocked",
            "确认数组元素来源、批量上限、组合规则及空值语义"))

    lines += [
        "",
        "## 尚待逐项只读语义审查的官方操作",
        "",
        "这些操作已登记官方方法、路径和文档哈希，但尚未判定是否严格只读。审核人需"
        "给出 `read_only`、`blocked_mutation` 或 `not_applicable`，并说明依据；没有结论"
        "时保持 metadata-only。",
        "",
        "| 波次 | 操作 ID | 官方名称 | 方法与路径 | 当前状态 | 需要提供 | 文档 |",
        "|---|---|---|---|---|---|---|",
    ]
    for operation in sorted(unreviewed, key=lambda value: (
            str(value["wave"]), str(value["id"]))):
        lines.append("| " + " | ".join(map(_cell, (
            operation.get("wave"), operation.get("id"), operation.get("title"),
            f"{operation.get('method')} {operation.get('path')}",
            "metadata_only", "只读/写入/不适用结论及官方依据",
            f"[官方文档]({operation['documentation_url']})",
        ))) + " |")

    lines += [
        "",
        "## 回填与对账人工验收",
        "",
        "全部可执行资源完成后，还需要业务人员提供以下验收结论：",
        "",
        "- 领星能够提供的最早历史日期，按资源或模块记录；没有官方证据时不得写成“全部历史已覆盖”。",
        "- 六家已审核店铺在领星侧的订单、退款、库存、采购、广告和财务抽样总数或"
        "金额，按同一时区、币种和日期口径对账。",
        "- 原币、本位币、汇率版本和集团合并口径的确认版本；未确认前财务集团汇总保持关闭。",
        "- 对 schema_pending、无权限、不适用和无数据资源逐项签字，区分“没有数据”与“没有权限”。",
        "",
        "每次回复应使用资源键或操作 ID。收到答复后，实施方更新契约/ADR、补合成失败"
        "测试、在隔离候选库复测，再更新本清单状态。",
        "",
        f"生成依据：官方契约 `{worklist['official_contract_version']}`、"
        f"运行时工作清单 `{worklist['version']}`、只读审查 `{allowlist['allowlist_version']}`；"
        f"参数策略 `{parameter_policies['policy_version']}`、运行时资源 {len(runtime_keys)} 个；"
        "参数规则计数 " + "、".join(
            f"`{key}` × {value}" for key, value in sorted(strategy_counts.items())) + "。",
    ]
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--validation", type=Path, required=True)
    parser.add_argument("--dependency-status", type=Path)
    parser.add_argument("--output", type=Path, default=TARGET)
    args = parser.parse_args()
    validation = _load(args.validation)
    dependency_status = _load(args.dependency_status) if args.dependency_status else None
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(build(validation, dependency_status), encoding="utf-8")


if __name__ == "__main__":
    main()
