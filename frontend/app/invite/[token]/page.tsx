"use client";
import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { Clock, Mic, Video } from "lucide-react";
import { BrandLockup } from "@/components/brand/BrandMark";
import { PoweredByFloat } from "@/components/brand/PoweredBy";
import { useRole } from "@/components/RoleProvider";
import { ApiError, api, attemptApi, inviteApi, type InvitePreview } from "@/lib/api";

/**
 *  Where an invited candidate arrives.
 *
 *  Outside the app shell on purpose: no nav rail, no sign-in form, nothing
 *  suggesting an account they do not have and will not get. Somebody landing
 *  here has a link from an employer and one question — what am I about to do,
 *  and how long will it take.
 *
 *  **Looking costs nothing.** The preview is a GET and the link survives it,
 *  so opening this on the train to check, reloading, or having a mail client
 *  scan it does not burn the invitation. The claim happens on the button, and
 *  only there.
 */
export default function InvitePage() {
  const { token } = useParams<{ token: string }>();
  const router = useRouter();
  const { signIn } = useRole();

  const [preview, setPreview] = useState<InvitePreview | null>(null);
  const [loading, setLoading] = useState(true);
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  // "details" -> "consent" -> gone. Two steps, both of which mean something:
  // the first is who you are, the second is the permission without which
  // nothing may be recorded. Folding consent into the Start button would make
  // agreeing to be recorded a side effect of pressing a button labelled
  // something else.
  const [step, setStep] = useState<"details" | "consent">("details");
  const [session, setSession] = useState<{ token: string; profile_id: string } | null>(null);

  useEffect(() => {
    let alive = true;

    // Ask where we left off before asking about the link.
    //
    // `step` and `session` are React state, so a reload loses them -- and the
    // link is single-use, so the preview then says "already used" to the
    // person who used it. That candidate still holds a valid session and
    // every other route refuses them by role, so the refusal screen was a
    // dead end with no button on it.
    //
    // A refresh at the consent step, closing the tab and reopening the link,
    // or a phone locking mid-flow all land here. In a one-shot assessment
    // that is the whole thing lost.
    async function begin() {
      try {
        const mine = await attemptApi.resume();
        if (!alive || !mine) return false;
        if (mine.attempt_id) {
          // Finished, or still going -- either way this person has an
          // assessment and the link has nothing left to tell them. A
          // candidate who has already sat it lands on their own result;
          // before this they were shown "this invitation has already been
          // used, somebody else has your link", which is both a dead end and
          // an accusation.
          const done = mine.attempt_status === "submitted"
                    || mine.attempt_status === "scored";
          router.replace(done
            ? `/results/${mine.attempt_id}`
            : `/attempt/${mine.attempt_id}/check`);
          return true;
        }
        if (mine.profile_id && !mine.attempt_id) {
          // Claimed but never started: put them back on consent.
          setSession({ token: "", profile_id: mine.profile_id });
          // Every field here comes from the server. An earlier version
          // filled the gaps with zeros and rendered "About 0 minutes, in one
          // sitting" with no institution named, on the last screen before
          // somebody agrees to be recorded.
          setPreview({
            ok: true, reason: "", message: "",
            tenant_name: mine.tenant_name,
            profile_name: mine.profile_name,
            description: mine.profile_description,
            estimated_minutes: mine.estimated_minutes,
            camera_check: false, practice_item: false, invited_name: "",
          });
          setStep("consent");
          return true;
        }
      } catch {
        // Not a candidate, or the answer did not arrive. Either way this is
        // the ordinary first visit and the preview below is the right screen.
      }
      return false;
    }

    begin().then((resumed) => {
      if (!alive || resumed) { if (alive) setLoading(false); return; }
      inviteApi.preview(token)
        .then((p) => {
          if (!alive) return;
          setPreview(p);
          setName(p.invited_name ?? "");
        })
        .catch(() => alive && setError("This link could not be opened. Check "
          + "you copied all of it, or ask whoever invited you for a new one."))
        .finally(() => alive && setLoading(false));
    });

    return () => { alive = false; };
  }, [token, router]);

  /** Spend the link and become somebody who can sit this one assessment. */
  async function claim() {
    if (!preview) return;
    setBusy("claiming");
    setError("");
    try {
      const claimed = await inviteApi.claim(token, name.trim(), email.trim());
      signIn({
        id: claimed.candidate_id, email: email.trim(),
        full_name: claimed.full_name, role: "candidate", scope: "tenant",
        tenant_name: claimed.tenant_name,
      } as never, claimed.token);
      setSession({ token: claimed.token, profile_id: claimed.profile_id });
      setStep("consent");
    } catch (err) {
      setError(err instanceof ApiError ? err.detail
        : "Something went wrong opening your assessment. Try again, and if it "
          + "keeps happening tell whoever invited you.");
    } finally {
      setBusy("");
    }
  }

  /** Agree, then begin. Nothing is recorded before this. */
  async function agreeAndBegin() {
    if (!session) return;
    setBusy("starting");
    setError("");
    try {
      await api.giveConsent(["recording"]);
      const attempt = await attemptApi.start(session.profile_id, "official");
      router.replace(`/attempt/${attempt.attempt_id}/check`);
    } catch (err) {
      setBusy("");
      setError(err instanceof ApiError ? err.detail
        : "Something went wrong starting your assessment. Your invitation has "
          + "been accepted, so nothing is lost -- press the button again.");
    }
  }

  return (
    <main className="min-h-dvh grid place-items-center p-6">
      <div className="w-full max-w-[34rem]">
        <div className="mb-6"><BrandLockup /></div>

        {loading && <p className="text-sm text-muted">Opening your invitation…</p>}

        {!loading && preview && !preview.ok && (
          <div className="ds-card p-5">
            <h1 className="text-base font-bold mb-2">This link cannot be used</h1>
            <p className="text-sm text-muted leading-relaxed">{preview.message}</p>
          </div>
        )}

        {!loading && preview?.ok && (
          <div className="ds-card p-5">
            <div className="text-[11px] font-bold uppercase tracking-wider text-muted">
              {preview.tenant_name} invited you to
            </div>
            <h1 className="text-lg font-bold mt-1">{preview.profile_name}</h1>
            {preview.description && (
              <p className="text-sm text-muted leading-relaxed mt-2">
                {preview.description}
              </p>
            )}

            {/* What they are walking into, before they commit the link. */}
            <ul className="mt-4 space-y-2">
              <Fact icon={<Clock size={14} />}
                    text={`About ${preview.estimated_minutes} minutes, in one sitting.`} />
              <Fact icon={<Mic size={14} />}
                    text="You will need a microphone and somewhere quiet. Headphones help." />
              {preview.camera_check && (
                <Fact icon={<Video size={14} />}
                      text="A working camera is required. Nothing is recorded or watched — the check only confirms one is there." />
              )}
              {preview.practice_item && (
                <Fact icon={<Mic size={14} />}
                      text="The first question is practice. It is not kept and not scored." />
              )}
            </ul>

            {step === "details" && (
            <div className="mt-5 space-y-3">
              <label className="block">
                <span className="block text-[10px] font-bold uppercase tracking-wider text-muted mb-1">
                  Your name
                </span>
                <input className="ds-input w-full" value={name} autoFocus
                       onChange={(e) => setName(e.target.value)}
                       placeholder="The name your result should be in" />
              </label>
              <label className="block">
                <span className="block text-[10px] font-bold uppercase tracking-wider text-muted mb-1">
                  Email <span className="font-normal normal-case">(optional)</span>
                </span>
                <input className="ds-input w-full" type="email" value={email}
                       onChange={(e) => setEmail(e.target.value)}
                       placeholder="So your result can be sent to you" />
              </label>
            </div>
            )}

            {step === "consent" && (
              <div className="ds-inset p-4 mt-5">
                <h2 className="text-sm font-bold mb-2">Before anything is recorded</h2>
                <ul className="text-xs text-muted leading-relaxed space-y-1.5 list-disc pl-4">
                  <li>Your answers are recorded as audio and scored automatically.</li>
                  <li>The recordings are kept so your score can be checked and
                      explained, and are deleted after the retention period.</li>
                  <li>{preview.tenant_name} sees your result. Nobody else does.</li>
                  <li>You can stop at any time. Nothing you have not recorded
                      is kept.</li>
                </ul>
                <p className="text-[11px] text-muted leading-relaxed mt-3">
                  Pressing the button below records that you agreed, with the
                  date and time.
                </p>
              </div>
            )}

            {error && (
              <p className="text-xs mt-3" style={{ color: "var(--rag-red)" }}>{error}</p>
            )}

            {step === "details" ? (
              <button className="btn btn-primary w-full ds-focus mt-4"
                      disabled={!name.trim() || busy !== ""}
                      onClick={() => void claim()}>
                {busy === "claiming" ? "Setting up…" : "Continue"}
              </button>
            ) : (
              <button className="btn btn-primary w-full ds-focus mt-4"
                      disabled={busy !== ""}
                      onClick={() => void agreeAndBegin()}>
                {busy === "starting" ? "Opening the check…"
                  : "I agree — start the assessment"}
              </button>
            )}

            <p className="text-[10px] text-muted mt-3 leading-relaxed">
              This link works once. You will be asked to allow your microphone
              before anything starts. We ask for your name and nothing else
              about you.
            </p>
          </div>
        )}

        {!loading && !preview && error && (
          <div className="ds-card p-5">
            <p className="text-sm text-muted leading-relaxed">{error}</p>
          </div>
        )}
      </div>
      <PoweredByFloat />
    </main>
  );
}

function Fact({ icon, text }: { icon: React.ReactNode; text: string }) {
  return (
    <li className="flex items-start gap-2 text-xs text-muted leading-relaxed">
      <span className="shrink-0 mt-0.5" style={{ color: "var(--primary)" }}>{icon}</span>
      <span>{text}</span>
    </li>
  );
}
