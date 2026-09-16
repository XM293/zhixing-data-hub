"""Versioned, secret-free organization and administrator initialization contract."""
from __future__ import annotations

from typing import Annotated, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, model_validator

from zhixing_api.identity_seed import PERMISSIONS
from zhixing_api.login_names import LoginName

Identifier = Annotated[str, Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_.-]+$")]
Name = Annotated[str, Field(min_length=1, max_length=160)]
Key = Annotated[str, Field(min_length=1, max_length=120)]


class ManifestModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, hide_input_in_errors=True)


class GroupSpec(ManifestModel):
    id: Identifier
    code: Identifier
    name: Name
    timezone: str = "Asia/Shanghai"
    status: Literal["active"] = "active"


class EnterpriseSpec(ManifestModel):
    id: Identifier
    code: Identifier
    name: Name
    timezone: str | None = None


class UnitSpec(ManifestModel):
    id: Identifier
    enterprise_id: Identifier
    unit_key: Key
    name: Name
    unit_type: Literal["project", "brand", "division", "region"] = "project"
    parent_id: Identifier | None = None
    status: Literal["active"] = "active"


class RoleTemplateSpec(ManifestModel):
    role_key: Key
    name: Name
    permission_keys: list[Key] = Field(min_length=1)


class AdministratorSpec(ManifestModel):
    id: Identifier
    home_enterprise_id: Identifier
    login_name: LoginName
    display_name: Name
    password_env: Annotated[str, Field(pattern=r"^BOOTSTRAP_[A-Z0-9_]+_PASSWORD$")]
    enterprise_ids: list[Identifier] = Field(min_length=1)
    role_keys: list[Key] = Field(min_length=1)


class BootstrapManifest(ManifestModel):
    version: Literal[1, 2]
    group: GroupSpec
    enterprises: list[EnterpriseSpec] = Field(min_length=1)
    business_units: list[UnitSpec] = Field(default_factory=list)
    role_templates: list[RoleTemplateSpec] = Field(default_factory=list)
    administrators: list[AdministratorSpec] = Field(default_factory=list)
    read_only_tools: list[Literal["query_authoritative_orders"]] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_graph(self) -> BootstrapManifest:
        for timezone in [self.group.timezone, *(item.timezone for item in self.enterprises)]:
            if timezone is not None:
                try:
                    ZoneInfo(timezone)
                except (ZoneInfoNotFoundError, ValueError) as error:
                    raise ValueError("invalid timezone") from error
        enterprises = {item.id for item in self.enterprises}
        if len(enterprises) != len(self.enterprises):
            raise ValueError("duplicate enterprise ID")
        if len({item.code for item in self.enterprises}) != len(self.enterprises):
            raise ValueError("duplicate enterprise code")
        units = {item.id: item for item in self.business_units}
        if len(units) != len(self.business_units):
            raise ValueError("duplicate business unit ID")
        if len({(item.enterprise_id, item.unit_key) for item in units.values()}) != len(units):
            raise ValueError("duplicate business unit key")
        for unit in units.values():
            if unit.enterprise_id not in enterprises:
                raise ValueError("undeclared business unit enterprise")
            visited = {unit.id}
            parent_id = unit.parent_id
            while parent_id is not None:
                parent = units.get(parent_id)
                if parent is None or parent.enterprise_id != unit.enterprise_id:
                    raise ValueError("undeclared or cross-enterprise parent")
                if parent_id in visited:
                    raise ValueError("business unit cycle")
                visited.add(parent_id)
                parent_id = parent.parent_id
        if self.version == 1:
            if self.role_templates or self.administrators or self.read_only_tools:
                raise ValueError("administrator bootstrap requires version 2")
            return self
        if len(set(self.read_only_tools)) != len(self.read_only_tools):
            raise ValueError("duplicate read-only tool template")
        if len(self.administrators) < 2 or not self.role_templates:
            raise ValueError("version 2 requires two administrators and reviewed roles")
        roles = {item.role_key: item for item in self.role_templates}
        if len(roles) != len(self.role_templates):
            raise ValueError("duplicate role key")
        known_permissions = {row[0] for row in PERMISSIONS}
        for role in roles.values():
            if not set(role.permission_keys) <= known_permissions:
                raise ValueError("unknown permission")
            if len(set(role.permission_keys)) != len(role.permission_keys):
                raise ValueError("duplicate permission")
        for field in ("id", "login_name", "password_env"):
            values = [str(getattr(item, field)).casefold() for item in self.administrators]
            if len(set(values)) != len(values):
                raise ValueError("duplicate administrator identity or credential reference")
        required = {"identity.user.manage", "identity.access.manage", "platform.navigation.read"}
        for admin in self.administrators:
            if (set(admin.enterprise_ids) != enterprises
                    or admin.home_enterprise_id not in enterprises):
                raise ValueError("group administrator must declare all bootstrap enterprises")
            if len(set(admin.enterprise_ids)) != len(admin.enterprise_ids):
                raise ValueError("duplicate membership")
            if (len(set(admin.role_keys)) != len(admin.role_keys)
                    or not set(admin.role_keys) <= roles.keys()):
                raise ValueError("unknown or duplicate administrator role")
            permissions = {key for role in admin.role_keys for key in roles[role].permission_keys}
            if not required <= permissions:
                raise ValueError("administrator cannot manage organization and access")
        return self
