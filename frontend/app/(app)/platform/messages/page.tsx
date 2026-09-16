"use client";
import { useState, useEffect } from "react";
import {
  MessageSquare, Mail, MailOpen, CheckCircle, Send, ChevronDown, ChevronRight,
  Clock,
} from "lucide-react";
import { RequireAuth } from "@/components/RequireAuth";
import { PageHeader } from "@/components/ui";
import { PLATFORM_ROLES } from "@/lib/roles";
import { API_BASE, getToken } from "@/lib/api";
import { useToast } from "@/components/Toast";

export default function MessagesPage() {
  return (
    <RequireAuth roles={PLATFORM_ROLES}>
      <Messages />
    </RequireAuth>
  );
}

function Messages() {
  const { toast } = useToast();
  const [messages, setMessages] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState("");
  const [expanded, setExpanded] = useState<string | null>(null);
  const [replyText, setReplyText] = useState("");
  const [replying, setReplying] = useState(false);

  const loadMessages = async () => {
    setLoading(true);
    try {
      const token = getToken();
      const url = filter ? `${API_BASE}/platform/messages?status=${filter}` : `${API_BASE}/platform/messages`;
      const res = await fetch(url, { headers: token ? { Authorization: `Bearer ${token}` } : {} });
      if (res.ok) setMessages(await res.json());
    } catch {}
    setLoading(false);
  };

  useEffect(() => { loadMessages(); }, [filter]); // eslint-disable-line react-hooks/exhaustive-deps

  const updateStatus = async (id: string, status: string) => {
    const token = getToken();
    await fetch(`${API_BASE}/platform/messages/${id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json", ...(token ? { Authorization: `Bearer ${token}` } : {}) },
      body: JSON.stringify({ status }),
    });
    loadMessages();
  };

  const sendReply = async (id: string) => {
    if (!replyText.trim()) return;
    setReplying(true);
    try {
      const token = getToken();
      const res = await fetch(`${API_BASE}/platform/messages/${id}/reply`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...(token ? { Authorization: `Bearer ${token}` } : {}) },
        body: JSON.stringify({ text: replyText.trim() }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || "Failed to send reply");
      }
      await updateStatus(id, "read");
      setReplyText("");
      toast("success", "Reply sent");
      loadMessages();
    } catch (e: any) {
      toast("error", e.message || "Failed to send reply");
    }
    setReplying(false);
  };

  const openCount = messages.filter((m) => m.status === "open").length;
  const readCount = messages.filter((m) => m.status === "read").length;
  const resolvedCount = messages.filter((m) => m.status === "resolved").length;

  return (
    <>
      <PageHeader title="Messages" sub={`${openCount} open · ${readCount} read · ${resolvedCount} resolved`} />

      <div className="flex gap-2 mb-4">
        {[{ v: "", l: "All" }, { v: "open", l: "Open" }, { v: "read", l: "Read" }, { v: "resolved", l: "Resolved" }].map((f) => (
          <button key={f.v} onClick={() => setFilter(f.v)}
            className="px-3 py-1.5 text-xs rounded-md border"
            style={{
              borderColor: filter === f.v ? "var(--primary)" : "var(--border)",
              background: filter === f.v ? "color-mix(in srgb, var(--primary) 10%, transparent)" : "transparent",
            }}>
            {f.l}
          </button>
        ))}
      </div>

      {loading ? (
        <div className="flex flex-col items-center justify-center py-16 gap-3">
          <div className="w-10 h-10 rounded-full border-[3px] border-[var(--border)] border-t-[var(--primary)] animate-spin" />
          <div className="text-xs text-muted">Loading messages...</div>
        </div>
      ) : messages.length === 0 ? (
        <div className="ds-card p-8 text-center">
          <MessageSquare size={32} className="mx-auto mb-2 text-muted" />
          <div className="text-sm text-muted">No messages</div>
        </div>
      ) : (
        <div className="space-y-2">
          {messages.map((msg) => (
            <div key={msg.id} className="ds-card">
              <button onClick={() => setExpanded(expanded === msg.id ? null : msg.id)}
                className="w-full flex items-center gap-3 p-3 text-left hover:bg-surface2 transition-colors">
                {msg.status === "open" ? (
                  <Mail size={14} style={{ color: "var(--rag-red)" }} />
                ) : msg.status === "read" ? (
                  <MailOpen size={14} style={{ color: "var(--rag-amber)" }} />
                ) : (
                  <CheckCircle size={14} style={{ color: "var(--rag-green)" }} />
                )}
                <div className="flex-1 min-w-0">
                  <div className="text-xs font-semibold truncate">{msg.subject}</div>
                  <div className="text-[10px] text-muted">
                    From: {msg.from_name || msg.from_email} ({msg.from_role || "user"})
                    {msg.from_tenant_id && " · Institution linked"}
                  </div>
                </div>
                <span className={`px-1.5 py-0.5 rounded text-[9px] font-medium ${
                  msg.priority === "urgent" ? "status-pill status-bad" :
                  msg.priority === "high" ? "status-pill status-warn" :
                  "bg-surface2 text-muted"
                }`}>
                  {msg.priority}
                </span>
                <span className="text-[10px] text-muted flex items-center gap-1">
                  <Clock size={10} />
                  {msg.created_at ? new Date(msg.created_at).toLocaleDateString() : "—"}
                </span>
                {expanded === msg.id ? <ChevronDown size={14} className="text-muted" /> : <ChevronRight size={14} className="text-muted" />}
              </button>

              {expanded === msg.id && (
                <div className="px-3 pb-3 space-y-3" style={{ borderTop: "1px solid var(--border)" }}>
                  <div className="p-3 rounded text-xs" style={{ background: "var(--surface-2)" }}>
                    {msg.body}
                  </div>

                  {msg.replies?.length > 0 && (
                    <div className="space-y-2">
                      <div className="text-[10px] font-semibold text-muted">Replies:</div>
                      {msg.replies.map((r: any, i: number) => (
                        <div key={i} className="p-2 rounded text-[11px]" style={{ background: "var(--surface)" }}>
                          <span className="font-semibold">{r.from}</span>
                          <span className="text-muted ml-2">{r.at ? new Date(r.at).toLocaleString() : ""}</span>
                          <div className="mt-1">{r.text}</div>
                        </div>
                      ))}
                    </div>
                  )}

                  <div className="flex items-center gap-2">
                    <input value={replyText} onChange={(e) => setReplyText(e.target.value)}
                      placeholder="Type a reply..."
                      className="flex-1 px-3 py-2 text-xs rounded-md border bg-transparent"
                      style={{ borderColor: "var(--border)" }}
                      onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendReply(msg.id); } }} />
                    <button onClick={() => sendReply(msg.id)} disabled={replying || !replyText.trim()}
                      className="px-3 py-2 text-xs rounded-md text-white flex items-center gap-1 disabled:opacity-50"
                      style={{ background: "var(--brand-grad)" }}>
                      <Send size={11} /> Reply
                    </button>
                  </div>

                  <div className="flex gap-2">
                    {msg.status !== "read" && (
                      <button onClick={() => updateStatus(msg.id, "read")}
                        className="text-[10px] px-2 py-1 rounded border hover:bg-surface2"
                        style={{ borderColor: "var(--border)" }}>
                        Mark as Read
                      </button>
                    )}
                    {msg.status !== "resolved" && (
                      <button onClick={() => updateStatus(msg.id, "resolved")}
                        className="text-[10px] px-2 py-1 rounded border hover:bg-surface2"
                        style={{ borderColor: "var(--border)" }}>
                        Resolve
                      </button>
                    )}
                  </div>
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </>
  );
}
