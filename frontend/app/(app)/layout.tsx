"use client";
import { AppShell } from "@/components/shell/AppShell";
import { RequireAuth } from "@/components/RequireAuth";

/** Everything inside the shell requires a session.
 *
 *  The test runner deliberately lives outside this group: a simulation with a
 *  nav rail and a sign-out button next to it is not a simulation.
 */
export default function AppLayout({ children }: { children: React.ReactNode }) {
  return (
    <RequireAuth>
      <AppShell>{children}</AppShell>
    </RequireAuth>
  );
}
