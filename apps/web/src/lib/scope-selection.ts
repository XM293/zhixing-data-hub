import type { ScopeContext, ScopeSelection } from "@/lib/identity-types";

export interface HierarchicalScopeOption {
  key: string;
  enterprise_id?: string;
  business_unit_id?: string;
}

export function scopeOptionVisible(
  option: HierarchicalScopeOption,
  context: ScopeContext | null
): boolean {
  if (!context) return false;
  if (option.enterprise_id && !context.selected_enterprise_ids.includes(option.enterprise_id)) {
    return false;
  }
  return !option.business_unit_id
    || context.business_unit_ids.length === 0
    || context.business_unit_ids.includes(option.business_unit_id);
}

export function businessUnitSelection(
  option: HierarchicalScopeOption,
  currentEnterpriseId: string
): ScopeSelection {
  const enterpriseId = option.enterprise_id ?? currentEnterpriseId;
  return {
    enterprise_id: enterpriseId,
    scope_level: "business_unit",
    selected_enterprise_ids: [enterpriseId],
    business_unit_ids: [option.key]
  };
}

export function entityScopeSelection(
  kind: "store" | "warehouse",
  option: HierarchicalScopeOption,
  context: ScopeContext,
  currentEnterpriseId: string
): ScopeSelection {
  const enterpriseId = option.enterprise_id ?? currentEnterpriseId;
  const businessUnitIds = option.business_unit_id
    ? [option.business_unit_id]
    : context.business_unit_ids;
  return {
    enterprise_id: enterpriseId,
    scope_level: kind,
    selected_enterprise_ids: [enterpriseId],
    business_unit_ids: businessUnitIds,
    store_ids: kind === "store" ? [option.key] : [],
    warehouse_ids: kind === "warehouse" ? [option.key] : []
  };
}

export function parentScopeSelection(context: ScopeContext): ScopeSelection {
  if (context.business_unit_ids.length > 0) {
    return {
      enterprise_id: context.current_enterprise_id,
      scope_level: "business_unit",
      selected_enterprise_ids: [context.current_enterprise_id],
      business_unit_ids: context.business_unit_ids
    };
  }
  return {
    enterprise_id: context.current_enterprise_id,
    scope_level: "enterprise",
    selected_enterprise_ids: [context.current_enterprise_id]
  };
}
