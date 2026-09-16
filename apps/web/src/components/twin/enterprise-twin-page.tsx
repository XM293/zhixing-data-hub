"use client";

import {
  AlertTriangle,
  Armchair,
  ArrowLeft,
  ArrowDownRight,
  ArrowUpRight,
  Building2,
  ChartSpline,
  ChevronRight,
  CircleDotDashed,
  Database,
  DatabaseZap,
  DoorOpen,
  ExternalLink,
  Layers3,
  LocateFixed,
  Move3d,
  Play,
  RadioTower,
  RefreshCw,
  RotateCcw,
  Rotate3d,
  ServerCog,
  UsersRound,
  Warehouse
} from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";

import { EnterpriseTwinScene } from "@/components/twin/enterprise-twin-scene";
import { ScopeTwinPanel } from "@/components/twin/scope-twin-panel";
import { useExperience } from "@/demo/experience-provider";
import { apiFetch } from "@/lib/api-client";
import { apiErrorMessage } from "@/lib/api-error";
import { detailSceneForSpace, meetingStatusLabel, resolveTwinFocus } from "@/lib/twin-experience";
import type {
  CameraInteractionMode,
  EnterpriseTwinOverview,
  MeetingAction,
  TwinActor,
  TwinHotspot,
  TwinMeetingSeat,
  TwinObjectAction,
  TwinSceneFocus,
  TwinSpace
} from "@/lib/twin-types";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000";
const METRIC_ORDER = ["gmv_today", "orders_today", "refund_rate", "ad_roi", "active_members", "low_stock_skus"];
const FOCUS_ITEMS: Array<{ key: TwinSceneFocus; label: string; icon: typeof Building2 }> = [
  { key: "campus", label: "企业园区", icon: Building2 },
  { key: "operations", label: "经营空间", icon: Layers3 },
  { key: "warehouse", label: "仓储异常", icon: Warehouse },
  { key: "meeting", label: "数字会议", icon: UsersRound }
];

function formatMetric(value: number, unit: string): string {
  if (unit === "元" && value >= 10000) return `${(value / 10000).toFixed(1)}万`;
  if (value >= 10000) return new Intl.NumberFormat("zh-CN", { notation: "compact" }).format(value);
  if (unit === "%" || unit === "x") return value.toFixed(2);
  return new Intl.NumberFormat("zh-CN", { maximumFractionDigits: 0 }).format(value);
}

function timeLabel(value: string | null): string {
  if (!value) return "等待首批同步";
  return new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false
  }).format(new Date(value));
}

function focusSelection(focus: TwinSceneFocus): string {
  if (focus === "operations") return "operations-center";
  if (focus === "warehouse") return "warehouse";
  if (focus === "meeting") return "decision-room";
  return "campus";
}

function detailIcon(
  space: TwinSpace | undefined,
  actor: TwinActor | undefined,
  hotspot: TwinHotspot | undefined,
  seat: TwinMeetingSeat | undefined
) {
  if (seat) return Armchair;
  if (actor) return UsersRound;
  if (hotspot?.hotspot_type === "automation") return ServerCog;
  if (hotspot) return CircleDotDashed;
  if (space?.space_type === "warehouse") return Warehouse;
  if (space?.space_type === "meeting-room") return UsersRound;
  if (space?.space_type === "data-hall") return Database;
  return Layers3;
}

const ACTION_ICONS: Record<string, typeof Building2> = {
  armchair: Armchair,
  chart: ChartSpline,
  "door-open": DoorOpen,
  "external-link": ExternalLink,
  "user-round": UsersRound
};

const HOTSPOT_DETAIL_LABELS: Record<string, string> = {
  sku: "关联商品",
  stock: "可用库存",
  coverage_days: "库存覆盖",
  inbound: "补货进度",
  today_batches: "今日批次",
  waiting_batches: "等待批次",
  average_minutes: "平均耗时",
  today_orders: "今日订单",
  backlog: "待分拣",
  on_time_rate: "准时率",
  task: "当前任务",
  progress: "任务进度",
  battery: "剩余电量",
  snapshot: "证据快照",
  source_count: "来源数量",
  as_of: "数据截止",
  scope: "证据范围",
  conflict: "争议焦点",
  positions: "独立观点",
  unresolved: "待解决分歧",
  moderator: "会议主持",
  recommendation: "决策建议",
  stop_condition: "停止条件",
  owner: "执行责任人",
  state: "生成状态",
  decision: "会议结论",
  action: "候选行动",
  approval: "审批要求",
  write_mode: "执行方式",
  audit: "审计要求"
};

function hotspotDetailValue(key: string, value: unknown): string {
  if (typeof value === "number" && ["on_time_rate", "progress", "battery"].includes(key)) return `${Math.round(value * 100)}%`;
  if (key === "coverage_days" && typeof value === "number") return `${value} 天`;
  return String(value);
}

function hotspotStateLabel(hotspot: TwinHotspot, meetingStatus: NonNullable<EnterpriseTwinOverview["meeting"]>["status"]): string {
  if (hotspot.hotspot_type === "evidence-wall") return "证据已校验";
  if (hotspot.hotspot_type === "deliberation-map") return meetingStatus === "scheduled" ? "等待角色观点" : meetingStatus === "decision_ready" ? "分歧已收敛" : "分歧研判中";
  if (hotspot.hotspot_type === "decision-output") return meetingStatus === "decision_ready" ? "决策包已形成" : "随研判生成";
  if (hotspot.hotspot_type === "action-gate") return meetingStatus === "decision_ready" ? "等待审批" : "尚未开放";
  return hotspot.severity === "critical" ? "需立即处理" : hotspot.severity === "warning" ? "需要关注" : "运行正常";
}

export function EnterpriseTwinPage() {
  const { scopeContext } = useExperience();
  if (!scopeContext) return <p role="status">正在读取范围</p>;
  if (scopeContext.scope_level !== "enterprise") return <ScopeTwinPanel key={scopeContext.scope_version} />;
  return <ScopedEnterpriseTwinPage key={scopeContext?.scope_version ?? "pending"} />;
}

function ScopedEnterpriseTwinPage() {
  const [overview, setOverview] = useState<EnterpriseTwinOverview | null>(null);
  const [focus, setFocus] = useState<TwinSceneFocus>("campus");
  const [selectedKey, setSelectedKey] = useState("campus");
  const [detailSceneKey, setDetailSceneKey] = useState<string | null>(null);
  const [activeLayerKeys, setActiveLayerKeys] = useState<string[]>([]);
  const [resetCameraToken, setResetCameraToken] = useState(0);
  const [cameraInteractionMode, setCameraInteractionMode] = useState<CameraInteractionMode>("rotate");
  const [loading, setLoading] = useState(true);
  const [meetingPending, setMeetingPending] = useState(false);
  const [followMeeting, setFollowMeeting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadOverview = useCallback(async () => {
    const response = await apiFetch(`${API_BASE_URL}/api/v1/data-center/overview`, { cache: "no-store" });
    if (!response.ok) throw new Error(await apiErrorMessage(response, "数据中心接口不可用"));
    const payload = (await response.json()) as EnterpriseTwinOverview;
    setOverview(payload);
    setActiveLayerKeys((current) => current.length > 0 ? current : payload.data_layers.filter((layer) => layer.enabled_default).map((layer) => layer.key));
  }, []);

  useEffect(() => {
    loadOverview()
      .catch((reason: unknown) => setError(reason instanceof Error ? reason.message : "无法读取数据中心"))
      .finally(() => setLoading(false));
  }, [loadOverview]);

  const applyMeetingAction = useCallback(async (meetingKey: string, action: MeetingAction) => {
    setMeetingPending(true);
    setError(null);
    try {
      const response = await apiFetch(
        `${API_BASE_URL}/api/v1/data-center/meetings/${encodeURIComponent(meetingKey)}/actions`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ action })
        }
      );
      if (!response.ok) {
        throw new Error(await apiErrorMessage(response, "会议状态更新失败"));
      }
      const payload = (await response.json()) as { overview: EnterpriseTwinOverview };
      if (!payload.overview.meeting) throw new Error("会议已不可用");
      setOverview(payload.overview);
      setFollowMeeting(action !== "reset");
      const detailScene = detailSceneForSpace(
        payload.overview.scenes,
        payload.overview.meeting.room_space_key
      );
      setDetailSceneKey(action === "reset" ? null : detailScene?.key ?? null);
      setFocus("meeting");
      const hotspotType = action === "decide" ? "decision-output" : "evidence-wall";
      const selectedHotspot = payload.overview.hotspots.find(
        (item) => item.scene_key === detailScene?.key && item.hotspot_type === hotspotType
      );
      setSelectedKey(selectedHotspot?.key ?? payload.overview.meeting.room_space_key);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "会议状态更新失败");
    } finally {
      setMeetingPending(false);
    }
  }, []);

  useEffect(() => {
    if (overview?.meeting?.status !== "convening") return;
    const timer = window.setInterval(() => {
      void loadOverview().catch((reason: unknown) => {
        setError(reason instanceof Error ? reason.message : "无法刷新会议状态");
      });
    }, 600);
    return () => window.clearInterval(timer);
  }, [loadOverview, overview?.meeting?.status]);

  const activeFocus = overview?.meeting ? resolveTwinFocus(focus, overview.meeting.status, followMeeting) : focus;
  const selectedSpace = useMemo(
    () => overview?.spaces.find((space) => space.key === selectedKey),
    [overview, selectedKey]
  );
  const selectedActor = useMemo(
    () => overview?.actors.find((actor) => actor.key === selectedKey),
    [overview, selectedKey]
  );
  const selectedHotspot = useMemo(
    () => overview?.hotspots.find((hotspot) => hotspot.key === selectedKey),
    [overview, selectedKey]
  );
  const selectedSeat = useMemo(
    () => overview?.meeting?.seats.find((seat) => seat.key === selectedKey),
    [overview, selectedKey]
  );
  const selectedInteraction = useMemo(
    () => overview?.interactions.find((interaction) => interaction.entity_key === selectedKey),
    [overview, selectedKey]
  );
  const selectedMetric = overview?.metrics.find((metric) => metric.key === (selectedSpace?.metric_key ?? selectedHotspot?.metric_key));

  function selectFocus(nextFocus: TwinSceneFocus) {
    setFollowMeeting(false);
    setDetailSceneKey(null);
    setFocus(nextFocus);
    setSelectedKey(focusSelection(nextFocus));
    setResetCameraToken((value) => value + 1);
  }

  function selectEntity(key: string) {
    setFollowMeeting(false);
    setSelectedKey(key);
    const space = overview?.spaces.find((item) => item.key === key);
    const hotspot = overview?.hotspots.find((item) => item.key === key);
    if (hotspot) return;
    if (space?.space_type === "warehouse") setFocus("warehouse");
    else if (space?.space_type === "meeting-room") setFocus("meeting");
    else if (space && space.key !== "campus") setFocus("operations");
  }

  function enterSpace(spaceKey: string) {
    if (!overview) return;
    const detailScene = detailSceneForSpace(overview.scenes, spaceKey);
    if (!detailScene) return;
    setDetailSceneKey(detailScene.key);
    setFollowMeeting(spaceKey === "decision-room");
    setFocus(spaceKey === "warehouse" ? "warehouse" : spaceKey === "decision-room" ? "meeting" : focus);
    const primaryHotspot = overview.hotspots.find((item) => item.scene_key === detailScene.key && item.severity === "critical")
      ?? overview.hotspots.find((item) => item.scene_key === detailScene.key);
    setSelectedKey(primaryHotspot?.key ?? spaceKey);
    setResetCameraToken((value) => value + 1);
  }

  function leaveDetailScene() {
    const detailScene = overview?.scenes.find((scene) => scene.key === detailSceneKey);
    const entrySpaceKey = detailScene?.entry_space_key ?? "campus";
    setDetailSceneKey(null);
    setFollowMeeting(false);
    setFocus(entrySpaceKey === "warehouse" ? "warehouse" : entrySpaceKey === "decision-room" ? "meeting" : "campus");
    setSelectedKey(entrySpaceKey);
    setResetCameraToken((value) => value + 1);
  }

  function toggleLayer(layerKey: string) {
    setActiveLayerKeys((current) => current.includes(layerKey)
      ? current.filter((key) => key !== layerKey)
      : [...current, layerKey]);
  }

  function runObjectAction(action: TwinObjectAction) {
    if (action.action_type === "enter" && action.target_key) {
      enterSpace(action.target_key);
      return;
    }
    if (
      action.action_type === "focus"
      && action.target_key
      && ["campus", "operations", "warehouse", "meeting"].includes(action.target_key)
    ) {
      selectFocus(action.target_key as TwinSceneFocus);
    }
  }

  if (loading) {
    return (
      <div className="twin-boot-state">
        <DatabaseZap aria-hidden="true" size={28} />
        <strong>正在装载企业经营空间</strong>
      </div>
    );
  }

  if (!overview) {
    return (
      <div className="twin-boot-state failed">
        <AlertTriangle aria-hidden="true" size={28} />
        <strong>企业数据底座不可用</strong>
        <span>{error}</span>
        <button onClick={() => window.location.reload()} type="button">重新连接</button>
      </div>
    );
  }

  if (!overview.scene || !overview.meeting) {
    return <div className="twin-boot-state"><DatabaseZap aria-hidden="true" size={28} /><strong>暂无经营场景</strong></div>;
  }

  const source = overview.sources[0];
  const sourceOnline = source?.status === "connected";
  const metrics = [...overview.metrics]
    .sort((left, right) => {
      const leftRank = METRIC_ORDER.indexOf(left.key);
      const rightRank = METRIC_ORDER.indexOf(right.key);
      return (leftRank < 0 ? Number.MAX_SAFE_INTEGER : leftRank)
        - (rightRank < 0 ? Number.MAX_SAFE_INTEGER : rightRank);
    })
    .slice(0, 5);
  const DetailIcon = detailIcon(selectedSpace, selectedActor, selectedHotspot, selectedSeat);
  const meeting = overview.meeting;
  const activeScene = overview.scenes.find((scene) => scene.key === detailSceneKey) ?? overview.scene;
  const activeLayers = overview.data_layers.filter((layer) => layer.scene_key === detailSceneKey);
  const meetingActors = meeting.participants.map((participant) => ({
    participant,
    actor: overview.actors.find((actor) => actor.key === participant.actor_key)
  }));
  const selectedSeatParticipant = selectedSeat
    ? meeting.participants.find((participant) => participant.seat_key === selectedSeat.key)
    : undefined;
  const selectedSeatActor = selectedSeatParticipant
    ? overview.actors.find((actor) => actor.key === selectedSeatParticipant.actor_key)
    : undefined;

  return (
    <section className="twin-workbench twin-spatial-workbench" aria-label="企业经营数字孪生工作台">
      <EnterpriseTwinScene
        activeLayerKeys={activeLayerKeys}
        actors={overview.actors}
        cameraInteractionMode={cameraInteractionMode}
        detailSceneKey={detailSceneKey}
        focus={activeFocus}
        hotspots={overview.hotspots}
        interactions={overview.interactions}
        meeting={meeting}
        onEnter={enterSpace}
        onSelect={selectEntity}
        resetCameraToken={resetCameraToken}
        routes={overview.routes}
        scene={overview.scene}
        scenes={overview.scenes}
        selectedKey={selectedKey}
        spaces={overview.spaces}
      />

      <header className="twin-identity">
        <div className="twin-kicker"><span /> OPERATIONAL DIGITAL TWIN · {activeScene.version}</div>
        <h1>{detailSceneKey ? activeScene.name : overview.enterprise.name}</h1>
      </header>

      {detailSceneKey ? (
        <nav className="twin-scene-breadcrumb" aria-label="空间层级">
          <button onClick={leaveDetailScene} type="button">企业园区</button>
          <ChevronRight aria-hidden="true" size={12} />
          <span>{activeScene.name}</span>
        </nav>
      ) : null}

      <div className="twin-view-controls" aria-label="三维镜头控制">
        {detailSceneKey ? (
          <button aria-label="返回企业园区" onClick={leaveDetailScene} title="返回企业园区" type="button">
            <ArrowLeft aria-hidden="true" size={16} />
          </button>
        ) : null}
        <div className="twin-camera-mode" role="group" aria-label="鼠标拖动模式">
          <button
            aria-label="左键拖动旋转视角"
            aria-pressed={cameraInteractionMode === "rotate"}
            className={cameraInteractionMode === "rotate" ? "active" : ""}
            onClick={() => setCameraInteractionMode("rotate")}
            title="旋转视角"
            type="button"
          >
            <Rotate3d aria-hidden="true" size={16} />
          </button>
          <button
            aria-label="左键拖动平移视角"
            aria-pressed={cameraInteractionMode === "pan"}
            className={cameraInteractionMode === "pan" ? "active" : ""}
            onClick={() => setCameraInteractionMode("pan")}
            title="平移视角"
            type="button"
          >
            <Move3d aria-hidden="true" size={16} />
          </button>
        </div>
        <button aria-label="复位当前视角" onClick={() => setResetCameraToken((value) => value + 1)} title="复位当前视角" type="button">
          <LocateFixed aria-hidden="true" size={16} />
        </button>
      </div>

      <div className="twin-runtime-status">
        <span className={sourceOnline ? "online" : "standby"} />
        <div>
          <strong>{sourceOnline ? "来源已连接" : "等待数据接入"}</strong>
          <small>{timeLabel(source?.last_sync_at ?? null)}</small>
        </div>
      </div>

      <nav className={`twin-focus-switch ${detailSceneKey ? "detail-hidden" : ""}`} aria-label="数字孪生空间导航">
        {FOCUS_ITEMS.map((item, index) => {
          const Icon = item.icon;
          const active = activeFocus === item.key;
          return (
            <button
              aria-pressed={active}
              className={active ? "active" : ""}
              key={item.key}
              onClick={() => selectFocus(item.key)}
              type="button"
            >
              <span>{String(index + 1).padStart(2, "0")}</span>
              <Icon aria-hidden="true" size={16} />
              <div><strong>{item.label}</strong>{item.key === "meeting" ? <small>{meetingStatusLabel(meeting.status)}</small> : null}</div>
              <ChevronRight aria-hidden="true" className="focus-arrow" size={14} />
            </button>
          );
        })}
      </nav>

      {detailSceneKey && activeLayers.length > 0 ? (
        <div className="twin-layer-switch" aria-label="空间数据图层">
          <span><Layers3 aria-hidden="true" size={14} />数据图层</span>
          {activeLayers.map((layer) => {
            const enabled = activeLayerKeys.includes(layer.key);
            return (
              <button
                aria-pressed={enabled}
                className={enabled ? "active" : ""}
                key={layer.key}
                onClick={() => toggleLayer(layer.key)}
                type="button"
              >
                <i />{layer.label}
              </button>
            );
          })}
        </div>
      ) : null}

      <aside className={`twin-command-panel ${activeFocus === "meeting" ? "meeting-mode" : ""}`}>
        <div className="command-panel-heading">
          <span className={`detail-signal ${selectedSpace?.alert_level === "warning" || selectedHotspot?.severity === "warning" ? "warning" : ""} ${selectedHotspot?.severity === "critical" ? "critical" : ""}`}>
            <DetailIcon aria-hidden="true" size={17} />
          </span>
          <div>
            <small>{selectedActor ? "ROLE TWIN" : selectedSeat ? "MEETING SEAT" : selectedHotspot ? "LIVE BUSINESS HOTSPOT" : selectedSpace?.space_type.toUpperCase() ?? "ENTERPRISE SCENE"}</small>
            <h2>{selectedActor?.display_name ?? selectedSeat?.label ?? selectedHotspot?.label ?? selectedSpace?.label ?? overview.scene.name}</h2>
          </div>
          <div className="command-heading-actions">
            <span className="implemented-badge">实时投影</span>
            {selectedInteraction?.detail_route ? (
              <Link
                aria-label="打开所选对象的二维详情"
                className="command-detail-link"
                href={selectedInteraction.detail_route}
                title="打开二维详情"
              >
                <ExternalLink aria-hidden="true" size={14} />
              </Link>
            ) : null}
          </div>
        </div>

        {selectedActor ? (
          <div className="entity-detail">
            <p>{selectedActor.role_title}，当前状态为 {selectedActor.status === "in_transit" ? "前往会议室" : selectedActor.status === "in_meeting" ? "参与研判" : "在线待命"}。</p>
            <div className="capability-list">
              {selectedActor.capabilities.map((capability) => <span key={capability}>{capability}</span>)}
            </div>
          </div>
        ) : selectedSeat ? (
          <div className="entity-detail">
            <p>
              {selectedSeatActor
                ? `当前分配给 ${selectedSeatActor.display_name}，作为${selectedSeatParticipant?.position ?? "会议角色"}参与研判。`
                : "当前席位空闲，可在会议编排中分配给新增数字分身。"}
            </p>
            <dl className="space-health-grid">
              <div><dt>布局模板</dt><dd>{selectedSeat.layout_key}</dd></div>
              <div><dt>席位状态</dt><dd>{selectedSeatActor ? "已分配" : "空闲"}</dd></div>
              <div><dt>席位编号</dt><dd>{selectedSeat.key}</dd></div>
            </dl>
          </div>
        ) : selectedHotspot ? (
          <div className="entity-detail hotspot-detail">
            <p>{selectedHotspot.business_ref}</p>
            <dl>
              {Object.entries(selectedHotspot.details).slice(0, 5).map(([key, value]) => (
                <div key={key}>
                  <dt>{HOTSPOT_DETAIL_LABELS[key] ?? key}</dt>
                  <dd>{hotspotDetailValue(key, value)}</dd>
                </div>
              ))}
            </dl>
            <div className={`hotspot-severity ${selectedHotspot.severity}`}>
              <span />{hotspotStateLabel(selectedHotspot, meeting.status)}
            </div>
          </div>
        ) : (
          <div className="entity-detail">
            <p>{selectedSpace?.description ?? overview.scene.description}</p>
            <dl className="space-health-grid">
              <div><dt>空间健康</dt><dd>{Math.round((selectedSpace?.health ?? 0.96) * 100)}%</dd></div>
              <div><dt>运行状态</dt><dd>{selectedSpace?.alert_level === "warning" ? "需研判" : "正常"}</dd></div>
              <div>
                <dt>{selectedSpace?.key === "campus" ? "园区尺度" : "关联指标"}</dt>
                <dd>
                  {selectedSpace?.key === "campus"
                    ? `${selectedSpace.size[0]} × ${selectedSpace.size[2]}m`
                    : selectedMetric
                      ? formatMetric(selectedMetric.value, selectedMetric.unit)
                      : "实时映射"}
                </dd>
              </div>
            </dl>
          </div>
        )}

        {selectedInteraction?.actions.length ? (
          <div className="context-actions" aria-label="所选对象功能">
            {selectedInteraction.actions.map((action) => {
              const ActionIcon = ACTION_ICONS[action.icon_key] ?? ExternalLink;
              return action.action_type === "navigate" && action.href ? (
                <Link className={action.emphasis} href={action.href} key={action.key}>
                  <ActionIcon aria-hidden="true" size={15} />{action.label}
                </Link>
              ) : (
                <button
                  className={action.emphasis}
                  key={action.key}
                  onClick={() => runObjectAction(action)}
                  type="button"
                >
                  <ActionIcon aria-hidden="true" size={15} />{action.label}
                </button>
              );
            })}
          </div>
        ) : null}

        {activeFocus === "meeting" ? (
          <div className="meeting-console">
            <div className="meeting-title-row">
              <div><span>数字会议</span><strong>{meeting.title}</strong></div>
              <em>{meetingStatusLabel(meeting.status)}</em>
            </div>
            <p className="meeting-topic">{meeting.topic}</p>
            {!detailSceneKey ? (
              <button className="meeting-spatial-entry" onClick={() => enterSpace("decision-room")} type="button">
                <DoorOpen aria-hidden="true" size={15} />
                <span><strong>进入数字会议空间</strong><small>查看证据、观点和决策链</small></span>
                <ChevronRight aria-hidden="true" size={14} />
              </button>
            ) : null}
            <div className="meeting-participants">
              {meetingActors.map(({ participant, actor }) => (
                <button key={participant.actor_key} onClick={() => selectEntity(participant.actor_key)} type="button">
                  <span style={{ "--actor-color": actor?.color ?? "#70e1c1" } as React.CSSProperties} />
                  <div><strong>{actor?.display_name}</strong><small>{participant.position}</small></div>
                  <em className={participant.status}>{participant.status === "traveling" ? "到场中" : participant.status === "present" ? "研判中" : participant.status === "completed" ? "完成" : "待召集"}</em>
                </button>
              ))}
            </div>
            {meeting.status === "decision_ready" ? (
              <div className="decision-output">
                <span>AI 主持人汇总</span>
                <p>{meeting.decision}</p>
              </div>
            ) : null}
            <div className="meeting-actions">
              {meeting.status === "scheduled" ? (
                <button className="primary" disabled={meetingPending} onClick={() => void applyMeetingAction(meeting.key, "convene")} type="button">
                  <UsersRound aria-hidden="true" size={15} />召集分身会议
                </button>
              ) : null}
              {meeting.status === "convening" ? (
                <button className="primary" disabled type="button"><CircleDotDashed aria-hidden="true" size={15} />分身正在到场</button>
              ) : null}
              {meeting.status === "in_session" ? (
                <button className="primary" disabled={meetingPending} onClick={() => void applyMeetingAction(meeting.key, "decide")} type="button">
                  <Play aria-hidden="true" size={15} />形成决策包
                </button>
              ) : null}
              {meeting.status === "decision_ready" ? (
                <>
                  <Link className="primary" href={`/console/meetings/${meeting.key}`}><ExternalLink aria-hidden="true" size={15} />打开二维会议台账</Link>
                  <button aria-label="复位会议体验" className="icon-only" onClick={() => void applyMeetingAction(meeting.key, "reset")} title="复位会议体验" type="button"><RotateCcw size={15} /></button>
                </>
              ) : null}
            </div>
          </div>
        ) : null}
      </aside>

      <div className="twin-metric-dock" aria-label="实时经营指标">
        <div className="metric-dock-label"><RadioTower aria-hidden="true" size={15} /><span>LIVE<br />METRICS</span></div>
        {metrics.length > 0 ? metrics.map((metric) => {
          const positive = (metric.change_rate ?? 0) >= 0;
          const DeltaIcon = positive ? ArrowUpRight : ArrowDownRight;
          return (
            <article key={metric.key}>
              <span>{metric.label}</span>
              <strong>{formatMetric(metric.value, metric.unit)}<small>{metric.unit === "元" && metric.value >= 10000 ? "元" : metric.unit}</small></strong>
              <em className={positive ? "positive" : "negative"}><DeltaIcon aria-hidden="true" size={11} />{metric.change_rate === null ? "实时" : `${Math.abs(metric.change_rate * 100).toFixed(1)}%`}</em>
            </article>
          );
        }) : (
          <article className="metric-placeholder"><strong>暂无经营指标</strong></article>
        )}
        <div className="twin-source-control">
          <Link href="/console/reconciliation">经营对账</Link>
          <Link href="/console/assistant">高管分身</Link>
          <button onClick={() => void loadOverview().catch((reason: unknown) => setError(reason instanceof Error ? reason.message : "刷新失败"))} type="button">
            <RefreshCw aria-hidden="true" size={14} />刷新
          </button>
        </div>
      </div>

      <footer className="twin-runtime-footprint">
        <span><Database aria-hidden="true" size={12} />{overview.database.engine.toUpperCase()} · {overview.database.schema_revision}</span>
        <span><ServerCog aria-hidden="true" size={12} />{overview.spaces.length} 个经营空间</span>
        <span><UsersRound aria-hidden="true" size={12} />{overview.actors.length} 个分身</span>
        <span>{overview.source_record_count} 条原始记录</span>
      </footer>

      {error ? <div className="twin-error"><AlertTriangle aria-hidden="true" size={14} />{error}</div> : null}
    </section>
  );
}
