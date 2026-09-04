import Link from "next/link";
import { BrandLockup } from "@/components/brand/BrandMark";

export const metadata = { title: "Terms & Conditions — CommunicationIQ" };

const SECTIONS: { title: string; body: string[] }[] = [
  {
    title: "1. Acceptance of Terms",
    body: [
      "By creating an account or using CommunicationIQ, you agree to these Terms & Conditions. If you are using the platform on behalf of an institution, the institution also agrees to them.",
      "We may update these terms from time to time; continued use after an update means you accept the new terms.",
    ],
  },
  {
    title: "2. Accounts & Eligibility",
    body: [
      "You must be at least 16 years old to use the platform, or have the consent of a parent or guardian.",
      "Institution accounts are created by the institution's administrator. General accounts are created through self-registration. You are responsible for keeping your login credentials confidential.",
    ],
  },
  {
    title: "3. Use of the Platform",
    body: [
      "CommunicationIQ is an English communication assessment and practice tool covering speaking, listening, reading and writing.",
      "You agree not to: misuse or reverse-engineer the platform, attempt to circumvent proctoring or assessment rules, share answers between sittings, or use the platform for any unlawful purpose.",
      "Assessments are timed and monitored. Prompt audio may play only once per sitting; navigating away may end or flag your attempt.",
    ],
  },
  {
    title: "4. Recordings & Content",
    body: [
      "Speaking assessments require a microphone. By starting an assessment you consent to audio recording of your responses for the purpose of scoring and feedback.",
      "You retain ownership of your content; you grant us a licence to process it solely to provide the service (transcription, scoring, reporting).",
      "We never resell or redistribute your recordings. Recordings are retained only as long as needed and are deleted per our retention policy.",
    ],
  },
  {
    title: "5. Proctoring",
    body: [
      "Assessments may use camera, microphone and browser-monitoring signals (fullscreen, tab switching, multiple faces) to protect integrity.",
      "These signals are used only for assessment integrity and are not used for any other purpose.",
    ],
  },
  {
    title: "6. Payments & Plans",
    body: [
      "General users may subscribe to paid plans. Fees are charged according to the plan chosen and are non-refundable except where required by law.",
      "Institution access is governed by the agreement between the institution and the platform.",
    ],
  },
  {
    title: "7. Intellectual Property",
    body: [
      "The platform, its design, question bank and scoring technology are the property of CommunicationIQ / Fluenzee. You may not copy, resell or redistribute them.",
      "Company-named practice tests (e.g. \"Versant-style\", company communication rounds) are practice formats only and are not affiliated with, endorsed by, or representative of any named employer or test provider.",
    ],
  },
  {
    title: "8. Limitation of Liability",
    body: [
      "The platform is provided \"as is\". We do not guarantee specific placement, employment or test outcomes.",
      "To the maximum extent permitted by law, we are not liable for indirect, incidental or consequential damages arising from your use of the platform.",
    ],
  },
  {
    title: "9. Termination",
    body: [
      "We may suspend or close accounts that violate these terms, or that an institution requests to be closed. You may stop using the platform at any time; your data will be handled per the Privacy Policy.",
    ],
  },
  {
    title: "10. Contact",
    body: [
      "Questions about these terms can be sent through the Contact page or to the platform administrator of your institution.",
    ],
  },
];

export default function TermsPage() {
  return (
    <div className="min-h-screen flex flex-col">
      <div className="bgfx" />
      <header className="app-header h-14 flex items-center px-4 border-b border-border bg-surface">
        <Link href="/" className="hover:opacity-80 transition-opacity"><BrandLockup /></Link>
        <div className="flex-1" />
        <Link href="/login" className="text-xs font-semibold hover:underline">Sign in</Link>
      </header>
      <main className="flex-1 max-w-3xl w-full mx-auto px-6 py-10">
        <h1 className="text-2xl font-bold mb-2">Terms & Conditions</h1>
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