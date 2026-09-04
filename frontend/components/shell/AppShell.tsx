"use client";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import {
  Bell, LogOut, Mail, Menu, PanelLeftClose, PanelLeftOpen, ShieldCheck, Trophy, X,
  FileText, Clock, AlertTriangle, CheckCircle2,
} from "lucide-react";
import { BrandMark, TenantLockup } from "@/components/brand/BrandMark";
import { useRole } from "@/components/RoleProvider";
import { ThemePicker } from "@/components/shell/ThemePicker";
import { useRailCollapsed } from "@/components/shell/useRailCollapsed";
import { WordField } from "@/components/shell/WordField";
import { Avatar } from "@/components/ui";
import { api, assetUrl, type SessionUser } from "@/lib/api";
import { navFor } from "@/lib/nav";
import { ROLE_LABEL } from "@/lib/roles";

export function AppShell({ children }: { children: React.ReactNode }) {
  const { user, signOut } = useRole();
  const pathname = usePathname();
  const [mobileOpen, setMobileOpen] = useState(false);
  const [collapsed, toggleRail] = useRailCollapsed();
  const sections = navFor(user?.role, user?.tenant_slug);

  // Branding comes off the session so it is present on first paint. A tenant
  // with none leaves these null and the product mark is used instead.
  const brand = {
    logoUrl: assetUrl(user?.tenant_logo_url),
    displayName: user?.tenant_display_name,
    tenantName: user?.tenant_name,
  };

  // Hide rail during practice/exam sessions — the ExamSidebar takes over fullscreen
  // Use negative lookahead to NOT match /writing-reviews, /reading-foo etc.
  const isExamRoute = /^\/(writing(?!-)|reading(?!-)|listening(?!-)|quiz(?!-)|attempt\/)/.test(pathname);

  return (
    <div className="min-h-screen flex">
      <div className="bgfx" />
      <WordField />

      {/* Rail — hidden during exam routes and on small screens */}
      {!isExamRoute && (
      <aside
        id="app-rail"
        className={`app-shell-nav hidden md:flex shrink-0 flex-col ${
          collapsed ? "is-collapsed" : ""
        }`}
        style={{ background: "var(--rail)", borderRight: "1px solid var(--rail-line)" }}
      >
        <RailContent sections={sections} pathname={pathname} brand={brand}
                     collapsed={collapsed} />
      </aside>
      )}

      {!isExamRoute && mobileOpen && (
        <div className="fixed inset-0 z-40 md:hidden" onClick={() => setMobileOpen(false)}>
          <div className="absolute inset-0 bg-black/50" />
          <aside
            className="rail-sheet absolute left-0 top-0 bottom-0 w-64 flex flex-col animate-slide-in-r"
            style={{ background: "var(--rail)" }}
            onClick={(e) => e.stopPropagation()}
          >
            <RailContent sections={sections} pathname={pathname} brand={brand}
                         collapsed={false}
                         onNavigate={() => setMobileOpen(false)} />
          </aside>
        </div>
      )}

      <div className={`flex-1 min-w-0 flex flex-col ${isExamRoute ? "" : ""}`}>
        {!isExamRoute && (
        <header className="app-header flex items-center gap-3 px-4 h-14 border-b border-border bg-surface">
          <button
            className="btn btn-icon btn-ghost md:hidden ds-focus"
            onClick={() => setMobileOpen(true)}
            aria-label="Open navigation"
          >
            <Menu size={16} />
          </button>

          {/* Desktop only: on a phone the rail is a sheet, and collapsing a
              sheet means nothing. */}
          <button
            className="btn btn-icon btn-ghost hidden md:inline-flex ds-focus"
            onClick={toggleRail}
            aria-expanded={!collapsed}
            aria-controls="app-rail"
            aria-label={collapsed ? "Expand menu" : "Collapse menu"}
            title={collapsed ? "Expand menu (Ctrl+B)" : "Collapse menu (Ctrl+B)"}
          >
            {collapsed ? <PanelLeftOpen size={16} /> : <PanelLeftClose size={16} />}
          </button>

          <div className="md:hidden"><BrandMark size={24} /></div>

          <div className="flex-1 min-w-0">
            {user?.tenant_display_name && (
              <div className="text-xs font-semibold truncate">{user.tenant_display_name}</div>
            )}
            {user?.tenant_name && user?.tenant_display_name !== user?.tenant_name && (
              <div className="text-[10px] text-muted truncate">{user.tenant_name}</div>
            )}
            {user?.scope === "platform" && (
              <div className="text-xs font-semibold">Platform console</div>
            )}
          </div>

          <ThemePicker />

          <NotificationBell user={user} />

          {user && <ProfileMenu user={user} onSignOut={signOut} />}
        </header>
        )}

        <main className={`flex-1 ${isExamRoute ? "p-0" : "p-4 md:p-6"} max-w-[1400px] w-full ${isExamRoute ? "" : "animate-fade-up"}`}>
          {children}
        </main>

        {!isExamRoute && (
        <footer className="border-t border-border bg-surface/50 px-4 py-3 flex items-center justify-between text-[11px] text-muted shrink-0">
          <div className="flex items-center gap-3">
            <span className="font-semibold text-foreground/70"><Link href="/" className="hover:text-foreground transition-colors">CommunicationIQ</Link></span>
            <span className="text-muted">|</span>
            <Link href="/terms" className="hover:text-foreground transition-colors">Terms</Link>
            <Link href="/privacy" className="hover:text-foreground transition-colors">Privacy</Link>
            <span className="text-muted">|</span>
            <span>&copy; {new Date().getFullYear()} Fluenzee. All rights reserved.</span>
          </div>
        </footer>
        )}
      </div>
    </div>
  );
}

/** Avatar + name in the header, made clickable: opens a small card with the
 *  signed-in account's basic details and sign-out, rather than sign-out
 *  living as its own icon with nothing behind the name it sits next to. */
/** Notification bell fed by the backend /notifications feed (role-aware),
 *  with persisted read state and click-through to the related page. */
interface BellItem {
  key: string;
  type: "exam_result" | "reminder" | "achievement" | "warning" | "info";
  title: string;
  message: string;
  timestamp: string;
  read: boolean;
  action_url?: string;
}

function NotificationBell({ user }: { user: SessionUser | null }) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const [items, setItems] = useState<BellItem[]>([]);

  const load = async (silent = false) => {
    if (!user) return;
    try {
      const data = await api.notificationsFeed();
      setItems((data?.items ?? []).slice(0, 25));
    } catch {
      if (!silent) setItems([]);
    }
  };

  useEffect(() => {
    void load();
    const t = setInterval(() => void load(true), 45_000);
    return () => clearInterval(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user?.id, user?.role, user?.scope]);

  useEffect(() => {
    if (!open) return;
    const close = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, [open]);

  const markRead = async (n: BellItem) => {
    if (!n.read) {
      setItems((prev) => prev.map((x) => x.key === n.key ? { ...x, read: true } : x));
      api.notificationsMarkRead([n.key]).catch(() => {});
    }
    setOpen(false);
    if (n.action_url) router.push(n.action_url);
  };

  const markAllRead = async () => {
    setItems((prev) => prev.map((x) => ({ ...x, read: true })));
    api.notificationsReadAll().catch(() => {});
  };

  const unread = items.filter((n) => !n.read).length;

  const typeIcon = (type: BellItem["type"]) => {
    switch (type) {
      case "exam_result": return <FileText size={13} style={{ color: "var(--primary)" }} />;
      case "reminder": return <Clock size={13} style={{ color: "var(--rag-amber)" }} />;
      case "achievement": return <Trophy size={13} style={{ color: "var(--rag-green)" }} />;
      case "warning": return <AlertTriangle size={13} style={{ color: "var(--rag-red)" }} />;
      default: return <Bell size={13} style={{ color: "var(--muted)" }} />;
    }
  };
  const timeAgo = (ts: string) => {
    if (!ts) return "";
    const diff = Date.now() - new Date(ts).getTime();
    if (Number.isNaN(diff)) return "";
    const mins = Math.floor(diff / 60000);
    if (mins < 1) return "just now";
    if (mins < 60) return `${mins}m ago`;
    const hrs = Math.floor(mins / 60);
    if (hrs < 24) return `${hrs}h ago`;
    return `${Math.floor(hrs / 24)}d ago`;
  };

  return (
    <div className="relative" ref={ref}>
      <button
        onClick={() => setOpen((v) => !v)}
        className="relative btn btn-icon btn-ghost ds-focus"
        title="Notifications"
        aria-label="Notifications"
      >
        <Bell size={16} />
        {unread > 0 && (
          <span className="absolute -top-1 -right-1 min-w-[16px] h-4 flex items-center justify-center rounded-full text-[9px] font-bold text-white px-1"
                style={{ background: "var(--rag-red)" }}>
            {unread > 99 ? "99+" : unread}
          </span>
        )}
      </button>

      {open && (
        <div className="absolute right-0 mt-2 w-96 max-h-[70vh] overflow-y-auto ds-card p-3 z-50 animate-fade-in">
          <div className="flex items-center justify-between mb-2">
            <span className="text-xs font-bold">Notifications</span>
            {unread > 0 && (
              <button onClick={markAllRead} className="text-[10px] text-primary hover:underline ds-focus">Mark all read</button>
            )}
          </div>
          {items.length === 0 ? (
            <p className="text-[11px] text-muted py-2">No notifications yet.</p>
          ) : (
            <div className="space-y-1.5">
              {items.map((n) => (
                <button
                  key={n.key}
                  onClick={() => markRead(n)}
                  className="w-full text-left p-2 rounded-ds text-xs transition-colors hover:bg-surface2"
                  style={{ background: n.read ? "transparent" : "color-mix(in srgb, var(--primary) 5%, transparent)" }}
                >
                  <div className="flex items-center gap-1.5">
                    <span className="shrink-0">{typeIcon(n.type)}</span>
                    {!n.read && <span className="w-1.5 h-1.5 rounded-full shrink-0" style={{ background: "var(--primary)" }} />}
                    <span className="font-semibold capitalize flex-1 truncate">{n.title}</span>
                    {n.read && <CheckCircle2 size={12} className="shrink-0" style={{ color: "var(--rag-green)", opacity: 0.6 }} />}
                  </div>
                  <div className="text-muted mt-0.5 ml-[22px] leading-relaxed">{n.message}</div>
                  {n.timestamp && <div className="text-[10px] text-muted mt-0.5 ml-[22px]">{timeAgo(n.timestamp)}</div>}
                </button>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function ProfileMenu({ user, onSignOut }: { user: SessionUser; onSignOut: () => void }) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const close = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    const esc = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    document.addEventListener("mousedown", close);
    document.addEventListener("keydown", esc);
    return () => {
      document.removeEventListener("mousedown", close);
      document.removeEventListener("keydown", esc);
    };
  }, [open]);

  return (
    <div className="relative pl-2 border-l border-border" ref={ref}>
      <button
        onClick={() => setOpen((v) => !v)}
        className="flex items-center gap-2 ds-focus rounded"
        aria-haspopup="menu"
        aria-expanded={open}
        title="Profile"
      >
        <Avatar name={user.full_name} size={26} src={(user as any).avatar_url} />
        <div className="hidden sm:block leading-tight text-left">
          <div className="text-xs font-semibold truncate max-w-[12rem]">{user.full_name}</div>
          <div className="text-[10px] text-muted">{ROLE_LABEL[user.role] ?? user.role}</div>
        </div>
      </button>

      {open && (
        <div
          role="menu"
          className="absolute right-0 mt-2 w-64 ds-card p-3 z-50 animate-fade-in"
        >
          <div className="flex items-center gap-2.5 pb-3 mb-2 border-b border-border">
            <Avatar name={user.full_name} size={34} src={(user as any).avatar_url} />
            <div className="leading-tight min-w-0">
              <div className="text-sm font-semibold truncate">{user.full_name}</div>
              <div className="text-[11px] text-muted truncate">{ROLE_LABEL[user.role] ?? user.role}</div>
            </div>
          </div>

          <div className="space-y-1.5 mb-3 text-xs">
            <div className="flex items-center gap-2 text-muted">
              <Mail size={13} className="shrink-0" />
              <span className="truncate">{user.email}</span>
            </div>
            {user.tenant_name && (
              <div className="flex items-center gap-2 text-muted">
                <ShieldCheck size={13} className="shrink-0" />
                <span className="truncate">{user.tenant_name}</span>
              </div>
            )}
          </div>

          <button
            role="menuitem"
            onClick={onSignOut}
            className="btn btn-ghost btn-sm w-full justify-start ds-focus"
          >
            <LogOut size={14} />
            Sign out
          </button>
        </div>
      )}
    </div>
  );
}

function RailContent({ sections, pathname, onNavigate, brand, collapsed = false }: {
  sections: ReturnType<typeof navFor>;
  pathname: string;
  onNavigate?: () => void;
  brand?: {
    logoUrl?: string | null;
    displayName?: string | null;
    tenantName?: string | null;
  };
  collapsed?: boolean;
}) {
  return (
    <>
      <div className="rail-head h-14 flex items-center justify-between px-4 shrink-0"
           style={{ borderBottom: "1px solid var(--rail-line)", color: "var(--rail-text)" }}>
        {collapsed ? (
          // Just the mark. It still identifies the tenant, and it still links
          // nowhere — the rail head has never been a link.
          brand?.logoUrl ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img src={brand.logoUrl} alt="" width={26} height={26}
                 className="rounded-ds object-contain"
                 style={{ width: 26, height: 26, background: "rgba(255,255,255,.10)" }}
                 onError={(e) => { e.currentTarget.style.display = "none"; }} />
          ) : <BrandMark />
        ) : (
          <Link href="/" className="hover:opacity-80 transition-opacity">
            <TenantLockup
              logoUrl={brand?.logoUrl}
              displayName={brand?.displayName}
              fallbackName={brand?.tenantName}
            />
          </Link>
        )}
        {onNavigate && (
          <button onClick={onNavigate} className="btn btn-icon ds-focus" aria-label="Close navigation"
                  style={{ color: "var(--rail-muted)" }}>
            <X size={16} />
          </button>
        )}
      </div>

      <nav className="rail-nav flex-1 overflow-y-auto thin-scroll py-3">
        {sections.map((section) => (
          <div key={section.title} className="rail-group mb-4">
            <div className="rail-section-title px-4 pb-1.5 text-[10px] font-bold uppercase tracking-wider"
                 style={{ color: "var(--rail-muted)" }}>
              {section.title}
            </div>
            {section.items.map((item) => {
              const active = pathname === item.href || pathname.startsWith(`${item.href}/`);
              const Icon = item.icon;
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  onClick={onNavigate}
                  // Feeds the CSS tooltip when collapsed. The label also stays
                  // in the DOM below, so a screen reader reads the destination
                  // either way -- an icon-only link that announces nothing is
                  // not a link anybody can use.
                  data-label={item.label}
                  aria-current={active ? "page" : undefined}
                  className={`rail-item flex items-center gap-2.5 px-4 py-2 text-[13px] font-medium ds-focus ${
                    active ? "is-active" : ""
                  }`}
                >
                  {/* The tint is the icon's own, not the row's: a coloured
                      glyph beside neutral text reads as an identifier, while
                      colouring the label too would read as a status. Muted
                      slightly when the row is idle so the rail does not look
                      like a paint chart, full strength on hover and on the
                      page you are actually on. */}
                  <Icon
                    size={15}
                    className="rail-icon shrink-0"
                    style={item.tint ? { color: item.tint } : undefined}
                  />
                  <span className={collapsed ? "sr-only" : "rail-label flex-1 truncate"}>
                    {item.label}
                  </span>
                  {item.milestone && (
                    <span className="rail-badge text-[9px] font-bold px-1.5 py-0.5 rounded"
                          style={{ background: "rgba(255,255,255,.12)", color: "var(--rail-muted)" }}>
                      {item.milestone}
                    </span>
                  )}
                </Link>
              );
            })}
          </div>
        ))}
      </nav>

      <div className="rail-foot shrink-0 px-4 py-3 border-t flex items-center gap-1.5"
           style={{ borderColor: "var(--rail-line)", color: "var(--rail-muted)" }}>
        <span className="text-[9px] font-semibold opacity-70" style={{ color: "var(--rail-muted)" }}>
          Powered by Graymatter Technologies
        </span>
        <span className="text-[9px] opacity-50" style={{ color: "var(--rail-muted)" }}>
          &copy; 2026
        </span>
      </div>

    </>
  );
}
