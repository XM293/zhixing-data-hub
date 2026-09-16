from __future__ import annotations

import argparse
import signal
from threading import Event


def main() -> int:
    from zhixing_worker.main import run

    parser = argparse.ArgumentParser(description="知行数枢通用后台 Worker")
    parser.add_argument("--once", action="store_true", help="最多领取一个任务后退出")
    args = parser.parse_args()
    stop_event = Event()

    def request_stop(_signum: int, _frame: object) -> None:
        stop_event.set()

    signal.signal(signal.SIGINT, request_stop)
    signal.signal(signal.SIGTERM, request_stop)
    return run(once=args.once, stop_event=stop_event)


if __name__ == "__main__":
    raise SystemExit(main())
