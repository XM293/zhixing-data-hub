"use client";

import {
  Bell,
  LogOut,
  LoaderCircle,
  Maximize2,
  Menu,
  Minimize2,
  Search,
  Sparkles,
  X
} from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

import { LoginScreen } from "@/components/auth/login-screen";
import { InteractionProvider, useNotifications } from "@/components/console/interaction";
import { CenterNavigation, FIVE_BUSINESS_CENTERS } from "@/components/navigation/center-navigation";
import { TagsView } from "@/components/navigation/tags-view";
import { ExperienceProvider, useExperience } from "@/demo/experience-provider";
import { projectNavigation, sectionForPath } from "@/lib/navigation";
import {
  businessUnitSelection,
  entityScopeSelection,
  parentScopeSelection,
  scopeOptionVisible
} from "@/lib/scope-selection";

export function ConsoleExperience({ children }: { children: React.ReactNode }) {
  return (
    <InteractionProvider>
      <ExperienceProvider>
        <ConsoleShell>{children}</ConsoleShell>
      </ExperienceProvider>
    </InteractionProvider>
  );
}

function ConsoleShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const { notify } = useNotifications();
  const { allowedSectionKeys, can, centerCatalog, identity, identityError, identityLoading, sessionActive, sessionBusy, startSession, endSession, toast, dismissToast, scopeOptions, scopeContext, switchScope, switchEnterprise } = useExperience();
  const [menuOpen, setMenuOpen] = useState(false);
  const [searchOpen, setSearchOpen] = useState(false);
  const [isFullscreen, setIsFullscreen] = useState(false);

  const toggleFullscreen = () => {
    if (typeof document === "undefined") return;
    if (!document.fullscreenElement) {
      document.documentElement.requestFullscreen().catch(() => {});
      setIsFullscreen(true);
    } else {
      document.exitFullscreen().catch(() => {});
      setIsFullscreen(false);
    }
  };
  const isTwinHome = pathname === "/console" || pathname === "/console/spatial";
  const isTwinScene = isTwinHome && scopeContext?.scope_level === "enterprise";
  const isCockpit = pathname === "/console/cockpit";
  const isCockpitScene = isCockpit && scopeContext?.scope_level === "enterprise";
  const isDatabaseDataCenter = pathname.startsWith("/console/data");
  const isDataWorkspace = pathname.startsWith("/console/data/");
  const isDatabaseKnowledge = pathname.startsWith("/console/knowledge");
  const isDatabaseTwins = pathname.startsWith("/console/twins");
  const isDatabaseMeetings = pathname.startsWith("/console/meetings");
  const isDatabaseActions = pathname.startsWith("/console/actions");
  const isDatabaseAdmin = [
    "/console/admin/users",
    "/console/admin/org",
    "/console/admin/access",
    "/console/admin/tools",
    "/console/admin/audit"
  ].includes(pathname);
  const isDatabaseAssistant = pathname === "/console/assistant" || pathname === "/console/analysis/ask";
  const isDatabaseAnalysis = pathname.startsWith("/console/analysis");
  const isDatabaseCustomerService = pathname.startsWith("/console/customer-service");
  const isAnalysisWorkspace = [
    "/console/analysis/store-review",
    "/console/analysis/briefs",
    "/console/analysis/review-plans"
  ].includes(pathname);
  const isCustomerServiceWorkspace = isDatabaseCustomerService;
  const usesDatabaseView = isTwinHome || isCockpit || isDatabaseDataCenter || isDatabaseKnowledge || isDatabaseTwins || isDatabaseMeetings || isDatabaseActions || isDatabaseAdmin || isDatabaseAssistant || isDatabaseAnalysis || isDatabaseCustomerService;
  const section = sectionForPath(pathname);
  const currentItem = section.items.find((item) => pathname === item.href);
  const breadcrumbInfo = useMemo(() => {
    for (const center of FIVE_BUSINESS_CENTERS) {
      const item = center.items.find((i) => i.matches(pathname));
      if (item) {
        return { center: center.label, item: item.label };
      }
    }
    return { center: isTwinHome ? "企业数字孪生" : section.shortLabel, item: currentItem?.label || "控制台" };
  }, [pathname, isTwinHome, section.shortLabel, currentItem?.label]);
  const visibleNavigation = useMemo(
    () => projectNavigation(allowedSectionKeys, identity?.navigation),
    [allowedSectionKeys, identity?.navigation]
  );

  useEffect(() => {
    setMenuOpen(false);
    setSearchOpen(false);
  }, [pathname]);

  useEffect(() => {
    if (!toast) return;
    notify({ title: toast, tone: "success" });
    dismissToast();
  }, [dismissToast, notify, toast]);

  if (identityLoading) {
    return (
      <div className="auth-state-screen">
        <LoaderCircle aria-hidden="true" className="spinning" size={22} />
        <span>正在建立企业会话…</span>
      </div>
    );
  }

  if (!identity) {
    return <LoginScreen busy={sessionBusy} error={identityError} onSubmit={startSession} />;
  }

  return (
    <div className={`console-root ${isTwinScene || isCockpitScene ? "twin-shell" : ""} ${isCockpitScene ? "cockpit-shell" : ""}`}>
      <button
        aria-label="关闭导航"
        className={`nav-scrim ${menuOpen ? "visible" : ""}`}
        onClick={() => setMenuOpen(false)}
        type="button"
      />
      <aside className={`console-sidebar ${menuOpen ? "open" : ""}`}>
        <div className="sidebar-brand">
          <span className="brand-symbol">知</span>
          <span className="brand-wordmark">
            <strong>知行数枢</strong>
            <small>企业数据智能运营中枢</small>
          </span>
          <button
            aria-label="关闭导航"
            className="icon-button sidebar-close"
            onClick={() => setMenuOpen(false)}
            type="button"
          >
            <X size={18} />
          </button>
        </div>

        <nav className="primary-nav" aria-label="产品中心">
          <CenterNavigation
            activeSectionKey={section.key}
            catalog={centerCatalog}
            fallback={visibleNavigation}
            pathname={pathname}
          />
        </nav>

        <div className="sidebar-footer">
          <div className="sidebar-identity">
            <span aria-hidden="true" />
            <div>
              <strong>{identity.actor.organization}</strong>
              <small>{identity.actor.position}</small>
            </div>
          </div>
        </div>
      </aside>

      <div className="console-workspace">
        <header className={`console-topbar ${isTwinScene ? "twin-topbar" : ""} ${isCockpitScene ? "cockpit-topbar" : ""}`}>
          <div className="topbar-context">
            <button
              aria-label="打开导航"
              className="icon-button mobile-menu"
              onClick={() => setMenuOpen(true)}
              type="button"
            >
              <Menu size={20} />
            </button>
            <div className="breadcrumb">
              <span>{breadcrumbInfo.center}</span>
              <span aria-hidden="true">/</span>
              <strong>{breadcrumbInfo.item}</strong>
            </div>
          </div>

          <div className="topbar-actions">
            <label className="scope-chip" title={identity.group_id ?? undefined}>
              <span aria-hidden="true" />
              <select
                aria-label="集团或法人范围"
                disabled={sessionBusy}
                value={scopeContext?.scope_level === "group" ? `group:${scopeContext.group_id}` : identity.enterprise_id}
                onChange={(event) => void (event.target.value.startsWith("group:")
                  ? switchScope({ enterprise_id: identity.enterprise_id, scope_level: "group" })
                  : switchEnterprise(event.target.value)).catch(() => undefined)}
              >
                {scopeOptions?.groups?.map((group) => <option key={group.key} value={`group:${group.key}`}>{group.label}</option>)}
                {(scopeOptions?.enterprises ?? [{ key: identity.enterprise_id, label: identity.enterprise_name, scope_type: "enterprise" }]).map((enterprise) => (
                  <option key={enterprise.key} value={enterprise.key}>{enterprise.label}</option>
                ))}
              </select>
            </label>
            <label className="scope-chip"><select aria-label="业务单元范围" disabled={sessionBusy}
              value={scopeContext?.business_unit_ids.length === 1 ? scopeContext.business_unit_ids[0] : ""}
              onChange={(event) => {
                const unit = scopeOptions?.business_units.find((item) => item.key === event.target.value);
                const selection = unit
                  ? businessUnitSelection(unit, identity.enterprise_id)
                  : { enterprise_id: identity.enterprise_id, scope_level: "enterprise" as const };
                void switchScope(selection).catch(() => undefined);
              }}>
              <option value="">全部业务单元</option>
              {scopeOptions?.business_units.filter((unit) => !unit.enterprise_id || scopeContext?.selected_enterprise_ids.includes(unit.enterprise_id)).map((unit) => <option key={unit.key} value={unit.key}>{unit.label}</option>)}
            </select></label>
            <label className="scope-chip"><select aria-label="店铺范围" disabled={sessionBusy}
              value={scopeContext?.scope_level === "store" && scopeContext.store_ids.length === 1 ? scopeContext.store_ids[0] : ""}
              onChange={(event) => {
                if (!scopeContext) return;
                const store = scopeOptions?.stores.find((item) => item.key === event.target.value);
                void switchScope(store
                  ? entityScopeSelection("store", store, scopeContext, identity.enterprise_id)
                  : parentScopeSelection(scopeContext)).catch(() => undefined);
              }}>
              <option value="">全部店铺</option>
              {scopeOptions?.stores.filter((store) => scopeOptionVisible(store, scopeContext)).map((store) => <option key={store.key} value={store.key}>{store.label}</option>)}
            </select></label>
            <label className="scope-chip"><select aria-label="仓库范围" disabled={sessionBusy}
              value={scopeContext?.scope_level === "warehouse" && scopeContext.warehouse_ids.length === 1 ? scopeContext.warehouse_ids[0] : ""}
              onChange={(event) => {
                if (!scopeContext) return;
                const warehouse = scopeOptions?.warehouses.find((item) => item.key === event.target.value);
                void switchScope(warehouse
                  ? entityScopeSelection("warehouse", warehouse, scopeContext, identity.enterprise_id)
                  : parentScopeSelection(scopeContext)).catch(() => undefined);
              }}>
              <option value="">全部仓库</option>
              {scopeOptions?.warehouses.filter((warehouse) => scopeOptionVisible(warehouse, scopeContext)).map((warehouse) => <option key={warehouse.key} value={warehouse.key}>{warehouse.label}</option>)}
            </select></label>
            {sessionActive ? (
              <>
                <div className="session-chip" title="当前请求使用服务端登录会话">
                  <span aria-hidden="true" />
                  已登录
                </div>
                <button
                  aria-label="退出会话"
                  className="icon-button"
                  disabled={sessionBusy}
                  onClick={() => void endSession()}
                  title="退出会话"
                  type="button"
                >
                  <LogOut size={17} />
                </button>
              </>
            ) : null}
            <button
              aria-label={isFullscreen ? "退出全屏" : "全屏模式"}
              className="icon-button"
              onClick={toggleFullscreen}
              title={isFullscreen ? "退出全屏" : "全屏模式"}
              type="button"
            >
              {isFullscreen ? <Minimize2 size={17} /> : <Maximize2 size={17} />}
            </button>
            <button
              aria-label="全局搜索"
              className="icon-button"
              onClick={() => setSearchOpen((open) => !open)}
              title="全局搜索"
              type="button"
            >
              <Search size={18} />
            </button>
            {(!identity || can("role-twin.invoke")) ? (
              <Link className="icon-button" href="/console/assistant" title="企业助手">
                <Sparkles size={18} />
              </Link>
            ) : null}
            <Link className="icon-button notification-button" href="/console/inbox" title="待办与通知">
              <Bell size={18} />
            </Link>
            <div className="identity-chip">
              <span className="avatar">{identity.actor.display_name.slice(0, 1)}</span>
              <span className="role-copy">
                <strong>{identity.actor.display_name.split(" / ")[0]}</strong>
                <small>{identity.actor.position} · {identity.actor.organization}</small>
              </span>
            </div>
          </div>
        </header>

        <TagsView />

        {searchOpen ? (
          <GlobalSearch
            items={centerCatalog?.groups.length
              ? centerCatalog.groups.flatMap((group) => group.items.map((item) => ({
                href: item.href,
                label: item.label,
                meta: group.label
              })))
              : visibleNavigation.flatMap((navigationSection) => navigationSection.items.map((item) => ({
                href: item.href,
                label: item.label,
                meta: navigationSection.shortLabel
              })))}
            onClose={() => setSearchOpen(false)}
          />
        ) : null}

        <main key={scopeContext?.scope_version ?? identity.enterprise_id} className={`console-main ${isTwinScene ? "twin-main" : ""} ${isCockpitScene ? "cockpit-main" : ""} ${isDataWorkspace ? "data-workspace-main" : ""} ${isAnalysisWorkspace ? "analysis-workspace-main" : ""} ${isCustomerServiceWorkspace ? "customer-service-main" : ""}`}>{children}</main>
      </div>

    </div>
  );
}


function GlobalSearch({ items, onClose }: { items: Array<{ label: string; meta: string; href: string }>; onClose: () => void }) {
  const [query, setQuery] = useState("");
  const normalizedQuery = query.trim().toLocaleLowerCase("zh-CN");
  const results = normalizedQuery
    ? items.filter((item) => `${item.label} ${item.meta}`.toLocaleLowerCase("zh-CN").includes(normalizedQuery)).slice(0, 8)
    : items.slice(0, 8);
  return (
    <div className="search-popover" role="dialog" aria-label="全局搜索">
      <div className="search-input-row">
        <Search aria-hidden="true" size={18} />
        <input autoFocus aria-label="搜索菜单" onChange={(event) => setQuery(event.target.value)} placeholder="搜索菜单" value={query} />
        <button aria-label="关闭搜索" className="icon-button" onClick={onClose} type="button">
          <X size={17} />
        </button>
      </div>
      <div className="search-results">
        {results.length ? results.map((result) => (
          <Link href={result.href} key={result.href}>
            <div>
              <strong>{result.label}</strong>
              <span>{result.meta}</span>
            </div>
            <span>打开</span>
          </Link>
        )) : <span>没有匹配的菜单</span>}
      </div>
    </div>
  );
}
