import {
  Activity, BarChart3, Building2, BookOpen,
  Home, LineChart, Mic, PenLine,
  ScrollText, Settings, ShieldCheck, Star, Target, Trophy, Users,
  CreditCard, Mail, Package, MessageSquare, ClipboardList, Contact,
  CalendarClock,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import type { Role } from "@/lib/api";

export interface NavItem {
  href: string;
  label: string;
  icon: LucideIcon;
  roles: Role[];
  milestone?: string;
  tint?: string;
  generalOnly?: boolean; // visible only for general (non-institution) students
}

export const TINT = {
  sky: "#7dd3fc",
  teal: "#5eead4",
  emerald: "#6ee7b7",
  lime: "#bef264",
  amber: "#fcd34d",
  orange: "#fdba74",
  rose: "#fda4af",
  violet: "#c4b5fd",
  indigo: "#a5b4fc",
  cyan: "#67e8f9",
  slate: "#cbd5e1",
} as const;

export interface NavSection {
  title: string;
  items: NavItem[];
}

const STUDENT: Role[] = ["student"];
const TENANT: Role[] = ["tenant_admin"];
const PLATFORM: Role[] = ["super_admin"];

export const NAV: NavSection[] = [
  {
    title: "Practice",
    items: [
      { href: "/home", label: "Today", icon: Home, roles: STUDENT, tint: TINT.amber },
      { href: "/practise", label: "Practise", icon: Target, roles: STUDENT, tint: TINT.teal },
      { href: "/tests", label: "Take a test", icon: Mic, roles: STUDENT, tint: TINT.violet },
      { href: "/my-progress", label: "My progress", icon: LineChart, roles: STUDENT, tint: TINT.sky },
      { href: "/leaderboard", label: "Leaderboard", icon: Trophy, roles: STUDENT, tint: TINT.emerald },
      { href: "/writing-reviews", label: "Writing reviews", icon: PenLine, roles: STUDENT, tint: TINT.orange },
      { href: "/plans", label: "Plans", icon: CreditCard, roles: STUDENT, tint: TINT.violet, generalOnly: true },
      { href: "/contact", label: "Contact Us", icon: Contact, roles: STUDENT, tint: TINT.sky },
    ],
  },
  {
    title: "Institution",
    items: [
      { href: "/tenant", label: "Overview", icon: Building2, roles: TENANT, tint: TINT.sky },
      { href: "/tenant/users", label: "People", icon: Users, roles: TENANT, tint: TINT.cyan },
      { href: "/tenant/results", label: "Exam results", icon: Trophy, roles: TENANT, tint: TINT.rose },
      { href: "/tenant/reviews", label: "Reviews", icon: Star, roles: TENANT, tint: TINT.amber },
      { href: "/tenant/readiness", label: "Readiness", icon: BarChart3, roles: TENANT, tint: TINT.emerald },
      { href: "/tenant/audit", label: "Activity Log", icon: ShieldCheck, roles: TENANT, tint: TINT.slate },
    ],
  },
  // ── Super Admin: Main ──────────────────────────────────────────────────
  {
    title: "Overview",
    items: [
      { href: "/platform", label: "Dashboard", icon: Activity, roles: PLATFORM, tint: TINT.sky },
    ],
  },
  {
    title: "Institutions",
    items: [
      { href: "/platform/tenants", label: "All Institutions", icon: Building2, roles: PLATFORM, tint: TINT.cyan },
      { href: "/platform/plans", label: "Plans & Pricing", icon: Package, roles: PLATFORM, tint: TINT.violet },
    ],
  },
  {
    title: "Exam",
    items: [
      { href: "/platform/content", label: "Question Bank", icon: BookOpen, roles: PLATFORM, tint: TINT.emerald },
      { href: "/platform/exam-tests", label: "Exam Tests", icon: ClipboardList, roles: PLATFORM, tint: TINT.cyan },
      { href: "/platform/exam-schedules", label: "Exam Schedules", icon: CalendarClock, roles: PLATFORM, tint: TINT.rose },
      { href: "/platform/companies", label: "Companies", icon: Building2, roles: PLATFORM, tint: TINT.indigo },
    ],
  },
  {
    title: "Results & Reviews",
    items: [
      { href: "/platform/results", label: "All Results", icon: Trophy, roles: PLATFORM, tint: TINT.rose },
      { href: "/platform/reviews", label: "Reviews", icon: Star, roles: PLATFORM, tint: TINT.amber },
    ],
  },
  {
    title: "Login & Security",
    items: [
      { href: "/platform/audit", label: "Audit Log", icon: ScrollText, roles: PLATFORM, tint: TINT.slate },
    ],
  },
  {
    title: "Communication",
    items: [
      { href: "/platform/messages", label: "Messages", icon: MessageSquare, roles: PLATFORM, tint: TINT.rose },
      { href: "/platform/smtp", label: "Email / SMTP", icon: Mail, roles: PLATFORM, tint: TINT.orange },
      { href: "/platform/payments", label: "Payments", icon: CreditCard, roles: PLATFORM, tint: TINT.rose },
    ],
  },
  {
    title: "Account",
    items: [
      { href: "/settings", label: "Settings", icon: Settings, roles: [...STUDENT, ...TENANT, ...PLATFORM], tint: TINT.slate },
    ],
  },
];

export function navFor(role: Role | undefined, tenantSlug?: string | null): NavSection[] {
  if (!role) return [];
  const isGeneral = !tenantSlug || tenantSlug === "general";
  return NAV
    .map((section) => ({
      ...section,
      items: section.items.filter((i) =>
        i.roles.includes(role) && (!i.generalOnly || isGeneral)
      ),
    }))
    .filter((section) => section.items.length > 0);
}

export const SITTING_ROLES: Role[] = ["student"];

export function landingFor(role: Role | undefined): string {
  switch (role) {
    case "student": return "/home";
    case "tenant_admin": return "/tenant";
    case "super_admin": return "/platform";
    default: return "/login";
  }
}

export const ShieldIcon = ShieldCheck;
