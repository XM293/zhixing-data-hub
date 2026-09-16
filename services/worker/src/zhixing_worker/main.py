from __future__ import annotations

import asyncio
from collections.abc import Callable, Mapping
from dataclasses import replace
from datetime import UTC, datetime
from os import getenv
from pathlib import Path
from threading import Event
from time import monotonic, sleep

import httpx
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Connection, Engine
from zhixing_api.actor_context import require_permission, resolve_database_actor
from zhixing_api.database import Database
from zhixing_api.errors import ApiProblem
from zhixing_api.ingestion.dependencies import persist_dependency_values
from zhixing_api.ingestion.mirror import defer_projection
from zhixing_api.ingestion.persistence import persist_canonical_page
from zhixing_api.scope_context import build_scope_context
from zhixing_connectors import (
    LingxingBusinessError,
    LingxingClient,
    LingxingConfig,
    LingxingTokenProvider,
)
from zhixing_connectors.auth import LingxingTokenCache
from zhixing_connectors.catalog import (
    can_project_to_core,
    materialize_request_parameters,
    materialize_window_parameters,
    page_parameters,
    resource_spec,
    response_value,
    validate_resource_parameters,
)
from zhixing_connectors.reports import ReportReader
from zhixing_jobs import (
    JOB_EXECUTION_TOKEN_HEADER,
    WORKER_ID_HEADER,
    JobContinuation,
    JobExecutionContext,
    JobRecord,
    JobRepository,
    PermanentJobError,
    RetryableJobError,
    WorkerRunner,
)
from zhixing_jobs.repository import JobStateConflict
from zhixing_jobs.runner import JobHandler
from zhixing_observability import REQUEST_ID_HEADER, RUN_ID_HEADER

from zhixing_worker.archive import RawArchive
from zhixing_worker.config import WorkerSettings, load_settings
from zhixing_worker.rate_limit import SourceRateLimiter
from zhixing_worker.replay import replay_archived_page
from zhixing_worker.scheduling import SourceScheduleTick
from zhixing_worker.source_jobs import execute_mock_source
from zhixing_worker.sync_store import SyncStore

SYNC_PAGES_PER_TURN = 100

STORE_SCOPED_RESOURCES = frozenset({
    "orders", "after_sales", "listings", "fulfillments", "fbm_orders",
    "fba_shipments", "fba_inventory", "advertising", "finance", "customer_service",
    "source_reports",
})
SINGLE_STORE_RESOURCES = frozenset({
    "listings", "fbm_orders", "advertising", "finance", "customer_service",
    "source_reports",
})
# The FBA cost contracts use singular opaque ``seller_id`` values.  Other
# contracts named ``sellerIds`` are legacy numeric sid arrays despite the
# similar spelling, so they must remain on the numeric scope path.
SELLER_ID_SCOPE_PARAMETERS = frozenset({"sellerid"})
WAREHOUSE_SCOPED_RESOURCES = frozenset({
    "warehouse_bins", "inventory", "inbound_orders", "outbound_orders",
    "inventory_statements",
})


def _response_path_is_explicit_null(payload: Mapping[str, object],
                                    path: tuple[str, ...]) -> bool:
    current: object = payload
    for part in path:
        if current is None:
            return True
        if not isinstance(current, Mapping) or part not in current:
            return False
        current = current[part]
    return current is None


def noop_handler(
    job: JobRecord,
    context: JobExecutionContext,
) -> Mapping[str, object]:
    context.ensure_active()
    return {"accepted": True, "job_id": job.id}


def _execute_lingxing_sync(
    job: JobRecord,
    context: JobExecutionContext,
    settings: WorkerSettings,
    *,
    transport: httpx.AsyncBaseTransport | None = None,
    persist_page: Callable[[dict[str, object], dict[str, object],
                            dict[str, object]], object] | None = None,
    validate_scope: Callable[[], object] | None = None,
    budget_engine: Engine | None = None,
    token_cache: LingxingTokenCache | None = None,
) -> Mapping[str, object]:
    """Execute one bounded read-only page and archive the response.

    The API only enqueues this job; all external I/O happens here.
    """
    context.ensure_active()
    if job.payload.get("provider") != "lingxing":
        raise PermanentJobError("同步任务来源不受支持", code="sync.provider_unsupported")
    if not settings.lingxing_enabled:
        raise PermanentJobError("领星接入已停用", code="sync.provider_disabled")
    snapshot = job.payload.get("scope_snapshot")
    if (
        isinstance(snapshot, dict)
        and snapshot.get("enterprise_id") not in (None, job.enterprise_id)
    ):
        raise PermanentJobError("同步范围与任务法人不一致", code="sync.scope_mismatch")
    resource = str(job.payload.get("resource_key") or "")
    spec = resource_spec(resource)
    if spec is None or not spec.path:
        raise PermanentJobError("同步资源未进入只读目录", code="sync.resource_unsupported")
    method, path = spec.method, spec.path
    page_size = spec.page_size
    filters: dict[str, object] = dict(spec.parameters)
    try:
        parameters = job.payload.get("resource_parameters", {})
        if not isinstance(parameters, dict):
            raise ValueError("parameters invalid")
        window_start = job.payload.get("window_start")
        window_end = job.payload.get("window_end")
        if spec.window_fields and (window_start is not None or window_end is not None):
            start = datetime.fromisoformat(str(window_start or ""))
            end = datetime.fromisoformat(str(window_end or ""))
            # Jobs queued before schedule parameters became partition-only may still
            # contain their old window values. The authoritative run bounds replace
            # those fields while every unrelated parameter remains strictly checked.
            partition_parameters = {
                key: value for key, value in parameters.items()
                if key not in spec.window_fields
            }
            filters.update(materialize_window_parameters(
                spec, partition_parameters, start, end
            ))
        else:
            filters.update(validate_resource_parameters(spec, parameters))
    except ValueError:
        raise PermanentJobError("资源查询参数无效", code="sync.parameters_invalid") from None
    if spec.scope_kind == "store":
        selected_sids = resolve_order_store_filter(
            snapshot, budget_engine, job.enterprise_id,
            str(job.payload.get("source_id") or ""), spec.scope_namespace or "amazon"
        )
    elif resource in STORE_SCOPED_RESOURCES:
        selected_sids = resolve_order_store_filter(
            snapshot, budget_engine, job.enterprise_id,
            str(job.payload.get("source_id") or "")
        )
    else:
        selected_sids = None
    selected_wids = resolve_warehouse_filter(
        snapshot, budget_engine, job.enterprise_id, str(job.payload.get("source_id") or "")
    ) if resource in WAREHOUSE_SCOPED_RESOURCES or spec.scope_kind == "warehouse" else None
    if spec.scope_kind is not None:
        parameter = spec.scope_parameter or ""
        allowed = (resolve_store_scope_parameter(
            selected_sids, budget_engine, job.enterprise_id,
            str(job.payload.get("source_id") or ""), parameter,
            spec.scope_namespace or "amazon"
        ) if spec.scope_kind == "store" else selected_wids)
        if allowed is None or parameter not in filters:
            raise PermanentJobError("官方资源缺少已审批范围", code="sync.contract_scope_required")
        requested = [value.strip() for value in str(filters[parameter]).split(",")
                     if value.strip()]
        is_seller_id_scope = parameter.replace("_", "").lower() in SELLER_ID_SCOPE_PARAMETERS
        if is_seller_id_scope:
            requested_values = sorted(set(requested))
            allowed_values = {str(value) for value in allowed}
            # API fanout uses approved numeric store ids as a virtual scope
            # value; resolve them to opaque Amazon seller ids before sending
            # the provider request. Direct callers may already provide the
            # opaque seller ids, which remain accepted and scope-checked.
            if requested_values and all(value.isdigit() for value in requested_values):
                requested_sids = {int(value) for value in requested_values}
                approved_sids = set(selected_sids or [])
                if not requested_sids or not requested_sids.issubset(approved_sids):
                    raise PermanentJobError(
                        "官方资源超出已审批范围", code="sync.contract_scope_invalid"
                    )
                seller_by_sid = {
                    sid: str(value)
                    for sid, value in zip(selected_sids or [], allowed, strict=True)
                }
                if any(sid not in seller_by_sid for sid in requested_sids):
                    raise PermanentJobError(
                        "官方资源缺少 seller_id 映射",
                        code="sync.contract_scope_mapping_missing",
                    )
                normalized_values = sorted(seller_by_sid[sid] for sid in requested_sids)
            else:
                if not requested_values or not set(requested_values).issubset(allowed_values):
                    raise PermanentJobError(
                        "官方资源超出已审批范围", code="sync.contract_scope_invalid"
                    )
                normalized_values = requested_values
        else:
            try:
                requested_ids = sorted({int(value) for value in requested})
            except ValueError:
                requested_ids = []
            if not requested_ids or not set(requested_ids).issubset(set(allowed)):
                raise PermanentJobError(
                    "官方资源超出已审批范围", code="sync.contract_scope_invalid"
                )
            normalized_values = requested_ids
        filters[parameter] = (normalized_values if spec.scope_parameter_mode == "list" else
                              ",".join(str(value) for value in normalized_values)
                              if spec.scope_parameter_mode == "csv" else normalized_values[0])
    if resource in SINGLE_STORE_RESOURCES:
        requested_sid = int(str(filters["sid"]))
        if selected_sids is not None and requested_sid not in selected_sids:
            raise PermanentJobError("请求店铺不在授权范围", code="sync.store_scope_invalid")
        selected_sids = [requested_sid]
    if selected_sids is not None and spec.scope_kind is None:
        if resource == "orders":
            filters["sid_list"] = selected_sids
        elif resource == "fulfillments":
            filters["sid_arr"] = selected_sids
        elif resource == "fba_shipments":
            filters["sids"] = ",".join(str(sid) for sid in selected_sids)
        elif resource == "finance":
            filters.pop("sid", None)
            filters["sids"] = selected_sids
        elif resource == "customer_service":
            filters.pop("sid", None)
            filters["sids"] = ",".join(str(sid) for sid in selected_sids)
        elif resource in {"advertising", "source_reports"}:
            filters["sid"] = selected_sids[0]
        elif resource in {"listings", "fbm_orders"}:
            filters["sid"] = str(selected_sids[0])
        else:
            filters["sid"] = ",".join(str(sid) for sid in selected_sids)
    if selected_wids is not None and spec.scope_kind is None:
        if resource in {"inbound_orders", "outbound_orders"}:
            if len(selected_wids) != 1:
                raise PermanentJobError(
                    "出入库单每个任务必须选择一个仓库",
                    code="sync.warehouse_single_partition_required",
                )
            filters["wid"] = selected_wids[0]
        elif resource == "inventory_statements":
            filters["wids"] = ",".join(str(wid) for wid in selected_wids)
        else:
            filters["wid"] = ",".join(str(wid) for wid in selected_wids)
    try:
        request_filters = materialize_request_parameters(spec, filters)
    except ValueError:
        raise PermanentJobError(
            "资源请求结构无效", code="sync.parameters_invalid"
        ) from None
    app_id, app_secret = _lingxing_credentials(
        str(job.payload.get("credential_ref") or ""), settings
    )
    if not app_id or not app_secret:
        raise PermanentJobError("领星凭据未配置", code="sync.credentials_missing")
    try:
        config = LingxingConfig(
            app_id, app_secret, settings.lingxing_base_url
        )
        provider = (token_cache.provider(app_id, app_secret, settings.lingxing_base_url)
                    if token_cache is not None else LingxingTokenProvider(
                        app_id, app_secret, settings.lingxing_base_url, transport=transport,
                    ))
        limiter = (SourceRateLimiter(budget_engine, app_id, ensure_active=context.ensure_active)
                   if budget_engine is not None else None)
        client = LingxingClient(config, transport=transport, credential_provider=provider,
                               rate_limiter=limiter)
    except ValueError as exc:
        raise PermanentJobError(
            "领星 Host 不在官方只读 allowlist", code="sync.host_blocked"
        ) from exc

    async def fetch_page(page: int) -> dict[str, object]:
        context.ensure_active()
        if validate_scope is not None:
            validate_scope()
        try:
            parameters = page_parameters(spec, request_filters, page)
            if method == "POST":
                return await client.request_json_post_with_retry(
                    path, body=parameters
                )
            return await client.request_with_retry(path, params=parameters)
        except (JobStateConflict, RetryableJobError, PermanentJobError):
            raise
        except LingxingBusinessError as exc:
            raise PermanentJobError("领星业务请求失败",
                                    code=f"sync.external_business.{exc.code}") from exc
        except RuntimeError as exc:
            if str(exc) in {"rate_limited", "external_retryable"}:
                raise RetryableJobError("领星暂时不可用", code="sync.external_retryable") from exc
            raise PermanentJobError("领星业务请求失败", code="sync.external_permanent") from exc

    start_page = max(1, int(str(job.payload.get("checkpoint", job.payload.get("page", 1)))))
    archive_root = Path(
        settings.source_archive_path or Path.cwd() / "var" / "source-archive"
    ).resolve()
    archived_pages: list[dict[str, object]] = []
    archive = RawArchive(archive_root)

    def archive_page(page: int, payload: dict[str, object], *,
                     schema_status: str | None = None) -> dict[str, object]:
        rows = response_value(payload, spec.rows_path)
        observed_schema = schema_status or spec.schema_status
        if (observed_schema == "confirmed" and rows is not None
                and selected_sids is not None
                and spec.scope_kind is None and not _store_response_in_scope(
            resource, rows, selected_sids
        )):
            raise PermanentJobError(
                "响应包含所选店铺范围外数据", code="sync.response_scope_mismatch")
        if (observed_schema == "confirmed" and rows is not None
                and selected_wids is not None
                and spec.scope_kind is None
                and not _warehouse_response_in_scope(
            rows, selected_wids
        )):
            raise PermanentJobError(
                "响应包含所选仓库范围外数据", code="sync.response_scope_mismatch")
        blob = archive.write(payload)
        return {
            "page": page, "content_hash": blob.content_hash,
            "storage_key": blob.storage_key,
            "byte_count": blob.byte_count,
            "row_count": len(rows) if isinstance(rows, list) else int(rows is not None),
            "cursor": str(page),
            "schema_status": observed_schema,
        }

    async def fetch_pages() -> list[dict[str, object]]:
        page = start_page
        started = monotonic()
        while True:
            payload = await fetch_page(page)
            context.ensure_active()
            if validate_scope is not None:
                validate_scope()
            observed = response_value(payload, spec.rows_path)
            explicit_empty = _response_path_is_explicit_null(payload, spec.rows_path)
            data = [] if explicit_empty else observed
            shape_valid = data is not None and (
                not spec.paginated or isinstance(data, list))
            schema_status = spec.schema_status if shape_valid else "schema_pending"
            page_result = archive_page(page, payload, schema_status=schema_status)
            archived_pages.append(page_result)
            if persist_page is not None:
                persist_page(page_result, payload, dict(request_filters))
            if not shape_valid:
                raise PermanentJobError("响应页结构待确认", code="sync.schema_pending")
            # Probe jobs validate authentication, scope, request shape, response shape and
            # durable Raw archival without accidentally expanding into a full extraction.
            if job.payload.get("probe"):
                return archived_pages
            has_more = isinstance(data, list) and len(data) >= page_size
            total = response_value(payload, spec.total_path)
            if isinstance(total, int):
                has_more = total > (page * page_size)
                if has_more and not data:
                    raise RetryableJobError("分页数量不一致", code="sync.page_count_mismatch")
            if not spec.paginated or not has_more:
                return archived_pages
            remaining = getattr(context, "deadline_monotonic", float("inf")) - monotonic()
            if persist_page is not None and (
                page - start_page + 1 >= SYNC_PAGES_PER_TURN
                or monotonic() - started >= 180 or remaining <= 30
            ):
                raise JobContinuation(page)
            page += 1
            if page - start_page >= 1000:
                raise PermanentJobError("领星分页超过安全上限", code="sync.pagination_limit")

    async def fetch_report() -> None:
        def ensure_current() -> None:
            context.ensure_active()
            if validate_scope is not None:
                validate_scope()

        reader = ReportReader(client, download_hosts=frozenset(settings.report_download_hosts),
                              download_transport=transport, ensure_active=ensure_current)
        ensure_current()
        try:
            report = await reader.poll(request_filters)
        except (JobStateConflict, RetryableJobError, PermanentJobError):
            raise
        except RuntimeError as exc:
            if str(exc) in {"rate_limited", "external_retryable"}:
                raise RetryableJobError(
                    "报告查询暂时不可用", code="sync.external_retryable",
                ) from None
            raise PermanentJobError("报告状态查询失败", code="sync.report_query_failed") from None
        ensure_current()
        page = max(1, int(getattr(job, "attempt", 1))) * 2 - 1
        safe = report.safe_payload()
        item = archive_page(page, safe)
        # Report lifecycle metadata is a control record; only downloaded report
        # contents can contribute business row counts.
        item["row_count"] = 0
        item["cursor"] = f"report:{page}:{report.progress_status}"
        archived_pages.append(item)
        if persist_page is not None:
            persist_page(item, safe, dict(request_filters))
        if report.state == "waiting":
            raise RetryableJobError(
                "报告正在生成", code=f"sync.report_{report.progress_status.lower()}",
                retry_after_seconds=30,
            )
        if report.state != "ready":
            raise PermanentJobError("报告不可下载", code=f"sync.report_{report.state}")
        try:
            content = await reader.download(report)
        except (JobStateConflict, RetryableJobError, PermanentJobError):
            raise
        except RuntimeError as exc:
            if str(exc) in {"external_retryable", "report.download_link_expired"}:
                raise RetryableJobError("报告下载暂时不可用", code="sync.report_download_retry",
                                        retry_after_seconds=30) from None
            raise PermanentJobError("报告下载未就绪", code=f"sync.{exc}") from None
        ensure_current()
        blob = archive.write_bytes(content)
        item = {"page": page + 1, "content_hash": blob.content_hash,
                "storage_key": blob.storage_key, "byte_count": blob.byte_count,
                "row_count": 0, "cursor": f"report:{page + 1}:DOWNLOADED"}
        archived_pages.append(item)
        if persist_page is not None:
            persist_page(item, {"report_document_id": report.document_id,
                                "compression_algorithm": report.compression},
                         dict(request_filters))

    async def execute_pages() -> None:
        try:
            if spec.execution_mode == "async_report":
                await fetch_report()
            else:
                await fetch_pages()
        finally:
            await client.close()

    asyncio.run(execute_pages())
    context.ensure_active()
    last = archived_pages[-1]
    return {
        "provider": "lingxing",
        "resource_key": resource,
        "content_hash": last["content_hash"],
        "storage_key": last["storage_key"],
        "byte_count": last["byte_count"],
        "row_count": sum(_result_int(item["row_count"]) for item in archived_pages),
        "cursor": str(last["cursor"]),
        "pages": archived_pages,
    }


def lingxing_sync_handler(job: JobRecord, context: JobExecutionContext) -> Mapping[str, object]:
    return _execute_lingxing_sync(job, context, load_settings())


def _raw_row_count(payload: Mapping[str, object]) -> int:
    data = payload.get("data")
    if isinstance(data, list):
        return len(data)
    if isinstance(data, dict):
        for key in ("list", "items", "records"):
            value = data.get(key)
            if isinstance(value, list):
                return len(value)
    return 0


def _store_response_in_scope(resource: str, rows: object,
                             selected_sids: list[int]) -> bool:
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        return False
    allowed = {str(sid) for sid in selected_sids}
    if resource in {"fbm_orders", "advertising", "finance", "customer_service"}:
        # The official FBM list omits sid from each row. Its required single-sid
        # request is persisted with the Raw manifest and supplies the scope identity.
        return True
    if resource == "fba_shipments":
        return all(
            isinstance(relations := row.get("relate_list"), list)
            and bool(relations)
            and all(isinstance(item, dict) and str(item.get("sid")) in allowed
                    for item in relations)
            for row in rows
        )
    if resource == "fba_inventory":
        for row in rows:
            sid = str(row.get("sid"))
            if sid in allowed:
                continue
            shared = row.get("fba_storage_quantity_list")
            if sid != "0" or not isinstance(shared, list) or not shared or any(
                not isinstance(item, dict) or str(item.get("sid")) not in allowed
                for item in shared
            ):
                return False
        return True
    return all(str(row.get("sid")) in allowed for row in rows)


def _warehouse_response_in_scope(rows: object, selected_wids: list[int]) -> bool:
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        return False
    allowed = {str(wid) for wid in selected_wids}
    return all(str(row.get("wid")) in allowed for row in rows)


def resolve_order_store_filter(
    snapshot: object, engine: Engine | None, enterprise_id: str, source_key: str,
    namespace: str = "amazon",
) -> list[int] | None:
    mapping, project_bound = _resolve_entity_scope_mapping(
        engine, enterprise_id, source_key, "store"
    )
    return order_store_filter(snapshot, mapping, required=project_bound, namespace=namespace)


def resolve_store_scope_parameter(
    selected_sids: list[int] | None,
    engine: Engine | None,
    enterprise_id: str,
    source_key: str,
    parameter: str,
    namespace: str = "amazon",
) -> list[str] | list[int] | None:
    """Resolve the provider's approved value for a store-scoped parameter.

    Most Lingxing store scopes use numeric ``sid`` values.  FBA cost-center
    contracts instead require Amazon ``seller_id`` strings, which are a
    separate provider identity and must be looked up from Raw-derived,
    store-scoped dependency values rather than accepted from the request.
    """
    if (selected_sids is None
            or parameter.replace("_", "").lower() not in SELLER_ID_SCOPE_PARAMETERS):
        return selected_sids
    if engine is None:
        return None
    prefix = "store:multiplatform:" if namespace == "multiplatform" else "store:"
    with engine.connect() as connection:
        source = connection.execute(text(
            "SELECT id, business_unit_id FROM external_systems "
            "WHERE enterprise_id=:enterprise AND system_key=:source"
        ), {"enterprise": enterprise_id, "source": source_key}).first()
        if source is None:
            return None
        source_id, business_unit_id = str(source[0]), source[1]
        business_unit_filter = ("AND business_unit_id=:business_unit"
                                if business_unit_id is not None else "")
        rows = connection.execute(text(
            "SELECT external_value, scope_external_key "
            "FROM source_dependency_values "
            "WHERE enterprise_id=:enterprise AND external_system_id=:source_id "
            "AND value_type='seller_id' AND scope_kind='store' AND status='active' "
            f"{business_unit_filter}"
        ), {"enterprise": enterprise_id, "source_id": source_id,
            **({"business_unit": business_unit_id} if business_unit_id is not None else {})}).all()
    by_scope: dict[str, set[str]] = {}
    for value, scope_key in rows:
        by_scope.setdefault(str(scope_key), set()).add(str(value))
    resolved: list[str] = []
    seen: set[str] = set()
    for sid in selected_sids:
        values = by_scope.get(f"{prefix}{sid}", set())
        if not values:
            raise PermanentJobError(
                "店铺缺少 seller_id 映射", code="sync.contract_scope_mapping_missing"
            )
        for value in sorted(values):
            if value not in seen:
                resolved.append(value)
                seen.add(value)
    return resolved


def resolve_warehouse_filter(
    snapshot: object, engine: Engine | None, enterprise_id: str, source_key: str,
) -> list[int] | None:
    mapping, project_bound = _resolve_entity_scope_mapping(
        engine, enterprise_id, source_key, "warehouse"
    )
    return warehouse_scope_filter(snapshot, mapping, required=project_bound)


def _resolve_entity_scope_mapping(
    engine: Engine | None, enterprise_id: str, source_key: str, entity_type: str,
) -> tuple[dict[str, str] | None, bool]:
    if engine is None:
        return None, False
    with engine.connect() as connection:
        source_unit = connection.execute(text(
            "SELECT business_unit_id FROM external_systems "
            "WHERE enterprise_id=:enterprise AND system_key=:source"
        ), {"enterprise": enterprise_id, "source": source_key}).scalar_one_or_none()
        rows = connection.execute(text(
            "SELECT e.canonical_key, o.external_key FROM canonical_entity_origins o "
            "JOIN business_entities e ON e.id=o.entity_id AND e.enterprise_id=o.enterprise_id "
            "JOIN external_systems s ON s.id=o.external_system_id "
            "WHERE o.enterprise_id=:enterprise AND s.system_key=:source "
            "AND e.entity_type=:entity_type AND o.status='assigned' "
            "AND (s.business_unit_id IS NULL OR o.business_unit_id=s.business_unit_id)"
        ), {"enterprise": enterprise_id, "source": source_key,
             "entity_type": entity_type})
        mapping = {str(row[0]): str(row[1]) for row in rows}
    return mapping, source_unit is not None


def order_store_filter(snapshot: object, mapping: dict[str, str] | None = None, *,
                       required: bool = False, namespace: str = "amazon") -> list[int] | None:
    """Restricted scopes must never fall back to account-wide acquisition."""
    restricted = (isinstance(snapshot, dict) and snapshot.get("scope_level") in {
        "business_unit", "store", "warehouse"
    })
    if not restricted and not required:
        return None
    stores = snapshot.get("store_ids") if isinstance(snapshot, dict) else None
    if not isinstance(stores, list) or not stores or len(stores) > 20:
        raise PermanentJobError("订单店铺范围须为 1 至 20 家", code="sync.store_partition_required")
    if namespace not in {"amazon", "multiplatform"}:
        raise PermanentJobError("店铺命名空间无效", code="sync.store_namespace_invalid")
    ids: list[int] = []
    for key in stores:
        if not isinstance(key, str) or mapping is None or key not in mapping:
            raise PermanentJobError("订单店铺标识无效", code="sync.store_scope_invalid")
        value = mapping[key]
        external_id = (value.removeprefix("multiplatform:")
                       if namespace == "multiplatform"
                       and value.startswith("multiplatform:") else
                       value if namespace == "amazon" and not value.startswith("multiplatform:")
                       else "")
        if external_id.isascii() and external_id.isdecimal() and int(external_id) > 0:
            ids.append(int(external_id))
    if not ids:
        raise PermanentJobError("店铺命名空间未获批准", code="sync.store_namespace_unapproved")
    return sorted(set(ids))


def warehouse_scope_filter(snapshot: object, mapping: dict[str, str] | None = None, *,
                           required: bool = False) -> list[int] | None:
    restricted = (isinstance(snapshot, dict) and snapshot.get("scope_level") in {
        "business_unit", "store", "warehouse"
    })
    if not restricted and not required:
        return None
    warehouses = snapshot.get("warehouse_ids") if isinstance(snapshot, dict) else None
    if not isinstance(warehouses, list) or not warehouses or len(warehouses) > 100:
        raise PermanentJobError(
            "仓库范围须为 1 至 100 个", code="sync.warehouse_partition_required"
        )
    ids: list[int] = []
    for key in warehouses:
        if not isinstance(key, str) or mapping is None or key not in mapping:
            raise PermanentJobError("仓库标识无效", code="sync.warehouse_scope_invalid")
        value = mapping[key]
        if not value.isascii() or not value.isdecimal() or int(value) <= 0:
            raise PermanentJobError("仓库标识无效", code="sync.warehouse_scope_invalid")
        ids.append(int(value))
    return sorted(set(ids))


def _lingxing_credentials(
    credential_ref: str, settings: WorkerSettings
) -> tuple[str, str]:
    """Resolve a reference from the process environment without logging secrets."""
    if credential_ref.startswith("env:"):
        prefix = credential_ref.removeprefix("env:")
        return getenv(f"{prefix}_APP_ID", ""), getenv(f"{prefix}_APP_SECRET", "")
    if credential_ref:
        raise PermanentJobError(
            "凭据引用类型未配置", code="sync.credential_provider_unsupported"
        )
    return settings.lingxing_app_id, settings.lingxing_app_secret


def _result_int(value: object) -> int:
    if isinstance(value, int):
        return value
    raise PermanentJobError("同步结果计数无效", code="sync.result_invalid")


def build_lingxing_sync_handler(
    settings: WorkerSettings,
    engine: Engine,
    *,
    transport: httpx.AsyncBaseTransport | None = None,
) -> JobHandler:
    store = SyncStore(engine)
    database = Database.from_engine(engine)
    token_cache = LingxingTokenCache(transport=transport)

    def handler(job: JobRecord, context: JobExecutionContext) -> Mapping[str, object]:
        if job.payload.get("provider") == "mock":
            return execute_mock_source(engine, job, context)
        source_key = str(job.payload.get("source_id") or "")
        resource_key = str(job.payload.get("resource_key") or "")
        spec = resource_spec(resource_key)
        if spec is None or not spec.path:
            raise PermanentJobError("资源未进入只读目录", code="sync.resource_unsupported")
        partition = str(job.payload.get("partition") or "default")
        try:
            ref = store.begin_resource(
                sync_run_id=job.run_id,
                source_key=source_key,
                resource_key=resource_key,
                partition=partition,
                enterprise_id=job.enterprise_id,
                fence=getattr(context, "fence", None),
            )
        except LookupError as exc:
            raise PermanentJobError(
                "同步资源未登记或已停用", code="sync.resource_not_registered"
            ) from exc
        try:
            checkpoint = store.checkpoint(ref, partition)
            scope_snapshot = _validate_source_job(database, job, ref.resource_id)
            if "raw_replay" in job.payload:
                with engine.connect() as connection:
                    source_id = _source_id(connection, ref.resource_id)
                replay_result = replay_archived_page(database, store, ref, job, context, spec,
                    Path(settings.source_archive_path or Path.cwd() / "var" / "source-archive"),
                    source_id, lambda: _validate_source_job(database, job, ref.resource_id,
                                                            selection=scope_snapshot))
                store.finish_resource(ref.run_id, fence=getattr(context, "fence", None))
                return replay_result
            if checkpoint and checkpoint.isdigit():
                job = replace(job, payload={**job.payload, "checkpoint": int(checkpoint) + 1})
            def persist_page(item: dict[str, object], payload: dict[str, object],
                             request_parameters: dict[str, object]) -> bool:
                observed_at = datetime.now(UTC)
                deferred = job.payload.get("projection_mode") == "deferred"
                def after_archive(connection: Connection, manifest: str, status: str) -> None:
                    if status == "confirmed":
                        persist_dependency_values(
                            connection, enterprise_id=job.enterprise_id,
                            external_system_id=_source_id(connection, ref.resource_id),
                            source_resource_id=ref.resource_id, resource_key=resource_key,
                            manifest_id=manifest, payload=payload,
                            request_parameters=request_parameters, observed_at=observed_at)
                    if deferred:
                        defer_projection(connection, job=job, manifest_id=manifest,
                                         schema_status=status, scope_snapshot=scope_snapshot)
                return store.record_page(ref, partition=partition, cursor=str(item["cursor"]),
                    storage_key=str(item["storage_key"]), content_hash=str(item["content_hash"]),
                    byte_count=_result_int(item["byte_count"]),
                    row_count=_result_int(item["row_count"]), page_number=_result_int(item["page"]),
                    schema_status=str(item.get("schema_status") or spec.schema_status),
                    fetched_at=observed_at,
                    request_parameters=request_parameters,
                    fence=getattr(context, "fence", None),
                    write_canonical=(lambda connection, manifest: persist_canonical_page(
                        connection, enterprise_id=job.enterprise_id,
                        source_id=_source_id(connection, ref.resource_id),
                        resource_key=resource_key,
                        manifest_id=manifest, payload=payload, observed_at=observed_at,
                        scope_snapshot=scope_snapshot,
                        request_parameters=request_parameters).accepted
                    ) if can_project_to_core(spec)
                    and not deferred else None,
                    after_archive=after_archive)
            result = _execute_lingxing_sync(
                job,
                context,
                settings,
                transport=transport,
                budget_engine=engine,
                token_cache=token_cache,
                validate_scope=lambda: _validate_source_job(
                    database, job, ref.resource_id, selection=scope_snapshot),
                persist_page=persist_page,
            )
        except JobContinuation:
            store.finish_resource(ref.run_id, status="queued",
                                  fence=getattr(context, "fence", None))
            raise
        except JobStateConflict:
            # Cancellation is persisted by its owner; a stale Worker cannot change the ledger.
            raise
        except RetryableJobError as exc:
            exhausted = (getattr(job, "attempt", 1) - getattr(job, "continuation_count", 0)
                         >= getattr(job, "max_attempts", 3))
            store.finish_resource(ref.run_id, status="failed" if exhausted else "queued",
                                  error_code=exc.code, fence=getattr(context, "fence", None))
            raise
        except PermanentJobError as exc:
            status = "cancelled" if exc.code == "sync.report_cancelled" else "failed"
            store.finish_resource(ref.run_id,
                                  status=status, error_code=exc.code,
                                  fence=getattr(context, "fence", None))
            raise
        except Exception:
            store.finish_resource(ref.run_id, status="failed", error_code="sync.internal_error",
                                  fence=getattr(context, "fence", None))
            raise
        store.finish_resource(ref.run_id, fence=getattr(context, "fence", None))
        return result

    return handler


def _source_id(connection: object, resource_id: str) -> str:
    from sqlalchemy import Connection, text
    if not isinstance(connection, Connection):
        raise TypeError("source connection invalid")
    return str(connection.execute(text(
        "SELECT external_system_id FROM source_resources WHERE id = :id"
    ), {"id": resource_id}).scalar_one())


def _validate_source_job(database: Database, job: JobRecord, resource_id: str, *,
                         selection: dict[str, object] | None = None) -> dict[str, object]:
    from sqlalchemy import text
    with database.engine.connect() as connection:
        active = connection.execute(text(
            "SELECT sr.id, sr.version FROM source_resources sr JOIN external_systems es "
            "ON sr.external_system_id = es.id JOIN sync_runs run "
            "ON run.external_system_id = es.id WHERE sr.id = :resource_id "
            "AND es.enterprise_id = :enterprise_id AND sr.enabled = true "
            "AND es.status <> 'disabled' AND run.id = :run_id "
            "AND run.cancel_requested_at IS NULL"
        ), {"resource_id": resource_id, "enterprise_id": job.enterprise_id,
            "run_id": job.run_id}).mappings().one_or_none()
    if active is None:
        raise PermanentJobError("来源或运行已停用", code="sync.source_disabled")
    requested_version = job.payload.get("resource_version")
    if requested_version is not None and active["version"] != requested_version:
        raise PermanentJobError("来源资源契约已变化", code="sync.resource_contract_changed")
    snapshot = getattr(job, "actor_snapshot", {})
    account_id = snapshot.get("user_account_id")
    if not account_id:
        raise PermanentJobError("任务缺少可信发起人", code="sync.actor_missing")
    try:
        actor = resolve_database_actor(
            database, login_name="", user_account_id=str(account_id),
            enterprise_id=job.enterprise_id, request_id=job.request_id, run_id=job.run_id,
        )
        require_permission(actor, "source.manage", database, resource_type="source",
                           resource_key=resource_id, scope_type="enterprise",
                           scope_id=job.enterprise_id)
        if selection is None:
            requested = job.payload.get("scope_snapshot")
            selection = requested if isinstance(requested, dict) else None
        current = build_scope_context(database, actor, selection=selection
                                      if isinstance(selection, dict) else None)
        if job.enterprise_id not in current.selected_enterprise_ids:
            raise ApiProblem(status_code=403, code="source.enterprise_denied",
                             message="来源法人不在当前范围内")
        return current.snapshot()
    except ApiProblem:
        raise PermanentJobError(
            "同步发起人的权限或范围已失效", code="sync.authorization_revoked"
        ) from None


def build_analysis_review_handler(
    settings: WorkerSettings,
    *,
    transport: httpx.BaseTransport | None = None,
) -> JobHandler:
    def handler(job: JobRecord, context: JobExecutionContext) -> Mapping[str, object]:
        context.ensure_active()
        if not job.execution_token:
            raise PermanentJobError(
                "巡店任务缺少当前 Worker 领取令牌",
                code="authorization.worker_execution_token_missing",
            )
        try:
            with httpx.Client(
                base_url=settings.api_base_url,
                timeout=settings.api_timeout_seconds,
                transport=transport,
            ) as client:
                response = client.post(
                    f"/api/v1/analysis/internal/jobs/{job.id}/execute",
                    headers={
                        REQUEST_ID_HEADER: job.request_id,
                        RUN_ID_HEADER: job.run_id,
                        WORKER_ID_HEADER: settings.worker_id,
                        JOB_EXECUTION_TOKEN_HEADER: job.execution_token,
                    },
                )
        except httpx.HTTPError as exc:
            raise RetryableJobError(
                f"巡店 API 暂不可用：{exc}",
                code="analysis.schedule.api_unavailable",
            ) from exc
        context.ensure_active()
        if response.status_code >= 500:
            raise RetryableJobError(
                "巡店 API 返回服务端错误",
                code="analysis.schedule.api_server_error",
            )
        if response.status_code >= 400:
            raise PermanentJobError(
                _api_error_message(response),
                code=_api_error_code(response),
            )
        payload = response.json()
        if not isinstance(payload, dict):
            raise PermanentJobError(
                "巡店 API 返回了无效响应",
                code="analysis.schedule.api_invalid_response",
            )
        return {str(key): value for key, value in payload.items()}

    return handler


def _api_error_code(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        return "analysis.schedule.api_rejected"
    if isinstance(payload, dict):
        error = payload.get("error")
        if isinstance(error, dict) and isinstance(error.get("code"), str):
            return str(error["code"])
    return "analysis.schedule.api_rejected"


def _api_error_message(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        return f"巡店 API 拒绝任务（HTTP {response.status_code}）"
    if isinstance(payload, dict):
        error = payload.get("error")
        if isinstance(error, dict) and isinstance(error.get("message"), str):
            return str(error["message"])
    return f"巡店 API 拒绝任务（HTTP {response.status_code}）"


def create_worker_engine(settings: WorkerSettings) -> Engine:
    connect_args = (
        {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
    )
    pool_options: dict[str, int | float] = {}
    if not settings.database_url.startswith("sqlite"):
        pool_options = {
            "pool_size": settings.database_pool_size,
            "max_overflow": settings.database_max_overflow,
            "pool_timeout": settings.database_pool_timeout_seconds,
            "pool_recycle": settings.database_pool_recycle_seconds,
        }
    return create_engine(
        settings.database_url,
        pool_pre_ping=True,
        connect_args=connect_args,
        **pool_options,
    )


def wait_for_schema(engine: Engine, timeout_seconds: float) -> None:
    deadline = monotonic() + timeout_seconds
    while True:
        try:
            if inspect(engine).has_table("background_jobs"):
                return
        except Exception:
            pass
        if monotonic() >= deadline:
            raise RuntimeError("后台任务表尚未就绪；请确认数据库可访问并先执行 pnpm db:upgrade")
        sleep(0.2)


def build_runner(settings: WorkerSettings, engine: Engine) -> WorkerRunner:
    return WorkerRunner(
        JobRepository(engine),
        {
            "system.noop": noop_handler,
            "data-source.sync": build_lingxing_sync_handler(settings, engine),
            "analysis.daily-store-review": build_analysis_review_handler(settings),
        },
        worker_id=settings.worker_id,
        poll_seconds=settings.poll_seconds,
        lease_seconds=settings.lease_seconds,
        retry_delay_seconds=settings.retry_delay_seconds,
        before_poll=SourceScheduleTick(engine, enabled=settings.lingxing_enabled),
    )


def run(*, once: bool = False, stop_event: Event | None = None) -> int:
    settings = load_settings()
    engine = create_worker_engine(settings)
    try:
        wait_for_schema(engine, settings.schema_wait_seconds)
        runner = build_runner(settings, engine)
        if once:
            runner.run_once()
            return 0
        runner.run_forever(stop_event or Event())
        return 0
    finally:
        engine.dispose()
