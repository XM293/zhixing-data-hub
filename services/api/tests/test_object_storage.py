from pathlib import Path

import pytest

from zhixing_api.object_storage import (
    LocalObjectStorage,
    ObjectStorageError,
    build_object_storage,
)


def test_local_object_storage_round_trip_and_delete(tmp_path: Path) -> None:
    storage = LocalObjectStorage(str(tmp_path / "objects"))

    storage.put("enterprise/asset", b"content")

    assert storage.ready() is True
    assert storage.get("enterprise/asset") == b"content"
    storage.delete("enterprise/asset")
    with pytest.raises(ObjectStorageError, match="不存在"):
        storage.get("enterprise/asset")


def test_local_object_storage_rejects_path_escape(tmp_path: Path) -> None:
    storage = LocalObjectStorage(str(tmp_path / "objects"))

    with pytest.raises(ObjectStorageError, match="越过"):
        storage.put("../outside", b"blocked")


def test_storage_registry_routes_legacy_local_assets(tmp_path: Path) -> None:
    registry = build_object_storage(
        provider="local",
        local_root=str(tmp_path / "objects"),
        s3_endpoint="",
        s3_region="us-east-1",
        s3_bucket="",
        s3_access_key="",
        s3_secret_key="",
        s3_force_path_style=False,
        s3_auto_create_bucket=False,
    )
    registry.put("enterprise/legacy", b"legacy")

    assert registry.provider_key == "local-object-storage"
    assert registry.get("local-object-storage", "enterprise/legacy") == b"legacy"
