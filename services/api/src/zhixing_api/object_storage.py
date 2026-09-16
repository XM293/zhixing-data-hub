from __future__ import annotations

from pathlib import Path
from typing import Protocol


class ObjectStorageError(RuntimeError):
    """Raised when an object storage operation cannot be completed."""


class ObjectStorage(Protocol):
    provider_key: str

    def put(self, object_key: str, content: bytes) -> None: ...

    def get(self, object_key: str) -> bytes: ...

    def delete(self, object_key: str) -> None: ...

    def ready(self) -> bool: ...


class LocalObjectStorage:
    provider_key = "local-object-storage"

    def __init__(self, root: str) -> None:
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def put(self, object_key: str, content: bytes) -> None:
        path = self._path(object_key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)

    def get(self, object_key: str) -> bytes:
        path = self._path(object_key)
        if not path.is_file():
            raise ObjectStorageError("文件对象不存在")
        return path.read_bytes()

    def delete(self, object_key: str) -> None:
        path = self._path(object_key)
        if path.is_file():
            path.unlink()

    def ready(self) -> bool:
        return self.root.is_dir()

    def _path(self, object_key: str) -> Path:
        if not object_key or "\\" in object_key:
            raise ObjectStorageError("文件对象键无效")
        path = (self.root / object_key).resolve()
        if self.root not in path.parents:
            raise ObjectStorageError("文件对象键越过存储根目录")
        return path


class S3ObjectStorage:
    provider_key = "s3-object-storage"

    def __init__(
        self,
        *,
        endpoint: str,
        region: str,
        bucket: str,
        access_key: str,
        secret_key: str,
        force_path_style: bool,
        auto_create_bucket: bool,
    ) -> None:
        try:
            import boto3  # type: ignore[import-untyped]
            from botocore.config import Config  # type: ignore[import-untyped]
        except ImportError as exc:  # pragma: no cover - dependency is installed in runtime
            raise ObjectStorageError("S3 对象存储依赖未安装") from exc

        client_config = Config(
            signature_version="s3v4",
            s3={"addressing_style": "path" if force_path_style else "auto"},
        )
        self.client = boto3.client(
            "s3",
            endpoint_url=endpoint or None,
            region_name=region,
            aws_access_key_id=access_key or None,
            aws_secret_access_key=secret_key or None,
            config=client_config,
        )
        self.bucket = bucket
        self.auto_create_bucket = auto_create_bucket
        self._bucket_checked = False

    def put(self, object_key: str, content: bytes) -> None:
        self._ensure_bucket()
        try:
            self.client.put_object(Bucket=self.bucket, Key=object_key, Body=content)
        except Exception as exc:  # boto3 providers expose different exception classes
            raise ObjectStorageError("S3 对象写入失败") from exc

    def get(self, object_key: str) -> bytes:
        try:
            response = self.client.get_object(Bucket=self.bucket, Key=object_key)
            body = response["Body"].read()
            if not isinstance(body, bytes):
                raise ObjectStorageError("S3 对象响应无效")
            return body
        except ObjectStorageError:
            raise
        except Exception as exc:
            raise ObjectStorageError("S3 对象读取失败") from exc

    def delete(self, object_key: str) -> None:
        try:
            self.client.delete_object(Bucket=self.bucket, Key=object_key)
        except Exception as exc:
            raise ObjectStorageError("S3 对象删除失败") from exc

    def ready(self) -> bool:
        try:
            self._ensure_bucket()
            return True
        except ObjectStorageError:
            return False

    def _ensure_bucket(self) -> None:
        if self._bucket_checked:
            return
        try:
            self.client.head_bucket(Bucket=self.bucket)
        except Exception as exc:
            if not self.auto_create_bucket:
                raise ObjectStorageError("S3 存储桶不可用") from exc
            try:
                self.client.create_bucket(Bucket=self.bucket)
            except Exception as create_exc:
                raise ObjectStorageError("S3 存储桶创建失败") from create_exc
        self._bucket_checked = True


class ObjectStorageRegistry:
    def __init__(self, active: ObjectStorage, providers: dict[str, ObjectStorage]) -> None:
        self.active = active
        self.providers = providers

    @property
    def provider_key(self) -> str:
        return self.active.provider_key

    def put(self, object_key: str, content: bytes) -> None:
        self.active.put(object_key, content)

    def get(self, provider_key: str, object_key: str) -> bytes:
        provider = self.providers.get(provider_key)
        if provider is None:
            raise ObjectStorageError("文件资产使用了未配置的存储提供方")
        return provider.get(object_key)

    def delete(self, object_key: str) -> None:
        self.active.delete(object_key)

    def ready(self) -> bool:
        return self.active.ready()


def build_object_storage(
    *,
    provider: str,
    local_root: str,
    s3_endpoint: str,
    s3_region: str,
    s3_bucket: str,
    s3_access_key: str,
    s3_secret_key: str,
    s3_force_path_style: bool,
    s3_auto_create_bucket: bool,
) -> ObjectStorageRegistry:
    local = LocalObjectStorage(local_root)
    s3: ObjectStorage | None = None
    if provider == "s3":
        s3 = S3ObjectStorage(
            endpoint=s3_endpoint,
            region=s3_region,
            bucket=s3_bucket,
            access_key=s3_access_key,
            secret_key=s3_secret_key,
            force_path_style=s3_force_path_style,
            auto_create_bucket=s3_auto_create_bucket,
        )
    active = s3 or local
    providers = {local.provider_key: local, active.provider_key: active}
    return ObjectStorageRegistry(active, providers)
