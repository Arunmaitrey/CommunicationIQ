"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { UserPlus } from "lucide-react";
import { BrandLockup } from "@/components/brand/BrandMark";
import { HeroMic } from "@/components/brand/HeroMic";
import { PoweredByFloat } from "@/components/brand/PoweredBy";
import { WordField } from "@/components/shell/WordField";
import { ThemePicker } from "@/components/shell/ThemePicker";
import { API_BASE, ApiError } from "@/lib/api";
import { useRole } from "@/components/RoleProvider";
import { useToast } from "@/components/Toast";
import { landingFor } from "@/lib/nav";

export default function SignupPage() {
  const router = useRouter();
  const { signIn } = useRole();
  const { toast } = useToast();
  const [form, setForm] = useState({
    full_name: "",
    email: "",
    password: "",
  });
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const res = await fetch(`${API_BASE}/auth/signup`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          email: form.email,
          password: form.password,
          full_name: form.full_name,
        }),
      });
      if (!res.ok) {
        let detail = res.statusText;
        try {
          const body = await res.json();
          detail = body?.detail ?? detail;
        } catch { /* non-JSON */ }
        throw new ApiError(res.status, detail);
      }
      const { token, user } = await res.json();
      signIn(user, token);
      toast("success", `Welcome, ${user.full_name}!`);
      router.replace(landingFor(user.role));
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Could not reach the server");
      setBusy(false);
    }
  }

  return (
    <div className="min-h-screen flex">
      <div className="bgfx" />
      <WordField />
      <PoweredByFloat />

      {/* Hero panel */}
      <div className="hidden lg:flex flex-1 flex-col justify-between p-10 relative overflow-hidden"
           style={{ background: "var(--rail)", color: "var(--rail-text)" }}>
        <div className="auth-dotgrid absolute inset-0" />
        <div className="relative"><Link href="/" className="hover:opacity-80 transition-opacity"><BrandLockup /></Link></div>

        <div className="relative flex-1 flex items-center justify-center py-6">
          <HeroMic />
        </div>

        <div className="relative max-w-md">
          <h1 className="text-3xl font-bold leading-tight mb-4">
            Create your student account
          </h1>
          <p className="text-sm leading-relaxed" style={{ color: "var(--rail-muted)" }}>
            Join your institution&apos;s placement readiness program. Practise
            speaking, listening, reading and writing with assessments
            that tell you exactly where to improve.
          </p>
        </div>
      </div>

      <div className="flex-1 flex items-center justify-center p-6">
        <div className="w-full max-w-sm">
          <div className="flex items-center justify-between mb-6">
            <div className="lg:hidden"><Link href="/" className="hover:opacity-80 transition-opacity"><BrandLockup /></Link></div>
            <div className="ml-auto"><ThemePicker /></div>
          </div>

          <h2 className="text-lg font-bold mb-1">Sign up</h2>
          <p className="text-xs text-muted mb-5">
            Students register here using your institution email. Admins are
            created by the platform super admin.
          </p>

          <form onSubmit={submit} className="space-y-3">
            <div>
              <label className="ds-label" htmlFor="full_name">Full Name</label>
              <input id="full_name" type="text" required
                     className="ds-input ds-focus" value={form.full_name}
                     onChange={(e) => setForm({ ...form, full_name: e.target.value })}
                     placeholder="Aarav Reddy" />
            </div>
            <div>
              <label className="ds-label" htmlFor="email">Institution Email</label>
              <input id="email" type="email" required autoComplete="username"
                     className="ds-input ds-focus" value={form.email}
                     onChange={(e) => setForm({ ...form, email: e.target.value })}
                     placeholder="aarav.reddy@stmarys.edu" />
            </div>
            <div>
              <label className="ds-label" htmlFor="password">Password</label>
              <input id="password" type="password" required minLength={8}
                     autoComplete="new-password"
                     className="ds-input ds-focus" value={form.password}
                     onChange={(e) => setForm({ ...form, password: e.target.value })}
                     placeholder="At least 8 characters" />
            </div>

            {error && (
              <div className="text-xs font-medium" style={{ color: "var(--rag-red)" }}>{error}</div>
            )}

            <button type="submit" disabled={busy} className="btn btn-primary w-full ds-focus">
              <UserPlus size={15} />
              {busy ? "Creating account…" : "Create account"}
            </button>
          </form>

          <p className="text-xs text-muted mt-4 text-center">
            Already have an account?{" "}
            <Link href="/login" className="underline ds-focus">Sign in</Link>
          </p>
        </div>
      </div>
    </div>
  );
}
