import pytest
from pydantic import ValidationError

from zhixing_api.bootstrap_schema import AdministratorSpec
from zhixing_api.identity_schemas import DevelopmentSessionRequest, LocalLoginRequest


def test_bootstrap_names_are_accepted_by_both_login_contracts():
    admin = AdministratorSpec(id="synthetic", home_enterprise_id="legal",
        login_name=" Admin-1@Verify ", display_name="Synthetic",
        password_env="BOOTSTRAP_VERIFY_PASSWORD", enterprise_ids=["legal"], role_keys=["admin"])
    assert admin.login_name == "admin-1@verify"
    assert LocalLoginRequest(login_name=admin.login_name,
        password="Synthetic-password-only").login_name == admin.login_name
    assert DevelopmentSessionRequest(login_name=admin.login_name).login_name == admin.login_name
    with pytest.raises(ValidationError):
        LocalLoginRequest(login_name="admin user", password="Synthetic-password-only")
