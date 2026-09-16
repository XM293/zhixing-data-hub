from zhixing_connectors.catalog import OFFICIAL_RAW_SPECS
from zhixing_connectors.parameter_policies import (
    PARAMETER_POLICY_VERSION,
    parameter_policies,
    parameter_policy,
)


def test_every_extra_required_parameter_has_a_versioned_fail_closed_policy():
    expected = {
        spec.key: set(spec.required_parameters) - set(spec.window_fields)
        - {str(spec.scope_parameter)}
        for spec in OFFICIAL_RAW_SPECS
        if set(spec.required_parameters) - set(spec.window_fields)
        - {str(spec.scope_parameter)}
    }
    policies = {item.resource_key: item for item in parameter_policies()}
    assert PARAMETER_POLICY_VERSION == "lingxing-parameter-policy-2026-09-13.5"
    assert policies.keys() == expected.keys()
    for key, fields in expected.items():
        assert {rule.field for rule in policies[key].rules} == fields
        assert 1 <= policies[key].max_partitions_per_batch <= 64


def test_only_unconfirmed_business_semantics_remain_manual():
    manual = {item.resource_key: {rule.field for rule in item.rules
                                 if rule.strategy == "manual"}
              for item in parameter_policies() if item.status == "manual_required"}
    assert manual == {
        "official_044ffc8e4003fc69": {"mids"},
        "official_708956ecb911c985": {"productType"},
        "official_a6eed442006d8186": {"productType"},
        "official_81f530f8a30f8ad7": {"region"},
    }
    assert parameter_policy("official_29c2ecea89316017").status == (
        "ready_for_bounded_fanout")
    newad = parameter_policy("official_91609b93ec2b7dfc")
    assert newad is not None and newad.status == "ready_for_bounded_fanout"
    assert {rule.field: rule.values for rule in newad.rules} == {
        "log_source": ("all",),
        "operate_type": (
            "campaigns", "adGroups", "productAds", "keywords", "negativeKeywords",
            "targets", "negativeTargets", "profiles",
        ),
        "sponsored_type": ("sp", "sb", "sd"),
    }
    prep = parameter_policy("official_4ce492e4cc82b516")
    assert prep is not None and prep.status == "ready_for_bounded_fanout"
    assert len(prep.rules) == 1
    assert prep.rules[0].field == "msku"
    assert prep.rules[0].strategy == "dependency"
    assert prep.rules[0].value_types == ("msku",)
    products = parameter_policy("official_04957300fd9047e6")
    assert products is not None and products.rules[0].field == "skus"
    assert products.rules[0].value_types == ("sellerSku", "msku")
    analysis = parameter_policy("official_a2fa77b89b3172af")
    assert analysis is not None and analysis.status == "ready_for_bounded_fanout"
    assert {rule.field: rule.strategy for rule in analysis.rules} == {
        "group_type": "enum", "sku": "dependency",
    }
    assert parameter_policy("shops") is None
