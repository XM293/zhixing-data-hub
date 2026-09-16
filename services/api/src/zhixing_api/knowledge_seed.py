from __future__ import annotations

from datetime import UTC, datetime
from typing import TypedDict, cast

from sqlalchemy import select
from sqlalchemy.orm import Session

from zhixing_api.data_models import (
    KnowledgeChunk,
    KnowledgeDocument,
    KnowledgeVersion,
    Principal,
    RoleTemplate,
    RoleTemplateVersion,
    RoleTwinProfile,
    RoleTwinVersion,
    TwinActor,
)
from zhixing_api.knowledge_text import chunk_document, content_hash

# Seed paragraphs stay intact so chunking and citation tests remain deterministic.
# ruff: noqa: E501


class VersionSeed(TypedDict):
    label: str
    number: int
    status: str
    effective_from: str
    effective_until: str | None
    summary: str
    content: str


class DocumentSeed(TypedDict):
    key: str
    title: str
    type: str
    space: str
    owner: str
    tags: list[str]
    versions: list[VersionSeed]


KNOWLEDGE_SEEDS: list[DocumentSeed] = [
    {
        "key": "policy-commerce-kpi",
        "title": "电商运营绩效考核制度",
        "type": "policy",
        "space": "运营制度",
        "owner": "人力中心 / 运营中心",
        "tags": ["绩效", "退款率", "广告ROI", "运营"],
        "versions": [
            {
                "label": "v2",
                "number": 2,
                "status": "active",
                "effective_from": "2026-01-01T00:00:00+08:00",
                "effective_until": "2026-09-01T00:00:00+08:00",
                "summary": "现行版本，明确退款率和广告 ROI 的绩效权重。",
                "content": """# 适用范围
本制度适用于运营中心各店铺负责人、推广专员和商品运营岗位，考核周期为自然月。
# 退款率考核
2026 年 1 月 1 日至 2026 年 8 月 31 日，退款率指标占月度绩效总分的 15%。退款率按退款金额除以同期支付金额计算，以企业数据中心已发布的退款率口径为准。旗舰店退款率目标为不高于 5.5%，超过 6.0%时由运营经理组织专项复盘。
# 广告效率考核
广告 ROI 指标占月度绩效总分的 25%。单一活动连续 3 天 ROI 低于 2.5 时，应停止扩量并提交素材、人群和商品承接分析。
# 执行要求
月度口径确认后不得追溯修改。制度新版本未到生效时间前，不得提前改变当月已确认权重。""",
            },
            {
                "label": "v3",
                "number": 3,
                "status": "published",
                "effective_from": "2026-09-01T00:00:00+08:00",
                "effective_until": None,
                "summary": "退款率权重由 15% 调整为 20%，增加高退款商品整改要求。",
                "content": """# 版本与生效
本版本已发布，计划于 2026 年 9 月 1 日 00:00 生效。在生效时间到达前，v2 仍是现行制度。
# 退款率考核
自 2026 年 9 月 1 日起，退款率指标占月度绩效总分的 20%。退款率按退款金额除以同期支付金额计算，以企业数据中心的已发布口径为准。旗舰店目标仍为不高于 5.5%，超过 6.0%必须在 2 个工作日内完成专项复盘。
# 高退款商品治理
单 SKU 七日退款率超过类目基准 30%时，暂停继续扩量，商品运营、客服与供应链共同确认商品描述、质量和履约问题后方可恢复。
# 宣导与切换
运营中心应在 2026 年 8 月 31 日前完成目标拆解与团队宣导，但不得在制度生效前提前修改 8 月已确认口径。""",
            },
        ],
    },
    {
        "key": "policy-ad-budget",
        "title": "广告预算审批与止损制度",
        "type": "policy",
        "space": "经营管理",
        "owner": "财务中心 / 运营中心",
        "tags": ["广告", "预算", "ROI", "审批", "止损"],
        "versions": [
            {
                "label": "v2",
                "number": 2,
                "status": "active",
                "effective_from": "2026-06-01T00:00:00+08:00",
                "effective_until": None,
                "summary": "建立预算分级审批、七日试验和自动止损条件。",
                "content": """# 预算分级
单店单次新增广告预算不超过 5 万元由运营经理审批；5 万元以上、20 万元以内由运营负责人和财务负责人共同审批；超过 20 万元须提交 CEO 决策。
# 试验规则
无法证明稳定增量的新增预算，应先执行 7 天小流量试验。试验必须绑定目标商品、素材、人群、预算上限和复盘时间。
# 止损条件
试验期广告 ROI 连续 3 天低于 2.5，或重点 SKU 可售库存覆盖低于 7 天，应立即停止扩量。任何自动化执行只能生成停止建议，首期必须经有权限人员批准。
# 复盘要求
复盘必须同时呈现成交、毛利、退款、库存和广告归因，不得只以成交金额作为扩量依据。""",
            }
        ],
    },
    {
        "key": "policy-inventory-response",
        "title": "库存预警与补货协同规则",
        "type": "policy",
        "space": "供应链制度",
        "owner": "供应链中心",
        "tags": ["库存", "SKU", "补货", "仓库", "预警"],
        "versions": [
            {
                "label": "v4",
                "number": 4,
                "status": "active",
                "effective_from": "2026-07-15T00:00:00+08:00",
                "effective_until": None,
                "summary": "统一库存覆盖天数、分级预警和促销联动规则。",
                "content": """# 预警分级
可售库存覆盖 14 天以下为关注，7 天以下为黄色预警，3 天以下为红色预警。覆盖天数使用近 14 天日均销量与已确认活动增量共同计算。
# 处理时限
黄色预警由供应链在 4 小时内确认在途量和可承诺到货时间；红色预警须在 1 小时内通知运营，并暂停相关商品继续加大广告投放。
# 仓库异常
库位盘点差异超过 2%或同一 SKU 连续两次出库缺货时，仓库负责人应发起复核，系统库存不得直接覆盖实盘结果。
# 跨部门协同
运营提出活动扩量前必须校验重点 SKU 的库存覆盖、在途计划和替代品方案。""",
            }
        ],
    },
    {
        "key": "policy-service-compensation",
        "title": "客服补偿与升级处理规则",
        "type": "policy",
        "space": "客服制度",
        "owner": "客服中心",
        "tags": ["客服", "补偿", "退款", "升级", "回复"],
        "versions": [
            {
                "label": "v5",
                "number": 5,
                "status": "active",
                "effective_from": "2026-08-20T00:00:00+08:00",
                "effective_until": None,
                "summary": "增加物流异常话术和人工升级闸门。",
                "content": """# 普通补偿权限
普通客服可在订单实付金额 10%且不超过 50 元的范围内提供优惠券补偿。超出范围必须提交值班主管审批，不得由智能客服自行承诺。
# 物流异常
物流超过承诺时间 48 小时仍无有效轨迹时，先向客户说明核查进度并创建物流工单；确认丢件后按订单退款规则处理。
# 七天无理由与退款
符合平台七天无理由条件的订单，客服可以指引客户从当前订单售后入口提交申请，但不得在审核完成前承诺通过。数据中心已有退款事实时必须说明当前系统状态；渠道上下文与规范退款状态不一致时转人工核验。退款到账依赖支付机构，禁止承诺具体到账日期。
# 订单信息、发票与支付
已完成且满足开票条件的订单，可指引客户从订单详情的发票入口提交抬头和税号；订单处于退款中、已退款或开票资格不明确时，先转发票专员核验。修改收货地址、疑似重复扣款或支付争议必须创建核验工单，客服不得承诺修改成功或直接认定重复扣款。
# 商品、活动与错发
尺码和适用场景只能依据商品页、尺码表及客户提供的信息给出建议；清洁保养以商品洗护标签为准。优惠券叠加和活动价格以结算页实时结果为准。错发、漏发需要核验订单行和出库记录，核验前不得承诺补发时间。
# 高风险会话与回复要求
涉及人身安全、媒体曝光、监管投诉、批量质量、个人信息删除或客户明确要求人工时，智能客服必须停止自动发送并即时转人工。自动草稿必须引用本次订单事实和对应场景的当前有效规则，禁止虚构物流节点、退款到账时间、发票资格、活动规则或补偿审批结果。""",
            }
        ],
    },
    {
        "key": "guide-store-operations",
        "title": "店铺日常经营异常处置手册",
        "type": "playbook",
        "space": "运营知识",
        "owner": "运营中心",
        "tags": ["店铺", "异常", "运营", "诊断", "复盘"],
        "versions": [
            {
                "label": "v7",
                "number": 7,
                "status": "active",
                "effective_from": "2026-08-01T00:00:00+08:00",
                "effective_until": None,
                "summary": "统一成交、流量、转化、退款和库存异常的诊断顺序。",
                "content": """# 诊断顺序
店铺成交异常时，先确认数据是否完整，再按流量、点击率、转化率、客单价、退款率和库存承接顺序定位原因。不得在数据质量未通过时直接调整经营策略。
# 广告异常
广告消耗上涨而成交未同步增长时，先拆解素材、人群、关键词和商品落地页。连续 3 天 ROI 低于 2.5 时按预算制度进入止损流程。
# 商品异常
高流量商品转化下滑时，应检查价格、评价、页面承诺和库存。退款率同时升高时，优先排查商品质量与描述一致性。
# 复盘输出
每次异常处理必须记录数据时间、指标口径、判断、负责人、截止时间和验证条件，形成可追溯行动。""",
            }
        ],
    },
    {
        "key": "record-budget-meeting-0825",
        "title": "旗舰店广告预算与库存联动会议决议",
        "type": "decision-record",
        "space": "经营决策",
        "owner": "CEO 办公室",
        "tags": ["会议", "决策", "广告", "库存", "旗舰店"],
        "versions": [
            {
                "label": "v1",
                "number": 1,
                "status": "active",
                "effective_from": "2026-08-25T15:30:00+08:00",
                "effective_until": None,
                "summary": "冻结七日试验、预算上限和停止条件。",
                "content": """# 议题
仓库低库存风险上升且广告 ROI 下降，是否继续增加旗舰店广告预算。
# 决议
不全面增加预算。先执行 7 天素材与人群试验，新增预算上限 20 万元；广告 ROI 低于 2.5 自动形成停止建议，并同步校验重点 SKU 库存覆盖。
# 责任与复盘
运营经理负责试验设计，财务负责人监控预算与毛利，供应链负责人每日确认重点 SKU 覆盖。第 7 天由经营会议复盘是否扩量。
# 保留条件
任何自动停止或预算变更均需进入行动审批队列，数字分身只能提出建议，不直接越权执行。""",
            }
        ],
    },
]

ROLE_TWIN_SEEDS: list[dict[str, str]] = [
    {
        "key": "twin-ceo",
        "display_name": "林知远分身",
        "role_title": "CEO 决策分身",
        "voice_guide": "直接、克制、先讲结论；不使用空泛口号，明确负责人、期限和判断条件。",
        "reasoning_guide": "先核对数据时间和制度版本，再区分事实、判断与建议；同时考虑成交、利润、退款、库存和执行风险。",
        "answer_policy": "正式制度和已发布经营事实优先；未来规则必须说明生效时间；证据不足时明确未知；不替用户扩大权限或直接承诺审批结果。",
        "provider": "openai-compatible-responses",
        "model": "environment-configured",
    },
    {
        "key": "twin-ops",
        "display_name": "周岚分身",
        "role_title": "运营负责人分身",
        "voice_guide": "面向执行，优先说明店铺、商品、投放与库存动作；结论后给验证周期、负责人和停止条件。",
        "reasoning_guide": "先检查店铺成交、广告 ROI、退款率和库存覆盖，再区分短期试验与长期扩量，避免只看成交不看履约。",
        "answer_policy": "所有建议必须绑定经营指标和库存约束；不虚构平台规则；预算和自动化动作只形成草案并进入审批。",
        "provider": "openai-compatible-responses",
        "model": "environment-configured",
    },
    {
        "key": "twin-finance",
        "display_name": "陈硕分身",
        "role_title": "财务负责人分身",
        "voice_guide": "审慎、量化、先指出资金与利润约束；明确最坏情形、预算上限和退出条件。",
        "reasoning_guide": "核对指标口径与数据时间，检查收入、退款、投放消耗、库存资金占用和审批边界，主动寻找错误激励。",
        "answer_policy": "证据不足时不推断利润；任何预算建议必须说明上限、监控指标和停止条件；不代替审批人作最终授权。",
        "provider": "openai-compatible-responses",
        "model": "environment-configured",
    },
    {
        "key": "twin-service",
        "display_name": "许然客服分身",
        "role_title": "客服专员辅助分身",
        "voice_guide": "礼貌、简洁、先回应客户当前问题；不使用推诿话术，不夸大确定性。",
        "reasoning_guide": "先核对客户原话、订单与物流同步时间，再读取现行客服制度；明确可直接说明、需要核验和必须转人工的边界。",
        "answer_policy": "不得虚构订单、物流、退款到账或补偿审批结果；高风险、超权限承诺和客户明确要求人工时停止自动发送。",
        "provider": "openai-compatible-responses",
        "model": "environment-configured",
    },
]

ROLE_TEMPLATE_SEEDS: list[dict[str, object]] = [
    {
        "key": "template-enterprise-leader",
        "name": "企业经营负责人",
        "description": "负责全企业经营目标、制度边界、跨部门取舍与最终决策。",
        "twin_key": "twin-ceo",
        "owner_principal_id": "principal-ceo-lin",
        "responsibilities": ["企业经营研判", "制度解释", "跨部门决策", "行动边界确认"],
        "capability_boundaries": ["不替代有权审批人", "不绕过调用者数据范围", "证据不足时明确未知"],
    },
    {
        "key": "template-operations-leader",
        "name": "运营中心负责人",
        "description": "负责店铺经营、广告投放、商品承接和库存协同。",
        "twin_key": "twin-ops",
        "owner_principal_id": "principal-ops-manager-zhou",
        "responsibilities": ["店铺经营诊断", "投放试验设计", "库存协同", "运营动作复盘"],
        "capability_boundaries": ["预算动作只形成建议", "不虚构平台规则", "不读取未授权店铺"],
    },
    {
        "key": "template-finance-leader",
        "name": "财务决策负责人",
        "description": "负责预算约束、资金风险、利润口径和错误激励审查。",
        "twin_key": "twin-finance",
        "owner_principal_id": "principal-finance-chen",
        "responsibilities": ["预算审查", "资金风险评估", "利润口径核验", "错误激励识别"],
        "capability_boundaries": ["证据不足不推断利润", "不替代预算审批", "所有建议包含退出条件"],
    },
    {
        "key": "template-service-agent",
        "name": "客户服务专员",
        "description": "负责客户会话响应、订单履约解释、售后指引和高风险升级。",
        "twin_key": "twin-service",
        "owner_principal_id": "principal-service-demo",
        "responsibilities": ["客户会话分流", "订单履约解释", "回复草稿", "风险升级"],
        "capability_boundaries": ["不虚构业务状态", "不承诺超权限补偿", "高风险必须转人工"],
    },
]


def seed_knowledge(session: Session, *, enterprise_id: str, now: datetime) -> None:
    for document_index, seed in enumerate(KNOWLEDGE_SEEDS, start=1):
        versions = list(seed["versions"])
        latest = max(versions, key=lambda item: int(item["number"]))
        document_id = f"knowledge_doc_{document_index:02d}"
        document = session.scalar(
            select(KnowledgeDocument).where(
                KnowledgeDocument.enterprise_id == enterprise_id,
                KnowledgeDocument.document_key == seed["key"],
            )
        )
        if document is None:
            document = KnowledgeDocument(
                id=document_id,
                enterprise_id=enterprise_id,
                document_key=str(seed["key"]),
                title=str(seed["title"]),
                document_type=str(seed["type"]),
                knowledge_space=str(seed["space"]),
                source_type="simulated-enterprise-document",
                source_uri=None,
                content_hash=content_hash(str(latest["content"])),
                owner=str(seed["owner"]),
                tags=[str(item) for item in seed["tags"]],
                status="active",
                created_at=now,
                updated_at=now,
            )
            session.add(document)
        else:
            document.title = str(seed["title"])
            document.document_type = str(seed["type"])
            document.knowledge_space = str(seed["space"])
            document.content_hash = content_hash(str(latest["content"]))
            document.owner = str(seed["owner"])
            document.tags = [str(item) for item in seed["tags"]]
            document.status = "active"
            document.updated_at = now
        session.flush()

        for version_seed in versions:
            version_id = f"knowledge_ver_{document_index:02d}_{int(version_seed['number']):02d}"
            version = session.scalar(
                select(KnowledgeVersion).where(
                    KnowledgeVersion.document_id == document.id,
                    KnowledgeVersion.version_label == version_seed["label"],
                )
            )
            effective_from = _parse_datetime(version_seed["effective_from"])
            effective_until = _parse_datetime(version_seed["effective_until"])
            version_content = str(version_seed["content"])
            if version is None:
                version = KnowledgeVersion(
                    id=version_id,
                    document_id=document.id,
                    version_label=str(version_seed["label"]),
                    version_number=int(version_seed["number"]),
                    status=str(version_seed["status"]),
                    effective_from=effective_from,
                    effective_until=effective_until,
                    published_at=effective_from,
                    content=version_content,
                    content_hash=content_hash(version_content),
                    change_summary=str(version_seed["summary"]),
                    created_at=now,
                )
                session.add(version)
            else:
                version.status = str(version_seed["status"])
                version.effective_from = effective_from
                version.effective_until = effective_until
                version.content = version_content
                version.content_hash = content_hash(version_content)
                version.change_summary = str(version_seed["summary"])
            session.flush()

            existing_chunks = {
                item.chunk_key: item
                for item in session.scalars(
                    select(KnowledgeChunk).where(KnowledgeChunk.version_id == version.id)
                )
            }
            for sequence, text_chunk in enumerate(chunk_document(version_content), start=1):
                chunk_key = f"{seed['key']}:{version_seed['label']}:{sequence:03d}"
                chunk = existing_chunks.get(chunk_key)
                if chunk is None:
                    chunk = KnowledgeChunk(
                        id=f"knowledge_chunk_{document_index:02d}_{int(version_seed['number']):02d}_{sequence:03d}",
                        version_id=version.id,
                        chunk_key=chunk_key,
                        sequence=sequence,
                        heading=text_chunk.heading,
                        content=text_chunk.content,
                        locator=text_chunk.locator,
                        token_estimate=text_chunk.token_estimate,
                        metadata_json={"seed": True, "language": "zh-CN"},
                        index_status="indexed",
                        created_at=now,
                    )
                    session.add(chunk)
                else:
                    chunk.heading = text_chunk.heading
                    chunk.content = text_chunk.content
                    chunk.locator = text_chunk.locator
                    chunk.token_estimate = text_chunk.token_estimate
                    chunk.index_status = "indexed"

    role_seeds_by_key = {item["key"]: item for item in ROLE_TWIN_SEEDS}
    template_by_twin_key: dict[str, tuple[RoleTemplate, RoleTemplateVersion]] = {}
    for index, template_seed in enumerate(ROLE_TEMPLATE_SEEDS, start=1):
        template_key = str(template_seed["key"])
        twin_key = str(template_seed["twin_key"])
        role_seed = role_seeds_by_key[twin_key]
        template = session.scalar(
            select(RoleTemplate).where(
                RoleTemplate.enterprise_id == enterprise_id,
                RoleTemplate.template_key == template_key,
            )
        )
        if template is None:
            template = RoleTemplate(
                id=f"role_template_{index:02d}",
                enterprise_id=enterprise_id,
                template_key=template_key,
                name=str(template_seed["name"]),
                description=str(template_seed["description"]),
                status="published",
                created_at=now,
                updated_at=now,
            )
            session.add(template)
        else:
            template.name = str(template_seed["name"])
            template.description = str(template_seed["description"])
            template.status = "published"
            template.updated_at = now
        session.flush()
        template_version = session.scalar(
            select(RoleTemplateVersion).where(
                RoleTemplateVersion.template_id == template.id,
                RoleTemplateVersion.version_number == 1,
            )
        )
        if template_version is None:
            template_version = RoleTemplateVersion(
                id=f"role_template_version_{index:02d}_01",
                template_id=template.id,
                version_number=1,
                status="published",
                role_title=role_seed["role_title"],
                responsibilities=[
                    str(item)
                    for item in cast(list[object], template_seed["responsibilities"])
                ],
                capability_boundaries=[
                    str(item)
                    for item in cast(list[object], template_seed["capability_boundaries"])
                ],
                default_voice_guide=role_seed["voice_guide"],
                default_reasoning_guide=role_seed["reasoning_guide"],
                default_answer_policy=role_seed["answer_policy"],
                change_summary="建立首批岗位模板基线",
                created_by_principal_id=None,
                created_at=now,
                published_at=now,
            )
            session.add(template_version)
        session.flush()
        template_by_twin_key[twin_key] = (template, template_version)

    for index, role_seed in enumerate(ROLE_TWIN_SEEDS, start=1):
        template, template_version = template_by_twin_key[role_seed["key"]]
        template_seed = next(
            item for item in ROLE_TEMPLATE_SEEDS if item["twin_key"] == role_seed["key"]
        )
        owner = session.get(Principal, str(template_seed["owner_principal_id"]))
        profile = session.scalar(
            select(RoleTwinProfile).where(
                RoleTwinProfile.enterprise_id == enterprise_id,
                RoleTwinProfile.twin_key == role_seed["key"],
            )
        )
        if profile is None:
            profile = RoleTwinProfile(
                id=f"role_twin_profile_{index:02d}",
                enterprise_id=enterprise_id,
                role_template_id=template.id,
                owner_principal_id=owner.id if owner else None,
                twin_key=role_seed["key"],
                display_name=role_seed["display_name"],
                role_title=role_seed["role_title"],
                voice_guide=role_seed["voice_guide"],
                reasoning_guide=role_seed["reasoning_guide"],
                answer_policy=role_seed["answer_policy"],
                provider=role_seed["provider"],
                model=role_seed["model"],
                status="published",
                published_at=now,
                updated_at=now,
            )
            session.add(profile)
        else:
            profile.role_template_id = template.id
            profile.owner_principal_id = owner.id if owner else None
            profile.display_name = role_seed["display_name"]
            profile.role_title = role_seed["role_title"]
            profile.voice_guide = role_seed["voice_guide"]
            profile.reasoning_guide = role_seed["reasoning_guide"]
            profile.answer_policy = role_seed["answer_policy"]
            profile.provider = role_seed["provider"]
            profile.model = role_seed["model"]
            profile.status = "published"
            profile.updated_at = now
        session.flush()

        actor = session.scalar(
            select(TwinActor).where(
                TwinActor.enterprise_id == enterprise_id,
                TwinActor.actor_key == role_seed["key"],
            )
        )
        twin_version = session.scalar(
            select(RoleTwinVersion).where(
                RoleTwinVersion.twin_profile_id == profile.id,
                RoleTwinVersion.version_number == 1,
            )
        )
        if twin_version is None:
            twin_version = RoleTwinVersion(
                id=f"role_twin_version_{index:02d}_01",
                twin_profile_id=profile.id,
                template_version_id=template_version.id,
                version_number=1,
                status="published",
                display_name=role_seed["display_name"],
                voice_guide=role_seed["voice_guide"],
                reasoning_guide=role_seed["reasoning_guide"],
                answer_policy=role_seed["answer_policy"],
                provider=role_seed["provider"],
                model=role_seed["model"],
                capabilities=list(actor.capabilities) if actor else [],
                change_summary="建立首批个人分身配置基线",
                created_by_principal_id=None,
                created_at=now,
                published_at=now,
            )
            session.add(twin_version)


def knowledge_seed_checksum_payload() -> dict[str, object]:
    return {
        "documents": KNOWLEDGE_SEEDS,
        "role_templates": ROLE_TEMPLATE_SEEDS,
        "role_twins": ROLE_TWIN_SEEDS,
    }


def _parse_datetime(value: object) -> datetime | None:
    if value is None:
        return None
    parsed = datetime.fromisoformat(str(value))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
