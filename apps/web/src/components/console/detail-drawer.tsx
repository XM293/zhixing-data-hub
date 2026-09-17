"use client";

import { X } from "lucide-react";
import { useEffect } from "react";

export interface DetailDrawerProps {
  isOpen: boolean;
  onClose: () => void;
  title: string;
  subtitle?: string;
  badge?: {
    label: string;
    tone?: "neutral" | "success" | "warning" | "danger" | "info";
  };
  children: React.ReactNode;
  footer?: React.ReactNode;
  width?: string;
}

export function DetailDrawer({
  isOpen,
  onClose,
  title,
  subtitle,
  badge,
  children,
  footer,
  width = "560px"
}: DetailDrawerProps) {
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape" && isOpen) {
        onClose();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  return (
    <div className="detail-drawer-overlay" onClick={onClose}>
      <aside
        aria-label={title}
        aria-modal="true"
        className="detail-drawer-panel"
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        style={{ width: `min(100vw, ${width})` }}
      >
        <header className="detail-drawer-header">
          <div className="detail-drawer-heading">
            <div className="detail-drawer-title-row">
              <h3>{title}</h3>
              {badge && (
                <span className={`status-badge tone-${badge.tone || "neutral"}`}>
                  {badge.label}
                </span>
              )}
            </div>
            {subtitle && <p className="detail-drawer-subtitle">{subtitle}</p>}
          </div>
          <button
            aria-label="关闭抽屉"
            className="icon-button detail-drawer-close"
            onClick={onClose}
            type="button"
          >
            <X size={18} />
          </button>
        </header>

        <div className="detail-drawer-body">
          {children}
        </div>

        {footer && (
          <footer className="detail-drawer-footer">
            {footer}
          </footer>
        )}
      </aside>
    </div>
  );
}
