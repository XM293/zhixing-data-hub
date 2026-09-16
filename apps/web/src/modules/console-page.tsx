"use client";

import {
  ArrowRight,
  Bot,
  CalendarCheck,
  Check,
  CheckCircle2,
  CircleAlert,
  ClipboardCheck,
  FileCheck2,
  FileText,
  MessageSquareText,
  Play,
  RotateCcw,
  Send,
  Sparkles,
  X
} from "lucide-react";
import Link from "next/link";
import { useMemo, useState } from "react";

import {
  CapabilityNote,
  DataTable,
  EvidenceList,
  InlineCallout,
  InlineLink,
  MetaGrid,
  MetricStrip,
  NotFoundState,
  PageHeader,
  PermissionDenied,
  Statement,
  StatusBadge,
  Surface,
  Timeline,
  WorkList
} from "@/components/console/ui";
import { EnterpriseCockpitPage } from "@/components/cockpit/enterprise-cockpit-page";
import { AnalysisCenterPage } from "@/components/analysis/analysis-center-pages";
import { ReviewSchedulePage } from "@/components/analysis/review-schedule-page";
import { CustomerServicePage } from "@/components/customer-service/customer-service-pages";
import { ActionCenterPage, type ActionCenterView } from "@/components/action/action-center-pages";
import { CommerceCenterPage, DataCenterOperationsPage } from "@/components/data-center/data-center-pages";
import { DataReconciliationPage } from "@/components/data-center/data-reconciliation-page";
import { DataSourcesPage } from "@/components/data-center/data-sources-page";
import { Customer360Page } from "@/components/data-center/customer-360-page";
import { Customer360DetailPage } from "@/components/data-center/customer-360-detail-page";
import { KnowledgeCenterPage } from "@/components/knowledge/knowledge-center-pages";
import { IdentityAdminPage, type IdentityAdminView } from "@/components/identity/identity-admin-pages";
import { ChannelIdentityPage } from "@/components/identity/channel-identity-page";
import { AccessDelegationPage } from "@/components/identity/access-delegation-page";
import { EnterpriseTwinPage } from "@/components/twin/enterprise-twin-page";
import { AgentFeedbackPage } from "@/components/twin/agent-feedback-page";
import { RoleStudioPage, type RoleStudioView } from "@/components/twin/role-studio-page";
import { RoleTwinTestPage } from "@/components/twin/role-twin-test-page";
import { EvaluationStudioPage } from "@/components/twin/evaluation-studio-page";
import { TwinAssistantPage } from "@/components/twin/twin-assistant-page";
import { TwinManagementPage, type TwinManagementView } from "@/components/twin/twin-management-pages";
import { DecisionMeetingsPage } from "@/components/meeting/decision-meeting-pages";
import { ToolAdminPage } from "@/components/tools/tool-admin-page";
import { SkillStudioPage } from "@/components/tools/skill-studio-page";
import { AIRuntimePage } from "@/components/operations/ai-runtime-page";
import { SystemSettingsPage } from "@/components/settings/system-settings-page";
import { WorkspaceHomePage } from "@/components/workspace/workspace-home-page";
import type { WorkspaceKey } from "@/lib/workspace-types";
import { UnifiedAuditPage } from "@/components/operations/unified-audit-page";
import { NotificationInboxPage } from "@/components/operations/notification-inbox-page";
import { JobAdminPage } from "@/components/operations/job-admin-page";
import { PlatformConfigPage } from "@/components/operations/platform-config-page";
import { BulkExchangePage, FileAssetPage } from "@/components/operations/file-exchange-pages";
import { useExperience } from "@/demo/experience-provider";
import { pageKeyForPath, sectionForPath } from "@/lib/navigation";

export function ConsolePage({ path }: { path: string[] }) {
  const pathname = path.length > 0 ? `/console/${path.join("/")}` : "/console";
  const section = sectionForPath(pathname);
  const pageKey = pageKeyForPath(pathname);
  const customerDetailMatch = pageKey.match(/^data\/customers\/([^/]+)\/([^/]+)$/);
  const { allowedSectionKeys, centerCatalog, identity, snapshot, roleId } = useExperience();
  const role = snapshot.roles.find((item) => item.id === roleId) ?? snapshot.roles[0];
  const currentItem = section.items.find(
    (item) => pathname === item.href || pathname.startsWith(`${item.href}/`)
  );
  const itemDenied = Boolean(
    identity &&
      currentItem?.requiredPermission &&
      !identity.actor.permissions.includes(currentItem.requiredPermission)
  );
  const catalogItem = centerCatalog?.groups
    .flatMap((group) => group.items)
    .find((item) =>
      (item.key === "digital-twin" && pathname === "/console")
      || pathname === item.href
      || pathname.startsWith(`${item.href}/`)
    );
  const hasCatalogAccess = Boolean(catalogItem);

  if ((!hasCatalogAccess && !allowedSectionKeys.includes(section.key)) || itemDenied) {
    return <PermissionDenied roleName={`${role.label}（${role.scope}）`} />;
  }

  if (pageKey === "home") return <EnterpriseTwinPage />;
  if (pageKey === "spatial") return <EnterpriseTwinPage />;
  if (pageKey === "workspaces") return <WorkspaceHomePage />;
  if (pageKey.startsWith("workspaces/")) {
    const workspaceKey = pageKey.replace("workspaces/", "");
    const workspaceKeys = new Set([
      "executive",
      "manager",
      "operator",
      "service",
      "finance",
      "people",
      "data-governance",
      "platform-ops",
      "ai-ops"
    ]);
    if (workspaceKeys.has(workspaceKey)) {
      return <WorkspaceHomePage workspaceKey={workspaceKey as WorkspaceKey} />;
    }
    return <NotFoundState />;
  }

  let content: React.ReactNode;
  if (pageKey === "cockpit") content = <EnterpriseCockpitPage />;
  else if (pageKey === "inbox") content = <NotificationInboxPage />;
  else if (pageKey === "data/sources" || pageKey === "data/foundation/sources") content = <DataSourcesPage />;
  else if (pageKey === "data/sync-jobs" || pageKey === "data/foundation/sync-jobs") content = <DataCenterOperationsPage view="sync-runs" />;
  else if (pageKey === "commerce/stores") content = <CommerceCenterPage />;
  else if (pageKey === "data/commerce" || pageKey === "data/products/commerce") content = <DataCenterOperationsPage view="commerce" />;
  else if (pageKey === "data/customers" || pageKey === "data/products/customers") content = <Customer360Page />;
  else if (pageKey === "commerce/customers") content = <Customer360Page />;
  else if (customerDetailMatch) {
    content = (
      <Customer360DetailPage
        customerKey={decodeURIComponent(customerDetailMatch[2])}
        scopeKey={decodeURIComponent(customerDetailMatch[1])}
      />
    );
  }
  else if (pageKey === "data/entities" || pageKey === "data/foundation/entities") content = <DataCenterOperationsPage view="entities" />;
  else if (pageKey === "data/metrics" || pageKey === "data/foundation/metrics") content = <DataCenterOperationsPage view="metrics" />;
  else if (pageKey === "data/quality" || pageKey === "data/foundation/quality") content = <DataCenterOperationsPage view="quality" />;
  else if (pageKey === "reconciliation" || pageKey === "data/reconciliation" || pageKey === "data/foundation/reconciliation") content = <DataReconciliationPage />;
  else if (pageKey === "assistant" || pageKey === "analysis/ask") content = <TwinAssistantPage />;
  else if (pageKey === "settings" || pageKey.startsWith("settings/")) content = <SystemSettingsPage />;
  else if (pageKey === "knowledge/documents") content = <KnowledgeCenterPage view="documents" />;
  else if (pageKey === "knowledge/policies") content = <KnowledgeCenterPage view="policies" />;
  else if (pageKey === "knowledge/ingestion") content = <KnowledgeCenterPage view="ingestion" />;
  else if (pageKey === "knowledge/evidence") content = <KnowledgeCenterPage view="evidence" />;
  else if (["twins/templates", "twins/instances", "twins/prompts"].includes(pageKey)) content = <RoleStudioPage view={pageKey.replace("twins/", "") as RoleStudioView} />;
  else if (pageKey === "twins/test") content = <RoleTwinTestPage />;
  else if (pageKey === "twins/evaluations") content = <EvaluationStudioPage />;
  else if (pageKey === "twins/feedback") content = <AgentFeedbackPage />;
  else if (pageKey.startsWith("twins/")) content = <TwinManagementPage view={pageKey.replace("twins/", "") as TwinManagementView} />;
  else if (pageKey === "meetings") content = <DecisionMeetingsPage />;
  else if (pageKey.startsWith("meetings/")) content = <DecisionMeetingsPage meetingKey={pageKey.replace("meetings/", "")} />;
  else if (pageKey === "analysis/store-review") content = <AnalysisCenterPage view="store-review" />;
  else if (pageKey === "analysis/review-plans") content = <ReviewSchedulePage />;
  else if (pageKey === "analysis/briefs") content = <AnalysisCenterPage view="briefs" />;
  else if (pageKey.startsWith("actions/")) content = <ActionCenterPage view={pageKey.replace("actions/", "") as ActionCenterView} />;
  else if (["admin/users", "admin/org", "admin/access"].includes(pageKey)) content = <IdentityAdminPage view={pageKey.replace("admin/", "") as IdentityAdminView} />;
  else if (pageKey === "admin/audit") content = <UnifiedAuditPage />;
  else if (pageKey === "admin/tools") content = <ToolAdminPage />;
  else if (pageKey === "twins/skills") content = <SkillStudioPage />;
  else if (pageKey === "admin/ai-runtime") content = <AIRuntimePage />;
  else if (pageKey === "admin/channels") content = <ChannelIdentityPage />;
  else if (pageKey === "admin/jobs") content = <JobAdminPage />;
  else if (pageKey === "admin/config") content = <PlatformConfigPage />;
  else if (pageKey === "admin/files") content = <FileAssetPage />;
  else if (pageKey === "admin/exchange") content = <BulkExchangePage />;
  else if (pageKey === "admin/delegations") content = <AccessDelegationPage />;
  else if (pageKey === "customer-service/drafts") content = <CustomerServicePage view="drafts" />;
  else if (pageKey === "customer-service/conversations") content = <CustomerServicePage view="conversations" />;
  else if (pageKey.startsWith("customer-service/conversations/")) {
    content = (
      <CustomerServicePage
        conversationKey={pageKey.replace("customer-service/conversations/", "")}
        view="conversations"
      />
    );
  } else content = <NotFoundState />;

  return (
    <div className="page-stack">
      {content}
    </div>
  );
}

function DashboardPage() {
  const { snapshot, roleId } = useExperience();
  const dashboard = snapshot.dashboards[roleId];
  const role = snapshot.roles.find((item) => item.id === roleId) ?? snapshot.roles[0];

  return (
    <>
      <PageHeader
        actions={
          <Link className="button primary" href="/console/assistant">
            <Sparkles aria-hidden="true" size={16} />
            向企业助手提问
          </Link>
        }
        description={dashboard.description}
        eyebrow={`${role.title} · ${role.scope}`}
        meta="业务快照"
        title={dashboard.title}
      />
      <MetricStrip metrics={dashboard.metrics} />
      <div className="dashboard-grid">
        <Surface
          action={<InlineLink href="/console/inbox">查看全部待办</InlineLink>}
          className="dashboard-priority"
          meta="按业务影响和截止时间排序"
          title={dashboard.priorityTitle}
        >
          <WorkList items={dashboard.priorities} />
        </Surface>
        <Surface meta={`${dashboard.tasks.length} 项待处理`} title="我的待办">
          <WorkList items={dashboard.tasks} />
        </Surface>
        <Surface meta="来自数据、知识与运行中心" title="最新动态">
          <WorkList items={dashboard.updates} />
        </Surface>
      </div>
      <CapabilityNote />
    </>
  );
}

function AssistantPage() {
  const { snapshot, roleId } = useExperience();
  const [question, setQuestion] = useState("9 月退款率如何考核？");
  const [submittedQuestion, setSubmittedQuestion] = useState("9 月退款率如何考核？");
  const [answered, setAnswered] = useState(true);
  const currentRole = snapshot.roles.find((role) => role.id === roleId) ?? snapshot.roles[0];
  const currentPolicy = snapshot.policy.currentVersion;

  function submitQuestion(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const trimmed = question.trim();
    if (!trimmed) return;
    setSubmittedQuestion(trimmed);
    setAnswered(true);
  }

  return (
    <>
      <PageHeader
        description="在当前用户权限范围内组合制度、经营事实和已审核角色记忆；回答附带证据与时间。"
        eyebrow="企业助手 · CEO 分身"
        meta={`${currentRole.label} · ${currentRole.scope}`}
        title="基于企业上下文提问"
      />
      <InlineCallout
        description="正式制度和经营事实优先于聊天记忆；无权限内容不会进入提示词。"
        title="当前回答边界"
        tone="info"
      />
      <div className="assistant-layout">
        <Surface meta="当前会话 · web-console-0825" title="与 CEO 分身对话">
          <div className="chat-thread" aria-live="polite">
            <div className="message user-message">
              <span>你</span>
              <p>{submittedQuestion}</p>
            </div>
            {answered ? (
              <div className="message assistant-message">
                <span><Bot aria-hidden="true" size={15} /> CEO 分身</span>
                <p>
                  9 月 1 日前仍按绩效制度 {currentPolicy} 执行，退款率权重为 15%。待 v3 正式发布并到达生效时间后，权重调整为 20%。
                </p>
                <p>
                  建议运营中心本周完成目标拆解和团队说明，但不要在制度生效前提前更改当月已确认口径。
                </p>
                <div className="answer-tags">
                  <StatusBadge value={{ label: "事实", tone: "positive" }} />
                  <StatusBadge value={{ label: "建议", tone: "info" }} />
                  <span>置信度：高</span>
                </div>
              </div>
            ) : null}
          </div>
          <form className="composer" onSubmit={submitQuestion}>
            <textarea
              aria-label="输入企业问题"
              onChange={(event) => setQuestion(event.target.value)}
              rows={3}
              value={question}
            />
            <div>
              <span>回答将使用当前角色和数据范围</span>
              <button className="button primary" type="submit">
                <Send aria-hidden="true" size={16} />
                发送问题
              </button>
            </div>
          </form>
        </Surface>
        <div className="assistant-side">
          <Surface meta="本次回答实际使用" title="依据与上下文">
            <EvidenceList
              items={[
                { label: `电商运营绩效考核制度 ${currentPolicy}`, detail: "第 3 章 / 退款率 · 当前有效" },
                { label: `待发布制度 ${snapshot.policy.pendingVersion}`, detail: `计划 ${snapshot.policy.effectiveAt} 生效` },
                { label: "角色记忆候选", detail: snapshot.memory.status === "rejected" ? "冲突内容已拒绝" : "存在冲突，未用于事实判断" }
              ]}
            />
          </Surface>
          <Surface title="你可以继续问">
            <div className="suggestion-list">
              {["为什么退款率权重要调整？", "旗舰店昨天的广告效率如何？", "把异常分析整理成会议议题"].map((item) => (
                <button
                  key={item}
                  onClick={() => {
                    setQuestion(item);
                    setSubmittedQuestion(item);
                    setAnswered(true);
                  }}
                  type="button"
                >
                  <MessageSquareText aria-hidden="true" size={15} />
                  {item}
                </button>
              ))}
            </div>
          </Surface>
        </div>
      </div>
    </>
  );
}

function PoliciesPage() {
  const { snapshot, roleId, publishPolicy } = useExperience();
  const { policy } = snapshot;
  const canPublish = roleId === "ceo" || roleId === "admin";
  const page = snapshot.tablePages["knowledge/policies"];

  return (
    <>
      <PageHeader
        actions={
          <button className="button primary" disabled={!canPublish || policy.status === "published"} onClick={publishPolicy} type="button">
            <FileCheck2 aria-hidden="true" size={16} />
            {policy.status === "published" ? "v3 已发布" : "发布 v3"}
          </button>
        }
        description="制度版本不可覆盖修改；发布、生效、废止和引用位置均可追溯。"
        eyebrow="知识中心 · 制度管理"
        meta="2 个有效版本"
        title="企业制度与规则"
      />
      <InlineCallout
        description={policy.status === "published" ? "v3 已发布，系统将在生效时间后自动作为现行规则。" : "v3 尚未发布，企业助手仍以 v2 作为当前有效事实。"}
        title={policy.status === "published" ? "发布完成" : "有 1 个版本等待发布"}
        tone={policy.status === "published" ? "positive" : "warning"}
      />
      <div className="detail-grid">
        <Surface className="detail-main" meta="正式知识对象" title={`${policy.name} ${policy.pendingVersion}`}>
          <MetaGrid
            items={[
              { label: "当前有效", value: policy.currentVersion },
              { label: "计划生效", value: policy.effectiveAt },
              { label: "责任部门", value: policy.owner },
              { label: "版本状态", value: policy.status === "published" ? "已发布 / 待生效" : "待发布" }
            ]}
          />
          <Statement label="变更摘要" tone="info">{policy.changeSummary}</Statement>
          <h3 className="subheading">引用定位</h3>
          <EvidenceList items={policy.citations.map((citation) => ({ label: citation, detail: `${policy.name} ${policy.pendingVersion}` }))} />
        </Surface>
        <Surface meta="检测于 08:56" title="影响检查">
          <div className="impact-list">
            <div><CircleAlert aria-hidden="true" size={17} /><span><strong>1 条角色记忆冲突</strong>旧退款率权重仍为 15%</span></div>
            <div><CheckCircle2 aria-hidden="true" size={17} /><span><strong>2 个指标引用有效</strong>退款率 v3 / 广告 ROI v2</span></div>
            <div><CalendarCheck aria-hidden="true" size={17} /><span><strong>12 名员工待宣导</strong>运营中心相关岗位</span></div>
          </div>
          <InlineLink href="/console/twins/memories">处理冲突记忆</InlineLink>
        </Surface>
      </div>
      <Surface meta={`${page.rows.length} 条制度`} title="制度版本列表"><DataTable page={page} /></Surface>
    </>
  );
}

function MemoriesPage() {
  const { snapshot, roleId, reviewMemory } = useExperience();
  const { memory } = snapshot;
  const canReview = roleId === "ceo" || roleId === "admin";
  const status = memory.status === "pending"
    ? { label: "待审核", tone: "warning" as const }
    : memory.status === "approved"
      ? { label: "已批准", tone: "positive" as const }
      : { label: "已拒绝", tone: "critical" as const };

  return (
    <>
      <PageHeader
        description="聊天内容先成为记忆候选，经来源、冲突和权限审核后才能进入角色长期记忆。"
        eyebrow="分身中心 · 记忆治理"
        meta="1 条冲突待处理"
        title="角色记忆审核"
      />
      <div className="detail-grid">
        <Surface className="detail-main" meta={memory.roleTwin} title="候选记忆详情">
          <div className="record-heading">
            <StatusBadge value={status} />
            <code>{memory.id}</code>
          </div>
          <blockquote className="memory-quote">“{memory.candidate}”</blockquote>
          <MetaGrid items={[{ label: "来源", value: memory.source }, { label: "目标分身", value: memory.roleTwin }]} />
          <InlineCallout description={memory.conflict} title="与正式制度存在冲突" tone="critical" />
          <div className="action-row">
            <button className="button secondary danger" disabled={!canReview || memory.status !== "pending"} onClick={() => reviewMemory("rejected")} type="button">
              <X aria-hidden="true" size={16} />拒绝候选
            </button>
            <button className="button secondary" disabled={!canReview || memory.status !== "pending"} onClick={() => reviewMemory("approved")} type="button">
              <Check aria-hidden="true" size={16} />批准进入记忆
            </button>
          </div>
          {!canReview ? <p className="permission-hint">当前角色可查看冲突，但只有记忆所有者或平台管理员可以审核。</p> : null}
        </Surface>
        <Surface title="事实优先级">
          <Timeline items={[
            { title: "正式制度", description: "电商运营绩效考核制度 v3", meta: "最高优先级", tone: "positive" },
            { title: "结构化经营事实", description: "带口径、时间与来源的数据", meta: "按时间有效", tone: "info" },
            { title: "已审核角色记忆", description: "表达偏好、经验和判断方式", meta: "不得覆盖事实", tone: "neutral" }
          ]} />
        </Surface>
      </div>
      <CapabilityNote />
    </>
  );
}

function MeetingDetailPage() {
  const { snapshot, advanceMeeting } = useExperience();
  const { meeting } = snapshot;
  const ready = meeting.status === "decision_ready";

  return (
    <>
      <PageHeader
        actions={
          ready ? <Link className="button primary" href="/console/actions/approvals"><ClipboardCheck aria-hidden="true" size={16} />查看行动审批</Link>
            : <button className="button primary" onClick={advanceMeeting} type="button"><Play aria-hidden="true" size={16} />形成决策包</button>
        }
        description="多角色分身围绕同一证据快照提出独立意见，保留分歧后由主持流程汇总结论。"
        eyebrow="数字会议 · 经营议题"
        meta={ready ? "决策包已生成" : "分析与质询中"}
        title={meeting.title}
      />
      <MetaGrid items={[
        { label: "会议编号", value: meeting.id },
        { label: "证据快照", value: meeting.evidenceSnapshot },
        { label: "事实时间", value: meeting.asOf },
        { label: "当前状态", value: ready ? "待人工确认" : "分析中" }
      ]} />
      <Surface meta="角色先独立分析，再进入交叉质询" title="角色观点">
        <div className="participant-grid">
          {meeting.participants.map((participant) => (
            <article className={`participant-row ${participant.tone}`} key={participant.role}>
              <span className="participant-icon"><Bot aria-hidden="true" size={17} /></span>
              <div><strong>{participant.role}</strong><b>{participant.position}</b><p>{participant.finding}</p></div>
            </article>
          ))}
        </div>
      </Surface>
      <div className="detail-grid">
        <Surface title="保留分歧">
          <ul className="plain-list">{meeting.disagreements.map((item) => <li key={item}><CircleAlert aria-hidden="true" size={16} />{item}</li>)}</ul>
        </Surface>
        <Surface className={ready ? "decision-ready" : ""} title="主持人汇总">
          {ready ? (
            <div className="decision-package"><CheckCircle2 aria-hidden="true" size={22} /><div><strong>决策建议</strong><p>{meeting.decision}</p><span>需由周岚审批后才可生成内部行动台账。</span></div></div>
          ) : (
            <div className="pending-decision"><RotateCcw aria-hidden="true" size={20} /><p>点击“形成决策包”查看汇总结论、停止条件和后续行动。</p></div>
          )}
        </Surface>
      </div>
    </>
  );
}
