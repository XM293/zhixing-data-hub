from __future__ import annotations

import sys
from pathlib import Path

API_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(API_ROOT / "src"))


def main() -> int:
    from zhixing_api.database_cli import run

    return run()


if __name__ == "__main__":
    raise SystemExit(main())
