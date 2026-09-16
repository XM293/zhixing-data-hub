from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

API_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(API_ROOT / "src"))


async def verify(*, probe_ai: bool) -> int:
    from zhixing_api.ai_provider import AIProviderError, ResponsesAIProvider
    from zhixing_api.config import load_settings, validate_settings
    from zhixing_api.database import Database
    from zhixing_api.object_storage import build_object_storage
    from zhixing_api.redis_coordinator import build_redis_coordinator

    settings = load_settings()
    result: dict[str, object] = {"status": "ready", "environment": settings.environment}
    errors: list[str] = []
    try:
        validate_settings(settings)
    except ValueError as exc:
        errors.append(str(exc))

    database = Database(
        settings.database_url,
        pool_size=settings.database_pool_size,
        max_overflow=settings.database_max_overflow,
        pool_timeout_seconds=settings.database_pool_timeout_seconds,
        pool_recycle_seconds=settings.database_pool_recycle_seconds,
    )
    storage = build_object_storage(
        provider=settings.file_asset_storage_provider,
        local_root=settings.file_asset_storage_path,
        s3_endpoint=settings.s3_endpoint,
        s3_region=settings.s3_region,
        s3_bucket=settings.s3_bucket,
        s3_access_key=settings.s3_access_key,
        s3_secret_key=settings.s3_secret_key,
        s3_force_path_style=settings.s3_force_path_style,
        s3_auto_create_bucket=settings.s3_auto_create_bucket,
    )
    coordinator = build_redis_coordinator(
        enabled=settings.redis_enabled,
        url=settings.redis_url,
        key_prefix=settings.redis_key_prefix,
    )
    try:
        database_ready = database.ready()
        revision = database.revision() if database_ready else None
        migration_head = database.migration_head()
        migrations_ready = bool(database_ready and revision == migration_head)
        result["database"] = {
            "ready": database_ready,
            "engine": database.engine_name,
            "revision": revision,
            "migration_head": migration_head,
            "migrations_ready": migrations_ready,
        }
        if not database_ready:
            errors.append("database")
        elif not migrations_ready:
            errors.append("database-migrations")
        storage_ready = storage.ready()
        result["object_storage"] = {
            "ready": storage_ready,
            "provider": storage.provider_key,
        }
        if not storage_ready:
            errors.append("object-storage")
        redis_ready = await coordinator.ready()
        result["redis"] = {"ready": redis_ready, "enabled": settings.redis_enabled}
        if not redis_ready:
            errors.append("redis")

        ai_result: dict[str, object] = {
            "enabled": settings.ai_enabled,
            "configured": bool(settings.ai_api_key),
            "model": settings.ai_model,
            "probed": probe_ai,
        }
        if probe_ai:
            try:
                completion = await ResponsesAIProvider().generate(
                    settings,
                    instructions="返回运行依赖探针状态。",
                    input_text="只返回 status=ok 和简短 message。",
                    run_id="runtime-verification",
                    schema_name="runtime_verification",
                    response_schema={
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "status": {"type": "string", "enum": ["ok"]},
                            "message": {"type": "string"},
                        },
                        "required": ["status", "message"],
                    },
                )
                ai_result.update(
                    {
                        "ready": completion.payload.get("status") == "ok",
                        "structured_output": completion.structured_output,
                        "input_tokens": completion.input_tokens,
                        "output_tokens": completion.output_tokens,
                    }
                )
            except AIProviderError as exc:
                ai_result["ready"] = False
                ai_result["error"] = str(exc)
                errors.append("ai-provider")
        result["ai"] = ai_result
    finally:
        await coordinator.close()
        database.dispose()

    if errors:
        result["status"] = "failed"
        result["failed_dependencies"] = errors
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if errors else 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--probe-ai", action="store_true")
    args = parser.parse_args()
    return asyncio.run(verify(probe_ai=args.probe_ai))


if __name__ == "__main__":
    raise SystemExit(main())
