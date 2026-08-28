"use client";
import { useEffect, useState } from "react";
import { Bell, Check, Clock, AlertTriangle, Trophy, FileText, X, CheckCircle } from "lucide-react";

export interface Notification {
  id: string;
  type: "exam_result" | "reminder" | "achievement" | "warning" | "info";
  title: string;
  message: string;
  timestamp: string;
  read: boolean;
  actionUrl?: string;
}

/**
 * Notifications sidebar — slides in from the right.
 * Shows exam results, practice reminders, achievements, and warnings.
 * Students can mark individual notifications as read or clear all.
 */
export function NotificationsSidebar({
  open,
  onClose,
  notifications,
  onMarkRead,
  onClearAll,
}: {
  open: boolean;
  onClose: () => void;
  notifications: Notification[];
  onMarkRead: (id: string) => void;
  onClearAll: () => void;
}) {
  const unread = notifications.filter((n) => !n.read).length;

  if (!open) return null;

  const typeIcon = (type: Notification["type"]) => {
    switch (type) {
      case "exam_result": return <FileText size={14} style={{ color: "var(--primary)" }} />;
      case "reminder": return <Clock size={14} style={{ color: "var(--rag-amber)" }} />;
      case "achievement": return <Trophy size={14} style={{ color: "var(--rag-green)" }} />;
      case "warning": return <AlertTriangle size={14} style={{ color: "var(--rag-red)" }} />;
      default: return <Bell size={14} style={{ color: "var(--muted)" }} />;
    }
  };

  const typeBg = (type: Notification["type"]) => {
    switch (type) {
      case "exam_result": return "color-mix(in srgb, var(--primary) 8%, transparent)";
      case "reminder": return "color-mix(in srgb, var(--rag-amber) 8%, transparent)";
      case "achievement": return "color-mix(in srgb, var(--rag-green) 8%, transparent)";
      case "warning": return "color-mix(in srgb, var(--rag-red) 8%, transparent)";
      default: return "var(--surface)";
    }
  };

  const timeAgo = (ts: string) => {
    const diff = Date.now() - new Date(ts).getTime();
    const mins = Math.floor(diff / 60000);
    if (mins < 1) return "just now";
    if (mins < 60) return `${mins}m ago`;
    const hrs = Math.floor(mins / 60);
    if (hrs < 24) return `${hrs}h ago`;
    return `${Math.floor(hrs / 24)}d ago`;
  };

  return (
    <>
      {/* Backdrop */}
      <div
        className="fixed inset-0 z-[80]"
        style={{ background: "rgba(0,0,0,0.3)" }}
        onClick={onClose}
      />

      {/* Sidebar */}
      <div
        className="fixed top-0 right-0 bottom-0 z-[90] flex flex-col"
        style={{
          width: 380,
          maxWidth: "90vw",
          background: "var(--surface)",
          borderLeft: "1px solid var(--border)",
          boxShadow: "-8px 0 30px rgba(0,0,0,0.15)",
        }}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-4 py-3" style={{ borderBottom: "1px solid var(--border)" }}>
          <div className="flex items-center gap-2">
            <Bell size={16} style={{ color: "var(--primary)" }} />
            <span className="text-sm font-bold">Notifications</span>
            {unread > 0 && (
              <span className="text-[10px] font-bold px-1.5 py-0.5 rounded-full" style={{ background: "var(--primary)", color: "white" }}>
                {unread}
              </span>
            )}
          </div>
          <div className="flex items-center gap-2">
            {unread > 0 && (
              <button
                onClick={onClearAll}
                className="text-[10px] text-muted hover:text-text"
              >
                Mark all read
              </button>
            )}
            <button onClick={onClose} className="p-1 rounded hover:bg-black/5">
              <X size={16} className="text-muted" />
            </button>
          </div>
        </div>

        {/* Notifications list */}
        <div className="flex-1 overflow-y-auto">
          {notifications.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-full text-center px-6">
              <Bell size={32} className="text-muted mb-3" style={{ opacity: 0.4 }} />
              <p className="text-xs text-muted">No notifications yet</p>
              <p className="text-[10px] text-muted mt-1">Exam results and reminders will appear here</p>
            </div>
          ) : (
            <div className="divide-y" style={{ borderColor: "var(--border)" }}>
              {notifications.map((n) => (
                <button
                  key={n.id}
                  className="w-full text-left px-4 py-3 flex gap-3 transition-colors"
                  style={{
                    background: n.read ? "transparent" : typeBg(n.type),
                  }}
                  onClick={() => {
                    onMarkRead(n.id);
                    if (n.actionUrl) window.open(n.actionUrl, "_blank");
                  }}
                >
                  {/* Icon */}
                  <div
                    className="w-8 h-8 rounded-full flex items-center justify-center shrink-0 mt-0.5"
                    style={{ background: typeBg(n.type) }}
                  >
                    {typeIcon(n.type)}
                  </div>

                  {/* Content */}
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <span className="text-xs font-semibold truncate">{n.title}</span>
                      {!n.read && (
                        <span className="w-2 h-2 rounded-full shrink-0" style={{ background: "var(--primary)" }} />
                      )}
                    </div>
                    <p className="text-[11px] text-muted leading-relaxed mt-0.5 line-clamp-2">{n.message}</p>
                    <span className="text-[9px] text-muted mt-1 block">{timeAgo(n.timestamp)}</span>
                  </div>

                  {/* Read indicator */}
                  {n.read && (
                    <CheckCircle size={12} className="shrink-0 mt-1" style={{ color: "var(--rag-green)", opacity: 0.5 }} />
                  )}
                </button>
              ))}
            </div>
          )}
        </div>
      </div>
    </>
  );
}

/**
 * Bell button with unread count badge — place in the header.
 */
export function NotificationBell({
  unread,
  onClick,
}: {
  unread: number;
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      className="relative p-2 rounded-lg transition-colors"
      style={{ background: "var(--surface)" }}
      title="Notifications"
    >
      <Bell size={16} style={{ color: "var(--text)" }} />
      {unread > 0 && (
        <span
          className="absolute -top-1 -right-1 w-4 h-4 rounded-full flex items-center justify-center text-[8px] font-bold"
          style={{ background: "var(--rag-red)", color: "white" }}
        >
          {unread > 9 ? "9+" : unread}
        </span>
      )}
    </button>
  );
}
