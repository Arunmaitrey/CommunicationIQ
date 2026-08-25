# Communication IQ — Prerequisites Checklist

Everything that must exist, be decided, or be signed up for **before** (or in parallel with) the first line of product code. Organized by category, with a "blocks what" note so you can see what's truly blocking versus what can run in parallel.

Legend: 🔴 = blocks Phase 1 build start · 🟡 = needed before Phase 1 *launch* (can run parallel to build) · 🟢 = needed for Phase 2/3, start when convenient

---

## 1. Business & Legal Foundation

- [ ] 🔴 **Legal entity confirmed** — which company builds and owns this (SaashX AI Labs? A new entity? Relationship to Pyramid Innovations formalized — partner, customer, or parent?). Contracts, IP ownership, and the college pilot agreements all hang on this answer.
- [ ] 🟡 **GST registration** active for the billing entity (invoicing requirement, BRD BILL-04).
- [ ] 🟡 **IP/legal opinion on "-style" simulation** — a written review from an IP lawyer on replicating Versant/SVAR/SpeechX format, timing, and pressure. The BRD flags this as a company-ending risk if ignored; get it before any public launch, ideally before pilot.
- [ ] 🟡 **DPDP Act compliance basics**: privacy policy, consent-notice wording (what's recorded, why, retention, deletion), a named Data Protection Officer / Consent Manager, and a data-retention policy for voice recordings. Voice data sits adjacent to biometric data — this is not paperwork to defer.
- [ ] 🟡 **Pilot agreement template** for colleges: seats, price (or free-pilot terms), data ownership, who consents on behalf of students, outcome-data sharing clause (this clause is what powers your closed-loop moat later — don't leave it out).
- [ ] 🟢 **Trademark check** on the product name ("Communication IQ") in India.

## 2. Key Decisions (from BRD §16.3 — answers needed, not money)

- [ ] 🔴 **Cloud/hosting provider** consistent with India data residency (AWS Mumbai / Azure India / GCP Mumbai / DigitalOcean BLR). Blocks infra setup.
- [ ] 🔴 **Tech stack commitment** — backend language/framework (the BRD implies Python for the ML engine; decide the web stack: e.g., Python/FastAPI + React/Next.js + Postgres + Redis), and monorepo vs. multi-repo.
- [ ] 🔴 **Phase 1 scope freeze** — which 2–3 task types ship first (recommendation already in BRD: Read Aloud + Repeat Sentence, then Open Response).
- [ ] 🟡 **Accuracy bar before going live** — the minimum engine-quality number (e.g., "pronunciation scores correlate ≥0.7 with human raters on our test set") below which Phase 1 does not touch real students. Decide it now, in writing, so launch pressure can't erode it.
- [ ] 🟡 **Initial plan/pricing sheet** — per-seat and per-institution numbers for the first 3 pilot conversations (can be provisional).
- [ ] 🟡 **Pre-18 students yes/no** for pilot tenants — activates or parks the parental-consent flow.

## 3. Team / Skills (the real constraint)

Minimum viable team for Phase 1 as specced:

- [ ] 🔴 **Full-stack engineer(s)** — platform, tenant, student app, billing (1–2 people).
- [ ] 🔴 **Speech/ML engineer** — owns the engine: ASR pipeline, VAD, alignment, feature-based fluency model, provider-contract layer (1 person, but the right person; this hire is the project's critical path given the own-build decision).
- [ ] 🔴 **Frontend engineer with audio experience** — browser mic capture, WebSocket streaming, one-shot playback enforcement on flaky Android devices. Often underestimated; this is half the "simulator feel."
- [ ] 🟡 **Psychometrics advisor** (part-time/consultant) — IRT calibration, item-bank design, rater-agreement methodology. Needed before Phase 2, useful from day one for item authoring standards.
- [ ] 🟡 **Content/assessment author** — writes the actual test items (sentences, passages, retell stories, prompts) with difficulty metadata. Engineers cannot do this well; budget for it.
- [ ] 🟡 **Human rating panel** (contract, ~3–5 Indian raters to start) — for the intelligibility labelling program (ENG-09). Longest lead-time item in the whole project; recruit during Phase 1 build.
- [ ] 🟢 **DevOps/SRE capability** — can be a hat worn by an engineer until placement-season scale approaches.

## 4. Accounts, Services & Subscriptions

- [ ] 🔴 **Cloud account** with billing set up + India region enabled; object storage bucket (S3-class) for audio.
- [ ] 🔴 **Git hosting + CI/CD** (GitHub/GitLab org).
- [ ] 🔴 **Domain name** + DNS + TLS (wildcard cert if tenant subdomains are planned).
- [ ] 🟡 **Razorpay account** (KYC takes days-to-weeks; start early) — Day-1 payment gateway per BRD BILL-01.
- [ ] 🟡 **Transactional email service** (SES/Postmark/Brevo) and **SMS provider** (MSG91/Twilio) — first notification channels.
- [ ] 🟡 **Error tracking + monitoring** (Sentry + basic uptime/APM).
- [ ] 🟢 **WhatsApp Business API** access (approval process is slow; start when Phase 2 nears).
- [ ] 🟢 **Apple/Google developer accounts** (only when the mobile app phase approaches).

## 5. ML & Data Prerequisites

- [ ] 🔴 **GPU access for the engine** — a cloud GPU instance (or provider like RunPod/Lambda) for running/fine-tuning Whisper-class ASR and wav2vec2-class models. CPU-only will not give you the latency budget (≤5s per response).
- [ ] 🔴 **Base models & datasets downloaded and evaluated**: WhisperX, Silero-VAD, wav2vec2/HuBERT checkpoints, speechocean762 dataset, CommonAccent ECAPA checkpoint. All free/open — needs engineering time, not money.
- [ ] 🔴 **Indian-L1 evaluation set (small, immediate)**: ~50–100 recordings of real target-population speech (Telugu/Hindi/Tamil-L1 English) with quick human quality judgments — the yardstick every model choice gets measured against from week 1. Without this you are tuning blind.
- [ ] 🟡 **Consent-cleared audio collection pipeline** — the mechanism (and legal wording) by which pilot students' recordings become training data. Must exist before the first pilot student speaks.
- [ ] 🟡 **Rater guidelines document** — how the human panel scores intelligibility (scale, anchors, examples), with an inter-rater agreement target. Prerequisite for the labelling program to produce usable data rather than noise.
- [ ] 🟢 **Item bank seed content** — ~200–300 authored items across the Phase 1 task types with difficulty tags (enough for practice variety before IRT calibration exists).

## 6. Development Environment & Standards

- [ ] 🔴 **Repo scaffold** matching the module map (platform-admin, tenant, student-app, engine, notifications, billing) with the Provider Contract interfaces defined first — the BRD's "no capability without its contract" rule starts at the scaffold.
- [ ] 🔴 **Environments**: local dev, staging, production — with the DPDP rule "no real student audio outside production" set from day one.
- [ ] 🔴 **Multi-tenancy test harness** — automated cross-tenant isolation tests in CI from the first table created (BRD calls this non-negotiable; retrofitting it is how leaks happen).
- [ ] 🟡 **Test devices**: at least 2 real budget Android phones (₹8–12K class) + throttled-network testing setup — the "works on a hostel connection" requirement can't be verified on a MacBook.
- [ ] 🟡 **Audio QA fixtures**: a library of recorded test clips (clean, noisy, clipped, accented, silent) for regression-testing the scoring pipeline.

## 7. Pilot Readiness (before first real students)

- [ ] 🟡 **1–2 committed pilot colleges** with a named placement-officer sponsor each (the Pyramid network is the obvious source).
- [ ] 🟡 **Pilot success criteria written down** — e.g., ≥60% of an assigned cohort completes baseline; ≥5 average re-attempts; measured sub-score improvement attempt 1→5. Decide what "the pilot worked" means before it starts.
- [ ] 🟡 **Support channel** for pilot students/trainers (even just WhatsApp + a shared inbox) and a named owner.
- [ ] 🟡 **Compliance sign-off gate passed**: consent flow live, DPO named, retention policy active — before the first real recording.

---

## The short version (what actually blocks you this month)

1. Decide the entity/ownership question and the cloud + tech stack.
2. Hire or contract the speech/ML engineer — the critical-path person.
3. Set up cloud, repo scaffold with provider contracts, CI with tenant-isolation tests.
4. Download and benchmark the open models against a small, real Indian-L1 evaluation set.
5. Start the two long-lead clocks now: Razorpay KYC and the human-rater program.

Everything else can start in parallel once these five are moving.
