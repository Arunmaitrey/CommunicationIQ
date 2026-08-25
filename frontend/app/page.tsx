"use client";
import { useEffect } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { ArrowRight, GraduationCap, LineChart, LogIn, Mic, Users } from "lucide-react";
import { BrandLockup } from "@/components/brand/BrandMark";
import { HeroMic } from "@/components/brand/HeroMic";
import { PoweredByFloat } from "@/components/brand/PoweredBy";
import { WordField } from "@/components/shell/WordField";
import { useRole } from "@/components/RoleProvider";
import { landingFor } from "@/lib/nav";

/** The front door.
 *
 *  A signed-in person is sent straight to the screen that is their job. A
 *  visitor gets the product's home page — what this is, who it serves —
 *  rather than a wall that demands credentials before saying anything.
 *  Signing in stays one click away; being anonymous no longer means being
 *  redirected.
 */
export default function Index() {
  const { user, loading } = useRole();
  const router = useRouter();

  useEffect(() => {
    if (loading) return;
    if (user) router.replace(landingFor(user.role));
  }, [user, loading, router]);

  if (loading || user) {
    return <div className="p-8 text-xs text-muted">Opening Fluenzee AI…</div>;
  }

  return (
    <div className="min-h-screen flex flex-col">
      <div className="bgfx" />
      <WordField />
      <PoweredByFloat />

      {/* Top bar */}
      <header className="relative z-10 flex items-center justify-between px-6 lg:px-10 py-5">
        <BrandLockup />
        <Link
          href="/login"
          className="inline-flex items-center gap-2 rounded-ds px-4 py-2 text-sm font-semibold transition-opacity hover:opacity-90"
          style={{ background: "var(--primary)", color: "#fff" }}
        >
          <LogIn size={16} /> Sign in
        </Link>
      </header>

      {/* Hero */}
      <main className="relative z-10 flex-1 flex items-center">
        <div className="w-full grid lg:grid-cols-2 gap-10 items-center px-6 lg:px-10 py-10">
          <div className="max-w-xl">
            <h1 className="text-4xl lg:text-5xl font-black leading-[1.05] tracking-tight mb-5">
              Simulate the real test.
              <br />
              Diagnose the real gap.
            </h1>
            <p className="text-sm lg:text-base leading-relaxed mb-8" style={{ color: "var(--muted)" }}>
              Versant-, SVAR- and SpeechX-style simulations with the timing and
              one-shot pressure of the real thing — then the part the real thing
              never gives you: why the score is what it is, and the one change
              that moves it most.
            </p>
            <div className="flex flex-wrap items-center gap-3">
              <Link
                href="/login"
                className="inline-flex items-center gap-2 rounded-ds px-6 py-3 text-sm font-bold transition-transform hover:-translate-y-0.5"
                style={{ background: "var(--brand-grad)", color: "#fff" }}
              >
                Start practising <ArrowRight size={16} />
              </Link>
              <span className="text-xs" style={{ color: "var(--muted)" }}>
                Invited to an assessment? Open the link your institution sent.
              </span>
            </div>
          </div>

          <div className="hidden lg:flex items-center justify-center">
            <HeroMic />
          </div>
        </div>
      </main>

      {/* What it does */}
      <section className="relative z-10 px-6 lg:px-10 pb-12">
        <div className="grid sm:grid-cols-3 gap-4 max-w-5xl">
          {[
            {
              icon: Mic,
              title: "Speak under real pressure",
              body: "Section-by-section rounds with server-enforced one-shot prompts and honest clocks.",
            },
            {
              icon: LineChart,
              title: "Scores you can interrogate",
              body: "Every dimension carries its evidence — transcript, timings, word-level clarity.",
            },
            {
              icon: GraduationCap,
              title: "Practice that targets",
              body: "The diagnosis prescribes drills and quizzes against your weakest skill, not generic volume.",
            },
          ].map(({ icon: Icon, title, body }) => (
            <div key={title}
                 className="rounded-ds p-5 border"
                 style={{ background: "var(--card)", borderColor: "var(--line)" }}>
              <Icon size={20} style={{ color: "var(--primary)" }} className="mb-3" />
              <h3 className="text-sm font-bold mb-1.5">{title}</h3>
              <p className="text-xs leading-relaxed" style={{ color: "var(--muted)" }}>{body}</p>
            </div>
          ))}
        </div>
      </section>

      {/* Who signs in */}
      <section className="relative z-10 px-6 lg:px-10 pb-16">
        <div className="max-w-5xl rounded-ds border p-6"
             style={{ background: "var(--rail)", color: "var(--rail-text)", borderColor: "transparent" }}>
          <div className="flex items-start gap-3 mb-4">
            <Users size={18} style={{ color: "var(--accent)" }} />
            <h2 className="text-sm font-bold">One product, four consoles</h2>
          </div>
          <div className="grid sm:grid-cols-4 gap-4 text-xs leading-relaxed">
            <p><strong>Students</strong><br />Practise, take tests, watch the needle move.</p>
            <p><strong>Trainers</strong><br />Cohort momentum and at-risk flags.</p>
            <p><strong>Institutions</strong><br />People, assessments, placement season.</p>
            <p><strong>Platform</strong><br />Tenants, plans, providers, audit.</p>
          </div>
        </div>
      </section>

      <footer className="relative z-10 px-6 lg:px-10 py-5 text-xs flex items-center justify-between"
              style={{ color: "var(--muted)" }}>
        <span>Fluenzee AI — communication assessment for placement readiness.</span>
        <span>Sign in with the account provided by your institution.</span>
      </footer>
    </div>
  );
}
