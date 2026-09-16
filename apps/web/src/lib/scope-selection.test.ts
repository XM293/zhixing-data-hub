import { describe, expect, it } from "vitest";

import type { ScopeContext } from "./identity-types";
import {
  businessUnitSelection,
  entityScopeSelection,
  parentScopeSelection,
  scopeOptionVisible
} from "./scope-selection";

const groupContext: ScopeContext = {
  schema_version: 2,
  enterprise_id: "legal-a",
  current_enterprise_id: "legal-a",
  group_id: "group-1",
  scope_level: "group",
  selected_enterprise_ids: ["legal-a", "legal-b"],
  business_unit_ids: ["project-a", "project-b"],
  store_ids: ["store-a", "store-b"],
  warehouse_ids: ["warehouse-a", "warehouse-b"],
  base_currency: "CNY",
  consolidation_profile_version: "group-v1",
  data_as_of: null,
  scope_version: "scope-v1"
};

describe("hierarchical scope selection", () => {
  it("switches the current legal entity when selecting another entity's unit", () => {
    expect(businessUnitSelection({ key: "project-b", enterprise_id: "legal-b" }, "legal-a"))
      .toEqual({
        enterprise_id: "legal-b",
        scope_level: "business_unit",
        selected_enterprise_ids: ["legal-b"],
        business_unit_ids: ["project-b"]
      });
  });

  it("keeps warehouses inside the selected legal entity and business unit", () => {
    expect(entityScopeSelection("warehouse", {
      key: "warehouse-b", enterprise_id: "legal-b", business_unit_id: "project-b"
    }, groupContext, "legal-a")).toEqual({
      enterprise_id: "legal-b",
      scope_level: "warehouse",
      selected_enterprise_ids: ["legal-b"],
      business_unit_ids: ["project-b"],
      store_ids: [],
      warehouse_ids: ["warehouse-b"]
    });
    expect(scopeOptionVisible({
      key: "store-a", enterprise_id: "legal-a", business_unit_id: "project-a"
    }, { ...groupContext, selected_enterprise_ids: ["legal-b"], business_unit_ids: ["project-b"] }))
      .toBe(false);
  });

  it("returns from a leaf to its business unit", () => {
    expect(parentScopeSelection({
      ...groupContext,
      current_enterprise_id: "legal-b",
      enterprise_id: "legal-b",
      selected_enterprise_ids: ["legal-b"],
      business_unit_ids: ["project-b"],
      scope_level: "store"
    })).toEqual({
      enterprise_id: "legal-b",
      scope_level: "business_unit",
      selected_enterprise_ids: ["legal-b"],
      business_unit_ids: ["project-b"]
    });
  });
});
