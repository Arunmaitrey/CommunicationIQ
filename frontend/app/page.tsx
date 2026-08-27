"use client";
import { useEffect } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { ArrowRight, BookOpen, GraduationCap, Headphones, LineChart, LogIn, Mic, PenLine, Shield, Target, Users } from "lucide-react";
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
    return <div className="p-8 text-xs text-muted">Loading…</div>;
  }

  return (
    <div className="min-h-screen flex flex-col">
      <div className="bgfx" />
      <WordField />
      <PoweredByFloat />

      {/* Top bar */}
      <header className="relative z-10 flex items-center justify-between px-6 lg:px-10 py-5">
        <BrandLockup />
        <nav className="hidden md:flex items-center gap-5 text-sm font-medium" style={{ color: "var(--muted)" }}>
          <Link href="#features" className="hover:text-text transition-colors">Features</Link>
          <Link href="#roles" className="hover:text-text transition-colors">Who it's for</Link>
          <Link href="/login" className="hover:text-text transition-colors">Sign in</Link>
        </nav>
        <div className="flex items-center gap-3">
          <Link
            href="/signup"
            className="inline-flex items-center gap-2 rounded-ds px-4 py-2 text-sm font-semibold transition-opacity hover:opacity-90 border"
            style={{ borderColor: "var(--border)" }}
          >
            Sign up
          </Link>
          <Link
            href="/login"
            className="inline-flex items-center gap-2 rounded-ds px-4 py-2 text-sm font-semibold transition-opacity hover:opacity-90"
            style={{ background: "var(--primary)", color: "#fff" }}
          >
            <LogIn size={16} /> Sign in
          </Link>
        </div>
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
      <section id="features" className="relative z-10 px-6 lg:px-10 pb-12">
        <h2 className="text-lg font-bold mb-5 max-w-5xl">How it works</h2>
        <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-4 max-w-5xl">
          {[
            { icon: Mic, title: "Speaking", body: "Read aloud, repeat sentences, answer questions. Scored on pronunciation, fluency, timing and content." },
            { icon: Headphones, title: "Listening", body: "Hear a passage once, then answer questions — the way a placement round does it." },
            { icon: BookOpen, title: "Reading", body: "Read a timed passage, then answer comprehension MCQs. Rate and accuracy measured separately." },
            { icon: PenLine, title: "Writing", body: "Essay and email tasks scored on content, grammar, vocabulary, coherence and mechanics." },
          ].map(({ icon: Icon, title, body }) => (
            <div key={title} className="rounded-ds p-5 border" style={{ background: "var(--card)", borderColor: "var(--line)" }}>
              <Icon size={20} style={{ color: "var(--primary)" }} className="mb-3" />
              <h3 className="text-sm font-bold mb-1.5">{title}</h3>
              <p className="text-xs leading-relaxed" style={{ color: "var(--muted)" }}>{body}</p>
            </div>
          ))}
        </div>
        <div className="grid sm:grid-cols-3 gap-4 max-w-5xl mt-4">
          {[
            { icon: Target, title: "Simulate the real test", body: "Versant-, SVAR- and SpeechX-style simulations with real timing and one-shot audio pressure." },
            { icon: LineChart, title: "Scores you can interrogate", body: "Every dimension carries its evidence — transcript, timings, word-level clarity, grammar patterns." },
            { icon: GraduationCap, title: "Diagnose the real gap", body: "The diagnosis prescribes drills and quizzes against your weakest skill, not generic volume." },
          ].map(({ icon: Icon, title, body }) => (
            <div key={title} className="rounded-ds p-5 border" style={{ background: "var(--card)", borderColor: "var(--line)" }}>
              <Icon size={20} style={{ color: "var(--primary)" }} className="mb-3" />
              <h3 className="text-sm font-bold mb-1.5">{title}</h3>
              <p className="text-xs leading-relaxed" style={{ color: "var(--muted)" }}>{body}</p>
            </div>
          ))}
        </div>
      </section>

      {/* Stats */}
      <section className="relative z-10 px-6 lg:px-10 pb-12">
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 max-w-5xl">
          {[
            { value: "4", label: "Skills assessed", sub: "Speaking, Listening, Reading, Writing" },
            { value: "500+", label: "Reading questions", sub: "100 passages, 5 MCQs each" },
            { value: "100", label: "Writing prompts", sub: "50 essays + 50 email scenarios" },
            { value: "10+", label: "Exam formats", sub: "Versant, SVAR, SpeechX, company rounds" },
          ].map(({ value, label, sub }) => (
            <div key={label} className="rounded-ds p-4 border text-center" style={{ background: "var(--card)", borderColor: "var(--line)" }}>
              <div className="text-2xl font-black" style={{ color: "var(--primary)" }}>{value}</div>
              <div className="text-xs font-bold mt-1">{label}</div>
              <div className="text-[10px] mt-0.5" style={{ color: "var(--muted)" }}>{sub}</div>
            </div>
          ))}
        </div>
      </section>

      {/* Who signs in */}
      <section id="roles" className="relative z-10 px-6 lg:px-10 pb-16">
        <div className="max-w-5xl rounded-ds border p-6"
             style={{ background: "var(--rail)", color: "var(--rail-text)", borderColor: "transparent" }}>
          <div className="flex items-start gap-3 mb-4">
            <Users size={18} style={{ color: "var(--accent)" }} />
            <h2 className="text-sm font-bold">One product, four consoles</h2>
          </div>
          <div className="grid sm:grid-cols-3 gap-4 text-xs leading-relaxed">
            <div>
              <p className="font-semibold">Students</p>
              <p className="mt-1">Practise, take tests, watch the needle move.</p>
              <Link href="/signup" className="text-[11px] mt-2 inline-block" style={{ color: "var(--accent)" }}>Create account →</Link>
            </div>
            <div>
              <p className="font-semibold">Institution Admin</p>
              <p className="mt-1">Manage people, assessments, and results.</p>
              <Link href="/login" className="text-[11px] mt-2 inline-block" style={{ color: "var(--accent)" }}>Sign in →</Link>
            </div>
            <div>
              <p className="font-semibold">Platform</p>
              <p className="mt-1">All institutions, results, audit trail.</p>
              <Link href="/login" className="text-[11px] mt-2 inline-block" style={{ color: "var(--accent)" }}>Sign in →</Link>
            </div>
          </div>
        </div>
      </section>

      <footer className="relative z-10 border-t" style={{ borderColor: "var(--line)" }}>
        <div className="max-w-5xl mx-auto px-6 lg:px-10 py-8">
          <div className="grid sm:grid-cols-3 gap-6 mb-6">
            <div>
              <BrandLockup />
              <p className="text-xs mt-2 leading-relaxed" style={{ color: "var(--muted)" }}>
                Communication assessment for placement readiness.
                Simulate the real test. Diagnose the real gap.
              </p>
            </div>
            <div>
              <h3 className="text-xs font-bold mb-2">Quick links</h3>
              <ul className="space-y-1.5 text-xs" style={{ color: "var(--muted)" }}>
                <li><Link href="/login" className="hover:text-text transition-colors">Sign in</Link></li>
                <li><Link href="/signup" className="hover:text-text transition-colors">Create student account</Link></li>
                <li><Link href="#features" className="hover:text-text transition-colors">Features</Link></li>
                <li><Link href="#roles" className="hover:text-text transition-colors">Who it's for</Link></li>
              </ul>
            </div>
            <div>
              <h3 className="text-xs font-bold mb-2">Modules</h3>
              <ul className="space-y-1.5 text-xs" style={{ color: "var(--muted)" }}>
                <li className="flex items-center gap-1.5"><Mic size={11} /> Speaking practice</li>
                <li className="flex items-center gap-1.5"><BookOpen size={11} /> Reading &amp; writing</li>
                <li className="flex items-center gap-1.5"><LineChart size={11} /> Progress tracking</li>
                <li className="flex items-center gap-1.5"><Shield size={11} /> Institution management</li>
              </ul>
            </div>
          </div>
          <div className="pt-4 text-xs flex items-center justify-between"
               style={{ borderTop: "1px solid var(--line)", color: "var(--muted)" }}>
            <span>© 2026 Fluenzee — Powered by Graymatter Technologies</span>
            <span>Sign in with the account provided by your institution.</span>
          </div>
        </div>
      </footer>
    </div>
  );
}
