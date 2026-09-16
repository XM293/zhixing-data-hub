import pytest

from zhixing_api.ingestion.mapping import map_head_logistics_provider


def test_logistics_identity_status_and_contact_minimization():
    row = {"providerId": "synthetic-provider-1", "name": "Synthetic logistics",
           "code": "SYNTH", "enabled": 0, "isAuth": 0, "payMethod": 2,
           "logisticsType": 3, "status": 0, "contactPhone": "synthetic-private"}
    mapped = map_head_logistics_provider(row)
    assert mapped.external_key == "synthetic-provider-1"
    assert mapped.status == "inactive"
    assert mapped.requires_assignment
    assert mapped.attributes["authorization_status"] == 0
    assert "contactPhone" not in mapped.attributes
    for bad in ({**row, "providerId": None}, {**row, "enabled": 9}):
        with pytest.raises(ValueError):
            map_head_logistics_provider(bad)
