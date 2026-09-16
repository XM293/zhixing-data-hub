"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";

import { demoExperienceDataSource } from "@/demo/experience-data-source";
import { apiFetch } from "@/lib/api-client";
import { apiErrorMessage } from "@/lib/api-error";
import type { DemoRoleId, ExperienceSnapshot } from "@/lib/experience-types";
import type {
  AuthSessionResponse,
  CenterCatalog,
  CurrentIdentity,
  ScopeContext,
  ScopeSelection,
  ScopeOptions
} from "@/lib/identity-types";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000";

interface ExperienceContextValue {
  snapshot: ExperienceSnapshot;
  roleId: DemoRoleId;
  setRoleId: (roleId: DemoRoleId) => void;
  identity: CurrentIdentity | null;
  centerCatalog: CenterCatalog | null;
  scopeOptions: ScopeOptions | null;
  scopeContext: ScopeContext | null;
  switchScope: (selection: ScopeSelection) => Promise<void>;
  switchEnterprise: (enterpriseId: string) => Promise<void>;
  refreshScope: () => Promise<void>;
  identityLoading: boolean;
  identityError: string | null;
  sessionActive: boolean;
  sessionBusy: boolean;
  startSession: (loginName: string, password: string) => Promise<void>;
  endSession: () => Promise<void>;
  allowedSectionKeys: string[];
  can: (permission: string) => boolean;
  toast: string | null;
  dismissToast: () => void;
  publishPolicy: () => void;
  reviewMemory: (decision: "approved" | "rejected") => void;
  advanceMeeting: () => void;
  approveAction: () => void;
  generateDraft: () => void;
  escalateConversation: () => void;
  retryCrmJob: () => void;
  resetDemo: () => void;
}

const ExperienceContext = createContext<ExperienceContextValue | null>(null);

export function ExperienceProvider({ children }: { children: React.ReactNode }) {
  const [snapshot, setSnapshot] = useState<ExperienceSnapshot>(() =>
    demoExperienceDataSource.readSnapshot()
  );
  const [roleId, setRoleId] = useState<DemoRoleId>("ceo");
  const [toast, setToast] = useState<string | null>(null);
  const [identity, setIdentity] = useState<CurrentIdentity | null>(null);
  const [centerCatalog, setCenterCatalog] = useState<CenterCatalog | null>(null);
  const [scopeOptions, setScopeOptions] = useState<ScopeOptions | null>(null);
  const [scopeContext, setScopeContext] = useState<ScopeContext | null>(null);
  const [identityLoading, setIdentityLoading] = useState(true);
  const [identityError, setIdentityError] = useState<string | null>(null);
  const [sessionActive, setSessionActive] = useState(false);
  const [sessionBusy, setSessionBusy] = useState(false);

  const loadCenterCatalog = useCallback(async (signal?: AbortSignal) => {
    const response = await apiFetch(`${API_BASE_URL}/api/v1/centers/me`, {
      cache: "no-store",
      signal
    });
    if (response.ok) {
      setCenterCatalog(await response.json() as CenterCatalog);
    } else {
      setCenterCatalog(null);
    }
  }, []);

  const loadScopeOptions = useCallback(async (signal?: AbortSignal) => {
    const response = await apiFetch(`${API_BASE_URL}/api/v1/auth/scope-options`, {
      cache: "no-store",
      signal
    });
    setScopeOptions(response.ok ? await response.json() as ScopeOptions : null);
    const contextResponse = await apiFetch(`${API_BASE_URL}/api/v1/context`, { cache: "no-store", signal });
    setScopeContext(contextResponse.ok ? await contextResponse.json() as ScopeContext : null);
  }, []);

  const loadIdentity = useCallback(async (signal?: AbortSignal) => {
    const sessionResponse = await apiFetch(`${API_BASE_URL}/api/v1/auth/session`, {
      cache: "no-store",
      signal
    });
    if (sessionResponse.ok) {
      const session = await sessionResponse.json() as CurrentIdentity;
      setSessionActive(true);
      setIdentity(session);
      await loadCenterCatalog(signal);
      await loadScopeOptions(signal);
      return;
    }
    if (sessionResponse.status !== 401) {
      throw new Error(await apiErrorMessage(sessionResponse, "无法解析当前会话"));
    }
    setSessionActive(false);
    setIdentity(null);
    setCenterCatalog(null);
    setScopeOptions(null);
    setScopeContext(null);
  }, [loadCenterCatalog, loadScopeOptions]);

  useEffect(() => {
    const controller = new AbortController();
    setIdentityLoading(true);
    setIdentityError(null);
    loadIdentity(controller.signal)
      .catch((reason: unknown) => {
        if (controller.signal.aborted) return;
        setIdentity(null);
        setIdentityError(reason instanceof Error ? reason.message : "数据库身份解析失败");
      })
      .finally(() => {
        if (!controller.signal.aborted) setIdentityLoading(false);
      });
    return () => controller.abort();
  }, [loadIdentity]);

  const startSession = useCallback(async (loginName: string, password: string) => {
    setSessionBusy(true);
    setIdentityError(null);
    try {
      const response = await apiFetch(`${API_BASE_URL}/api/v1/auth/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ login_name: loginName, password })
      });
      if (!response.ok) throw new Error(await apiErrorMessage(response, "无法建立登录会话"));
      const session = await response.json() as AuthSessionResponse;
      const nextRole = snapshot.roles.some((role) => role.id === session.identity.actor.experience_role_key)
        ? session.identity.actor.experience_role_key as DemoRoleId
        : "ceo";
      setRoleId(nextRole);
      setIdentity(session.identity);
      setSessionActive(true);
      await loadCenterCatalog();
      await loadScopeOptions();
    } catch (reason: unknown) {
      setIdentityError(reason instanceof Error ? reason.message : "无法建立登录会话");
      throw reason;
    } finally {
      setSessionBusy(false);
    }
  }, [loadCenterCatalog, snapshot.roles]);

  const endSession = useCallback(async () => {
    setSessionBusy(true);
    try {
      await apiFetch(`${API_BASE_URL}/api/v1/auth/logout`, { method: "POST" });
      setSessionActive(false);
      setIdentity(null);
      setCenterCatalog(null);
      setScopeOptions(null);
      setScopeContext(null);
      setIdentityError(null);
    } catch (reason: unknown) {
      setIdentityError(reason instanceof Error ? reason.message : "无法注销当前会话");
    } finally {
      setSessionBusy(false);
    }
  }, []);

  const switchScope = useCallback(async (selection: ScopeSelection) => {
    setSessionBusy(true);
    setIdentityError(null);
    try {
      const response = await apiFetch(`${API_BASE_URL}/api/v1/context/switch`, {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(selection)
      });
      if (!response.ok) throw new Error(await apiErrorMessage(response, "无法切换数据范围"));
      const result = await response.json() as { identity: CurrentIdentity; context: ScopeContext };
      setIdentity(result.identity);
      setScopeContext(result.context);
      await Promise.all([loadCenterCatalog(), loadScopeOptions()]);
    } catch (reason) {
      setIdentityError(reason instanceof Error ? reason.message : "范围切换失败");
      throw reason;
    } finally {
      setSessionBusy(false);
    }
  }, [loadCenterCatalog, loadScopeOptions]);

  const switchEnterprise = useCallback(async (enterpriseId: string) => {
    if (enterpriseId) await switchScope({ enterprise_id: enterpriseId, scope_level: "enterprise" });
  }, [switchScope]);

  const publishPolicy = useCallback(() => {
    setSnapshot((current) => {
      const page = current.tablePages["knowledge/policies"];
      return {
        ...current,
        policy: {
          ...current.policy,
          status: "published"
        },
        tablePages: {
          ...current.tablePages,
          "knowledge/policies": {
            ...page,
            rows: page.rows.map((row) =>
              row.id === current.policy.id
                ? { ...row, status: { label: "已发布 / 待生效", tone: "info" } }
                : row
            )
          }
        }
      };
    });
    setToast("制度 v3 已发布，计划于 2026-09-01 生效");
  }, []);

  const reviewMemory = useCallback((decision: "approved" | "rejected") => {
    setSnapshot((current) => {
      const page = current.tablePages["twins/memories"];
      return {
        ...current,
        memory: { ...current.memory, status: decision },
        tablePages: {
          ...current.tablePages,
          "twins/memories": {
            ...page,
            rows: page.rows.map((row) =>
              row.id === current.memory.id
                ? {
                    ...row,
                    status: decision === "approved"
                      ? { label: "已批准", tone: "positive" }
                      : { label: "已拒绝", tone: "critical" }
                  }
                : row
            )
          }
        }
      };
    });
    setToast(decision === "approved" ? "记忆候选已批准" : "冲突记忆已拒绝，不会进入长期记忆");
  }, []);

  const advanceMeeting = useCallback(() => {
    setSnapshot((current) => {
      const page = current.tablePages.meetings;
      return {
        ...current,
        meeting: { ...current.meeting, status: "decision_ready" },
        tablePages: {
          ...current.tablePages,
          meetings: {
            ...page,
            rows: page.rows.map((row) =>
              row.id === current.meeting.id
                ? { ...row, status: { label: "待确认", tone: "warning" } }
                : row
            )
          }
        }
      };
    });
    setToast("会议已形成决策包，分歧已保留");
  }, []);

  const approveAction = useCallback(() => {
    setSnapshot((current) => {
      const page = current.tablePages["actions/proposals"];
      return {
        ...current,
        action: { ...current.action, status: "simulated_succeeded" },
        tablePages: {
          ...current.tablePages,
          "actions/proposals": {
            ...page,
            rows: page.rows.map((row) =>
              row.id === current.action.id
                ? { ...row, status: { label: "已完成", tone: "positive" } }
                : row
            )
          }
        }
      };
    });
    setToast("审批已完成，执行记录已写入台账");
  }, []);

  const generateDraft = useCallback(() => {
    setSnapshot((current) => {
      const conversations = current.tablePages["customer-service/conversations"];
      const drafts = current.tablePages["customer-service/drafts"];
      return {
        ...current,
        conversation: { ...current.conversation, status: "drafted" },
        tablePages: {
          ...current.tablePages,
          "customer-service/conversations": {
            ...conversations,
            rows: conversations.rows.map((row) =>
              row.id === current.conversation.id
                ? { ...row, status: { label: "草稿待确认", tone: "info" } }
                : row
            )
          },
          "customer-service/drafts": {
            ...drafts,
            rows: drafts.rows.map((row) =>
              row.id === "draft-10086"
                ? {
                    ...row,
                    cells: { ...row.cells, updated: "09:30" },
                    status: { label: "待确认", tone: "warning" }
                  }
                : row
            )
          }
        }
      };
    });
    setToast("回复草稿已生成，补偿金额仍需人工确认");
  }, []);

  const escalateConversation = useCallback(() => {
    setSnapshot((current) => {
      const page = current.tablePages["customer-service/conversations"];
      return {
        ...current,
        conversation: { ...current.conversation, status: "escalated" },
        tablePages: {
          ...current.tablePages,
          "customer-service/conversations": {
            ...page,
            rows: page.rows.map((row) =>
              row.id === current.conversation.id
                ? { ...row, status: { label: "人工接管", tone: "warning" } }
                : row
            )
          }
        }
      };
    });
    setToast("会话已进入人工接管队列");
  }, []);

  const retryCrmJob = useCallback(() => {
    setSnapshot((current) => {
      const page = current.tablePages["admin/jobs"];
      return {
        ...current,
        tablePages: {
          ...current.tablePages,
          "admin/jobs": {
            ...page,
            rows: page.rows.map((row) =>
              row.id === "job-crm-admin"
                ? { ...row, status: { label: "重试排队", tone: "info" } }
                : row
            )
          }
        }
      };
    });
    setToast("CRM 同步已加入重试队列");
  }, []);

  const resetDemo = useCallback(() => {
    setSnapshot(demoExperienceDataSource.readSnapshot());
    setRoleId("ceo");
    setToast("业务快照已重置到 2026-08-25 09:30");
  }, []);

  const value = useMemo<ExperienceContextValue>(
    () => {
      const fallbackRole = snapshot.roles.find((role) => role.id === roleId) ?? snapshot.roles[0];
      return {
        snapshot,
        roleId,
        setRoleId,
        identity,
        centerCatalog,
        scopeOptions,
        scopeContext,
        switchScope,
        switchEnterprise,
        refreshScope: loadScopeOptions,
        identityLoading,
        identityError,
        sessionActive,
        sessionBusy,
        startSession,
        endSession,
        allowedSectionKeys: identity?.navigation_sections ?? fallbackRole.allowedSections,
        can: (permission: string) => identity?.actor.permissions.includes(permission) ?? false,
        toast,
        dismissToast: () => setToast(null),
        publishPolicy,
        reviewMemory,
        advanceMeeting,
        approveAction,
        generateDraft,
        escalateConversation,
        retryCrmJob,
        resetDemo
      };
    },
    [
      snapshot,
      roleId,
      identity,
      centerCatalog,
      scopeOptions,
      scopeContext,
      switchScope,
      loadScopeOptions,
      identityLoading,
      identityError,
      sessionActive,
      sessionBusy,
      startSession,
      endSession,
      switchEnterprise,
      toast,
      publishPolicy,
      reviewMemory,
      advanceMeeting,
      approveAction,
      generateDraft,
      escalateConversation,
      retryCrmJob,
      resetDemo
    ]
  );

  return <ExperienceContext.Provider value={value}>{children}</ExperienceContext.Provider>;
}

export function useExperience(): ExperienceContextValue {
  const context = useContext(ExperienceContext);
  if (!context) throw new Error("useExperience must be used within ExperienceProvider");
  return context;
}
