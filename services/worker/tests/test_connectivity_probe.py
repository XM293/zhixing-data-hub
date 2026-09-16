import asyncio
import importlib.util
import json
from pathlib import Path

import httpx


def test_probe_uses_shared_auth_and_only_outputs_aggregate_status():
    path = Path(__file__).resolve().parents[1] / "scripts/verify_lingxing_connectivity.py"
    spec = importlib.util.spec_from_file_location("connectivity_probe", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    requests = []
    def respond(request):
        requests.append(request.url.path)
        if request.url.path.endswith("access-token"):
            return httpx.Response(200, json={"code": 200, "data": {
                "access_token": "synthetic-access", "refresh_token": "synthetic-refresh",
                "expires_in": 3600}})
        assert request.url.path == "/erp/sc/data/seller/lists"
        assert "sign" in request.url.params
        return httpx.Response(200, json={"code": 0, "data": [
            {"sid": 123, "name": "SYNTHETIC-PRIVATE-NAME"}]})
    result = asyncio.run(module.run_probe("synthetic-app-16", "synthetic-secret",
                                         transport=httpx.MockTransport(respond)))
    assert result == {"authentication": "passed", "shop_directory": "passed", "records_read": 1}
    assert len(requests) == 2
    assert "SYNTHETIC-PRIVATE-NAME" not in json.dumps(result)
    def reject(request):
        return httpx.Response(200, json={"code": 400, "msg": "synthetic-secret"})
    result = asyncio.run(module.run_probe("synthetic-app-16", "synthetic-secret",
                                         transport=httpx.MockTransport(reject)))
    assert result == {"authentication": "failed", "shop_directory": "not_requested"}
