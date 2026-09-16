"use client";
import { Suspense, useState } from "react";
import Link from "next/link";
import { ArrowLeft, Mail, AlertCircle, X } from "lucide-react";
import { BrandLockup } from "@/components/brand/BrandMark";
import { api, ApiError } from "@/lib/api";

function ForgotPasswordForm() {
  const [email, setEmail] = useState("");
  const [error, setError] = useState("");
  const [success, setSuccess] = useState(false);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      await api.forgotPassword(email.trim());
      setSuccess(true);
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Could not reach the server");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center p-6">
      <div className="w-full max-w-sm">
        <div className="mb-6">
          <Link href="/login" className="flex items-center gap-1.5 text-xs text-muted hover:text-text ds-focus">
            <ArrowLeft size={13} /> Back to sign in
          </Link>
        </div>

        <h2 className="text-lg font-bold mb-1">Forgot password?</h2>
        <p className="text-xs text-muted mb-5">
          Enter your email address and we will send you a link to reset your password.
        </p>

        {success ? (
          <div className="ds-card p-4 text-center">
            <div className="flex justify-center mb-3">
              <div className="w-10 h-10 rounded-full flex items-center justify-center"
                   style={{ background: "color-mix(in srgb, var(--rag-green) 14%, transparent)" }}>
                <Mail size={18} style={{ color: "var(--rag-green)" }} />
              </div>
            </div>
            <p className="text-sm font-semibold mb-1">Check your email</p>
            <p className="text-xs text-muted mb-4">
              If an account exists for <strong>{email}</strong>, you will receive a password reset link shortly.
            </p>
            <Link href="/login" className="btn btn-primary ds-focus text-xs">
              Return to sign in
            </Link>
          </div>
        ) : (
          <form onSubmit={submit} className="space-y-3">
            <div>
              <label className="ds-label" htmlFor="email">Email</label>
              <input id="email" type="email" required autoComplete="email"
                     className="ds-input ds-focus" value={email}
                     onChange={(e) => setEmail(e.target.value)} />
            </div>

            {error && (
              <div className="flex items-start gap-2 px-3 py-2.5 rounded-lg text-xs font-medium" style={{
                background: "color-mix(in srgb, var(--rag-red) 10%, var(--surface))",
                border: "1px solid color-mix(in srgb, var(--rag-red) 25%, transparent)",
                color: "var(--rag-red)"
              }}>
                <AlertCircle size={14} className="shrink-0 mt-0.5" />
                <span className="flex-1">{error}</span>
                <button onClick={() => setError("")} className="shrink-0 opacity-60 hover:opacity-100">
                  <X size={12} />
                </button>
              </div>
            )}

            <button type="submit" disabled={busy} className="btn btn-primary w-full ds-focus">
              <Mail size={15} />
              {busy ? "Sending…" : "Send reset link"}
            </button>
          </form>
        )}
      </div>
    </div>
  );
}

export default function ForgotPasswordPage() {
  return (
    <Suspense fallback={
      <div className="flex flex-col items-center justify-center py-16 gap-3">
        <div className="w-10 h-10 rounded-full border-[3px] border-[var(--border)] border-t-[var(--primary)] animate-spin" />
        <div className="text-xs text-muted">Loading…</div>
      </div>
    }>
      <ForgotPasswordForm />
    </Suspense>
  );
}
