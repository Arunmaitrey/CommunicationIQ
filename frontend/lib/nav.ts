import {
  Activity, BarChart3, Building2, BookOpen,
  Home, Layers, LineChart, Mic,
  ScrollText, Settings, ShieldCheck, Target, Trophy, Users,
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
    ],
  },
  {
    title: "Institution",
    items: [
      { href: "/tenant", label: "Overview", icon: Building2, roles: TENANT, tint: TINT.sky },
      { href: "/tenant/users", label: "People", icon: Users, roles: TENANT, tint: TINT.cyan },
      { href: "/tenant/profiles", label: "Assessments", icon: Layers, roles: TENANT, tint: TINT.violet },
      { href: "/tenant/results", label: "Exam results", icon: Trophy, roles: TENANT, tint: TINT.rose },
      { href: "/tenant/readiness", label: "Readiness", icon: BarChart3, roles: TENANT, tint: TINT.emerald },
    ],
  },
  {
    title: "Platform",
    items: [
      { href: "/platform", label: "Overview", icon: Activity, roles: PLATFORM, tint: TINT.sky },
      { href: "/platform/tenants", label: "Institutions", icon: Building2, roles: PLATFORM, tint: TINT.cyan },
      { href: "/platform/content", label: "Question Bank", icon: BookOpen, roles: PLATFORM, tint: TINT.emerald },
      { href: "/platform/results", label: "Exam results", icon: Trophy, roles: PLATFORM, tint: TINT.rose },
      { href: "/platform/audit", label: "Audit log", icon: ScrollText, roles: PLATFORM, tint: TINT.slate },
    ],
  },
  {
    title: "Account",
    items: [
      { href: "/settings", label: "Settings", icon: Settings, roles: [...STUDENT, ...TENANT, ...PLATFORM], tint: TINT.slate },
    ],
  },
];

export function navFor(role: Role | undefined): NavSection[] {
  if (!role) return [];
  return NAV
    .map((section) => ({ ...section, items: section.items.filter((i) => i.roles.includes(role)) }))
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
