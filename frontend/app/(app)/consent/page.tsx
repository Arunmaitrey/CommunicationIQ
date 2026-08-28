"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { Check, Mic, ShieldCheck, Trash2 } from "lucide-react";
import { RequireAuth } from "@/components/RequireAuth";
import { ErrorNote, PageHeader, Section } from "@/components/ui";
import { useToast } from "@/components/Toast";
import { api, ApiError } from "@/lib/api";

export default function ConsentPage() {
  return (
    <RequireAuth roles={["student"]}>
      <Consent />
    </RequireAuth>
  );
}

/** The consent screen, before the first recording (STU-02).
 *
 *  Written to be read, not scrolled past. Two of the four scopes are optional
 *  and default to off — a screen where everything is pre-ticked is not consent,
 *  it is a checkbox. Only the first is required, and the product says plainly
 *  that declining it means no recording, rather than pretending otherwise.
 */
function Consent() {
  const router = useRouter();
  const { toast } = useToast();
  const [recording, setRecording] = useState(false);
  const [training, setTraining] = useState(false);
  const [outcome, setOutcome] = useState(false);
  const [notifications, setNotifications] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function submit() {
    setBusy(true);
    setError("");
    const scopes = [
      ...(recording ? ["recording"] : []),
      ...(training ? ["training_data"] : []),
      ...(outcome ? ["outcome_sharing"] : []),
      ...(notifications ? ["notifications"] : []),
    ];
    try {
      await api.giveConsent(scopes);
      toast("success", "Consent saved successfully");
      router.push("/simulate");
    } catch (err) {
      const msg = err instanceof ApiError ? err.detail : "Could not save your choices";
      setError(msg);
      toast("error", msg);
      setBusy(false);
    }
  }

  return (
    <>
      <PageHeader
        title="Before you record"
        sub="Your voice is personal data. Here is exactly what happens to it, in plain terms — read it, then choose."
      />

      <Section className="mb-4">
        <div className="space-y-4 text-xs leading-relaxed">
          <Fact icon={Mic} title="What is recorded">
            Only your spoken answers during a simulation or drill. The microphone
            is opened when an item starts and closed when it ends. Nothing is
            captured while you browse the app, and nothing is captured in the
            background.
          </Fact>
          <Fact icon={ShieldCheck} title="What it is used for">
            Scoring your answer and building your diagnostic report. Your
            institution admin can see your scores and your progress —
            never your recordings.
          </Fact>
          <Fact icon={Trash2} title="How long it is kept">
            Recordings are deleted 30 days after they are made. Your scores and
            your progress history are kept, so your report still works after
            the audio is gone. You can ask for immediate deletion at any time.
          </Fact>
        </div>
      </Section>

      <Section title="Your choices" className="mb-4">
        <div className="space-y-3">
          <Choice
            checked={recording} onChange={setRecording} required
            label="Record and score my speech"
            note="Required to take any simulation. Without it, there is nothing to score — and we will not record you."
          />
          <Choice
            checked={training} onChange={setTraining}
            label="Use my recordings to improve the scoring models"
            note="Optional, and it genuinely is optional: declining changes nothing about your own scores or your report."
          />
          <Choice
            checked={outcome} onChange={setOutcome}
            label="Let my institution link my practice to my placement outcome"
            note="Optional. Helps the platform learn what actually predicts a real result. Your individual outcome is never shown to other students."
          />
          <Choice
            checked={notifications} onChange={setNotifications}
            label="Send me practice reminders"
            note="Optional. At most one a day, quiet hours respected, and you can switch it off permanently in one tap."
          />
        </div>
      </Section>

      {error && <div className="mb-4"><ErrorNote message={error} /></div>}

      <div className="flex flex-wrap items-center gap-3">
        <button onClick={submit} disabled={busy || !recording}
                className="btn btn-primary ds-focus">
          <Check size={15} />
          {busy ? "Saving…" : "Save my choices"}
        </button>
        <button onClick={() => router.push("/home")} disabled={busy}
                className="btn btn-ghost ds-focus">
          Not now
        </button>
        {!recording && (
          <span className="text-[11px] text-muted">
            Simulations stay locked until the first choice is agreed.
          </span>
        )}
      </div>
    </>
  );
}

function Fact({ icon: Icon, title, children }: {
  icon: typeof Mic; title: string; children: React.ReactNode;
}) {
  return (
    <div className="flex items-start gap-3">
      <span className="rounded-full p-2 shrink-0"
            style={{ background: "color-mix(in srgb, var(--primary) 12%, transparent)" }}>
        <Icon size={14} style={{ color: "var(--primary)" }} />
      </span>
      <div>
        <div className="font-bold text-text mb-0.5">{title}</div>
        <p className="text-muted">{children}</p>
      </div>
    </div>
  );
}

function Choice({ checked, onChange, label, note, required = false }: {
  checked: boolean;
  onChange: (v: boolean) => void;
  label: string;
  note: string;
  required?: boolean;
}) {
  return (
    <label className="ds-inset p-3 flex items-start gap-3 cursor-pointer">
      <input
        type="checkbox"
        checked={checked}
        onChange={(e) => onChange(e.target.checked)}
        className="mt-0.5 ds-focus"
        style={{ accentColor: "var(--primary)", width: 16, height: 16 }}
      />
      <span>
        <span className="text-xs font-semibold block">
          {label}
          {required && <span className="ml-1.5 text-[10px] font-bold"
                             style={{ color: "var(--rag-amber)" }}>REQUIRED</span>}
        </span>
        <span className="text-[11px] text-muted block mt-0.5 leading-relaxed">{note}</span>
      </span>
    </label>
  );
}
