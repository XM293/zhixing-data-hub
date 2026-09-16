from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from math import atan2, cos, pi, sin
from typing import cast

from sqlalchemy import select

from zhixing_api.auth_service import hash_password
from zhixing_api.channel_identity_seed import (
    channel_identity_seed_checksum_payload,
    seed_channel_identities,
)
from zhixing_api.config import API_ROOT, Settings
from zhixing_api.customer_service_seed import (
    customer_service_seed_checksum_payload,
    seed_customer_service,
)
from zhixing_api.data_models import (
    BusinessUnit,
    ConsolidationProfile,
    DataQualityRule,
    Enterprise,
    EnterpriseGroup,
    EnterpriseMembership,
    ExternalSystem,
    MetricDefinition,
    MetricSnapshot,
    PlatformEvent,
    Principal,
    SeedVersion,
    SourceRecord,
    TwinActor,
    TwinDataLayer,
    TwinEdge,
    TwinHotspot,
    TwinInteractionProfile,
    TwinMeeting,
    TwinMeetingParticipant,
    TwinMeetingSeat,
    TwinNode,
    TwinRoute,
    TwinScene,
    TwinSpace,
)
from zhixing_api.database import Database
from zhixing_api.decision_seed import decision_seed_checksum_payload, seed_decision_runtime
from zhixing_api.evaluation_seed import evaluation_seed_checksum_payload, seed_evaluations
from zhixing_api.identity_seed import identity_seed_checksum_payload, seed_identity
from zhixing_api.knowledge_seed import knowledge_seed_checksum_payload, seed_knowledge
from zhixing_api.platform_admin_seed import (
    platform_admin_seed_checksum_payload,
    seed_platform_admin,
)
from zhixing_api.role_twin_test_seed import (
    role_twin_test_seed_checksum_payload,
    seed_role_twin_tests,
)
from zhixing_api.skill_seed import seed_skill_registry
from zhixing_api.tool_seed import seed_tool_registry, tool_seed_checksum_payload

ENTERPRISE_ID = "ent_zhixing_demo"
ERP_OMS_SYSTEM_ID = "source_mock_commerce"
CRM_SYSTEM_ID = "source_mock_crm"
ADVERTISING_SYSTEM_ID = "source_mock_advertising"
CUSTOMER_SERVICE_SYSTEM_ID = "source_mock_customer_service"
MOCK_SYSTEM_ID = ERP_OMS_SYSTEM_ID
SCENE_ID = "scene_enterprise_campus"
WAREHOUSE_SCENE_ID = "scene_warehouse_interior"
MEETING_SCENE_ID = "scene_decision_room_interior"
MEETING_ID = "meeting_budget_review"
SEED_MANIFEST_PATH = API_ROOT / "seeds" / "demo-operational-twin.v1.json"

METRIC_DEFINITION_SEEDS = [
    (
        "gmv_today",
        "今日成交",
        "统计业务日内已支付订单的含税成交金额。",
        "sum(paid_order.amount_tax_included)",
        "元",
        ["business_date", "store", "channel", "product"],
        "经营分析中心",
        "v1.0",
    ),
    (
        "orders_today",
        "支付订单",
        "统计业务日内完成支付的去重订单数量。",
        "count_distinct(paid_order.order_id)",
        "单",
        ["business_date", "store", "channel"],
        "经营分析中心",
        "v1.0",
    ),
    (
        "refund_rate",
        "退款率",
        "退款金额占同期支付金额的比例。",
        "sum(refund.amount) / nullif(sum(paid_order.amount), 0)",
        "%",
        ["business_date", "store", "channel", "product"],
        "财务中心",
        "v1.0",
    ),
    (
        "ad_roi",
        "广告 ROI",
        "归因成交金额与广告实际消耗的比值。",
        "sum(attributed_gmv) / nullif(sum(ad_spend), 0)",
        "x",
        ["business_date", "store", "platform", "campaign"],
        "投放中心",
        "v1.0",
    ),
    (
        "active_members",
        "活跃会员",
        "统计观察窗口内发生有效互动或交易的去重会员数。",
        "count_distinct(active_customer.customer_id)",
        "人",
        ["business_date", "store", "member_level"],
        "客服中心",
        "v1.0",
    ),
    (
        "low_stock_skus",
        "低库存 SKU",
        "可售库存低于安全库存的 SKU 数量。",
        "count(sku where available_stock < safety_stock)",
        "SKU",
        ["business_date", "warehouse", "store", "category"],
        "供应链中心",
        "v1.0",
    ),
]

METRIC_DEFINITION_SEEDS.extend(
    [
        (
            "gross_margin_rate",
            "毛利率",
            "销售收入扣除商品成本后的毛利占销售收入比例。",
            "sum(net_revenue - cost_of_goods) / nullif(sum(net_revenue), 0)",
            "%",
            ["business_date", "store", "channel", "product"],
            "财务中心",
            "v1.0",
        ),
        (
            "fulfillment_rate",
            "履约及时率",
            "承诺时效内完成出库或交接承运商的订单比例。",
            "count(on_time_fulfilled_order) / nullif(count(paid_order), 0)",
            "%",
            ["business_date", "store", "warehouse", "carrier"],
            "供应链中心",
            "v1.0",
        ),
        (
            "inventory_turnover_days",
            "库存周转天数",
            "按当前销售成本折算的平均库存周转天数。",
            "average_inventory / nullif(cost_of_goods_sold, 0) * period_days",
            "天",
            ["business_date", "warehouse", "category"],
            "供应链中心",
            "v1.0",
        ),
        (
            "new_members",
            "新增会员",
            "观察业务日内首次完成会员注册的去重客户数。",
            "count_distinct(customer where registered_on = business_date)",
            "人",
            ["business_date", "store", "channel"],
            "会员运营中心",
            "v1.0",
        ),
        (
            "repeat_purchase_rate",
            "复购率",
            "观察窗口内完成两次及以上有效购买的客户比例。",
            "count(repeat_customer) / nullif(count(purchasing_customer), 0)",
            "%",
            ["business_date", "store", "member_level"],
            "会员运营中心",
            "v1.0",
        ),
        (
            "churn_risk_members",
            "流失风险会员",
            "达到流失预警规则的有效会员数量。",
            "count(customer where churn_risk = true)",
            "人",
            ["business_date", "store", "member_level", "risk_band"],
            "会员运营中心",
            "v1.0",
        ),
        (
            "ad_spend",
            "广告消耗",
            "业务日内各广告平台已确认的实际消耗金额。",
            "sum(ad_delivery.confirmed_spend)",
            "元",
            ["business_date", "store", "platform", "campaign"],
            "投放中心",
            "v1.0",
        ),
        (
            "attributed_revenue",
            "广告归因成交",
            "按统一归因窗口计算的广告带来成交金额。",
            "sum(attribution.revenue)",
            "元",
            ["business_date", "store", "platform", "campaign"],
            "投放中心",
            "v1.0",
        ),
        (
            "ad_ctr",
            "广告点击率",
            "广告点击次数占有效曝光次数的比例。",
            "sum(clicks) / nullif(sum(impressions), 0)",
            "%",
            ["business_date", "store", "platform", "campaign", "creative"],
            "投放中心",
            "v1.0",
        ),
        (
            "ad_conversion_rate",
            "广告转化率",
            "广告归因支付订单数占有效点击次数的比例。",
            "count(attributed_paid_order) / nullif(sum(clicks), 0)",
            "%",
            ["business_date", "store", "platform", "campaign"],
            "投放中心",
            "v1.0",
        ),
        (
            "service_conversations",
            "客服会话",
            "业务日内进入客服渠道并形成有效互动的会话数。",
            "count_distinct(service_conversation.id)",
            "次",
            ["business_date", "store", "channel", "topic"],
            "客户服务中心",
            "v1.0",
        ),
        (
            "first_response_minutes",
            "首次响应时长",
            "客户首条消息到客服首次有效响应的平均分钟数。",
            "avg(first_response_at - customer_first_message_at)",
            "分钟",
            ["business_date", "store", "channel", "service_team"],
            "客户服务中心",
            "v1.0",
        ),
        (
            "service_resolution_rate",
            "一次解决率",
            "无需重复进线或升级工单即可关闭的客服会话比例。",
            "count(first_contact_resolved) / nullif(count(closed_conversation), 0)",
            "%",
            ["business_date", "store", "channel", "topic"],
            "客户服务中心",
            "v1.0",
        ),
        (
            "csat_score",
            "客户满意度",
            "客服会话结束后有效满意度评价的平均得分。",
            "avg(valid_csat_score)",
            "分",
            ["business_date", "store", "channel", "service_team"],
            "客户服务中心",
            "v1.0",
        ),
        (
            "human_handoff_rate",
            "人工接管率",
            "由 AI 辅助流程升级为人工处理的会话比例。",
            "count(human_handoff) / nullif(count(service_conversation), 0)",
            "%",
            ["business_date", "store", "channel", "risk_level"],
            "客户服务中心",
            "v1.0",
        ),
    ]
)

SOURCE_SYSTEM_SEEDS = (
    (
        ERP_OMS_SYSTEM_ID,
        "jky-erp-oms",
        "吉客云 ERP / OMS 测试源",
        "test-erp-oms",
        "JKY-ERP-2026.08",
        "1.3.0",
    ),
    (
        CRM_SYSTEM_ID,
        "crm-members",
        "CRM 会员测试源",
        "test-crm",
        "CRM-2026.08",
        "1.2.0",
    ),
    (
        ADVERTISING_SYSTEM_ID,
        "advertising-platforms",
        "广告平台测试源",
        "test-advertising",
        "ADS-2026.07",
        "1.1.0",
    ),
    (
        CUSTOMER_SERVICE_SYSTEM_ID,
        "customer-service-channels",
        "客服渠道测试源",
        "test-customer-service",
        "CS-2026.05",
        "1.0.0",
    ),
)

METRIC_SOURCE_SYSTEM_IDS = {
    **{
        key: ERP_OMS_SYSTEM_ID
        for key in (
            "gmv_today",
            "orders_today",
            "refund_rate",
            "low_stock_skus",
            "gross_margin_rate",
            "fulfillment_rate",
            "inventory_turnover_days",
        )
    },
    **{
        key: CRM_SYSTEM_ID
        for key in (
            "active_members",
            "new_members",
            "repeat_purchase_rate",
            "churn_risk_members",
        )
    },
    **{
        key: ADVERTISING_SYSTEM_ID
        for key in (
            "ad_roi",
            "ad_spend",
            "attributed_revenue",
            "ad_ctr",
            "ad_conversion_rate",
        )
    },
    **{
        key: CUSTOMER_SERVICE_SYSTEM_ID
        for key in (
            "service_conversations",
            "first_response_minutes",
            "service_resolution_rate",
            "csat_score",
            "human_handoff_rate",
        )
    },
}

QUALITY_RULE_SEEDS = [
    (
        "source-contract",
        "来源契约版本有效",
        "来源必须声明可识别的数据契约版本。",
        "validity",
        "source",
        "mock-commerce",
        "source_schema_version != unknown",
        "critical",
    ),
    (
        "record-completeness",
        "原始记录载荷完整",
        "同步批次中的原始记录必须包含非空业务载荷。",
        "completeness",
        "source-record",
        "mock-commerce/*",
        "non_empty_payload_rate = 100%",
        "critical",
    ),
    (
        "entity-mapping",
        "主数据映射覆盖",
        "同步批次必须生成至少一个稳定企业实体。",
        "mapping",
        "business-entity",
        "store",
        "mapped_entity_count >= 1",
        "warning",
    ),
    (
        "metric-coverage",
        "经营指标覆盖",
        "电商聚合来源应产出约定的六个首批经营指标。",
        "coverage",
        "metric",
        "commerce-core",
        "metric_count >= 6",
        "warning",
    ),
    (
        "sync-health",
        "同步批次健康度",
        "同步批次应完成全部资源读取且没有连接错误。",
        "freshness",
        "sync-run",
        "mock-commerce",
        "status = succeeded",
        "critical",
    ),
    (
        "customer-service-order-reconciliation",
        "客服订单跨源一致性",
        "订单型客服会话的状态、实付、件数与退款必须和规范交易事实一致。",
        "reconciliation",
        "customer-service-conversation",
        "order-context/*",
        "material_conflict_count = 0 and unresolved_order_count = 0",
        "critical",
    ),
]


@dataclass(frozen=True, slots=True)
class SeedManifest:
    seed_key: str
    version: str
    mode: str
    environments: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class SeedReport:
    seed_key: str
    version: str
    checksum: str
    applied_at: datetime

    def as_dict(self) -> dict[str, object]:
        return {
            "seed_key": self.seed_key,
            "version": self.version,
            "checksum": self.checksum,
            "applied_at": self.applied_at.isoformat(),
        }


class SeedDriftError(RuntimeError):
    pass


def load_seed_manifest() -> SeedManifest:
    payload = json.loads(SEED_MANIFEST_PATH.read_text(encoding="utf8"))
    if payload.get("schema_version") != 1:
        raise RuntimeError("不支持的种子清单 schema_version")
    return SeedManifest(
        seed_key=str(payload["seed_key"]),
        version=str(payload["version"]),
        mode=str(payload["mode"]),
        environments=tuple(str(item) for item in payload["environments"]),
    )


NODE_SEEDS = [
    ("source-commerce", "电商业务系统", "source", -6.2, 0.3, 0.6, "订单、库存、广告与会员原始数据"),
    ("source-crm", "CRM 客户域", "source", -5.3, -2.3, -1.2, "客户关系和服务触点"),
    ("source-docs", "企业文档库", "source", -4.8, 2.5, -1.5, "制度、流程和经营资料"),
    ("integration", "接入与映射层", "integration", -2.8, 0.2, 0.0, "隔离第三方字段并保留映射版本"),
    ("data-hub", "企业数据中心", "core", 0.0, 0.0, 0.0, "统一经营事实、实体和指标快照"),
    ("knowledge", "企业知识中心", "knowledge", -0.7, 2.9, -1.1, "版本化知识与可引用证据"),
    ("memory", "角色记忆中心", "memory", 1.0, -2.7, -1.0, "受审核的角色偏好和经验"),
    ("twin-ceo", "CEO 数字分身", "agent", 3.4, 2.4, 0.5, "基于权限、事实和证据参与决策"),
    ("twin-ops", "运营经理分身", "agent", 4.0, 0.1, -0.5, "店铺经营诊断与运营建议"),
    ("digital-meeting", "数字会议", "meeting", 3.1, -2.5, 0.8, "多角色独立研判和分歧留痕"),
    ("analysis", "智能分析", "analysis", 1.8, 1.5, 2.3, "指标归因、预测和异常识别"),
    ("action", "行动与执行", "action", 1.7, -1.7, 2.6, "审批后的工具调用与执行台账"),
    ("service", "智能客服", "service", 5.8, -1.2, 1.9, "订单上下文辅助与自动回复"),
]

EDGE_SEEDS = [
    ("commerce-integration", "source-commerce", "integration", "ingest"),
    ("crm-integration", "source-crm", "integration", "ingest"),
    ("docs-knowledge", "source-docs", "knowledge", "ingest"),
    ("integration-data", "integration", "data-hub", "normalize"),
    ("data-analysis", "data-hub", "analysis", "facts"),
    ("data-ceo", "data-hub", "twin-ceo", "context"),
    ("data-ops", "data-hub", "twin-ops", "context"),
    ("knowledge-ceo", "knowledge", "twin-ceo", "evidence"),
    ("memory-ceo", "memory", "twin-ceo", "memory"),
    ("ceo-meeting", "twin-ceo", "digital-meeting", "opinion"),
    ("ops-meeting", "twin-ops", "digital-meeting", "opinion"),
    ("analysis-meeting", "analysis", "digital-meeting", "finding"),
    ("meeting-action", "digital-meeting", "action", "decision"),
    ("data-service", "data-hub", "service", "order-context"),
    ("knowledge-service", "knowledge", "service", "policy"),
]

SPACE_SEEDS = [
    (
        "campus",
        "企业经营园区",
        "campus",
        None,
        "online",
        0.96,
        "normal",
        None,
        [0.0, 0.0, 0.0],
        [72.0, 1.0, 48.0],
        "企业经营空间、数据流与智能体协作的统一空间投影。",
    ),
    (
        "data-hall",
        "数据接入大厅",
        "data-hall",
        "campus",
        "online",
        0.98,
        "normal",
        "orders_today",
        [-21.0, 2.4, -10.5],
        [12.0, 4.8, 10.0],
        "吉客云、CRM、广告和知识来源在此完成接入、校验与标准映射。",
    ),
    (
        "operations-center",
        "经营指挥中心",
        "operations",
        "campus",
        "online",
        0.93,
        "normal",
        "gmv_today",
        [-2.0, 3.2, -10.0],
        [16.0, 6.4, 12.0],
        "汇聚店铺、商品、广告、会员和客服指标，承载经营异常研判。",
    ),
    (
        "warehouse",
        "智能仓储",
        "warehouse",
        "campus",
        "attention",
        0.74,
        "warning",
        "low_stock_skus",
        [21.0, 2.6, -8.0],
        [18.0, 5.2, 16.0],
        "库存覆盖下降的 SKU 已进入补货评估，等待运营与财务联合研判。",
    ),
    (
        "knowledge-center",
        "企业知识中心",
        "knowledge",
        "campus",
        "online",
        0.95,
        "normal",
        None,
        [-19.0, 2.6, 12.0],
        [14.0, 5.2, 10.0],
        "版本化制度、流程和经营资料，为问答与决策提供可引用证据。",
    ),
    (
        "twin-studio",
        "数字分身工作室",
        "twin-studio",
        "campus",
        "online",
        0.91,
        "normal",
        None,
        [-1.0, 2.6, 12.0],
        [14.0, 5.2, 10.0],
        "管理岗位分身、个人分身、记忆版本和能力边界。",
    ),
    (
        "decision-room",
        "数字决策会议室",
        "meeting-room",
        "campus",
        "ready",
        0.97,
        "normal",
        "ad_roi",
        [18.0, 2.6, 12.0],
        [14.0, 5.2, 10.0],
        "角色分身围绕同一证据快照独立研判、质询并形成决策包。",
    ),
]

ACTOR_SEEDS = [
    (
        "twin-ceo",
        "林知远分身",
        "CEO 决策分身",
        "twin-studio",
        [-2.0, 0.12, 12.8],
        "#70e1c1",
        ["战略研判", "制度解释", "决策主持"],
    ),
    (
        "twin-ops",
        "周岚分身",
        "运营负责人分身",
        "operations-center",
        [-2.0, 0.12, -9.6],
        "#57b8ff",
        ["店铺诊断", "广告优化", "运营执行"],
    ),
    (
        "twin-finance",
        "陈硕分身",
        "财务负责人分身",
        "data-hall",
        [-21.0, 0.12, -10.0],
        "#e7b45f",
        ["预算约束", "利润分析", "风险复核"],
    ),
]

ROUTE_SEEDS = [
    (
        "ceo-to-decision-room",
        "twin-studio",
        "decision-room",
        [
            [-2.0, 0.12, 12.8],
            [3.0, 0.12, 7.0],
            [8.0, 0.12, 7.0],
            [12.5, 0.12, 10.0],
            [17.0, 0.12, 12.0],
        ],
    ),
    (
        "ops-to-decision-room",
        "operations-center",
        "decision-room",
        [
            [-2.0, 0.12, -9.6],
            [-2.0, 0.12, -2.0],
            [5.0, 0.12, 0.0],
            [10.0, 0.12, 5.0],
            [17.0, 0.12, 12.0],
        ],
    ),
    (
        "finance-to-decision-room",
        "data-hall",
        "decision-room",
        [
            [-21.0, 0.12, -10.0],
            [-14.0, 0.12, -3.0],
            [-6.0, 0.12, 0.0],
            [7.0, 0.12, 4.0],
            [17.0, 0.12, 12.0],
        ],
    ),
]

PARTICIPANT_SEEDS = [
    (
        "twin-ceo",
        "谨慎推进",
        "销售增长真实，但新增流量质量必须通过限额实验验证。",
    ),
    (
        "twin-ops",
        "小范围加投",
        "素材组 B 转化稳定，建议只在高转化时段增加预算。",
    ),
    (
        "twin-finance",
        "设置停止条件",
        "ROI 下降已超过阈值，预算上限和自动停止条件不可缺失。",
    ),
]

PARTICIPANT_SEAT_KEYS = {
    "twin-ceo": "seat-01",
    "twin-ops": "seat-05",
    "twin-finance": "seat-09",
}

MEETING_SEAT_SEEDS = [
    (
        f"seat-{index + 1:02d}",
        f"{index + 1:02d} 号席位",
        "boardroom-12",
        [
            round(5.2 * cos(pi / 2 + index * 2 * pi / 12), 4),
            0.08,
            round(0.2 + 3.35 * sin(pi / 2 + index * 2 * pi / 12), 4),
        ],
        round(
            atan2(
                5.2 * cos(pi / 2 + index * 2 * pi / 12),
                3.35 * sin(pi / 2 + index * 2 * pi / 12),
            ),
            6,
        ),
        "available",
    )
    for index in range(12)
]

SCENE_SEEDS = [
    (
        SCENE_ID,
        "enterprise-campus",
        "知行企业经营数字孪生",
        "2.0.0",
        "campus",
        None,
        None,
        "procedural-campus-v2",
        "从企业园区进入经营空间，观察数据、组织与智能体协同运行。",
        {
            "overview": {"position": [56.0, 38.0, 62.0], "look_at": [0.0, 2.0, 0.0]},
            "operations": {"position": [25.0, 11.5, 18.0], "look_at": [-2.0, 2.8, -10.0]},
            "warehouse": {"position": [48.0, 11.5, 20.0], "look_at": [21.0, 2.1, -8.0]},
            "meeting": {"position": [42.0, 11.5, 34.0], "look_at": [18.0, 2.2, 12.0]},
        },
    ),
    (
        WAREHOUSE_SCENE_ID,
        "warehouse-interior",
        "智能仓储运行空间",
        "1.0.0",
        "space",
        "enterprise-campus",
        "warehouse",
        "procedural-warehouse-v1",
        "以库位、SKU 风险和履约流向组织的仓储经营空间。",
        {
            "entry": {"position": [13.0, 7.5, 14.5], "look_at": [0.0, 1.4, 0.0]},
            "risk": {"position": [8.8, 5.2, 9.5], "look_at": [-2.6, 1.2, -0.4]},
        },
    ),
    (
        MEETING_SCENE_ID,
        "decision-room-interior",
        "数字决策会议空间",
        "1.0.0",
        "space",
        "enterprise-campus",
        "decision-room",
        "procedural-meeting-v1",
        "围绕证据、角色观点、分歧和行动方案组织的决策空间。",
        {
            "entry": {"position": [11.8, 7.4, 13.2], "look_at": [0.0, 1.45, -0.7]},
            "table": {"position": [7.4, 4.8, 7.2], "look_at": [0.0, 1.2, 0.0]},
        },
    ),
]

HOTSPOT_SEEDS = [
    (
        WAREHOUSE_SCENE_ID,
        "rack-a07-risk",
        "A-07 畅销款库位",
        "sku-slot",
        "attention",
        "critical",
        "sku:ZX-CJY-042:warehouse-east",
        "low_stock_skus",
        [-4.8, 1.25, -2.4],
        {
            "sku": "轻量冲锋衣 · 墨黑 L",
            "stock": 42,
            "coverage_days": 2.8,
            "inbound": "补货单待供应商确认",
        },
    ),
    (
        WAREHOUSE_SCENE_ID,
        "rack-b03-risk",
        "B-03 活动款库位",
        "sku-slot",
        "attention",
        "warning",
        "sku:ZX-TS-118:warehouse-east",
        "low_stock_skus",
        [-1.6, 1.25, 1.8],
        {
            "sku": "速干训练 T 恤 · 雾蓝 M",
            "stock": 86,
            "coverage_days": 4.6,
            "inbound": "预计明日 14:00 到仓",
        },
    ),
    (
        WAREHOUSE_SCENE_ID,
        "rack-d11-healthy",
        "D-11 常规库存库位",
        "sku-slot",
        "online",
        "normal",
        "sku:ZX-KZ-205:warehouse-east",
        "low_stock_skus",
        [4.8, 1.25, -2.4],
        {"sku": "轻量工装裤 · 深灰 32", "stock": 318, "coverage_days": 18.2},
    ),
    (
        WAREHOUSE_SCENE_ID,
        "inbound-dock",
        "入库月台",
        "dock",
        "running",
        "normal",
        "facility:warehouse-east:inbound",
        None,
        [-7.2, 0.5, 4.6],
        {"today_batches": 12, "waiting_batches": 2, "average_minutes": 38},
    ),
    (
        WAREHOUSE_SCENE_ID,
        "outbound-sorter",
        "出库分拣线",
        "conveyor",
        "running",
        "normal",
        "facility:warehouse-east:outbound",
        "orders_today",
        [7.0, 0.65, 4.1],
        {"today_orders": 12684, "backlog": 186, "on_time_rate": 0.982},
    ),
    (
        WAREHOUSE_SCENE_ID,
        "agv-07",
        "AGV-07 搬运单元",
        "automation",
        "running",
        "normal",
        "device:warehouse-east:agv-07",
        None,
        [0.2, 0.35, 4.3],
        {"task": "A-07 → 复核台", "progress": 0.68, "battery": 0.74},
    ),
    (
        MEETING_SCENE_ID,
        "meeting-evidence-wall",
        "经营证据快照",
        "evidence-wall",
        "verified",
        "normal",
        "evidence:evs-budget-0825",
        "ad_roi",
        [-5.2, 1.65, -4.9],
        {
            "snapshot": "evs-budget-0825",
            "source_count": 4,
            "as_of": "2026-08-25 10:00",
            "scope": "旗舰店广告、成交、库存与毛利",
        },
    ),
    (
        MEETING_SCENE_ID,
        "meeting-disagreement-map",
        "核心分歧",
        "deliberation-map",
        "open",
        "warning",
        "meeting:mtg-budget-20260825:conflict-01",
        None,
        [0.0, 1.45, -5.0],
        {
            "conflict": "增长机会与库存、ROI 约束",
            "positions": 3,
            "unresolved": 1,
            "moderator": "林知远分身",
        },
    ),
    (
        MEETING_SCENE_ID,
        "meeting-decision-package",
        "决策包",
        "decision-output",
        "building",
        "normal",
        "decision:mtg-budget-20260825:v1",
        None,
        [5.2, 1.65, -4.9],
        {
            "state": "等待会议生成",
        },
    ),
    (
        MEETING_SCENE_ID,
        "meeting-action-gate",
        "行动与审批闸门",
        "action-gate",
        "guarded",
        "normal",
        "action:budget-experiment:pending",
        None,
        [7.2, 0.85, 2.7],
        {
            "action": "创建广告预算实验",
            "approval": "CEO 与财务负责人",
            "write_mode": "审批后执行",
            "audit": "保留幂等键和完整调用记录",
        },
    ),
]

DATA_LAYER_SEEDS = [
    (
        WAREHOUSE_SCENE_ID,
        "inventory-risk",
        "库存风险",
        "risk",
        True,
        {"normal": "#64d8b8", "warning": "#e3ad59", "critical": "#ec7468"},
    ),
    (
        WAREHOUSE_SCENE_ID,
        "stock-flow",
        "出入库流",
        "flow",
        True,
        {"inbound": "#57b8ff", "outbound": "#70e1c1"},
    ),
    (
        WAREHOUSE_SCENE_ID,
        "automation",
        "自动化设备",
        "asset",
        True,
        {"running": "#a88ee8", "idle": "#607c75"},
    ),
    (
        MEETING_SCENE_ID,
        "evidence-context",
        "证据上下文",
        "evidence",
        True,
        {"verified": "#57b8ff", "stale": "#607c75"},
    ),
    (
        MEETING_SCENE_ID,
        "stance-map",
        "角色观点",
        "deliberation",
        True,
        {"agreement": "#70e1c1", "conflict": "#e3ad59"},
    ),
    (
        MEETING_SCENE_ID,
        "decision-chain",
        "决策与行动",
        "decision",
        True,
        {"draft": "#607c75", "ready": "#f2c66d", "approved": "#70e1c1"},
    ),
]


def _navigate_action(label: str, href: str, icon_key: str) -> dict[str, object]:
    return {
        "key": "open-detail",
        "label": label,
        "action_type": "navigate",
        "href": href,
        "target_key": None,
        "icon_key": icon_key,
        "emphasis": "secondary",
    }


def _enter_action(space_key: str) -> dict[str, object]:
    return {
        "key": "enter-space",
        "label": "进入空间",
        "action_type": "enter",
        "href": None,
        "target_key": space_key,
        "icon_key": "door-open",
        "emphasis": "primary",
    }


def _build_interaction_profile_seeds() -> list[
    tuple[str, str, str | None, str | None, list[dict[str, object]]]
]:
    space_routes = {
        "campus": "/console",
        "data-hall": "/console/data/sources",
        "operations-center": "/console/analysis/store-review",
        "warehouse": "/console/analysis/store-review",
        "knowledge-center": "/console/knowledge/documents",
        "twin-studio": "/console/twins/instances",
        "decision-room": "/console/meetings/mtg-budget-20260825",
    }
    enter_spaces = {"warehouse", "decision-room"}
    result: list[tuple[str, str, str | None, str | None, list[dict[str, object]]]] = []
    for seed in SPACE_SEEDS:
        space_key = str(seed[0])
        detail_route = space_routes[space_key]
        actions = []
        if space_key in enter_spaces:
            actions.append(_enter_action(space_key))
        actions.append(_navigate_action("查看经营数据", detail_route, "chart"))
        result.append(
            (
                space_key,
                "space",
                detail_route,
                space_key if space_key in enter_spaces else None,
                actions,
            )
        )

    for actor_seed in ACTOR_SEEDS:
        actor_key = str(actor_seed[0])
        detail_route = "/console/twins/instances"
        result.append(
            (
                actor_key,
                "actor",
                detail_route,
                None,
                [_navigate_action("查看分身档案", detail_route, "user-round")],
            )
        )

    for hotspot_seed in HOTSPOT_SEEDS:
        scene_id = str(hotspot_seed[0])
        hotspot_key = str(hotspot_seed[1])
        detail_route = (
            "/console/analysis/store-review"
            if scene_id == WAREHOUSE_SCENE_ID
            else "/console/meetings/mtg-budget-20260825"
        )
        if hotspot_key == "meeting-action-gate":
            detail_route = "/console/actions/proposals"
        result.append(
            (
                hotspot_key,
                "hotspot",
                detail_route,
                None,
                [_navigate_action("查看业务明细", detail_route, "external-link")],
            )
        )

    meeting_route = "/console/meetings/mtg-budget-20260825"
    for seat_key, *_ in MEETING_SEAT_SEEDS:
        result.append(
            (
                seat_key,
                "meeting-seat",
                meeting_route,
                None,
                [_navigate_action("查看会议席位", meeting_route, "armchair")],
            )
        )
    return result


INTERACTION_PROFILE_SEEDS = _build_interaction_profile_seeds()


def demo_seed_checksum(manifest: SeedManifest) -> str:
    content = {
        "manifest": {
            "seed_key": manifest.seed_key,
            "version": manifest.version,
            "mode": manifest.mode,
            "environments": manifest.environments,
        },
        "stable_ids": {
            "enterprise": ENTERPRISE_ID,
            "source_systems": SOURCE_SYSTEM_SEEDS,
            "campus_scene": SCENE_ID,
            "warehouse_scene": WAREHOUSE_SCENE_ID,
            "meeting_scene": MEETING_SCENE_ID,
            "meeting": MEETING_ID,
        },
        "nodes": NODE_SEEDS,
        "edges": EDGE_SEEDS,
        "spaces": SPACE_SEEDS,
        "actors": ACTOR_SEEDS,
        "routes": ROUTE_SEEDS,
        "participants": PARTICIPANT_SEEDS,
        "participant_seats": PARTICIPANT_SEAT_KEYS,
        "meeting_seats": MEETING_SEAT_SEEDS,
        "scenes": SCENE_SEEDS,
        "hotspots": HOTSPOT_SEEDS,
        "data_layers": DATA_LAYER_SEEDS,
        "interaction_profiles": INTERACTION_PROFILE_SEEDS,
        "metric_definitions": METRIC_DEFINITION_SEEDS,
        "metric_source_systems": METRIC_SOURCE_SYSTEM_IDS,
        "quality_rules": QUALITY_RULE_SEEDS,
        "identity": identity_seed_checksum_payload(),
        "channel_identities": channel_identity_seed_checksum_payload(),
        "tools": tool_seed_checksum_payload(),
        "knowledge": knowledge_seed_checksum_payload(),
        "decision_runtime": decision_seed_checksum_payload(),
        "role_twin_tests": role_twin_test_seed_checksum_payload(),
        "evaluations": evaluation_seed_checksum_payload(),
        "customer_service": customer_service_seed_checksum_payload(),
        "platform_admin": platform_admin_seed_checksum_payload(),
    }
    canonical = json.dumps(
        content,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf8")
    return sha256(canonical).hexdigest()


def _legacy_record_source_id(record: SourceRecord) -> str:
    if record.record_type in {"customers", "crm/summary", "crm/touchpoints"}:
        return CRM_SYSTEM_ID
    if record.record_type.startswith("ads/"):
        return ADVERTISING_SYSTEM_ID
    if record.record_type.startswith("service/"):
        return CUSTOMER_SERVICE_SYSTEM_ID
    if record.record_type == "metrics/daily":
        indicator_code = str(record.payload.get("indicator_code", ""))
        if indicator_code in {
            "ACTIVE_MEMBER_COUNT",
            "NEW_MEMBER_COUNT",
            "REPEAT_PURCHASE_RATE_BPS",
            "CHURN_RISK_MEMBER_COUNT",
        }:
            return CRM_SYSTEM_ID
        if indicator_code in {
            "AD_ROI_X100",
            "AD_SPEND_FEN",
            "ATTRIBUTED_REVENUE_FEN",
            "AD_CTR_BPS",
            "AD_CONVERSION_RATE_BPS",
        }:
            return ADVERTISING_SYSTEM_ID
        if indicator_code in {
            "SERVICE_CONVERSATION_COUNT",
            "FIRST_RESPONSE_SECONDS",
            "SERVICE_RESOLUTION_RATE_BPS",
            "CSAT_SCORE_X100",
            "HUMAN_HANDOFF_RATE_BPS",
        }:
            return CUSTOMER_SERVICE_SYSTEM_ID
    return ERP_OMS_SYSTEM_ID


def seed_database(database: Database, settings: Settings) -> SeedReport:
    manifest = load_seed_manifest()
    if settings.environment not in manifest.environments:
        raise RuntimeError(f"种子 {manifest.seed_key} 不允许在 {settings.environment} 环境执行")
    checksum = demo_seed_checksum(manifest)
    now = datetime.now(UTC)
    with database.session() as session:
        seed_version = session.get(SeedVersion, manifest.seed_key)
        if (
            seed_version is not None
            and seed_version.version == manifest.version
            and seed_version.checksum != checksum
        ):
            raise SeedDriftError(
                f"种子 {manifest.seed_key} {manifest.version} 内容已变化，请先提升清单版本"
            )

        enterprise = session.get(Enterprise, ENTERPRISE_ID)
        if enterprise is None:
            enterprise = Enterprise(
                id=ENTERPRISE_ID,
                code="ZHIXING-DEMO",
                name="知行电商集团",
                timezone=settings.timezone,
                created_at=now,
            )
            session.add(enterprise)
            session.flush()

        group_id = enterprise.group_id or f"grp_{enterprise.id}"
        group = session.get(EnterpriseGroup, group_id)
        if group is None:
            group = EnterpriseGroup(
                id=group_id,
                code=f"GROUP-{enterprise.code}",
                name=enterprise.name,
                status="active",
                timezone=enterprise.timezone,
                created_at=now,
                updated_at=now,
            )
            session.add(group)
            # PostgreSQL checks the enterprise FK on UPDATE during autoflush.
            # Persist the group first because no ORM relationship exists to order
            # the INSERT and the following enterprise UPDATE automatically.
            session.flush()
        enterprise.group_id = group_id
        business_unit = session.scalar(
            select(BusinessUnit).where(
                BusinessUnit.enterprise_id == ENTERPRISE_ID,
                BusinessUnit.unit_key == "corporate",
            )
        )
        if business_unit is None:
            session.add(
                BusinessUnit(
                    id=f"bu_{ENTERPRISE_ID}_corporate",
                    enterprise_id=ENTERPRISE_ID,
                    unit_key="corporate",
                    name="集团本部",
                    unit_type="corporate",
                    parent_id=None,
                    status="active",
                    version=1,
                    created_at=now,
                    updated_at=now,
                )
            )
        consolidation = session.scalar(
            select(ConsolidationProfile).where(
                ConsolidationProfile.group_id == group_id,
                ConsolidationProfile.profile_key == "default",
                ConsolidationProfile.version == "v1",
            )
        )
        if consolidation is None:
            session.add(
                ConsolidationProfile(
                    id=f"consolidation_{group_id}_default_v1",
                    group_id=group_id,
                    profile_key="default",
                    name="集团经营合并口径",
                    base_currency="CNY",
                    elimination_rules=[],
                    exchange_rate_policy={"mode": "spot", "as_of": "business_date"},
                    version="v1",
                    status="published",
                    created_at=now,
                    updated_at=now,
                )
            )

        bootstrap_hash = (
            hash_password(settings.auth_bootstrap_password)
            if settings.auth_bootstrap_password
            else None
        )
        seed_identity(
            session,
            enterprise_id=ENTERPRISE_ID,
            now=now,
            bootstrap_password_hash=bootstrap_hash,
        )
        session.flush()
        principals = session.scalars(
            select(Principal).where(Principal.enterprise_id == ENTERPRISE_ID)
        )
        for principal in principals:
            membership = session.scalar(
                select(EnterpriseMembership).where(
                    EnterpriseMembership.principal_id == principal.id,
                    EnterpriseMembership.enterprise_id == ENTERPRISE_ID,
                )
            )
            if membership is None:
                membership_token = sha256(
                    f"{principal.id}:{ENTERPRISE_ID}".encode()
                ).hexdigest()[:40]
                session.add(
                    EnterpriseMembership(
                        id=f"enterprise_membership_{membership_token}",
                        principal_id=principal.id,
                        enterprise_id=ENTERPRISE_ID,
                        membership_type="employee",
                        is_primary=True,
                        status="active",
                        valid_from=now,
                        valid_to=None,
                        version=1,
                        created_at=now,
                        updated_at=now,
                    )
                )
        seed_channel_identities(session, enterprise_id=ENTERPRISE_ID, now=now)
        seed_tool_registry(session, enterprise_id=ENTERPRISE_ID, now=now)
        seed_platform_admin(session, enterprise_id=ENTERPRISE_ID, now=now)

        for (
            source_id,
            system_key,
            source_name,
            system_type,
            schema_version,
            mapping_version,
        ) in SOURCE_SYSTEM_SEEDS:
            source = session.get(ExternalSystem, source_id)
            if source is None:
                source = ExternalSystem(
                    id=source_id,
                    enterprise_id=ENTERPRISE_ID,
                    system_key=system_key,
                    name=source_name,
                    system_type=system_type,
                    base_url=settings.mock_commerce_url,
                    status="configured",
                    source_schema_version=schema_version,
                    mapping_version=mapping_version,
                )
                session.add(source)
            else:
                source.system_key = system_key
                source.name = source_name
                source.system_type = system_type
                source.base_url = settings.mock_commerce_url
                if source.source_schema_version == "unknown":
                    source.source_schema_version = schema_version
                if source.mapping_version == "1.0.0":
                    source.mapping_version = mapping_version
        session.flush()

        for record in session.scalars(
            select(SourceRecord).where(SourceRecord.external_system_id == ERP_OMS_SYSTEM_ID)
        ):
            record.external_system_id = _legacy_record_source_id(record)
        for snapshot in session.scalars(
            select(MetricSnapshot).where(MetricSnapshot.enterprise_id == ENTERPRISE_ID)
        ):
            snapshot.source_system_id = METRIC_SOURCE_SYSTEM_IDS.get(
                snapshot.metric_key, snapshot.source_system_id
            )

        existing_metric_definitions = {
            (item.metric_key, item.version): item
            for item in session.scalars(
                select(MetricDefinition).where(MetricDefinition.enterprise_id == ENTERPRISE_ID)
            )
        }
        for index, metric_definition_seed in enumerate(METRIC_DEFINITION_SEEDS):
            key, label, description, formula, unit, dimensions, owner, version = (
                metric_definition_seed
            )
            definition = existing_metric_definitions.get((key, version))
            if definition is None:
                definition = MetricDefinition(
                    id=f"metric_definition_{index:02d}",
                    enterprise_id=ENTERPRISE_ID,
                    source_system_id=METRIC_SOURCE_SYSTEM_IDS.get(key),
                    metric_key=key,
                    label=label,
                    description=description,
                    formula_expression=formula,
                    unit=unit,
                    dimensions=dimensions,
                    owner=owner,
                    version=version,
                    status="published",
                    updated_at=now,
                )
                session.add(definition)
            else:
                definition.label = label
                definition.source_system_id = METRIC_SOURCE_SYSTEM_IDS.get(key)
                definition.description = description
                definition.formula_expression = formula
                definition.unit = unit
                definition.dimensions = dimensions
                definition.owner = owner
                definition.status = "published"
                definition.updated_at = now

        existing_quality_rules = {
            item.rule_key: item
            for item in session.scalars(
                select(DataQualityRule).where(DataQualityRule.enterprise_id == ENTERPRISE_ID)
            )
        }
        for index, quality_rule_seed in enumerate(QUALITY_RULE_SEEDS):
            key, name, description, category, asset_type, asset_key, expectation, severity = (
                quality_rule_seed
            )
            rule = existing_quality_rules.get(key)
            if rule is None:
                rule = DataQualityRule(
                    id=f"quality_rule_{index:02d}",
                    enterprise_id=ENTERPRISE_ID,
                    rule_key=key,
                    name=name,
                    description=description,
                    category=category,
                    asset_type=asset_type,
                    asset_key=asset_key,
                    expectation=expectation,
                    severity=severity,
                    status="active",
                    updated_at=now,
                )
                session.add(rule)
            else:
                rule.name = name
                rule.description = description
                rule.category = category
                rule.asset_type = asset_type
                rule.asset_key = asset_key
                rule.expectation = expectation
                rule.severity = severity
                rule.status = "active"
                rule.updated_at = now

        existing_nodes = {
            item.node_key: item
            for item in session.scalars(
                select(TwinNode).where(TwinNode.enterprise_id == ENTERPRISE_ID)
            )
        }
        for index, (key, label, node_type, x, y, z, description) in enumerate(NODE_SEEDS):
            node = existing_nodes.get(key)
            if node is None:
                node = TwinNode(
                    id=f"node_{index:02d}",
                    enterprise_id=ENTERPRISE_ID,
                    node_key=key,
                    label=label,
                    node_type=node_type,
                    status="ready" if node_type not in {"source", "integration"} else "configured",
                    health=0.72 if node_type in {"source", "integration"} else 0.9,
                    position_x=x,
                    position_y=y,
                    position_z=z,
                    description=description,
                )
                session.add(node)
            else:
                node.label = label
                node.node_type = node_type
                node.position_x = x
                node.position_y = y
                node.position_z = z
                node.description = description

        existing_edges = set(
            session.scalars(
                select(TwinEdge.edge_key).where(TwinEdge.enterprise_id == ENTERPRISE_ID)
            )
        )
        for index, (key, source_key, target_key, flow_type) in enumerate(EDGE_SEEDS):
            if key in existing_edges:
                continue
            session.add(
                TwinEdge(
                    id=f"edge_{index:02d}",
                    enterprise_id=ENTERPRISE_ID,
                    edge_key=key,
                    source_key=source_key,
                    target_key=target_key,
                    flow_type=flow_type,
                    status="configured",
                    traffic=0.18,
                )
            )

        has_event = session.scalar(
            select(PlatformEvent.id).where(PlatformEvent.enterprise_id == ENTERPRISE_ID).limit(1)
        )
        if has_event is None:
            session.add(
                PlatformEvent(
                    id="event_foundation_ready",
                    enterprise_id=ENTERPRISE_ID,
                    event_type="foundation.ready",
                    severity="info",
                    title="企业数字底座已初始化",
                    detail="等待从电商业务沙箱执行首个同步批次。",
                    occurred_at=now,
                )
            )

        for (
            scene_id,
            scene_key,
            scene_name,
            scene_version,
            scene_level,
            parent_scene_key,
            entry_space_key,
            asset_bundle_key,
            scene_description,
            camera_preset,
        ) in SCENE_SEEDS:
            scene = session.get(TwinScene, scene_id)
            if scene is None:
                scene = TwinScene(
                    id=scene_id,
                    enterprise_id=ENTERPRISE_ID,
                    scene_key=scene_key,
                    name=scene_name,
                    version=scene_version,
                    status="published",
                    description=scene_description,
                    parent_scene_key=parent_scene_key,
                    scene_level=scene_level,
                    entry_space_key=entry_space_key,
                    asset_bundle_key=asset_bundle_key,
                    camera_preset=camera_preset,
                    updated_at=now,
                )
                session.add(scene)
            else:
                scene.name = scene_name
                scene.version = scene_version
                scene.description = scene_description
                scene.parent_scene_key = parent_scene_key
                scene.scene_level = scene_level
                scene.entry_space_key = entry_space_key
                scene.asset_bundle_key = asset_bundle_key
                scene.camera_preset = cast(dict[str, object], camera_preset)

        existing_spaces = {
            item.space_key: item
            for item in session.scalars(select(TwinSpace).where(TwinSpace.scene_id == SCENE_ID))
        }
        for index, space_seed in enumerate(SPACE_SEEDS):
            (
                key,
                label,
                space_type,
                parent_key,
                status,
                health,
                alert_level,
                metric_key,
                position,
                size,
                description,
            ) = space_seed
            space = existing_spaces.get(key)
            if space is None:
                session.add(
                    TwinSpace(
                        id=f"space_{index:02d}",
                        scene_id=SCENE_ID,
                        space_key=key,
                        label=label,
                        space_type=space_type,
                        parent_space_key=parent_key,
                        status=status,
                        health=health,
                        alert_level=alert_level,
                        metric_key=metric_key,
                        position=position,
                        size=size,
                        description=description,
                        sort_order=index,
                    )
                )
            else:
                space.label = label
                space.space_type = space_type
                space.parent_space_key = parent_key
                space.status = status
                space.health = health
                space.alert_level = alert_level
                space.metric_key = metric_key
                space.position = position
                space.size = size
                space.description = description
                space.sort_order = index

        existing_actors = {
            item.actor_key: item
            for item in session.scalars(
                select(TwinActor).where(TwinActor.enterprise_id == ENTERPRISE_ID)
            )
        }
        for index, (key, name, title, home, position, color, capabilities) in enumerate(
            ACTOR_SEEDS
        ):
            actor = existing_actors.get(key)
            if actor is None:
                session.add(
                    TwinActor(
                        id=f"actor_{index:02d}",
                        enterprise_id=ENTERPRISE_ID,
                        actor_key=key,
                        display_name=name,
                        role_title=title,
                        status="available",
                        home_space_key=home,
                        current_space_key=home,
                        avatar_style="architectural-hologram-v1",
                        color=color,
                        position=position,
                        capabilities=capabilities,
                        sort_order=index,
                    )
                )
            else:
                actor.display_name = name
                actor.role_title = title
                actor.home_space_key = home
                actor.position = position
                actor.color = color
                actor.capabilities = capabilities
                actor.sort_order = index

        existing_routes = {
            item.route_key: item
            for item in session.scalars(select(TwinRoute).where(TwinRoute.scene_id == SCENE_ID))
        }
        for index, (key, source_key, target_key, path) in enumerate(ROUTE_SEEDS):
            route = existing_routes.get(key)
            if route is None:
                session.add(
                    TwinRoute(
                        id=f"route_{index:02d}",
                        scene_id=SCENE_ID,
                        route_key=key,
                        source_space_key=source_key,
                        target_space_key=target_key,
                        route_type="avatar-transit",
                        path=path,
                    )
                )
            else:
                route.source_space_key = source_key
                route.target_space_key = target_key
                route.route_type = "avatar-transit"
                route.path = path

        meeting = session.get(TwinMeeting, MEETING_ID)
        if meeting is None:
            meeting = TwinMeeting(
                id=MEETING_ID,
                enterprise_id=ENTERPRISE_ID,
                scene_id=MEETING_SCENE_ID,
                meeting_key="mtg-budget-20260825",
                title="旗舰店广告预算与库存联动研判",
                topic="仓库低库存风险上升且广告 ROI 下降，是否继续增加旗舰店广告预算？",
                status="scheduled",
                protocol_status="draft",
                template_key="budget-inventory-review",
                initiated_by_principal_id="principal-ceo-lin",
                actor_snapshot=None,
                idempotency_key=None,
                request_hash=None,
                scope_type="store",
                scope_key="store-flagship",
                decision_owner="林知远 / CEO",
                deadline_at=None,
                success_metric="7 天试验期内广告 ROI 不低于 2.5，重点 SKU 库存覆盖保持可履约",
                evidence_snapshot="evs-budget-0825",
                decision=(
                    "不全面增加预算；先执行 7 天素材测试，预算上限 20 万元，"
                    "ROI 低于 2.5 自动停止，并同步校验重点 SKU 库存覆盖。"
                ),
                room_space_key="decision-room",
                next_transition_at=None,
                updated_at=now,
                created_at=now,
            )
            session.add(meeting)
        else:
            meeting.scene_id = MEETING_SCENE_ID
            meeting.template_key = "budget-inventory-review"
            meeting.initiated_by_principal_id = "principal-ceo-lin"
            meeting.scope_type = "store"
            meeting.scope_key = "store-flagship"
            meeting.decision_owner = "林知远 / CEO"
            meeting.success_metric = "7 天试验期内广告 ROI 不低于 2.5，重点 SKU 库存覆盖保持可履约"

        existing_seats = {
            item.seat_key: item
            for item in session.scalars(
                select(TwinMeetingSeat).where(TwinMeetingSeat.scene_id == MEETING_SCENE_ID)
            )
        }
        for index, (seat_key, label, layout_key, position, rotation_y, status) in enumerate(
            MEETING_SEAT_SEEDS
        ):
            seat = existing_seats.get(seat_key)
            if seat is None:
                seat = TwinMeetingSeat(
                    id=f"meeting_seat_{index:02d}",
                    scene_id=MEETING_SCENE_ID,
                    seat_key=seat_key,
                    label=label,
                    layout_key=layout_key,
                    position=position,
                    rotation_y=rotation_y,
                    status=status,
                    sort_order=index,
                )
                session.add(seat)
            else:
                seat.label = label
                seat.layout_key = layout_key
                seat.position = position
                seat.rotation_y = rotation_y
                seat.status = status
                seat.sort_order = index

        existing_participants = {
            item.actor_key: item
            for item in session.scalars(
                select(TwinMeetingParticipant).where(
                    TwinMeetingParticipant.meeting_id == MEETING_ID
                )
            )
        }
        for index, (actor_key, stance, finding) in enumerate(PARTICIPANT_SEEDS):
            participant = existing_participants.get(actor_key)
            if participant is None:
                participant = TwinMeetingParticipant(
                    id=f"participant_{index:02d}",
                    meeting_id=MEETING_ID,
                    actor_key=actor_key,
                    seat_key=PARTICIPANT_SEAT_KEYS[actor_key],
                    position=stance,
                    finding=finding,
                    status="invited",
                    speaking_order=index + 1,
                )
                session.add(participant)
            else:
                participant.seat_key = PARTICIPANT_SEAT_KEYS[actor_key]
                participant.position = stance
                participant.finding = finding
                participant.speaking_order = index + 1

        existing_hotspots = set(session.scalars(select(TwinHotspot.hotspot_key)))
        for index, hotspot_seed in enumerate(HOTSPOT_SEEDS):
            (
                hotspot_scene_id,
                hotspot_key,
                hotspot_label,
                hotspot_type,
                hotspot_status,
                hotspot_severity,
                hotspot_business_ref,
                hotspot_metric_key,
                hotspot_position,
                hotspot_details,
            ) = hotspot_seed
            if hotspot_key in existing_hotspots:
                continue
            session.add(
                TwinHotspot(
                    id=f"hotspot_{index:02d}",
                    scene_id=hotspot_scene_id,
                    hotspot_key=hotspot_key,
                    label=hotspot_label,
                    hotspot_type=hotspot_type,
                    status=hotspot_status,
                    severity=hotspot_severity,
                    business_ref=hotspot_business_ref,
                    metric_key=hotspot_metric_key,
                    position=hotspot_position,
                    details=hotspot_details,
                    sort_order=index,
                )
            )

        existing_layers = set(session.scalars(select(TwinDataLayer.layer_key)))
        for index, (scene_id, key, label, category, enabled, style) in enumerate(DATA_LAYER_SEEDS):
            if key in existing_layers:
                continue
            session.add(
                TwinDataLayer(
                    id=f"layer_{index:02d}",
                    scene_id=scene_id,
                    layer_key=key,
                    label=label,
                    category=category,
                    enabled_default=enabled,
                    style=style,
                    sort_order=index,
                )
            )

        existing_interactions = {
            item.entity_key: item
            for item in session.scalars(
                select(TwinInteractionProfile).where(
                    TwinInteractionProfile.enterprise_id == ENTERPRISE_ID
                )
            )
        }
        for index, (
            entity_key,
            entity_type,
            detail_route,
            enter_space_key,
            actions,
        ) in enumerate(INTERACTION_PROFILE_SEEDS):
            interaction = existing_interactions.get(entity_key)
            if interaction is None:
                interaction = TwinInteractionProfile(
                    id=f"interaction_{index:02d}",
                    enterprise_id=ENTERPRISE_ID,
                    entity_key=entity_key,
                    entity_type=entity_type,
                    detail_route=detail_route,
                    enter_space_key=enter_space_key,
                    actions=actions,
                    sort_order=index,
                )
                session.add(interaction)
            else:
                interaction.entity_type = entity_type
                interaction.detail_route = detail_route
                interaction.enter_space_key = enter_space_key
                interaction.actions = actions
                interaction.sort_order = index
        seed_knowledge(session, enterprise_id=ENTERPRISE_ID, now=now)
        seed_customer_service(session, enterprise_id=ENTERPRISE_ID, now=now)
        seed_role_twin_tests(session, enterprise_id=ENTERPRISE_ID, now=now)
        seed_evaluations(session, enterprise_id=ENTERPRISE_ID, now=now)
        seed_decision_runtime(
            session,
            enterprise_id=ENTERPRISE_ID,
            meeting_id=MEETING_ID,
            now=now,
        )
        seed_skill_registry(session, enterprise_id=ENTERPRISE_ID, now=now)
        if seed_version is None:
            seed_version = SeedVersion(
                seed_key=manifest.seed_key,
                version=manifest.version,
                checksum=checksum,
                applied_at=now,
            )
            session.add(seed_version)
        else:
            seed_version.version = manifest.version
            seed_version.checksum = checksum
            seed_version.applied_at = now
        session.commit()
    return SeedReport(
        seed_key=manifest.seed_key,
        version=manifest.version,
        checksum=checksum,
        applied_at=now,
    )
