import type { Role } from "@/lib/api";

export const ROLE_LABEL: Record<Role, string> = {
  student: "Student",
  // Somebody outside the institution, invited to sit one assessment. Not a
  // student: no practice, no history, no account after this.
  candidate: "Candidate",
  trainer: "Trainer",
  tenant_admin: "Institution admin",
  super_admin: "Platform super admin",
  finance: "Finance",
  content: "Content",
  data_ml: "Data / ML",
  support: "Support",
};

export const PLATFORM_ROLES: Role[] = ["super_admin", "finance", "content", "data_ml", "support"];

export const isPlatformRole = (role: Role | undefined): boolean =>
  !!role && PLATFORM_ROLES.includes(role);

/** Readiness bands, defined once on the server (app/readiness.py) and labelled
 *  once here. A student is never "placement ready" on one screen and "needs
 *  training" on another. */
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
