from zhixing_worker.lingxing_auth import LingxingAuth


def test_signed_params_contains_official_public_parameters() -> None:
    auth = LingxingAuth("synthetic-app-id", "secret", "https://openapi.lingxing.com")
    params = auth.signed_params({"page": 1, "empty": "", "nullable": None}, "token")
    assert params["access_token"] == "token"
    assert params["app_key"] == "synthetic-app-id"
    assert params["page"] == "1"
    assert params["nullable"] == "None"
    assert "sign" in params and params["sign"]
    assert "empty" not in params
