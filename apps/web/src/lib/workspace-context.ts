import { useEffect, useState } from "react";

import type { WorkspaceKey } from "@/lib/workspace-types";

const STORAGE_KEY = "zhixing.active-workspace";
const CHANGE_EVENT = "zhixing:workspace-changed";
const WORKSPACE_KEYS = new Set<WorkspaceKey>([
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

export function getActiveWorkspaceKey(): WorkspaceKey | null {
  if (typeof window === "undefined") return null;
  const value = window.sessionStorage.getItem(STORAGE_KEY);
  return value && WORKSPACE_KEYS.has(value as WorkspaceKey) ? value as WorkspaceKey : null;
}

export function setActiveWorkspaceKey(key: WorkspaceKey): void {
  if (typeof window === "undefined") return;
  window.sessionStorage.setItem(STORAGE_KEY, key);
  window.dispatchEvent(new Event(CHANGE_EVENT));
}

export function useActiveWorkspaceKey(): WorkspaceKey | null {
  const [workspaceKey, setWorkspaceKey] = useState<WorkspaceKey | null>(null);
  useEffect(() => {
    const sync = () => setWorkspaceKey(getActiveWorkspaceKey());
    sync();
    window.addEventListener(CHANGE_EVENT, sync);
    return () => window.removeEventListener(CHANGE_EVENT, sync);
  }, []);
  return workspaceKey;
}
