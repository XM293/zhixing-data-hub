from __future__ import annotations

from zhixing_api.connectors.contracts import ConnectorError, DataConnector
from zhixing_api.connectors.mock_commerce import ConnectorProfile, MockCommerceConnector

SYSTEM_TYPE_PROFILES: dict[str, ConnectorProfile] = {
    "test-erp-oms": "erp-oms",
    "test-crm": "crm",
    "test-advertising": "advertising",
    "test-customer-service": "customer-service",
}


def create_connector(system_type: str, base_url: str) -> DataConnector:
    profile = SYSTEM_TYPE_PROFILES.get(system_type)
    if profile is None:
        raise ConnectorError(f"unsupported connector system type: {system_type}")
    return MockCommerceConnector(base_url, profile=profile)
