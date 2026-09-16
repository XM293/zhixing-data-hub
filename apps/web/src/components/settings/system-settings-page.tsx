"use client";

import {
  Bot,
  Building2,
  Cpu,
  Database,
  FileText,
  Radio,
  RefreshCw,
  Settings2,
  ShieldCheck,
  Sparkles,
  Users
} from "lucide-react";
import { useState } from "react";

import { AIRuntimePage } from "@/components/operations/ai-runtime-page";
import { KnowledgeCenterPage } from "@/components/knowledge/knowledge-center-pages";
import { DataSourcesPage } from "@/components/data-center/data-sources-page";
import { IdentityAdminPage } from "@/components/identity/identity-admin-pages";
import { PageHeader } from "@/components/console/ui";

type SettingsTab = "ai" | "knowledge" | "data" | "org";

export function SystemSettingsPage({ initialTab = "ai" }: { initialTab?: SettingsTab }) {
  const [activeTab, setActiveTab] = useState<SettingsTab>(initialTab);

  return (
    <div className="system-settings-layout">
      <PageHeader
        eyebrow="系统运维管理中心"
        title="统一系统运维与技术底座"
        description="一站式管理 AI 双引擎路由、星云铁皮柜业务白皮书切片、领星 ERP 数据源同步流水以及组织店铺权限。"
        actions={
          <div className="status-indicators" style={{ display: "flex", gap: "0.5rem", alignItems: "center" }}>
            <span className="badge" style={{ display: "inline-flex", alignItems: "center", gap: "0.35rem", padding: "0.35rem 0.65rem", borderRadius: "6px", background: "rgba(16, 185, 129, 0.1)", color: "#10b981", fontSize: "0.82rem", fontWeight: 500 }}>
              <Sparkles size={14} /> AI引擎: Maysu gpt-6-astra (已就绪)
            </span>
            <span className="badge" style={{ display: "inline-flex", alignItems: "center", gap: "0.35rem", padding: "0.35rem 0.65rem", borderRadius: "6px", background: "rgba(59, 130, 246, 0.1)", color: "#3b82f6", fontSize: "0.82rem", fontWeight: 500 }}>
              <Database size={14} /> 领星ERP: OpenAPI v2.0 (实时同步)
            </span>
            <span className="badge" style={{ display: "inline-flex", alignItems: "center", gap: "0.35rem", padding: "0.35rem 0.65rem", borderRadius: "6px", background: "rgba(168, 85, 247, 0.1)", color: "#a855f7", fontSize: "0.82rem", fontWeight: 500 }}>
              <ShieldCheck size={14} /> 对账容差: 0.5% 铁律基准
            </span>
          </div>
        }
      />

      {/* 4-Tab 切换栏 */}
      <div
        className="settings-tabs-bar"
        style={{
          display: "flex",
          gap: "0.75rem",
          borderBottom: "1px solid var(--border-subtle, rgba(255, 255, 255, 0.08))",
          paddingBottom: "0.75rem",
          marginBottom: "1.5rem"
        }}
      >
        <button
          type="button"
          onClick={() => setActiveTab("ai")}
          className={`settings-tab-btn ${activeTab === "ai" ? "active" : ""}`}
          style={{
            display: "inline-flex",
            alignItems: "center",
            gap: "0.5rem",
            padding: "0.6rem 1.2rem",
            borderRadius: "8px",
            border: activeTab === "ai" ? "1px solid #3b82f6" : "1px solid transparent",
            background: activeTab === "ai" ? "rgba(59, 130, 246, 0.12)" : "transparent",
            color: activeTab === "ai" ? "#60a5fa" : "var(--text-secondary, #94a3b8)",
            fontWeight: activeTab === "ai" ? 600 : 400,
            cursor: "pointer",
            transition: "all 0.15s ease"
          }}
        >
          <Cpu size={16} />
          <span>AI 双引擎与模型调度</span>
        </button>

        <button
          type="button"
          onClick={() => setActiveTab("knowledge")}
          className={`settings-tab-btn ${activeTab === "knowledge" ? "active" : ""}`}
          style={{
            display: "inline-flex",
            alignItems: "center",
            gap: "0.5rem",
            padding: "0.6rem 1.2rem",
            borderRadius: "8px",
            border: activeTab === "knowledge" ? "1px solid #3b82f6" : "1px solid transparent",
            background: activeTab === "knowledge" ? "rgba(59, 130, 246, 0.12)" : "transparent",
            color: activeTab === "knowledge" ? "#60a5fa" : "var(--text-secondary, #94a3b8)",
            fontWeight: activeTab === "knowledge" ? 600 : 400,
            cursor: "pointer",
            transition: "all 0.15s ease"
          }}
        >
          <FileText size={16} />
          <span>知识库与业务白皮书</span>
        </button>

        <button
          type="button"
          onClick={() => setActiveTab("data")}
          className={`settings-tab-btn ${activeTab === "data" ? "active" : ""}`}
          style={{
            display: "inline-flex",
            alignItems: "center",
            gap: "0.5rem",
            padding: "0.6rem 1.2rem",
            borderRadius: "8px",
            border: activeTab === "data" ? "1px solid #3b82f6" : "1px solid transparent",
            background: activeTab === "data" ? "rgba(59, 130, 246, 0.12)" : "transparent",
            color: activeTab === "data" ? "#60a5fa" : "var(--text-secondary, #94a3b8)",
            fontWeight: activeTab === "data" ? 600 : 400,
            cursor: "pointer",
            transition: "all 0.15s ease"
          }}
        >
          <Database size={16} />
          <span>数据源与同步调度监控</span>
        </button>

        <button
          type="button"
          onClick={() => setActiveTab("org")}
          className={`settings-tab-btn ${activeTab === "org" ? "active" : ""}`}
          style={{
            display: "inline-flex",
            alignItems: "center",
            gap: "0.5rem",
            padding: "0.6rem 1.2rem",
            borderRadius: "8px",
            border: activeTab === "org" ? "1px solid #3b82f6" : "1px solid transparent",
            background: activeTab === "org" ? "rgba(59, 130, 246, 0.12)" : "transparent",
            color: activeTab === "org" ? "#60a5fa" : "var(--text-secondary, #94a3b8)",
            fontWeight: activeTab === "org" ? 600 : 400,
            cursor: "pointer",
            transition: "all 0.15s ease"
          }}
        >
          <Users size={16} />
          <span>组织架构与店铺权限</span>
        </button>
      </div>

      {/* Tab 内容区 */}
      <div className="settings-tab-content">
        {activeTab === "ai" && <AIRuntimePage />}
        {activeTab === "knowledge" && <KnowledgeCenterPage view="documents" />}
        {activeTab === "data" && <DataSourcesPage />}
        {activeTab === "org" && <IdentityAdminPage view="users" />}
      </div>
    </div>
  );
}
