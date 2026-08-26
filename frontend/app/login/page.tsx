"use client";
import { Suspense, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { LogIn } from "lucide-react";
import { BrandLockup } from "@/components/brand/BrandMark";
import { HeroMic } from "@/components/brand/HeroMic";
import { PoweredByFloat } from "@/components/brand/PoweredBy";
import { WordField } from "@/components/shell/WordField";
import { useRole } from "@/components/RoleProvider";
import { ThemePicker } from "@/components/shell/ThemePicker";
import { api, ApiError } from "@/lib/api";
import { landingFor } from "@/lib/nav";
import { useToast } from "@/components/Toast";

function LoginForm() {
  const router = useRouter();
  const params = useSearchParams();
  const { signIn } = useRole();
  const { toast } = useToast();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const expired = params.get("expired") === "1";
  const next = params.get("next");

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const { token, user } = await api.login(email.trim(), password);
      signIn(user, token);
      toast("success", `Welcome back, ${user.full_name}!`);
      router.replace(next && next !== "/login" ? next : landingFor(user.role));
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

      {/* Hero. Says what the product is for, in the words the BRD uses. */}
      <div className="hidden lg:flex flex-1 flex-col justify-between p-10 relative overflow-hidden"
           style={{ background: "var(--rail)", color: "var(--rail-text)" }}>
        <div className="auth-dotgrid absolute inset-0" />
        <div className="relative"><BrandLockup /></div>

        {/* The instrument the product measures, rendered in 3D. */}
        <div className="relative flex-1 flex items-center justify-center py-6">
          <HeroMic />
        </div>

        <div className="relative max-w-md">
          <h1 className="text-3xl font-bold leading-tight mb-4">
            Simulate the real test. Diagnose the real gap.
          </h1>
          <p className="text-sm leading-relaxed" style={{ color: "var(--rail-muted)" }}>
            Versant-, SVAR- and SpeechX-style simulations with the timing and
            one-shot pressure of the real thing — then the part the real thing
            never gives you: why the score is what it is, and the one change
            that moves it most.
          </p>
        </div>
      </div>

      <div className="flex-1 flex items-center justify-center p-6">
        <div className="w-full max-w-sm">
          <div className="flex items-center justify-between mb-6">
            <div className="lg:hidden"><BrandLockup /></div>
            <div className="ml-auto"><ThemePicker /></div>
          </div>

          <h2 className="text-lg font-bold mb-1">Sign in</h2>
          <p className="text-xs text-muted mb-5">
            Students, trainers and institution staff use the same door — your
            account decides what opens.
          </p>

          {expired && (
            <div className="chip mb-4 w-full justify-center py-2"
                 style={{ background: "color-mix(in srgb, var(--rag-amber) 14%, transparent)",
                          color: "var(--rag-amber)" }}>
              Your session expired — please sign in again
            </div>
          )}

          <form onSubmit={submit} className="space-y-3">
            <div>
              <label className="ds-label" htmlFor="email">Email</label>
              <input id="email" type="email" required autoComplete="username"
                     className="ds-input ds-focus" value={email}
                     onChange={(e) => setEmail(e.target.value)} />
            </div>
            <div>
              <label className="ds-label" htmlFor="password">Password</label>
              <input id="password" type="password" required autoComplete="current-password"
                     className="ds-input ds-focus" value={password}
                     onChange={(e) => setPassword(e.target.value)} />
            </div>

            {error && (
              <div className="text-xs font-medium" style={{ color: "var(--rag-red)" }}>{error}</div>
            )}

            <button type="submit" disabled={busy} className="btn btn-primary w-full ds-focus">
              <LogIn size={15} />
              {busy ? "Signing in…" : "Sign in"}
            </button>
          </form>

          </div>
        </div>
      </div>
  );
}

export default function LoginPage() {
  return (
    <Suspense fallback={<div className="p-8 text-xs text-muted">Loading…</div>}>
      <LoginForm />
    </Suspense>
  );
}
