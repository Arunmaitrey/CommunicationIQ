"use client";
import { useEffect } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { ArrowRight, BookOpen, CheckCircle, GraduationCap, Headphones, LineChart, LogIn, Mic, PenLine, Shield, Target, Users, Zap } from "lucide-react";
import { BrandLockup } from "@/components/brand/BrandMark";
import { HeroMic } from "@/components/brand/HeroMic";
import { useRole } from "@/components/RoleProvider";
import { landingFor } from "@/lib/nav";

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
    <div className="min-h-screen flex flex-col" style={{ background: "var(--bg)" }}>
      {/* Top bar */}
      <header className="relative z-10 flex items-center justify-between px-6 lg:px-16 py-5 mx-auto w-full" style={{ maxWidth: 1280 }}>
        <Link href="/" className="hover:opacity-80 transition-opacity"><BrandLockup /></Link>
        <nav className="hidden md:flex items-center gap-6 text-sm font-medium" style={{ color: "var(--muted)" }}>
          <Link href="#features" className="hover:text-foreground transition-colors">Features</Link>
          <Link href="#how" className="hover:text-foreground transition-colors">How it works</Link>
          <Link href="#roles" className="hover:text-foreground transition-colors">Who it's for</Link>
          <Link href="#stats" className="hover:text-foreground transition-colors">Results</Link>
          <Link href="/login" className="hover:text-foreground transition-colors">Sign in</Link>
        </nav>
        <div className="flex items-center gap-3">
          <Link href="/signup" className="inline-flex items-center gap-2 rounded-ds px-4 py-2 text-sm font-semibold transition-opacity hover:opacity-90 border" style={{ borderColor: "var(--border)" }}>
            Sign up
          </Link>
          <Link href="/login" className="inline-flex items-center gap-2 rounded-ds px-4 py-2 text-sm font-semibold transition-opacity hover:opacity-90" style={{ background: "var(--primary)", color: "#fff" }}>
            <LogIn size={16} /> Sign in
          </Link>
        </div>
      </header>

      {/* Hero — centered two-column */}
      <main className="relative z-10 flex-1">
        <div className="mx-auto w-full px-6 lg:px-16 py-12 lg:py-20" style={{ maxWidth: 1280 }}>
          <div className="grid lg:grid-cols-2 gap-12 items-center">
            <div className="max-w-xl">
              <h1 className="text-4xl lg:text-5xl font-black leading-[1.08] tracking-tight mb-5">
                Simulate the real test.
                <br />
                <span style={{ color: "var(--primary)" }}>Diagnose the real gap.</span>
              </h1>
              <p className="text-sm lg:text-base leading-relaxed mb-6" style={{ color: "var(--muted)" }}>
                Versant-, SVAR- and SpeechX-style simulations with the timing and
                one-shot pressure of the real thing — then the part the real thing
                never gives you: why the score is what it is, and the one change
                that moves it most.
              </p>
              <div className="flex flex-wrap items-center gap-3 mb-8">
                <Link href="/login" className="inline-flex items-center gap-2 rounded-ds px-6 py-3 text-sm font-bold transition-transform hover:-translate-y-0.5" style={{ background: "var(--brand-grad)", color: "#fff" }}>
                  Start practising <ArrowRight size={16} />
                </Link>
                <span className="text-xs" style={{ color: "var(--muted)" }}>
                  Invited to an assessment? Open the link your institution sent.
                </span>
              </div>
              <div className="flex flex-wrap gap-5 text-xs font-medium" style={{ color: "var(--muted)" }}>
                <span className="flex items-center gap-1.5"><CheckCircle size={13} style={{ color: "var(--rag-green)" }} /> 4 skills assessed</span>
                <span className="flex items-center gap-1.5"><CheckCircle size={13} style={{ color: "var(--rag-green)" }} /> AI-powered scoring</span>
                <span className="flex items-center gap-1.5"><CheckCircle size={13} style={{ color: "var(--rag-green)" }} /> Real-time feedback</span>
              </div>
            </div>
            <div className="hidden lg:flex items-center justify-center">
              <HeroMic />
            </div>
          </div>
        </div>

        {/* Features — full width, centered grid */}
        <section id="features" className="py-14" style={{ background: "var(--surface)" }}>
          <div className="mx-auto w-full px-6 lg:px-16" style={{ maxWidth: 1280 }}>
            <h2 className="text-lg font-bold mb-2 text-center">What you get</h2>
            <p className="text-xs text-center mb-6" style={{ color: "var(--muted)" }}>Four skills, one assessment, complete diagnosis.</p>
            <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-4">
              {[
                { icon: Mic, title: "Speaking", body: "Read aloud, repeat sentences, answer questions. Scored on pronunciation, fluency, timing and content.", color: "var(--primary)" },
                { icon: Headphones, title: "Listening", body: "Hear a passage once, then answer questions — the way a placement round does it.", color: "var(--secondary)" },
                { icon: BookOpen, title: "Reading", body: "Read a timed passage, then answer comprehension MCQs. Rate and accuracy measured separately.", color: "var(--accent)" },
                { icon: PenLine, title: "Writing", body: "Essay and email tasks scored on content, grammar, vocabulary, coherence and mechanics.", color: "var(--rag-green)" },
              ].map(({ icon: Icon, title, body, color }) => (
                <div key={title} className="rounded-ds p-5 border text-center" style={{ background: "var(--card)", borderColor: "var(--line)" }}>
                  <div className="w-10 h-10 rounded-full mx-auto mb-3 flex items-center justify-center" style={{ background: `${color}15` }}>
                    <Icon size={20} style={{ color }} />
                  </div>
                  <h3 className="text-sm font-bold mb-1.5">{title}</h3>
                  <p className="text-xs leading-relaxed" style={{ color: "var(--muted)" }}>{body}</p>
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* How it works */}
        <section id="how" className="py-14">
          <div className="mx-auto w-full px-6 lg:px-16" style={{ maxWidth: 1280 }}>
            <h2 className="text-lg font-bold mb-2 text-center">How it works</h2>
            <p className="text-xs text-center mb-6" style={{ color: "var(--muted)" }}>Three steps from first login to knowing exactly where you stand.</p>
            <div className="grid sm:grid-cols-3 gap-5">
              {[
                { step: "1", icon: Target, title: "Simulate the real test", body: "Take a full-length Versant-style exam with real timing, one-shot audio, and section-by-section progression. No pauses, no re-dos." },
                { step: "2", icon: Zap, title: "Get scored instantly", body: "AI analyses pronunciation, fluency, reading rate, writing quality and listening comprehension across every dimension." },
                { step: "3", icon: GraduationCap, title: "Diagnose and improve", body: "See exactly which skill is holding you back, what the gap is, and the specific drill that closes it." },
              ].map(({ step, icon: Icon, title, body }) => (
                <div key={title} className="rounded-ds p-6 border relative text-center" style={{ background: "var(--card)", borderColor: "var(--line)" }}>
                  <div className="w-8 h-8 rounded-full mx-auto mb-3 flex items-center justify-center text-sm font-black text-white" style={{ background: "var(--primary)" }}>{step}</div>
                  <Icon size={20} style={{ color: "var(--primary)" }} className="mb-2 mx-auto" />
                  <h3 className="text-sm font-bold mb-1.5">{title}</h3>
                  <p className="text-xs leading-relaxed" style={{ color: "var(--muted)" }}>{body}</p>
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* Stats — full width */}
        <section id="stats" className="py-14" style={{ background: "var(--surface)" }}>
          <div className="mx-auto w-full px-6 lg:px-16" style={{ maxWidth: 1280 }}>
            <h2 className="text-lg font-bold mb-6 text-center">Platform numbers</h2>
            <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
              {[
                { value: "4", label: "Skills assessed", sub: "Speaking, Listening, Reading, Writing" },
                { value: "500+", label: "Reading questions", sub: "Across passages and articles" },
                { value: "100+", label: "Writing prompts", sub: "Essays + email scenarios" },
                { value: "6+", label: "Exam formats", sub: "Versant, diagnostic, company rounds" },
              ].map(({ value, label, sub }) => (
                <div key={label} className="rounded-ds p-5 border text-center" style={{ background: "var(--card)", borderColor: "var(--line)" }}>
                  <div className="text-3xl font-black" style={{ color: "var(--primary)" }}>{value}</div>
                  <div className="text-xs font-bold mt-1">{label}</div>
                  <div className="text-[10px] mt-0.5" style={{ color: "var(--muted)" }}>{sub}</div>
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* Who signs in */}
        <section id="roles" className="py-14">
          <div className="mx-auto w-full px-6 lg:px-16" style={{ maxWidth: 1280 }}>
            <h2 className="text-lg font-bold mb-2 text-center">One product, four consoles</h2>
            <p className="text-xs text-center mb-6" style={{ color: "var(--muted)" }}>Different roles, different views, one shared question bank.</p>
            <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-4">
              {[
                { icon: Users, title: "Students", body: "Practise, take tests, watch the needle move. Track progress across every skill.", href: "/signup", link: "Create account" },
                { icon: Shield, title: "Institution Admin", body: "Manage people, assessments, cohorts, and results. Export reports.", href: "/login", link: "Sign in" },
                { icon: Target, title: "Platform", body: "All institutions, question bank, audit trail. Full control.", href: "/login", link: "Sign in" },
                { icon: LineChart, title: "Trainer", body: "Cohort readiness, student mastery, intervention flags.", href: "/login", link: "Sign in" },
              ].map(({ icon: Icon, title, body, href, link }) => (
                <div key={title} className="rounded-ds p-5 border" style={{ background: "var(--card)", borderColor: "var(--line)" }}>
                  <Icon size={18} style={{ color: "var(--primary)" }} className="mb-3" />
                  <p className="text-sm font-bold">{title}</p>
                  <p className="text-xs mt-1 leading-relaxed" style={{ color: "var(--muted)" }}>{body}</p>
                  <Link href={href} className="text-[11px] mt-3 inline-block font-medium" style={{ color: "var(--primary)" }}>{link} →</Link>
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* Company formats */}
        <section className="py-14" style={{ background: "var(--surface)" }}>
          <div className="mx-auto w-full px-6 lg:px-16" style={{ maxWidth: 1280 }}>
            <h2 className="text-lg font-bold mb-2 text-center">Company-specific rounds</h2>
            <p className="text-xs text-center mb-6" style={{ color: "var(--muted)" }}>
              Prepare for the exact format your target company uses. Each round mirrors the real placement test structure.
            </p>
            <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3 max-w-3xl mx-auto">
              {[
                { name: "Accenture", color: "#a100ff" },
                { name: "TCS", color: "#0072c6" },
                { name: "Cognizant", color: "#003366" },
                { name: "Wipro", color: "#ff6600" },
                { name: "Infosys", color: "#007cc3" },
              ].map(({ name, color }) => (
                <div key={name} className="rounded-ds p-4 border text-center hover:shadow-md transition-shadow" style={{ background: "var(--card)", borderColor: "var(--line)" }}>
                  <div className="w-10 h-10 rounded-full mx-auto mb-2 flex items-center justify-center text-xs font-black text-white" style={{ background: color }}>
                    {name.slice(0, 2).toUpperCase()}
                  </div>
                  <div className="text-sm font-bold">{name}</div>
                  <div className="text-[10px] mt-0.5" style={{ color: "var(--muted)" }}>LSRW + MCQ</div>
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* CTA */}
        <section className="py-14">
          <div className="mx-auto w-full px-6 lg:px-16" style={{ maxWidth: 1280 }}>
            <div className="rounded-ds p-10 text-center" style={{ background: "var(--brand-grad)" }}>
              <h2 className="text-2xl font-black text-white mb-3">Ready to find your gap?</h2>
              <p className="text-sm text-white/80 mb-6 max-w-lg mx-auto">
                Sign up with your institutional email or open the invitation link your college sent you.
              </p>
              <div className="flex items-center justify-center gap-3">
                <Link href="/signup" className="inline-flex items-center gap-2 rounded-ds px-6 py-3 text-sm font-bold bg-white transition-opacity hover:opacity-90" style={{ color: "var(--primary)" }}>
                  Create account <ArrowRight size={16} />
                </Link>
                <Link href="/login" className="inline-flex items-center gap-2 rounded-ds px-6 py-3 text-sm font-bold border border-white/30 text-white transition-opacity hover:opacity-90">
                  Sign in
                </Link>
              </div>
            </div>
          </div>
        </section>
      </main>

      <footer className="relative z-10 border-t" style={{ borderColor: "var(--line)" }}>
        <div className="mx-auto w-full px-6 lg:px-16 py-8" style={{ maxWidth: 1280 }}>
          <div className="grid sm:grid-cols-3 gap-6 mb-6">
            <div>
              <Link href="/" className="hover:opacity-80 transition-opacity inline-block"><BrandLockup /></Link>
              <p className="text-xs mt-2 leading-relaxed" style={{ color: "var(--muted)" }}>
                Communication assessment for placement readiness.
                Simulate the real test. Diagnose the real gap.
              </p>
            </div>
            <div>
              <h3 className="text-xs font-bold mb-2">Quick links</h3>
              <ul className="space-y-1.5 text-xs" style={{ color: "var(--muted)" }}>
                <li><Link href="/login" className="hover:text-foreground transition-colors">Sign in</Link></li>
                <li><Link href="/signup" className="hover:text-foreground transition-colors">Create student account</Link></li>
                <li><Link href="#features" className="hover:text-foreground transition-colors">Features</Link></li>
                <li><Link href="#how" className="hover:text-foreground transition-colors">How it works</Link></li>
                <li><Link href="#roles" className="hover:text-foreground transition-colors">Who it's for</Link></li>
              </ul>
            </div>
            <div>
              <h3 className="text-xs font-bold mb-2">Modules</h3>
              <ul className="space-y-1.5 text-xs" style={{ color: "var(--muted)" }}>
                <li className="flex items-center gap-1.5"><Mic size={11} /> Speaking practice</li>
                <li className="flex items-center gap-1.5"><Headphones size={11} /> Listening comprehension</li>
                <li className="flex items-center gap-1.5"><BookOpen size={11} /> Reading &amp; writing</li>
                <li className="flex items-center gap-1.5"><LineChart size={11} /> Progress tracking</li>
                <li className="flex items-center gap-1.5"><Shield size={11} /> Institution management</li>
              </ul>
            </div>
          </div>
          <div className="pt-4 text-xs flex flex-col sm:flex-row items-center justify-between gap-2" style={{ borderTop: "1px solid var(--line)", color: "var(--muted)" }}>
            <Link href="/" className="hover:text-foreground transition-colors font-semibold">Fluenzee</Link>
            <span>© 2026 Fluenzee — Powered by Graymatter Technologies</span>
          </div>
        </div>
      </footer>
    </div>
  );
}
