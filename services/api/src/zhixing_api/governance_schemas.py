from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import Field, field_validator

from zhixing_api.models import ApiModel


class OrganizationRequest(ApiModel):
    code: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    name: str = Field(min_length=1, max_length=160)
    timezone: str = Field(default="Asia/Shanghai", max_length=64)

    @field_validator("timezone")
    @classmethod
    def known_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError):
            raise ValueError("时区无效") from None
        return value


class BusinessUnitRequest(ApiModel):
    enterprise_id: str = Field(min_length=1, max_length=64)
    unit_key: str = Field(min_length=1, max_length=120, pattern=r"^[A-Za-z0-9_-]+$")
    name: str = Field(min_length=1, max_length=160)
    unit_type: Literal["project", "brand", "division", "region"] = "project"
    parent_id: str | None = Field(default=None, max_length=64)
    status: Literal["active", "disabled"] = "active"
    expected_version: int | None = Field(default=None, ge=1)


class MembershipRequest(ApiModel):
    principal_id: str = Field(min_length=1, max_length=64)
    enterprise_id: str = Field(min_length=1, max_length=64)
    status: Literal["active", "revoked"] = "active"
    expected_version: int | None = Field(default=None, ge=1)


class ConsolidationRequest(ApiModel):
    profile_key: str = Field(min_length=1, max_length=120, pattern=r"^[A-Za-z0-9_-]+$")
    name: str = Field(min_length=1, max_length=160)
    version: str = Field(min_length=1, max_length=32, pattern=r"^[A-Za-z0-9_.-]+$")
    base_currency: str = Field(pattern=r"^[A-Z]{3}$")
    exchange_rate_policy: dict[str, str] = Field(default_factory=dict)
    # Unimplemented elimination algebra must not be accepted as active behavior.
    elimination_rules: list[dict[str, object]] = Field(default_factory=list, max_length=0)
