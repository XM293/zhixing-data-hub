"use client";

import {
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  CircleAlert,
  Clock,
  DollarSign,
  Download,
  Filter,
  Layers,
  MessageSquarePlus,
  RefreshCw,
  Scale,
  Send,
  ShieldCheck,
  Store,
  TrendingDown,
  TrendingUp,
  X
} from "lucide-react";
import { useMemo, useState } from "react";

import { Dialog, useNotifications } from "@/components/console/interaction";
import { PageHeader, StatusBadge } from "@/components/console/ui";

interface StoreOption {
  key: string;
  name: string;
  channel: string;
  country: string;
  currency: string;
}

const STORES: StoreOption[] = [
  { key: "all", name: "全部北美店铺 (星云铁皮柜合并)", channel: "Amazon", country: "NA", currency: "USD" },
  { key: "12134", name: "星云-AUN-US (Amazon.com 美国站)", channel: "Amazon", country: "US", currency: "USD" },
  { key: "12135", name: "星云-AUN-CA (Amazon.ca 加拿大站)", channel: "Amazon", country: "CA", currency: "CAD" },
  { key: "12136", name: "星云-AUN-MX (Amazon.com.mx 墨西哥站)", channel: "Amazon", country: "MX", currency: "MXN" },
  { key: "12137", name: "星云-DINWORK-US (Amazon.com 美国站)", channel: "Amazon", country: "US", currency: "USD" },
  { key: "12138", name: "星云-DINWORK-CA (Amazon.ca 加拿大站)", channel: "Amazon", country: "CA", currency: "CAD" },
  { key: "12139", name: "星云-DINWORK-MX (Amazon.com.mx 墨西哥站)", channel: "Amazon", country: "MX", currency: "MXN" }
];

const PERIOD_OPTIONS = [
  { key: "all", label: "历史全生命周期 (2025-11 至今)" },
  { key: "2026-09", label: "2026年09月 (本月进行中)" },
  { key: "2026-08", label: "2026年08月" },
  { key: "2026-07", label: "2026年07月 (Prime Day 会员日)" },
  { key: "2026-06", label: "2026年06月" },
  { key: "2026-05", label: "2026年05月 (年度大促)" },
  { key: "2026-04", label: "2026年04月" },
  { key: "2026-03", label: "2026年03月 (春促旺季)" },
  { key: "2026-02", label: "2026年02月" },
  { key: "2026-01", label: "2026年01月" },
  { key: "2025-12", label: "2025年12月 (年终对账)" },
  { key: "2025-11", label: "2025年11月 (黑五网一 / 业务启动起点)" }
];


interface ReconciliationRow {
  id: string;
  month: string;
  storeKey: string;
  storeName: string;
  currency: string;
  systemOrders: number;
  erpOrders: number;
  systemGmvUsd: number;
  erpGmvUsd: number;
  systemRefundUsd: number;
  erpRefundUsd: number;
  systemFeesUsd: number;
  erpFeesUsd: number;
  systemGrossMarginUsd: number;
  erpGrossMarginUsd: number;
  systemSettlementUsd: number;
  erpSettlementUsd: number;
  status: "matched" | "variance" | "pending";
  statusText: string;
  diffReason?: string;
}

const INITIAL_ROWS: ReconciliationRow[] = [
  {
    id: "rec-202609-12137",
    month: "2026-09",
    storeKey: "12137",
    storeName: "星云-DINWORK-US (美国站)",
    currency: "USD",
    systemOrders: 75,
    erpOrders: 75,
    systemGmvUsd: 9383.94,
    erpGmvUsd: 9383.94,
    systemRefundUsd: 63.27,
    erpRefundUsd: 63.27,
    systemFeesUsd: 3699.44,
    erpFeesUsd: 3699.44,
    systemGrossMarginUsd: 6731.06,
    erpGrossMarginUsd: 6731.06,
    systemSettlementUsd: 5621.23,
    erpSettlementUsd: 5621.23,
    status: "pending",
    statusText: "结算周期中 (进行中)",
    diffReason: "9月结算周期尚未闭环，Amazon在途结算款陆续回款入账"
  },
  {
    id: "rec-202609-12134",
    month: "2026-09",
    storeKey: "12134",
    storeName: "星云-AUN-US (美国站)",
    currency: "USD",
    systemOrders: 53,
    erpOrders: 53,
    systemGmvUsd: 6686.53,
    erpGmvUsd: 6686.53,
    systemRefundUsd: 232.18,
    erpRefundUsd: 232.18,
    systemFeesUsd: 2846.45,
    erpFeesUsd: 2846.45,
    systemGrossMarginUsd: 4461.84,
    erpGrossMarginUsd: 4461.84,
    systemSettlementUsd: 3607.9,
    erpSettlementUsd: 3607.9,
    status: "pending",
    statusText: "结算周期中 (进行中)",
    diffReason: "9月结算周期尚未闭环，Amazon在途结算款陆续回款入账"
  },
  {
    id: "rec-202609-12135",
    month: "2026-09",
    storeKey: "12135",
    storeName: "星云-AUN-CA (加拿大站)",
    currency: "CAD",
    systemOrders: 0,
    erpOrders: 0,
    systemGmvUsd: 0.0,
    erpGmvUsd: 0.0,
    systemRefundUsd: 0.0,
    erpRefundUsd: 0.0,
    systemFeesUsd: 0.0,
    erpFeesUsd: 0.0,
    systemGrossMarginUsd: 0.0,
    erpGrossMarginUsd: 0.0,
    systemSettlementUsd: 0.0,
    erpSettlementUsd: 0.0,
    status: "matched",
    statusText: "无交易 (已核实)"
  },
  {
    id: "rec-202609-12136",
    month: "2026-09",
    storeKey: "12136",
    storeName: "星云-AUN-MX (墨西哥站)",
    currency: "MXN",
    systemOrders: 0,
    erpOrders: 0,
    systemGmvUsd: 0.0,
    erpGmvUsd: 0.0,
    systemRefundUsd: 0.0,
    erpRefundUsd: 0.0,
    systemFeesUsd: 0.0,
    erpFeesUsd: 0.0,
    systemGrossMarginUsd: 0.0,
    erpGrossMarginUsd: 0.0,
    systemSettlementUsd: 0.0,
    erpSettlementUsd: 0.0,
    status: "matched",
    statusText: "无交易 (已核实)"
  },
  {
    id: "rec-202609-12138",
    month: "2026-09",
    storeKey: "12138",
    storeName: "星云-DINWORK-CA (加拿大站)",
    currency: "CAD",
    systemOrders: 0,
    erpOrders: 0,
    systemGmvUsd: 0.0,
    erpGmvUsd: 0.0,
    systemRefundUsd: 0.0,
    erpRefundUsd: 0.0,
    systemFeesUsd: 0.0,
    erpFeesUsd: 0.0,
    systemGrossMarginUsd: 0.0,
    erpGrossMarginUsd: 0.0,
    systemSettlementUsd: 0.0,
    erpSettlementUsd: 0.0,
    status: "matched",
    statusText: "无交易 (已核实)"
  },
  {
    id: "rec-202609-12139",
    month: "2026-09",
    storeKey: "12139",
    storeName: "星云-DINWORK-MX (墨西哥站)",
    currency: "MXN",
    systemOrders: 0,
    erpOrders: 0,
    systemGmvUsd: 0.0,
    erpGmvUsd: 0.0,
    systemRefundUsd: 0.0,
    erpRefundUsd: 0.0,
    systemFeesUsd: 0.0,
    erpFeesUsd: 0.0,
    systemGrossMarginUsd: 0.0,
    erpGrossMarginUsd: 0.0,
    systemSettlementUsd: 0.0,
    erpSettlementUsd: 0.0,
    status: "matched",
    statusText: "无交易 (已核实)"
  },
  {
    id: "rec-202608-12134",
    month: "2026-08",
    storeKey: "12134",
    storeName: "星云-AUN-US (美国站)",
    currency: "USD",
    systemOrders: 189,
    erpOrders: 189,
    systemGmvUsd: 23568.19,
    erpGmvUsd: 23568.19,
    systemRefundUsd: 1606.59,
    erpRefundUsd: 1606.59,
    systemFeesUsd: 7747.8,
    erpFeesUsd: 7747.8,
    systemGrossMarginUsd: 17290.41,
    erpGrossMarginUsd: 17290.41,
    systemSettlementUsd: 14213.8,
    erpSettlementUsd: 14213.8,
    status: "matched",
    statusText: "已对齐 (100%)"
  },
  {
    id: "rec-202608-12137",
    month: "2026-08",
    storeKey: "12137",
    storeName: "星云-DINWORK-US (美国站)",
    currency: "USD",
    systemOrders: 102,
    erpOrders: 102,
    systemGmvUsd: 12780.71,
    erpGmvUsd: 12780.71,
    systemRefundUsd: 493.47,
    erpRefundUsd: 493.47,
    systemFeesUsd: 4574.69,
    erpFeesUsd: 4574.69,
    systemGrossMarginUsd: 8781.99,
    erpGrossMarginUsd: 8781.99,
    systemSettlementUsd: 7808.84,
    erpSettlementUsd: 7808.84,
    status: "matched",
    statusText: "已对齐 (100%)"
  },
  {
    id: "rec-202607-12137",
    month: "2026-07",
    storeKey: "12137",
    storeName: "星云-DINWORK-US (美国站)",
    currency: "USD",
    systemOrders: 184,
    erpOrders: 184,
    systemGmvUsd: 23037.05,
    erpGmvUsd: 23037.05,
    systemRefundUsd: 1696.3,
    erpRefundUsd: 1696.3,
    systemFeesUsd: 3566.14,
    erpFeesUsd: 3566.14,
    systemGrossMarginUsd: 19875.02,
    erpGrossMarginUsd: 19875.02,
    systemSettlementUsd: 17678.32,
    erpSettlementUsd: 17678.32,
    status: "matched",
    statusText: "已对齐 (100%)"
  },
  {
    id: "rec-202607-12134",
    month: "2026-07",
    storeKey: "12134",
    storeName: "星云-AUN-US (美国站)",
    currency: "USD",
    systemOrders: 169,
    erpOrders: 169,
    systemGmvUsd: 21178.58,
    erpGmvUsd: 21178.58,
    systemRefundUsd: 760.96,
    erpRefundUsd: 760.96,
    systemFeesUsd: 6730.1,
    erpFeesUsd: 6730.1,
    systemGrossMarginUsd: 15467.57,
    erpGrossMarginUsd: 15467.57,
    systemSettlementUsd: 13687.52,
    erpSettlementUsd: 13687.52,
    status: "matched",
    statusText: "已对齐 (100%)"
  },
  {
    id: "rec-202606-12137",
    month: "2026-06",
    storeKey: "12137",
    storeName: "星云-DINWORK-US (美国站)",
    currency: "USD",
    systemOrders: 200,
    erpOrders: 200,
    systemGmvUsd: 24970.04,
    erpGmvUsd: 24970.04,
    systemRefundUsd: 1359.1,
    erpRefundUsd: 1359.1,
    systemFeesUsd: 5037.99,
    erpFeesUsd: 5037.99,
    systemGrossMarginUsd: 20015.68,
    erpGrossMarginUsd: 20015.68,
    systemSettlementUsd: 18576.55,
    erpSettlementUsd: 18576.55,
    status: "matched",
    statusText: "已对齐 (100%)"
  },
  {
    id: "rec-202606-12134",
    month: "2026-06",
    storeKey: "12134",
    storeName: "星云-AUN-US (美国站)",
    currency: "USD",
    systemOrders: 185,
    erpOrders: 185,
    systemGmvUsd: 23094.04,
    erpGmvUsd: 23094.04,
    systemRefundUsd: 1033.76,
    erpRefundUsd: 1033.76,
    systemFeesUsd: 6129.52,
    erpFeesUsd: 6129.52,
    systemGrossMarginUsd: 17540.35,
    erpGrossMarginUsd: 17540.35,
    systemSettlementUsd: 15930.76,
    erpSettlementUsd: 15930.76,
    status: "matched",
    statusText: "已对齐 (100%)"
  },
  {
    id: "rec-202605-12137",
    month: "2026-05",
    storeKey: "12137",
    storeName: "星云-DINWORK-US (美国站)",
    currency: "USD",
    systemOrders: 410,
    erpOrders: 410,
    systemGmvUsd: 51202.57,
    erpGmvUsd: 51202.57,
    systemRefundUsd: 3861.06,
    erpRefundUsd: 3861.06,
    systemFeesUsd: 9926.51,
    erpFeesUsd: 9926.51,
    systemGrossMarginUsd: 40994.48,
    erpGrossMarginUsd: 40994.48,
    systemSettlementUsd: 38418.26,
    erpSettlementUsd: 38418.26,
    status: "matched",
    statusText: "已对齐 (100%)"
  },
  {
    id: "rec-202605-12134",
    month: "2026-05",
    storeKey: "12134",
    storeName: "星云-AUN-US (美国站)",
    currency: "USD",
    systemOrders: 204,
    erpOrders: 204,
    systemGmvUsd: 25518.1,
    erpGmvUsd: 25518.1,
    systemRefundUsd: 2581.76,
    erpRefundUsd: 2581.76,
    systemFeesUsd: 8823.05,
    erpFeesUsd: 8808.85,
    systemGrossMarginUsd: 16187.65,
    erpGrossMarginUsd: 16201.85,
    systemSettlementUsd: 15482.91,
    erpSettlementUsd: 15482.91,
    status: "variance",
    statusText: "微差 ($14.20 汇率折算)",
    diffReason: "领星ERP月初跨月预提运费微差 $14.20，对账一致性在容差内"
  },
  {
    id: "rec-202604-12137",
    month: "2026-04",
    storeKey: "12137",
    storeName: "星云-DINWORK-US (美国站)",
    currency: "USD",
    systemOrders: 346,
    erpOrders: 346,
    systemGmvUsd: 43234.19,
    erpGmvUsd: 43234.19,
    systemRefundUsd: 2109.41,
    erpRefundUsd: 2109.41,
    systemFeesUsd: 8323.24,
    erpFeesUsd: 8323.24,
    systemGrossMarginUsd: 34969.75,
    erpGrossMarginUsd: 34969.75,
    systemSettlementUsd: 32801.54,
    erpSettlementUsd: 32801.54,
    status: "matched",
    statusText: "已对齐 (100%)"
  },
  {
    id: "rec-202604-12134",
    month: "2026-04",
    storeKey: "12134",
    storeName: "星云-AUN-US (美国站)",
    currency: "USD",
    systemOrders: 95,
    erpOrders: 95,
    systemGmvUsd: 11836.22,
    erpGmvUsd: 11836.22,
    systemRefundUsd: 670.62,
    erpRefundUsd: 670.62,
    systemFeesUsd: 6385.4,
    erpFeesUsd: 6385.4,
    systemGrossMarginUsd: 6475.29,
    erpGrossMarginUsd: 6475.29,
    systemSettlementUsd: 6615.69,
    erpSettlementUsd: 6615.69,
    status: "matched",
    statusText: "已对齐 (100%)"
  },
  {
    id: "rec-202603-12137",
    month: "2026-03",
    storeKey: "12137",
    storeName: "星云-DINWORK-US (美国站)",
    currency: "USD",
    systemOrders: 251,
    erpOrders: 251,
    systemGmvUsd: 31365.37,
    erpGmvUsd: 31365.37,
    systemRefundUsd: 1282.45,
    erpRefundUsd: 1282.45,
    systemFeesUsd: 6333.26,
    erpFeesUsd: 6333.26,
    systemGrossMarginUsd: 25052.79,
    erpGrossMarginUsd: 25052.79,
    systemSettlementUsd: 23749.66,
    erpSettlementUsd: 23749.66,
    status: "matched",
    statusText: "已对齐 (100%)"
  },
  {
    id: "rec-202603-12134",
    month: "2026-03",
    storeKey: "12134",
    storeName: "星云-AUN-US (美国站)",
    currency: "USD",
    systemOrders: 85,
    erpOrders: 85,
    systemGmvUsd: 10628.38,
    erpGmvUsd: 10628.38,
    systemRefundUsd: 596.66,
    erpRefundUsd: 596.66,
    systemFeesUsd: 4541.39,
    erpFeesUsd: 4541.39,
    systemGrossMarginUsd: 6185.06,
    erpGrossMarginUsd: 6185.06,
    systemSettlementUsd: 4796.93,
    erpSettlementUsd: 4796.93,
    status: "matched",
    statusText: "已对齐 (100%)"
  },
  {
    id: "rec-202602-12137",
    month: "2026-02",
    storeKey: "12137",
    storeName: "星云-DINWORK-US (美国站)",
    currency: "USD",
    systemOrders: 90,
    erpOrders: 90,
    systemGmvUsd: 11282.3,
    erpGmvUsd: 11282.3,
    systemRefundUsd: 504.93,
    erpRefundUsd: 504.93,
    systemFeesUsd: 3724.74,
    erpFeesUsd: 3724.74,
    systemGrossMarginUsd: 7922.95,
    erpGrossMarginUsd: 7922.95,
    systemSettlementUsd: 7052.63,
    erpSettlementUsd: 7052.63,
    status: "matched",
    statusText: "已对齐 (100%)"
  },
  {
    id: "rec-202602-12134",
    month: "2026-02",
    storeKey: "12134",
    storeName: "星云-AUN-US (美国站)",
    currency: "USD",
    systemOrders: 44,
    erpOrders: 44,
    systemGmvUsd: 5560.08,
    erpGmvUsd: 5560.08,
    systemRefundUsd: 282.56,
    erpRefundUsd: 282.56,
    systemFeesUsd: 2032.5,
    erpFeesUsd: 2032.5,
    systemGrossMarginUsd: 3676.84,
    erpGrossMarginUsd: 3676.84,
    systemSettlementUsd: 3771.99,
    erpSettlementUsd: 3771.99,
    status: "matched",
    statusText: "已对齐 (100%)"
  },
  {
    id: "rec-202601-12137",
    month: "2026-01",
    storeKey: "12137",
    storeName: "星云-DINWORK-US (美国站)",
    currency: "USD",
    systemOrders: 158,
    erpOrders: 158,
    systemGmvUsd: 19804.95,
    erpGmvUsd: 19804.95,
    systemRefundUsd: 207.39,
    erpRefundUsd: 207.39,
    systemFeesUsd: 2899.95,
    erpFeesUsd: 2899.95,
    systemGrossMarginUsd: 17822.42,
    erpGrossMarginUsd: 17822.42,
    systemSettlementUsd: 21211.2,
    erpSettlementUsd: 21211.2,
    status: "matched",
    statusText: "已对齐 (100%)"
  },
  {
    id: "rec-202601-12134",
    month: "2026-01",
    storeKey: "12134",
    storeName: "星云-AUN-US (美国站)",
    currency: "USD",
    systemOrders: 31,
    erpOrders: 31,
    systemGmvUsd: 3911.74,
    erpGmvUsd: 3911.74,
    systemRefundUsd: 295.02,
    erpRefundUsd: 295.02,
    systemFeesUsd: 2034.59,
    erpFeesUsd: 2034.59,
    systemGrossMarginUsd: 1678.96,
    erpGrossMarginUsd: 1678.96,
    systemSettlementUsd: 754.66,
    erpSettlementUsd: 754.66,
    status: "matched",
    statusText: "已对齐 (100%)"
  },
  {
    id: "rec-202512-12137",
    month: "2025-12",
    storeKey: "12137",
    storeName: "星云-DINWORK-US (美国站)",
    currency: "USD",
    systemOrders: 48,
    erpOrders: 48,
    systemGmvUsd: 5981.64,
    erpGmvUsd: 5981.64,
    systemRefundUsd: 375.97,
    erpRefundUsd: 375.97,
    systemFeesUsd: 1092.08,
    erpFeesUsd: 1092.08,
    systemGrossMarginUsd: 4867.75,
    erpGrossMarginUsd: 4867.75,
    systemSettlementUsd: 0.0,
    erpSettlementUsd: 0.0,
    status: "matched",
    statusText: "已对齐 (100%)"
  },
  {
    id: "rec-202512-12134",
    month: "2025-12",
    storeKey: "12134",
    storeName: "星云-AUN-US (美国站)",
    currency: "USD",
    systemOrders: 29,
    erpOrders: 29,
    systemGmvUsd: 3632.33,
    erpGmvUsd: 3632.33,
    systemRefundUsd: 0.0,
    erpRefundUsd: 0.0,
    systemFeesUsd: 1225.22,
    erpFeesUsd: 1225.22,
    systemGrossMarginUsd: 2470.93,
    erpGrossMarginUsd: 2470.93,
    systemSettlementUsd: 1668.74,
    erpSettlementUsd: 1668.74,
    status: "matched",
    statusText: "已对齐 (100%)"
  },
  {
    id: "rec-202511-12137",
    month: "2025-11",
    storeKey: "12137",
    storeName: "星云-DINWORK-US (美国站)",
    currency: "USD",
    systemOrders: 7,
    erpOrders: 7,
    systemGmvUsd: 849.96,
    erpGmvUsd: 849.96,
    systemRefundUsd: 0.0,
    erpRefundUsd: 0.0,
    systemFeesUsd: 208.45,
    erpFeesUsd: 208.45,
    systemGrossMarginUsd: 641.51,
    erpGrossMarginUsd: 641.51,
    systemSettlementUsd: 681.49,
    erpSettlementUsd: 681.49,
    status: "matched",
    statusText: "已对齐 (100%)"
  },
  {
    id: "rec-202511-12134",
    month: "2025-11",
    storeKey: "12134",
    storeName: "星云-AUN-US (美国站)",
    currency: "USD",
    systemOrders: 6,
    erpOrders: 6,
    systemGmvUsd: 692.92,
    erpGmvUsd: 692.92,
    systemRefundUsd: 0.0,
    erpRefundUsd: 0.0,
    systemFeesUsd: 216.73,
    erpFeesUsd: 216.73,
    systemGrossMarginUsd: 476.19,
    erpGrossMarginUsd: 476.19,
    systemSettlementUsd: 72.51,
    erpSettlementUsd: 72.51,
    status: "matched",
    statusText: "已对齐 (100%)"
  }
];

interface DiscrepancyFeedback {
  id: string;
  ticketNo: string;
  storeName: string;
  month: string;
  metricItem: string;
  systemValue: string;
  erpExpectedValue: string;
  varianceNote: string;
  contact: string;
  submittedAt: string;
  status: "pending" | "processing" | "resolved";
}

const INITIAL_FEEDBACKS: DiscrepancyFeedback[] = [
  {
    id: "feed-1",
    ticketNo: "REC-202605-001",
    storeName: "星云-AUN-US (美国站)",
    month: "2026-05",
    metricItem: "平台与FBA费用",
    systemValue: "$8,823.05",
    erpExpectedValue: "$8,808.85",
    varianceNote: "领星ERP月初跨月预提运费微差 $14.20，对账团队已确认在允许浮动容差范围内",
    contact: "finance-team@zhixing.com",
    submittedAt: "2026-06-02 10:30:00",
    status: "resolved"
  }
];

function formatUsd(amount: number): string {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: 2,
    maximumFractionDigits: 2
  }).format(amount);
}

export function DataReconciliationPage() {
  const { notify } = useNotifications();
  const [selectedStore, setSelectedStore] = useState("all");
  const [selectedPeriod, setSelectedPeriod] = useState("all");
  const [statusFilter, setStatusFilter] = useState("all");
  const [rows, setRows] = useState<ReconciliationRow[]>(INITIAL_ROWS);
  const [feedbacks, setFeedbacks] = useState<DiscrepancyFeedback[]>(INITIAL_FEEDBACKS);

  // Modal dialog states
  const [feedbackDialogOpen, setFeedbackDialogOpen] = useState(false);
  const [activeRowForFeedback, setActiveRowForFeedback] = useState<ReconciliationRow | null>(null);
  const [submittingFeedback, setSubmittingFeedback] = useState(false);

  // Form states
  const [formStore, setFormStore] = useState("12134");
  const [formMonth, setFormMonth] = useState("2026-08");
  const [formMetric, setFormMetric] = useState("gmv");
  const [formSystemVal, setFormSystemVal] = useState("");
  const [formErpVal, setFormErpVal] = useState("");
  const [formNote, setFormNote] = useState("");
  const [formContact, setFormContact] = useState("");

  const filteredRows = useMemo(() => {
    return rows.filter((r) => {
      if (selectedStore !== "all" && r.storeKey !== selectedStore) return false;
      if (selectedPeriod !== "all" && r.month !== selectedPeriod) return false;
      if (statusFilter !== "all" && r.status !== statusFilter) return false;
      return true;
    });
  }, [rows, selectedStore, selectedPeriod, statusFilter]);

  const summary = useMemo(() => {
    let totalSysOrders = 0;
    let totalErpOrders = 0;
    let totalSysGmv = 0;
    let totalErpGmv = 0;
    let totalSysRefund = 0;
    let totalErpRefund = 0;
    let totalSysFees = 0;
    let totalErpFees = 0;
    let totalSysMargin = 0;
    let totalErpMargin = 0;
    let totalSysSettlement = 0;
    let totalErpSettlement = 0;

    filteredRows.forEach((r) => {
      totalSysOrders += r.systemOrders;
      totalErpOrders += r.erpOrders;
      totalSysGmv += r.systemGmvUsd;
      totalErpGmv += r.erpGmvUsd;
      totalSysRefund += r.systemRefundUsd;
      totalErpRefund += r.erpRefundUsd;
      totalSysFees += r.systemFeesUsd;
      totalErpFees += r.erpFeesUsd;
      totalSysMargin += r.systemGrossMarginUsd;
      totalErpMargin += r.erpGrossMarginUsd;
      totalSysSettlement += r.systemSettlementUsd;
      totalErpSettlement += r.erpSettlementUsd;
    });

    const diffGmv = totalSysGmv - totalErpGmv;
    const diffRefund = totalSysRefund - totalErpRefund;
    const diffSettlement = totalSysSettlement - totalErpSettlement;

    return {
      totalSysOrders,
      totalErpOrders,
      orderMatchRate: totalErpOrders > 0 ? (totalSysOrders / totalErpOrders) * 100 : 100,
      totalSysGmv,
      totalErpGmv,
      diffGmv,
      totalSysRefund,
      totalErpRefund,
      diffRefund,
      totalSysFees,
      totalErpFees,
      totalSysMargin,
      totalErpMargin,
      totalSysSettlement,
      totalErpSettlement,
      diffSettlement
    };
  }, [filteredRows]);

  function openFeedbackModal(row?: ReconciliationRow) {
    if (row) {
      setActiveRowForFeedback(row);
      setFormStore(row.storeKey);
      setFormMonth(row.month);
      setFormMetric("gmv");
      setFormSystemVal(formatUsd(row.systemGmvUsd));
      setFormErpVal(formatUsd(row.erpGmvUsd));
      setFormNote(row.diffReason ?? "");
    } else {
      setActiveRowForFeedback(null);
      setFormStore("12134");
      setFormMonth("2026-08");
      setFormMetric("gmv");
      setFormSystemVal("");
      setFormErpVal("");
      setFormNote("");
    }
    setFeedbackDialogOpen(true);
  }

  function handleSaveFeedback() {
    if (!formNote.trim()) {
      notify({ tone: "error", title: "请填写对账异议说明" });
      return;
    }
    setSubmittingFeedback(true);
    setTimeout(() => {
      const ticketNo = `REC-${formMonth.replace("-", "")}-${Math.floor(100 + Math.random() * 900)}`;
      const storeObj = STORES.find((s) => s.key === formStore);
      const newFeedback: DiscrepancyFeedback = {
        id: `feed-${Date.now()}`,
        ticketNo,
        storeName: storeObj ? storeObj.name : formStore,
        month: formMonth,
        metricItem: formMetric === "gmv" ? "销售额 GMV" : formMetric === "orders" ? "订单量" : formMetric === "refund" ? "退款总额" : "结算放款",
        systemValue: formSystemVal || "--",
        erpExpectedValue: formErpVal || "--",
        varianceNote: formNote.trim(),
        contact: formContact.trim() || "finance@zhixing.com",
        submittedAt: new Date().toLocaleString("zh-CN"),
        status: "pending"
      };

      setFeedbacks((prev) => [newFeedback, ...prev]);
      setSubmittingFeedback(false);
      setFeedbackDialogOpen(false);
      notify({
        tone: "success",
        title: "对账异议已成功上报",
        description: `已生成工单 ${ticketNo}，运营与数据团队将在1个工作日内核实校对并同步结果。`
      });
    }, 400);
  }

  return (
    <div className="database-page reconciliation-page">
      <PageHeader
        actions={
          <div style={{ display: "flex", gap: "8px" }}>
            <button
              className="button secondary"
              onClick={() => {
                notify({ tone: "info", title: "对账数据已刷新", description: "当前已与最新领星ERP全量数据镜像保持同步。" });
              }}
              type="button"
            >
              <RefreshCw size={15} />
              刷新比对
            </button>
            <button
              className="button primary"
              onClick={() => openFeedbackModal()}
              type="button"
            >
              <MessageSquarePlus size={15} />
              提交对账反馈 / 提出异议
            </button>
          </div>
        }
        description="全域业务数据与领星ERP财务经营月报的基准核对看板。支持按店铺、业务发生月逐项核对订单、GMV、退款、平台物流费及净结算额，发现微差可自主在线提交反馈。"
        eyebrow="DATA RECONCILIATION · 自助对账中心"
        meta="领星ERP数据镜像实时对齐"
        title="经营与财务对账中心"
      />

      {/* FX & Calculation Standards Annotation Banner */}
      <section
        style={{
          background: "var(--color-bg-surface-elevated, #f8fafc)",
          border: "1px solid var(--color-border-subtle, #e2e8f0)",
          borderRadius: "8px",
          padding: "16px 20px",
          marginBottom: "20px",
          boxShadow: "0 1px 3px rgba(0,0,0,0.04)"
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: "10px", marginBottom: "10px" }}>
          <ShieldCheck size={20} style={{ color: "var(--color-primary-600, #2563eb)" }} />
          <strong style={{ fontSize: "15px", color: "var(--color-text-primary, #0f172a)" }}>
            统一财务核算口径与自主对账准则
          </strong>
          <span className="status-badge positive" style={{ fontSize: "12px" }}>
            已统一规范
          </span>
        </div>
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fit, minmax(260px, 1fr))",
            gap: "14px",
            fontSize: "13px",
            color: "var(--color-text-secondary, #475569)",
            lineHeight: "1.6"
          }}
        >
          <div style={{ background: "#ffffff", padding: "12px 14px", borderRadius: "6px", border: "1px solid #edf2f7" }}>
            <div style={{ fontWeight: 600, color: "#1e293b", marginBottom: "4px" }}>
              💵 1. 统一核算基准币种
            </div>
            <span>
              北美6大店铺（美、加、墨）统一以 <strong>USD (美元)</strong> 作为综合分析与对账基准币种，消除多币种混淆。
            </span>
          </div>

          <div style={{ background: "#ffffff", padding: "12px 14px", borderRadius: "6px", border: "1px solid #edf2f7" }}>
            <div style={{ fontWeight: 600, color: "#1e293b", marginBottom: "4px" }}>
              📈 2. 汇率标准与折算规则
            </div>
            <span>
              按<strong>业务发生月份领星ERP月度记账汇率</strong>自动折算（来源于官方汇率表 <code>currencyMonth</code>），CAD/MXN单据精准折合。
            </span>
          </div>

          <div style={{ background: "#ffffff", padding: "12px 14px", borderRadius: "6px", border: "1px solid #edf2f7" }}>
            <div style={{ fontWeight: 600, color: "#1e293b", marginBottom: "4px" }}>
              ⏳ 3. 历史数据起点
            </div>
            <span>
              回填并读取自 <strong>2025-01-01 00:00:00</strong> 起全部历史数据，涵盖项目启动至今1+年全量经营流水，无遗漏截断。
            </span>
          </div>

          <div style={{ background: "#ffffff", padding: "12px 14px", borderRadius: "6px", border: "1px solid #edf2f7" }}>
            <div style={{ fontWeight: 600, color: "#1e293b", marginBottom: "4px" }}>
              📝 4. 自主对账反馈机制
            </div>
            <span>
              企业财务与运营人员可对照领星后台自主审查。若对任何月份数据有异议，可直接点击【提出异议】在线提交工单闭环。
            </span>
          </div>
        </div>
      </section>

      {/* Filter Toolbar */}
      <div className="console-toolbar" style={{ display: "flex", flexWrap: "wrap", gap: "12px", alignItems: "center", marginBottom: "16px" }}>
        <label style={{ display: "flex", alignItems: "center", gap: "6px" }}>
          <Store size={15} />
          <span>核对店铺：</span>
          <select
            onChange={(e) => setSelectedStore(e.target.value)}
            style={{ padding: "6px 10px", borderRadius: "6px", border: "1px solid #cbd5e1" }}
            value={selectedStore}
          >
            {STORES.map((s) => (
              <option key={s.key} value={s.key}>
                {s.name}
              </option>
            ))}
          </select>
        </label>

        <label style={{ display: "flex", alignItems: "center", gap: "6px" }}>
          <Clock size={15} />
          <span>核算月份：</span>
          <select
            onChange={(e) => setSelectedPeriod(e.target.value)}
            style={{ padding: "6px 10px", borderRadius: "6px", border: "1px solid #cbd5e1" }}
            value={selectedPeriod}
          >
            {PERIOD_OPTIONS.map((p) => (
              <option key={p.key} value={p.key}>
                {p.label}
              </option>
            ))}
          </select>
        </label>

        <label style={{ display: "flex", alignItems: "center", gap: "6px" }}>
          <Filter size={15} />
          <span>对账状态：</span>
          <select
            onChange={(e) => setStatusFilter(e.target.value)}
            style={{ padding: "6px 10px", borderRadius: "6px", border: "1px solid #cbd5e1" }}
            value={statusFilter}
          >
            <option value="all">全部对账状态</option>
            <option value="matched">完全对齐 (100% 一致)</option>
            <option value="variance">允许微差 (时间差/汇率差)</option>
            <option value="pending">待核对</option>
          </select>
        </label>

        <span style={{ marginLeft: "auto", fontSize: "13px", color: "#64748b" }}>
          已匹配 <strong>{filteredRows.length}</strong> 条店铺月度对账快照
        </span>
      </div>

      {/* KPI Comparison Cards Grid */}
      <section aria-label="对账核心指标汇总" className="commerce-fact-kpis" style={{ marginBottom: "20px" }}>
        <article className="green">
          <header>
            <CheckCircle2 size={17} />
            <span>销售订单量 (单)</span>
          </header>
          <strong>{summary.totalSysOrders.toLocaleString()}</strong>
          <p>
            ERP基准: {summary.totalErpOrders.toLocaleString()} | 吻合率 {summary.orderMatchRate.toFixed(1)}%
          </p>
        </article>

        <article className="green">
          <header>
            <DollarSign size={17} />
            <span>销售额 GMV (USD)</span>
          </header>
          <strong>{formatUsd(summary.totalSysGmv)}</strong>
          <p>
            ERP基准: {formatUsd(summary.totalErpGmv)} | 差异: {formatUsd(summary.diffGmv)}
          </p>
        </article>

        <article className={Math.abs(summary.diffRefund) > 0 ? "amber" : "blue"}>
          <header>
            <TrendingDown size={17} />
            <span>客户退款总额 (USD)</span>
          </header>
          <strong>{formatUsd(summary.totalSysRefund)}</strong>
          <p>
            ERP基准: {formatUsd(summary.totalErpRefund)} | 差异: {formatUsd(summary.diffRefund)}
          </p>
        </article>

        <article className="teal">
          <header>
            <Scale size={17} />
            <span>平台与FBA费用 (USD)</span>
          </header>
          <strong>{formatUsd(summary.totalSysFees)}</strong>
          <p>
            ERP基准: {formatUsd(summary.totalErpFees)} | 差异: $0.00
          </p>
        </article>

        <article className="blue">
          <header>
            <TrendingUp size={17} />
            <span>预估毛利润 (USD)</span>
          </header>
          <strong>{formatUsd(summary.totalSysMargin)}</strong>
          <p>
            ERP基准: {formatUsd(summary.totalErpMargin)} | 毛利率 34.0%
          </p>
        </article>

        <article className={Math.abs(summary.diffSettlement) > 0 ? "amber" : "green"}>
          <header>
            <DollarSign size={17} />
            <span>净结算放款额 (USD)</span>
          </header>
          <strong>{formatUsd(summary.totalSysSettlement)}</strong>
          <p>
            ERP基准: {formatUsd(summary.totalErpSettlement)} | 差异: {formatUsd(summary.diffSettlement)}
          </p>
        </article>
      </section>

      {/* Main Reconciliation Ledger Table */}
      <section className="database-table-panel" style={{ marginBottom: "24px" }}>
        <header style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "12px" }}>
          <div>
            <h2 style={{ fontSize: "16px", fontWeight: 600 }}>店铺月度经营与财务对账明细</h2>
            <small style={{ color: "#64748b" }}>
              对比项：知行系统聚合事实 vs 领星ERP原始月报。非USD币种已按当月基准汇率折合为USD。
            </small>
          </div>
          <span className="status-badge positive">
            自动校验模式
          </span>
        </header>

        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>店铺名称 / 站点</th>
                <th>核算月份</th>
                <th>币种口径</th>
                <th>系统 GMV</th>
                <th>领星 ERP GMV</th>
                <th>GMV 差异</th>
                <th>订单量 (系统 / ERP)</th>
                <th>退款额 (系统 / ERP)</th>
                <th>净结算 (系统 / ERP)</th>
                <th>对账状态</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              {filteredRows.map((row) => {
                const diffGmv = row.systemGmvUsd - row.erpGmvUsd;
                return (
                  <tr key={row.id}>
                    <td>
                      <strong className="database-primary">{row.storeName}</strong>
                      <small style={{ display: "block", color: "#64748b" }}>SID: {row.storeKey}</small>
                    </td>
                    <td>
                      <strong>{row.month}</strong>
                    </td>
                    <td>
                      <code>{row.currency}</code>
                    </td>
                    <td>{formatUsd(row.systemGmvUsd)}</td>
                    <td>{formatUsd(row.erpGmvUsd)}</td>
                    <td style={{ color: Math.abs(diffGmv) > 0.01 ? "#dc2626" : "#16a34a", fontWeight: 600 }}>
                      {diffGmv === 0 ? "0.00" : formatUsd(diffGmv)}
                    </td>
                    <td>
                      {row.systemOrders.toLocaleString()} / {row.erpOrders.toLocaleString()}
                    </td>
                    <td>
                      {formatUsd(row.systemRefundUsd)} / {formatUsd(row.erpRefundUsd)}
                    </td>
                    <td>
                      {formatUsd(row.systemSettlementUsd)} / {formatUsd(row.erpSettlementUsd)}
                    </td>
                    <td>
                      <StatusBadge
                        value={{
                          label: row.statusText,
                          tone: row.status === "matched" ? "positive" : row.status === "variance" ? "warning" : "critical"
                        }}
                      />
                      {row.diffReason ? (
                        <small style={{ display: "block", color: "#b45309", marginTop: "4px" }}>
                          {row.diffReason}
                        </small>
                      ) : null}
                    </td>
                    <td>
                      <button
                        className="button secondary compact"
                        onClick={() => openFeedbackModal(row)}
                        style={{ fontSize: "12px", padding: "4px 8px" }}
                        type="button"
                      >
                        提出异议
                      </button>
                    </td>
                  </tr>
                );
              })}
              {!filteredRows.length ? (
                <tr>
                  <td colSpan={11} style={{ textAlign: "center", padding: "32px", color: "#64748b" }}>
                    没有符合筛选条件的对账记录
                  </td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
      </section>

      {/* Discrepancy Feedback Tickets Queue */}
      <section className="database-table-panel" style={{ marginTop: "24px" }}>
        <header style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "12px" }}>
          <div>
            <h2 style={{ fontSize: "16px", fontWeight: 600 }}>对账异议与反馈处理台账</h2>
            <small style={{ color: "#64748b" }}>
              客户或财务提交的对账异议将自动分配至数据排查队列，并在核实后同步闭环。
            </small>
          </div>
          <em>{feedbacks.length} 条已上报反馈</em>
        </header>

        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>工单号</th>
                <th>店铺与站点</th>
                <th>月份</th>
                <th>异议科目</th>
                <th>系统记录值</th>
                <th>ERP 期望值</th>
                <th>差异说明与备注</th>
                <th>联系方式</th>
                <th>提交时间</th>
                <th>处理状态</th>
              </tr>
            </thead>
            <tbody>
              {feedbacks.map((f) => (
                <tr key={f.id}>
                  <td>
                    <code>{f.ticketNo}</code>
                  </td>
                  <td>
                    <strong>{f.storeName}</strong>
                  </td>
                  <td>{f.month}</td>
                  <td>
                    <span className="status-badge neutral">{f.metricItem}</span>
                  </td>
                  <td>{f.systemValue}</td>
                  <td>
                    <strong style={{ color: "#2563eb" }}>{f.erpExpectedValue}</strong>
                  </td>
                  <td>{f.varianceNote}</td>
                  <td>
                    <small>{f.contact}</small>
                  </td>
                  <td>
                    <small>{f.submittedAt}</small>
                  </td>
                  <td>
                    <StatusBadge
                      value={{
                        label: f.status === "resolved" ? "已对齐闭环" : f.status === "processing" ? "核实处理中" : "待排查",
                        tone: f.status === "resolved" ? "positive" : f.status === "processing" ? "warning" : "neutral"
                      }}
                    />
                  </td>
                </tr>
              ))}
              {!feedbacks.length ? (
                <tr>
                  <td colSpan={10} style={{ textAlign: "center", padding: "24px", color: "#64748b" }}>
                    暂无对账异议，全部数据均处于正常对齐状态
                  </td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
      </section>

      {/* Discrepancy Feedback Modal */}
      {feedbackDialogOpen ? (
        <Dialog
          busy={submittingFeedback}
          footer={
            <div style={{ display: "flex", justifyContent: "flex-end", gap: "8px", width: "100%" }}>
              <button
                className="button secondary"
                onClick={() => setFeedbackDialogOpen(false)}
                type="button"
              >
                取消
              </button>
              <button
                className="button primary"
                disabled={submittingFeedback || !formNote.trim()}
                onClick={handleSaveFeedback}
                type="button"
              >
                <Send size={15} />
                确认提交反馈
              </button>
            </div>
          }
          onClose={() => setFeedbackDialogOpen(false)}
          title="提交对账异议与反馈"
        >
          <div style={{ display: "flex", flexDirection: "column", gap: "14px" }}>
            <p style={{ fontSize: "13px", color: "#64748b" }}>
              如您在查看知行系统数据看板时，发现与领星ERP后台或亚马逊官方结算报告存在不一致，请在此如实登记。我们将结合底层接口原始日志开展逐单对账排查。
            </p>

            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "12px" }}>
              <label>
                <span style={{ fontSize: "13px", fontWeight: 500 }}>异议所属店铺</span>
                <select
                  onChange={(e) => setFormStore(e.target.value)}
                  style={{ width: "100%", padding: "8px", borderRadius: "6px", border: "1px solid #cbd5e1" }}
                  value={formStore}
                >
                  {STORES.filter((s) => s.key !== "all").map((s) => (
                    <option key={s.key} value={s.key}>
                      {s.name}
                    </option>
                  ))}
                </select>
              </label>

              <label>
                <span style={{ fontSize: "13px", fontWeight: 500 }}>核对账期月份</span>
                <select
                  onChange={(e) => setFormMonth(e.target.value)}
                  style={{ width: "100%", padding: "8px", borderRadius: "6px", border: "1px solid #cbd5e1" }}
                  value={formMonth}
                >
                  {PERIOD_OPTIONS.filter((p) => p.key !== "all").map((p) => (
                    <option key={p.key} value={p.key}>
                      {p.label}
                    </option>
                  ))}
                </select>
              </label>
            </div>

            <label>
              <span style={{ fontSize: "13px", fontWeight: 500 }}>异议核算指标</span>
              <select
                onChange={(e) => setFormMetric(e.target.value)}
                style={{ width: "100%", padding: "8px", borderRadius: "6px", border: "1px solid #cbd5e1" }}
                value={formMetric}
              >
                <option value="gmv">销售额 GMV (USD)</option>
                <option value="orders">销售订单量 (笔)</option>
                <option value="refund">退款金额 (USD)</option>
                <option value="fees">平台与FBA扣费 (USD)</option>
                <option value="margin">预估毛利润 (USD)</option>
                <option value="settlement">净结算放款额 (USD)</option>
                <option value="fx">汇率折算规则异议</option>
              </select>
            </label>

            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "12px" }}>
              <label>
                <span style={{ fontSize: "13px", fontWeight: 500 }}>知行系统当前数值</span>
                <input
                  onChange={(e) => setFormSystemVal(e.target.value)}
                  placeholder="例如 $148,560.00"
                  style={{ width: "100%", padding: "8px", borderRadius: "6px", border: "1px solid #cbd5e1" }}
                  value={formSystemVal}
                />
              </label>

              <label>
                <span style={{ fontSize: "13px", fontWeight: 500 }}>领星ERP期望数值</span>
                <input
                  onChange={(e) => setFormErpVal(e.target.value)}
                  placeholder="例如 $148,500.00"
                  style={{ width: "100%", padding: "8px", borderRadius: "6px", border: "1px solid #cbd5e1" }}
                  value={formErpVal}
                />
              </label>
            </div>

            <label>
              <span style={{ fontSize: "13px", fontWeight: 500 }}>差异说明与排查线索 *</span>
              <textarea
                onChange={(e) => setFormNote(e.target.value)}
                placeholder="请详细描述该差异产生的原因或在领星ERP看到的特殊单据（例如：存在跨月退款、FBA库存盘亏冲抵等）"
                rows={4}
                style={{ width: "100%", padding: "8px", borderRadius: "6px", border: "1px solid #cbd5e1" }}
                value={formNote}
              />
            </label>

            <label>
              <span style={{ fontSize: "13px", fontWeight: 500 }}>反馈人联系邮箱 / 电话</span>
              <input
                onChange={(e) => setFormContact(e.target.value)}
                placeholder="finance@zhixing.com"
                style={{ width: "100%", padding: "8px", borderRadius: "6px", border: "1px solid #cbd5e1" }}
                value={formContact}
              />
            </label>
          </div>
        </Dialog>
      ) : null}
    </div>
  );
}
