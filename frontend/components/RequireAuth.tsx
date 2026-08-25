"use client";
import { useEffect } from "react";
import { usePathname, useRouter } from "next/navigation";
import { useRole } from "@/components/RoleProvider";
import type { Role } from "@/lib/api";
import { landingFor } from "@/lib/nav";

/** Client-side gate.
 *
 *  This is convenience, not security: the API enforces role and tenant on
 *  every request, and a hand-crafted fetch from a student's browser gets a 403
 *  whatever this component does. What it buys is not showing somebody a
 *  console they cannot use.
 */
export function RequireAuth({ roles, children }: { roles?: Role[]; children: React.ReactNode }) {
  const { user, loading } = useRole();
  const router = useRouter();
  const pathname = usePathname();

  useEffect(() => {
    if (loading) return;
    if (!user) {
      router.replace(`/login?next=${encodeURIComponent(pathname)}`);
      return;
    }
    if (roles && !roles.includes(user.role)) {
      router.replace(landingFor(user.role));
    }
  }, [loading, user, roles, router, pathname]);

  if (loading) {
    return (
      <div className="p-8 text-xs text-muted animate-fade-in">Loading your session…</div>
    );
  }
  if (!user) return null;
  if (roles && !roles.includes(user.role)) return null;
  return <>{children}</>;
}
