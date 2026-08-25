"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";
import {
  LogOut, Menu, PanelLeftClose, PanelLeftOpen, X,
} from "lucide-react";
import { BrandLockup, BrandMark, TenantLockup } from "@/components/brand/BrandMark";
import { PoweredByFloat } from "@/components/brand/PoweredBy";
import { useRole } from "@/components/RoleProvider";
import { ThemePicker } from "@/components/shell/ThemePicker";
import { useRailCollapsed } from "@/components/shell/useRailCollapsed";
import { WordField } from "@/components/shell/WordField";
import { Avatar } from "@/components/ui";
import { assetUrl } from "@/lib/api";
import { navFor } from "@/lib/nav";
import { ROLE_LABEL } from "@/lib/roles";

export function AppShell({ children }: { children: React.ReactNode }) {
  const { user, signOut } = useRole();
  const pathname = usePathname();
  const [mobileOpen, setMobileOpen] = useState(false);
  const [collapsed, toggleRail] = useRailCollapsed();
  const sections = navFor(user?.role);

  // Branding comes off the session so it is present on first paint. A tenant
  // with none leaves these null and the product mark is used instead.
  const brand = {
    logoUrl: assetUrl(user?.tenant_logo_url),
    displayName: user?.tenant_display_name,
    tenantName: user?.tenant_name,
  };

  return (
    <div className="min-h-screen flex">
      <div className="bgfx" />
      <WordField />

      {/* Rail — hidden on small screens, where the same nav appears as a sheet. */}
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

      {mobileOpen && (
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

      <div className="flex-1 min-w-0 flex flex-col">
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
            {user?.tenant_name && (
              <div className="text-xs font-semibold truncate">{user.tenant_name}</div>
            )}
            {user?.scope === "platform" && (
              <div className="text-xs font-semibold">Platform console</div>
            )}
          </div>

          <ThemePicker />

          {user && (
            <div className="flex items-center gap-2 pl-2 border-l border-border">
              <Avatar name={user.full_name} size={26} />
              <div className="hidden sm:block leading-tight">
                <div className="text-xs font-semibold truncate max-w-[12rem]">{user.full_name}</div>
                <div className="text-[10px] text-muted">{ROLE_LABEL[user.role] ?? user.role}</div>
              </div>
              <button onClick={signOut} className="btn btn-icon btn-ghost ds-focus" title="Sign out">
                <LogOut size={15} />
              </button>
            </div>
          )}
        </header>

        <main className="flex-1 p-4 md:p-6 max-w-[1400px] w-full animate-fade-up">
          {children}
        </main>
      </div>

      <PoweredByFloat />
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
          <TenantLockup
            logoUrl={brand?.logoUrl}
            displayName={brand?.displayName}
            fallbackName={brand?.tenantName}
          />
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

    </>
  );
}
