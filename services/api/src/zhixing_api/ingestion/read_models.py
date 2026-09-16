from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class FactProvenance(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    enterprise_id: str
    business_unit_id: str | None
    external_system_id: str
    resource_key: str
    external_key: str
    raw_manifest_id: str
    schema_version: str
    mapping_version: str
    observed_at: datetime
    source_updated_at: datetime | None


class SalesOrderView(FactProvenance):
    store_key: str
    status: str
    amount: Decimal | None
    currency_code: str | None
    base_amount: Decimal | None
    base_currency_code: str | None
    exchange_rate_version: str | None
    ordered_at: datetime
    source_local_time: str
    store_timezone: str | None
    business_date: date
    fulfillment_channel: str | None


class AfterSaleView(FactProvenance):
    source_item_key: str
    store_key: str
    order_external_key: str
    sku: str
    after_type: str
    quantity: int
    status: str | None
    source_amount_text: str
    amount: Decimal | None
    currency_code: str | None
    base_amount: Decimal | None
    base_currency_code: str | None
    exchange_rate_version: str | None
    source_local_time: str
    source_updated_local_time: str
    occurred_at: datetime | None
    business_date: date
    store_timezone: str | None
    quality_flags: list[str]


class FulfillmentLineView(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    external_key: str
    product_external_key: str
    sku: str
    quantity: int
    bundle_type: int
    parent_external_key: str | None


class FulfillmentView(FactProvenance):
    store_key: str
    warehouse_key: str
    shipment_number: str
    order_external_key: str
    platform_order_keys: list[str]
    status: str
    logistics_status: int
    freight_amount: Decimal | None
    freight_currency_code: str | None
    base_freight_amount: Decimal | None
    base_currency_code: str | None
    exchange_rate_version: str | None
    source_local_time: str
    source_updated_local_time: str
    dispatched_local_time: str | None
    source_timezone: str | None
    created_at: datetime | None
    dispatched_at: datetime | None
    business_date: date
    quality_flags: list[str]
    lines: list[FulfillmentLineView] = Field(default_factory=list)


class InventoryBalanceView(FactProvenance):
    warehouse_key: str
    product_key: str
    store_key: str | None
    sku: str
    total: int
    available: int
    defective: int
    inspecting: int
    reserved: int
    in_transit: int | None


class OperationalFactView(FactProvenance):
    fact_type: str
    status: str
    store_key: str | None
    warehouse_key: str | None
    product_key: str | None
    source_local_time: str | None
    source_timezone: str | None
    business_date: date | None
    amount: Decimal | None
    currency_code: str | None
    quantity: Decimal | None
    attributes: dict[str, object]
    quality_flags: list[str]


class CanonicalPage(BaseModel):
    schema_version: int = 1
    authority_applied: bool = False
    scope_snapshot: dict[str, object]
    total: int
    offset: int
    limit: int
    items: list[
        SalesOrderView | InventoryBalanceView | AfterSaleView | FulfillmentView
        | OperationalFactView
    ]
    data_as_of: datetime | None
    currency_totals: dict[str, Decimal] = Field(default_factory=dict)
