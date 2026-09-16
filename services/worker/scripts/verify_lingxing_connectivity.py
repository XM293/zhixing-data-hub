"""Explicit server-only read probe; output contains no credentials or source records."""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import socket
from pathlib import Path
from urllib.request import ProxyHandler, build_opener

import httpx
from zhixing_connectors import LingxingClient, LingxingConfig, LingxingTokenProvider


async def run_probe(app_id: str, app_secret: str, *,
                    transport: httpx.AsyncBaseTransport | None = None) -> dict[str, object]:
    result: dict[str, object] = {"authentication": "failed", "shop_directory": "not_requested"}
    provider = LingxingTokenProvider(app_id, app_secret, "https://openapi.lingxing.com",
                                    transport=transport)
    try:
        await provider.get()
    except Exception:
        return result
    result["authentication"] = "passed"
    client = LingxingClient(LingxingConfig(app_id, app_secret), transport=transport,
                           credential_provider=provider)
    try:
        response = await client.request("/erp/sc/data/seller/lists")
        rows = response.get("data")
        if not isinstance(rows, list):
            result["shop_directory"] = "schema_pending"
        else:
            result.update(shop_directory="passed", records_read=len(rows))
    except Exception:
        result["shop_directory"] = "failed"
    finally:
        await client.close()
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--credential-file", type=Path, required=True)
    parser.add_argument("--credential-prefix", required=True)
    parser.add_argument("--expected-hostname", required=True)
    parser.add_argument("--expected-public-ip", required=True)
    args = parser.parse_args()
    try:
        if os.name != "posix" or os.geteuid() != 0:
            raise ValueError("requires protected server process")
        if socket.gethostname() != args.expected_hostname:
            raise ValueError("hostname mismatch")
        opener = build_opener(ProxyHandler({}))
        with opener.open("http://metadata.tencentyun.com/latest/meta-data/public-ipv4",
                         timeout=10) as response:
            public_ip = response.read(128).decode().strip()
        if public_ip != args.expected_public_ip:
            raise ValueError("IP mismatch")
        path = args.credential_file
        stat = path.stat()
        if (path.is_symlink() or not path.is_file() or stat.st_uid != 0
                or stat.st_mode & 0o077 or stat.st_size > 65536
                or not re.fullmatch(r"[A-Z][A-Z0-9_]*", args.credential_prefix)):
            raise ValueError("credential boundary invalid")
        values = dict(line.split("=", 1) for line in path.read_text().splitlines()
                      if re.match(r"^[A-Z][A-Z0-9_]*=", line))
        app_id = values[args.credential_prefix + "_APP_ID"]
        app_secret = values[args.credential_prefix + "_APP_SECRET"]
        result = asyncio.run(run_probe(app_id, app_secret))
    except Exception:
        print(json.dumps({"status": "probe_precondition_failed"}))
        return 1
    print(json.dumps(result))
    return 0 if result.get("shop_directory") == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
