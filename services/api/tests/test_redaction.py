from zhixing_api.connectors.lingxing.redaction import redact


def test_redaction_removes_credentials_and_nested_pii():
    data = redact({"access_token": "secret", "nested": {"phone": "138", "ok": 1}})
    assert data == {"access_token": "[REDACTED]", "nested": {"phone": "[REDACTED]", "ok": 1}}
