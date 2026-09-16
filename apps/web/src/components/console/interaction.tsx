"use client";

import {
  CheckCircle2,
  CircleAlert,
  Info,
  TriangleAlert,
  X
} from "lucide-react";
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useId,
  useMemo,
  useRef,
  useState
} from "react";
import { createPortal } from "react-dom";

export type NotificationTone = "success" | "error" | "warning" | "info";

interface NotificationInput {
  title: string;
  description?: string;
  tone?: NotificationTone;
  duration?: number;
}

interface NotificationItem extends NotificationInput {
  id: string;
  tone: NotificationTone;
}

interface InteractionContextValue {
  notify: (notification: NotificationInput) => string;
  dismiss: (id: string) => void;
}

const InteractionContext = createContext<InteractionContextValue | null>(null);
const overlayStack: symbol[] = [];

export function InteractionProvider({ children }: { children: React.ReactNode }) {
  const [mounted, setMounted] = useState(false);
  const [notifications, setNotifications] = useState<NotificationItem[]>([]);

  useEffect(() => setMounted(true), []);

  const dismiss = useCallback((id: string) => {
    setNotifications((current) => current.filter((item) => item.id !== id));
  }, []);

  const notify = useCallback((notification: NotificationInput) => {
    const id = typeof crypto.randomUUID === "function" ? crypto.randomUUID() : `${Date.now()}-${Math.random()}`;
    setNotifications((current) => [
      ...current,
      { ...notification, id, tone: notification.tone ?? "info" }
    ].slice(-4));
    return id;
  }, []);

  const value = useMemo(() => ({ dismiss, notify }), [dismiss, notify]);

  return (
    <InteractionContext.Provider value={value}>
      {children}
      {mounted ? createPortal(
        <div aria-live="polite" aria-relevant="additions" className="notification-viewport">
          {notifications.map((notification) => (
            <NotificationToast dismiss={dismiss} item={notification} key={notification.id} />
          ))}
        </div>,
        document.body
      ) : null}
    </InteractionContext.Provider>
  );
}

export function useNotifications(): InteractionContextValue {
  const context = useContext(InteractionContext);
  if (!context) throw new Error("useNotifications must be used within InteractionProvider");
  return context;
}

function NotificationToast({ dismiss, item }: { dismiss: (id: string) => void; item: NotificationItem }) {
  useEffect(() => {
    const timer = window.setTimeout(() => dismiss(item.id), item.duration ?? (item.tone === "error" ? 6500 : 3600));
    return () => window.clearTimeout(timer);
  }, [dismiss, item.duration, item.id, item.tone]);

  const Icon = item.tone === "success"
    ? CheckCircle2
    : item.tone === "error"
      ? TriangleAlert
      : item.tone === "warning"
        ? CircleAlert
        : Info;
  return (
    <div className={`notification-toast ${item.tone}`} role={item.tone === "error" ? "alert" : "status"}>
      <Icon aria-hidden="true" size={19} />
      <div>
        <strong>{item.title}</strong>
        {item.description ? <span>{item.description}</span> : null}
      </div>
      <button aria-label="关闭消息" onClick={() => dismiss(item.id)} type="button"><X size={15} /></button>
    </div>
  );
}

type OverlaySize = "small" | "medium" | "large";

interface OverlayProps {
  title: string;
  eyebrow?: string;
  description?: string;
  children: React.ReactNode;
  footer?: React.ReactNode;
  onClose: () => void;
  busy?: boolean;
  size?: OverlaySize;
  className?: string;
  initialFocusRef?: React.RefObject<HTMLElement | null>;
}

export function Dialog(props: OverlayProps) {
  return <OverlayShell {...props} variant="dialog" />;
}

export function Drawer(props: OverlayProps) {
  return <OverlayShell {...props} variant="drawer" />;
}

function OverlayShell({
  title,
  eyebrow,
  description,
  children,
  footer,
  onClose,
  busy = false,
  size = "medium",
  className = "",
  initialFocusRef,
  variant
}: OverlayProps & { variant: "dialog" | "drawer" }) {
  const [mounted, setMounted] = useState(false);
  const panelRef = useRef<HTMLElement>(null);
  const overlayIdRef = useRef(Symbol("interaction-overlay"));
  const busyRef = useRef(busy);
  const onCloseRef = useRef(onClose);
  const titleId = useId();
  const descriptionId = useId();
  const visibleEyebrow = eyebrow && /[\u3400-\u9fff]/.test(eyebrow) ? eyebrow : null;

  busyRef.current = busy;
  onCloseRef.current = onClose;

  useEffect(() => setMounted(true), []);

  useEffect(() => {
    if (!mounted) return;
    const previousFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const previousOverflow = document.body.style.overflow;
    const overlayId = overlayIdRef.current;
    overlayStack.push(overlayId);
    document.body.style.overflow = "hidden";
    const panel = panelRef.current;
    const preferred = initialFocusRef?.current ?? panel?.querySelector<HTMLElement>("[autofocus], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), button:not([disabled])");
    window.requestAnimationFrame(() => (preferred ?? panel)?.focus());

    function handleKeyDown(event: KeyboardEvent) {
      if (overlayStack.at(-1) !== overlayId) return;
      if (event.key === "Escape" && !busyRef.current) {
        event.preventDefault();
        onCloseRef.current();
        return;
      }
      if (event.key !== "Tab" || !panel) return;
      const focusable = Array.from(panel.querySelectorAll<HTMLElement>(
        'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'
      )).filter((element) => !element.hasAttribute("hidden"));
      if (!focusable.length) {
        event.preventDefault();
        panel.focus();
        return;
      }
      const first = focusable[0];
      const last = focusable.at(-1);
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last?.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    }

    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("keydown", handleKeyDown);
      const stackIndex = overlayStack.lastIndexOf(overlayId);
      if (stackIndex >= 0) overlayStack.splice(stackIndex, 1);
      document.body.style.overflow = previousOverflow;
      previousFocus?.focus();
    };
  }, [initialFocusRef, mounted]);

  if (!mounted) return null;
  return createPortal(
    <div
      className={`interaction-backdrop ${variant}`}
      onMouseDown={(event) => {
        if (event.currentTarget === event.target && !busy) onClose();
      }}
      role="presentation"
    >
      <section
        aria-describedby={description ? descriptionId : undefined}
        aria-labelledby={titleId}
        aria-modal="true"
        className={`interaction-surface interaction-${variant} ${size} ${className}`}
        ref={panelRef}
        role="dialog"
        tabIndex={-1}
      >
        <header className="interaction-header">
          <div>
            {visibleEyebrow ? <span>{visibleEyebrow}</span> : null}
            <h2 id={titleId}>{title}</h2>
            {description ? <p id={descriptionId}>{description}</p> : null}
          </div>
          <button aria-label="关闭" disabled={busy} onClick={onClose} title="关闭" type="button"><X size={18} /></button>
        </header>
        <div className="interaction-body">{children}</div>
        {footer ? <footer className="interaction-footer">{footer}</footer> : null}
      </section>
    </div>,
    document.body
  );
}

export function ConfirmDialog({
  title,
  description,
  detail,
  confirmLabel = "确认",
  cancelLabel = "取消",
  confirmDisabled = false,
  tone = "warning",
  busy = false,
  onCancel,
  onConfirm,
  children
}: {
  title: string;
  description: string;
  detail?: string;
  confirmLabel?: string;
  cancelLabel?: string;
  confirmDisabled?: boolean;
  tone?: "warning" | "danger" | "primary";
  busy?: boolean;
  onCancel: () => void;
  onConfirm: () => void;
  children?: React.ReactNode;
}) {
  const Icon = tone === "danger" ? TriangleAlert : tone === "primary" ? CheckCircle2 : CircleAlert;
  return (
    <Dialog
      busy={busy}
      className={`confirm-dialog ${tone}`}
      footer={<>
        <button className="button secondary" disabled={busy} onClick={onCancel} type="button">{cancelLabel}</button>
        <button className={`button ${tone === "danger" ? "critical" : "primary"}`} disabled={busy || confirmDisabled} onClick={onConfirm} type="button">{confirmLabel}</button>
      </>}
      onClose={onCancel}
      size="small"
      title={title}
    >
      <div className="confirm-dialog-message">
        <Icon aria-hidden="true" size={22} />
        <div><strong>{description}</strong>{detail ? <span>{detail}</span> : null}</div>
      </div>
      {children}
    </Dialog>
  );
}
