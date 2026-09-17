"use client";

import {
  ChevronLeft,
  ChevronRight,
  MoreHorizontal,
  RotateCw,
  X
} from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";

export interface TagItem {
  key: string;
  title: string;
  path: string;
  fixed?: boolean;
}

const DEFAULT_TAGS: TagItem[] = [
  { key: "cockpit", title: "经营驾驶舱", path: "/console/cockpit", fixed: true }
];

const PATH_TITLE_MAP: Record<string, string> = {
  "/console": "数字孪生",
  "/console/spatial": "3D空间孪生",
  "/console/cockpit": "经营驾驶舱",
  "/console/analysis/briefs": "经营简报",
  "/console/commerce/stores": "领星北美店铺",
  "/console/reconciliation": "铁皮柜对账",
  "/console/data/products/commerce": "订单经营事实",
  "/console/data/products/customers": "客户360",
  "/console/customer-service/conversations": "智能客服",
  "/console/customer-service/drafts": "回复草稿",
  "/console/assistant": "高管分身会议",
  "/console/twins/instances": "分身管理",
  "/console/twins/memories": "记忆审核",
  "/console/twins/evaluations": "回归评测",
  "/console/twins/test": "分身测试",
  "/console/actions/work": "决策行动台账",
  "/console/actions/proposals": "行动提议",
  "/console/actions/approvals": "审批队列",
  "/console/knowledge/documents": "知识白皮书",
  "/console/knowledge/policies": "制度规则",
  "/console/knowledge/evidence": "事实证据链",
  "/console/admin/users": "组织与账号",
  "/console/admin/ai-runtime": "AI运行控制",
  "/console/admin/tools": "外部工具与连接",
  "/console/settings": "系统运维配置",
  "/console/admin/audit": "审计日志",
  "/console/inbox": "待办通知",
  "/console/workspaces": "岗位工作台"
};

function getTitleForPath(path: string): string {
  if (PATH_TITLE_MAP[path]) return PATH_TITLE_MAP[path];
  for (const [key, title] of Object.entries(PATH_TITLE_MAP)) {
    if (path.startsWith(key)) return title;
  }
  return path.replace("/console/", "").split("/")[0] || "页面";
}

export function TagsView() {
  const pathname = usePathname();
  const router = useRouter();
  const scrollRef = useRef<HTMLDivElement>(null);
  const [tags, setTags] = useState<TagItem[]>(() => {
    if (typeof window === "undefined") return DEFAULT_TAGS;
    try {
      const saved = sessionStorage.getItem("zhixing_tags_view");
      if (saved) {
        const parsed = JSON.parse(saved);
        if (Array.isArray(parsed) && parsed.length > 0) return parsed;
      }
    } catch {
      // ignore
    }
    return DEFAULT_TAGS;
  });
  const [menuOpen, setMenuOpen] = useState(false);

  // Sync current pathname into tags
  useEffect(() => {
    if (!pathname || pathname === "/" || pathname === "/login") return;

    setTags((prev) => {
      const normalizedPath = pathname === "/console" ? "/console/cockpit" : pathname;
      const exists = prev.some((t) => t.path === normalizedPath);
      if (exists) return prev;

      const title = getTitleForPath(normalizedPath);
      const newTag: TagItem = {
        key: normalizedPath,
        title,
        path: normalizedPath,
        fixed: normalizedPath === "/console/cockpit"
      };
      const updated = [...prev, newTag];
      try {
        sessionStorage.setItem("zhixing_tags_view", JSON.stringify(updated));
      } catch {
        // ignore
      }
      return updated;
    });
  }, [pathname]);

  const activePath = pathname === "/console" ? "/console/cockpit" : pathname;

  const closeTag = (e: React.MouseEvent, tagToClose: TagItem) => {
    e.preventDefault();
    e.stopPropagation();
    if (tagToClose.fixed) return;

    const remaining = tags.filter((t) => t.path !== tagToClose.path);
    setTags(remaining);
    try {
      sessionStorage.setItem("zhixing_tags_view", JSON.stringify(remaining));
    } catch {
      // ignore
    }

    // If closing current active tag, navigate to the adjacent one
    if (tagToClose.path === activePath) {
      const index = tags.findIndex((t) => t.path === tagToClose.path);
      const nextTarget = remaining[index - 1] || remaining[0] || DEFAULT_TAGS[0];
      router.push(nextTarget.path);
    }
  };

  const closeOthers = () => {
    const kept = tags.filter((t) => t.fixed || t.path === activePath);
    setTags(kept);
    try {
      sessionStorage.setItem("zhixing_tags_view", JSON.stringify(kept));
    } catch {
      // ignore
    }
    setMenuOpen(false);
  };

  const closeAll = () => {
    const fixedOnly = tags.filter((t) => t.fixed);
    const result = fixedOnly.length > 0 ? fixedOnly : DEFAULT_TAGS;
    setTags(result);
    try {
      sessionStorage.setItem("zhixing_tags_view", JSON.stringify(result));
    } catch {
      // ignore
    }
    router.push(result[0].path);
    setMenuOpen(false);
  };

  const refreshCurrent = () => {
    router.refresh();
    setMenuOpen(false);
  };

  const scrollLeft = () => {
    if (scrollRef.current) scrollRef.current.scrollBy({ left: -160, behavior: "smooth" });
  };

  const scrollRight = () => {
    if (scrollRef.current) scrollRef.current.scrollBy({ left: 160, behavior: "smooth" });
  };

  return (
    <div className="tags-view-container">
      <button
        aria-label="向前滚动标签"
        className="tags-nav-btn"
        onClick={scrollLeft}
        type="button"
      >
        <ChevronLeft size={14} />
      </button>

      <div className="tags-view-scroll" ref={scrollRef}>
        {tags.map((tag) => {
          const isActive = tag.path === activePath;
          return (
            <Link
              className={`tag-item ${isActive ? "active" : ""}`}
              href={tag.path}
              key={tag.key}
            >
              {isActive && <span className="tag-dot" />}
              <span className="tag-title">{tag.title}</span>
              {!tag.fixed && (
                <button
                  aria-label={`关闭 ${tag.title}`}
                  className="tag-close-btn"
                  onClick={(e) => closeTag(e, tag)}
                  type="button"
                >
                  <X size={12} />
                </button>
              )}
            </Link>
          );
        })}
      </div>

      <button
        aria-label="向后滚动标签"
        className="tags-nav-btn"
        onClick={scrollRight}
        type="button"
      >
        <ChevronRight size={14} />
      </button>

      <div className="tags-actions-wrapper">
        <button
          aria-label="标签操作菜单"
          className="tags-actions-trigger"
          onClick={() => setMenuOpen((prev) => !prev)}
          type="button"
        >
          <MoreHorizontal size={15} />
        </button>

        {menuOpen && (
          <div className="tags-dropdown-menu">
            <button className="dropdown-item" onClick={refreshCurrent} type="button">
              <RotateCw size={13} />
              <span>刷新当前页</span>
            </button>
            <button className="dropdown-item" onClick={closeOthers} type="button">
              <X size={13} />
              <span>关闭其他标签</span>
            </button>
            <button className="dropdown-item" onClick={closeAll} type="button">
              <X size={13} />
              <span>关闭全部标签</span>
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
