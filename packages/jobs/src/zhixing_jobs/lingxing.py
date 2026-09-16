from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from zhixing_jobs.contracts import EnqueueJob


@dataclass(frozen=True)
class LingxingSyncCommand:
    enterprise_id: str
    source_id: str
    resource_key: str
    partition: str = "default"
    window: str = "current"
    scope_snapshot: dict[str, object] | None = None
    credential_ref: str | None = None
    window_start: str | None = None
    window_end: str | None = None
    resource_parameters: dict[str, object] | None = None

    @property
    def idempotency_key(self) -> str:
        raw = json.dumps(self.__dict__, sort_keys=True, separators=(",", ":"))
        return "lingxing:" + hashlib.sha256(raw.encode()).hexdigest()

    def payload(self) -> dict[str, object]:
        partition = self.partition
        if partition == "default":
            scope = self.scope_snapshot or {}
            selection = json.dumps({
                "scope": {key: scope.get(key) for key in (
                    "enterprise_id", "selected_enterprise_ids", "business_unit_ids",
                    "store_ids", "warehouse_ids", "scope_level", "scope_version",
                )},
                "start": self.window_start,
                "end": self.window_end,
                "parameters": self.resource_parameters,
            }, sort_keys=True, separators=(",", ":"))
            partition = "window:" + hashlib.sha256(selection.encode()).hexdigest()
        return {
            "provider": "lingxing",
            "source_id": self.source_id,
            "resource_key": self.resource_key,
            "partition": partition,
            "window": self.window,
            "scope_snapshot": self.scope_snapshot or {"enterprise_id": self.enterprise_id},
            "credential_ref": self.credential_ref,
            "window_start": self.window_start,
            "window_end": self.window_end,
            "resource_parameters": self.resource_parameters or {},
        }

    def to_enqueue_job(self, *, initiator_id: str, request_id: str, run_id: str) -> EnqueueJob:
        return EnqueueJob(
            enterprise_id=self.enterprise_id,
            job_type="data-source.sync",
            payload=self.payload(),
            idempotency_key=self.idempotency_key,
            initiator_type="user",
            initiator_id=initiator_id,
            actor_snapshot={
                "enterprise_id": self.enterprise_id,
                "scope_snapshot": self.scope_snapshot or {"enterprise_id": self.enterprise_id},
            },
            permission_set_version="current",
            required_permissions=("source.manage",),
            scope_type="enterprise",
            scope_id=self.enterprise_id,
            run_id=run_id,
            request_id=request_id,
        )
