import type { ChannelBindingStatus, ChannelIdentityItem } from "@/lib/channel-identity-types";

export interface ChannelIdentityFilters {
  channel: string;
  status: ChannelBindingStatus | "all";
  query: string;
}

export function filterChannelIdentities(
  items: ChannelIdentityItem[],
  filters: ChannelIdentityFilters
): ChannelIdentityItem[] {
  const query = filters.query.trim().toLocaleLowerCase("zh-CN");
  return items.filter((item) => {
    if (filters.channel !== "all" && item.channel_key !== filters.channel) return false;
    if (filters.status !== "all" && item.binding_status !== filters.status) return false;
    if (!query) return true;
    return [
      item.observed_display_name,
      item.external_identity_hint,
      item.external_identity_fingerprint,
      item.principal_name,
      item.principal_account_key,
      item.external_tenant_key
    ].some((value) => value?.toLocaleLowerCase("zh-CN").includes(query));
  });
}

export function channelBindingStatusLabel(status: ChannelBindingStatus): string {
  if (status === "bound") return "已绑定";
  if (status === "suspended") return "已停用";
  return "未绑定";
}
