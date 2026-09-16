from zhixing_api.connectors.lingxing.signing import build_signature, canonicalize


def test_official_canonicalization_omits_empty_and_keeps_null_and_nested_json() -> None:
    assert canonicalize(
        {"z": "", "a": "中文", "nullable": None,
         "items": [1, {"z": "商品", "a": "数组"}]}
    ) == 'a=中文&items=[1,{"z":"商品","a":"数组"}]&nullable=null'


def test_signature_uses_raw_app_id_and_is_wire_unescaped() -> None:
    value = build_signature(
        {
            "access_token": "tok", "app_key": "synthetic-app-id",
            "timestamp": "1700000000", "items": [1, {"z": "商品", "a": "数组"}],
            "nullable": None, "empty": "",
        },
        "synthetic-app-id",
    )
    assert value == "EIsPUqCIapsglYwkZJEof44fWe3c0ikHLLihWDcOZQ9OxuCfutNSoExbHJQY5aTY"
    assert "%" not in value
