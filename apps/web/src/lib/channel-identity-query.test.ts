import { describe, expect, it } from "vitest";

import { channelBindingStatusLabel, filterChannelIdentities } from "./channel-identity-query";
import type { ChannelIdentityItem } from "./channel-identity-types";

const items: ChannelIdentityItem[] = [
  {
    id: "channel-1",
    channel_key: "feishu",
    channel_label: "飞书",
    external_tenant_key: "tenant-a",
    external_identity_hint: "ou_...0011",
    external_identity_fingerprint: "aabbccddeeff",
    observed_display_name: "林知远",
    principal_id: "principal-1",
    principal_name: "林知远",
    principal_account_key: "account_ceo",
    binding_status: "bound",
    version: 1,
    first_seen_at: "2026-08-20T00:00:00Z",
    last_seen_at: "2026-08-30T00:00:00Z",
    updated_at: "2026-08-30T00:00:00Z"
  },
  {
    id: "channel-2",
    channel_key: "wecom",
    channel_label: "企业微信",
    external_tenant_key: "tenant-b",
    external_identity_hint: "wm_...0022",
    external_identity_fingerprint: "112233445566",
    observed_display_name: "陈璐",
    principal_id: null,
    principal_name: null,
    principal_account_key: null,
    binding_status: "unknown",
    version: 1,
    first_seen_at: "2026-08-20T00:00:00Z",
    last_seen_at: "2026-08-30T00:00:00Z",
    updated_at: "2026-08-30T00:00:00Z"
  }
];

describe("channel identity query", () => {
  it("combines channel, status and text filters", () => {
    expect(filterChannelIdentities(items, { channel: "feishu", status: "bound", query: "CEO" }))
      .toHaveLength(1);
    expect(filterChannelIdentities(items, { channel: "all", status: "unknown", query: "陈璐" }))
      .toEqual([items[1]]);
    expect(filterChannelIdentities(items, { channel: "all", status: "all", query: "112233" }))
      .toEqual([items[1]]);
  });

  it("maps lifecycle states to business labels", () => {
    expect(["unknown", "bound", "suspended"].map((status) =>
      channelBindingStatusLabel(status as ChannelIdentityItem["binding_status"])
    )).toEqual(["未绑定", "已绑定", "已停用"]);
  });
});
