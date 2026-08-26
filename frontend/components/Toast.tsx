"use client";
import { createContext, useCallback, useContext, useRef, useState, type ReactNode } from "react";
import { CheckCircle, AlertCircle, X, Info } from "lucide-react";

type ToastType = "success" | "error" | "warning" | "info";

interface Toast {
  id: string;
  type: ToastType;
  message: string;
}

interface ToastCtx {
  toast: (type: ToastType, message: string) => void;
}

const ToastCtx = createContext<ToastCtx>({ toast: () => {} });

export function useToast() {
  return useContext(ToastCtx);
}

const ICONS: Record<ToastType, typeof CheckCircle> = {
  success: CheckCircle,
  error: AlertCircle,
  warning: AlertCircle,
  info: Info,
};

const COLORS: Record<ToastType, { bg: string; text: string; border: string }> = {
  success: {
    bg: "color-mix(in srgb, var(--rag-green) 12%, var(--surface))",
    text: "var(--rag-green)",
    border: "color-mix(in srgb, var(--rag-green) 30%, var(--border))",
  },
  error: {
    bg: "color-mix(in srgb, var(--rag-red) 12%, var(--surface))",
    text: "var(--rag-red)",
    border: "color-mix(in srgb, var(--rag-red) 30%, var(--border))",
  },
  warning: {
    bg: "color-mix(in srgb, var(--rag-amber) 12%, var(--surface))",
    text: "var(--rag-amber)",
    border: "color-mix(in srgb, var(--rag-amber) 30%, var(--border))",
  },
  info: {
    bg: "color-mix(in srgb, var(--primary) 12%, var(--surface))",
    text: "var(--primary)",
    border: "color-mix(in srgb, var(--primary) 30%, var(--border))",
  },
};

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const counter = useRef(0);

  const toast = useCallback((type: ToastType, message: string) => {
    const id = String(++counter.current);
    setToasts((prev) => [...prev, { id, type, message }]);
    setTimeout(() => {
      setToasts((prev) => prev.filter((t) => t.id !== id));
    }, 4000);
  }, []);

  const dismiss = (id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  };

  return (
    <ToastCtx.Provider value={{ toast }}>
      {children}
      {/* Toast container */}
      <div className="fixed bottom-4 right-4 z-[70] flex flex-col gap-2 max-w-sm">
        {toasts.map((t) => {
          const Icon = ICONS[t.type];
          const colors = COLORS[t.type];
          return (
            <div
              key={t.id}
              className="animate-slide-in-r flex items-start gap-3 px-4 py-3 rounded-lg border shadow-lg"
              style={{
                background: colors.bg,
                borderColor: colors.border,
                color: "var(--text)",
              }}
            >
              <Icon size={16} style={{ color: colors.text }} className="mt-0.5 shrink-0" />
              <span className="text-xs font-medium flex-1">{t.message}</span>
              <button onClick={() => dismiss(t.id)} className="shrink-0 opacity-50 hover:opacity-100">
                <X size={14} />
              </button>
            </div>
          );
        })}
      </div>
    </ToastCtx.Provider>
  );
}
