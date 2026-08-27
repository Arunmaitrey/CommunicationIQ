import type { Role } from "@/lib/api";

export const ROLE_LABEL: Record<Role, string> = {
  student: "Student",
  tenant_admin: "Institution Admin",
  super_admin: "Super Admin",
};

/** Only super_admin, tenant_admin, and student are real roles. */
export const PLATFORM_ROLES: Role[] = ["super_admin"];
export const TENANT_ROLES: Role[] = ["tenant_admin"];
export const STUDENT_ROLES: Role[] = ["student"];

export const isPlatformRole = (role: Role | undefined): boolean =>
  !!role && PLATFORM_ROLES.includes(role);

/** Readiness bands */
export const READINESS: Record<string, { label: string; color: string }> = {
  placement_ready: { label: "Placement ready", color: "var(--rag-green)" },
  needs_training: { label: "Needs training", color: "var(--rag-amber)" },
  high_risk: { label: "High risk", color: "var(--rag-red)" },
  not_started: { label: "Not started", color: "var(--muted)" },
};

export const SKILL_LABEL: Record<string, string> = {
  pronunciation: "Pronunciation",
  fluency: "Fluency",
  grammar: "Grammar",
  vocabulary: "Vocabulary",
  response_latency: "Response speed",
  listening: "Listening",
  content_recall: "Content recall",
};

export const skillLabel = (skill: string) =>
  SKILL_LABEL[skill] ?? skill.replace(/_/g, " ");
