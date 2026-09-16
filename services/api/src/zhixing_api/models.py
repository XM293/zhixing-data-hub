from typing import Literal

from pydantic import BaseModel, ConfigDict


class ApiModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class HealthResponse(ApiModel):
    service: str
    status: Literal["live", "ready"]
    version: str
    environment: str


class PlatformModule(ApiModel):
    key: str
    label: str
    navigation: str
    owner: str
    summary: str
    milestone: str
    availability: Literal["foundation", "planned"]


class PlatformModulesResponse(ApiModel):
    schema_version: Literal[1] = 1
    modules: list[PlatformModule]
