"""Generate the non-secret rollout worklist for structurally safe official resources."""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

from zhixing_connectors.catalog import official_raw_spec
from zhixing_connectors.official_contracts import (
    OFFICIAL_CONTRACT_VERSION,
    official_contracts,
)

VERSION = "lingxing-rollout-2026-09-11.13"


def build() -> dict[str, object]:
    items: list[dict[str, object]] = []
    for contract in official_contracts():
        spec = official_raw_spec(contract.id)
        if spec is None:
            continue
        required_configuration = sorted(set(spec.required_parameters)
                                        - set(spec.window_fields)
                                        - {str(spec.scope_parameter)})
        state = ("needs_required_parameter_configuration" if required_configuration else
                 "awaiting_validation" if spec.scope_kind == "store" else
                 "blocked_binding_approval")
        items.append({
            "resource_key": spec.key,
            "operation_id": contract.id,
            "wave": spec.wave,
            "method": spec.method,
            "path": spec.path,
            "documentation_url": contract.documentation_url,
            "scope_kind": spec.scope_kind,
            "scope_namespace": spec.scope_namespace,
            "scope_parameter": spec.scope_parameter,
            "scope_parameter_mode": spec.scope_parameter_mode,
            "window_fields": list(spec.window_fields),
            "window_format": spec.window_format,
            "schedule_strategy": spec.schedule_strategy or "snapshot",
            "required_configuration": required_configuration,
            "projection_mode": "raw_only",
            "rollout_state": state,
        })
    counts = Counter(str(item["rollout_state"]) for item in items)
    scope_counts = Counter(str(item["scope_kind"]) for item in items)
    return {
        "version": VERSION,
        "official_contract_version": OFFICIAL_CONTRACT_VERSION,
        "source": "https://apidoc.lingxing.com/",
        "summary": {
            "eligible": len(items),
            "windowed": sum(bool(item["window_fields"]) for item in items),
            "snapshot": sum(not item["window_fields"] for item in items),
            "by_scope": dict(sorted(scope_counts.items())),
            "by_state": dict(sorted(counts.items())),
        },
        "items": sorted(items, key=lambda item: (str(item["wave"]), str(item["resource_key"]))),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="生成领星官方只读资源上线工作清单")
    parser.add_argument("--output", type=Path,
        default=Path("contracts/data/lingxing-official-rollout-worklist.json"))
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(build(), ensure_ascii=False, indent=2) + "\n",
                           encoding="utf-8")


if __name__ == "__main__":
    main()
