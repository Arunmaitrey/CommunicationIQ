import Link from "next/link";
import { BrandLockup } from "@/components/brand/BrandMark";

export const metadata = { title: "Privacy Policy — CommunicationIQ" };

const SECTIONS: { title: string; body: string[] }[] = [
  {
    title: "1. What we collect",
    body: [
      "Account information: name, email, institution, and login records.",
      "Assessment data: your responses (typed and spoken), scores, timing and proctoring signals from assessments you take.",
      "Usage data: pages visited and features used, to operate and improve the service.",
    ],
  },
  {
    title: "2. How we use it",
    body: [
      "To run assessments, score responses (including speech transcription), produce reports, and show progress.",
      "To maintain assessment integrity through proctoring signals (fullscreen, tab switching, face/gaze signals).",
      "To communicate with you (results, scheduled exams, support replies) and to administer institution programs.",
    ],
  },
  {
    title: "3. Recordings & consent",
    body: [
      "Speaking responses are recorded only after you consent, when starting an assessment.",
      "Recordings are processed to generate your score and feedback and are stored securely.",
      "Recordings are retained only for as long as needed for your reports and are deleted in line with our retention policy. Institution administrators may see scores and reports, not raw recordings beyond what their program requires.",
    ],
  },
  {
    title: "4. Who we share with",
    body: [
      "Your institution (for institution accounts): your scores, attempts and activity, so they can run their placement-readiness program.",
      "Service providers who help operate the platform (hosting, speech processing, email) — only as needed and under confidentiality obligations.",
      "We do not sell your personal data.",
    ],
  },
  {
    title: "5. Security",
    body: [
      "Passwords are hashed, sessions are encrypted, and access is role-scoped. Records are stored on secured infrastructure.",
      "No method of transmission is 100% secure, but we apply reasonable safeguards to protect your data.",
    ],
  },
  {
    title: "6. Your choices & rights",
    body: [
      "You can update your profile, change your password, and view your own results at any time.",
      "Depending on your region you may have rights to access, correct, export or delete your data — contact us through the Contact page to exercise them.",
      "General users can close their account and request deletion; institution data is managed with the institution.",
    ],
  },
  {
    title: "7. Cookies & local storage",
    body: [
      "We use necessary cookies/local storage for sessions and preferences. We do not use tracking cookies for advertising.",
    ],
  },
  {
    title: "8. Changes to this policy",
    body: [
      "We may update this policy; the latest version is always available at /privacy with the effective date shown.",
    ],
  },
];

export default function PrivacyPage() {
  return (
    <div className="min-h-screen flex flex-col">
      <div className="bgfx" />
      <header className="app-header h-14 flex items-center px-4 border-b border-border bg-surface">
        <Link href="/" className="hover:opacity-80 transition-opacity"><BrandLockup /></Link>
        <div className="flex-1" />
        <Link href="/login" className="text-xs font-semibold hover:underline">Sign in</Link>
      </header>
      <main className="flex-1 max-w-3xl w-full mx-auto px-6 py-10">
        <h1 className="text-2xl font-bold mb-2">Privacy Policy</h1>
        <p className="text-xs text-muted mb-8">Effective: 4 September 2026</p>
        <div className="space-y-8">
          {SECTIONS.map((s) => (
            <section key={s.title}>
              <h2 className="text-sm font-bold mb-2">{s.title}</h2>
              {s.body.map((p, i) => (
                <p key={i} className="text-[12px] leading-relaxed text-muted mb-2">{p}</p>
              ))}
            </section>
          ))}
        </div>
      </main>
      <footer className="border-t border-border bg-surface/50 px-4 py-3 flex items-center justify-between text-[11px] text-muted">
        <span>© {new Date().getFullYear()} Fluenzee. All rights reserved.</span>
        <div className="flex gap-4">
          <Link href="/terms" className="hover:underline">Terms</Link>
          <Link href="/privacy" className="hover:underline">Privacy</Link>
        </div>
      </footer>
    </div>
  );
}