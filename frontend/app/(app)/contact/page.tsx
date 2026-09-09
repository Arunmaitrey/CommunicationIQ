"use client";
import { useState } from "react";
import { Send } from "lucide-react";
import { RequireAuth } from "@/components/RequireAuth";
import { useToast } from "@/components/Toast";
import { ErrorNote, PageHeader, Section } from "@/components/ui";
import { api, ApiError } from "@/lib/api";

const PRIORITIES = [
  { value: "low", label: "Low" },
  { value: "normal", label: "Normal" },
  { value: "high", label: "High" },
  { value: "urgent", label: "Urgent" },
];

export default function ContactPage() {
  return (
    <RequireAuth roles={["student", "tenant_admin", "trainer"]}>
      <Contact />
    </RequireAuth>
  );
}

/** A student's own way to reach the platform. Goes to the same inbox a
 *  super admin reads on /platform/messages, through a route a student can
 *  actually call -- that one sits behind platform-only auth despite its own
 *  docstring saying "from any user". */
function Contact() {
  const { toast } = useToast();
  const [subject, setSubject] = useState("");
  const [priority, setPriority] = useState("normal");
  const [body, setBody] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [sent, setSent] = useState(false);

  async function send() {
    setError("");
    setBusy(true);
    try {
      await api.submitContact({ subject: subject.trim(), body: body.trim(), priority });
      setSent(true);
      setSubject("");
      setBody("");
      setPriority("normal");
      toast("success", "Message sent — we'll get back to you soon.");
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Could not send your message");
    } finally {
      setBusy(false);
    }
  }

  const canSend = subject.trim().length > 0 && body.trim().length > 0 && !busy;

  return (
    <>
      <PageHeader title="Contact us" sub="Have a question or need help? Send us a message." />

      <Section className="max-w-xl">
        <div className="mb-3">
          <label className="ds-label" htmlFor="contact-subject">Subject</label>
          <input
            id="contact-subject" className="ds-input" value={subject}
            onChange={(e) => setSubject(e.target.value)}
            placeholder="What is this about?" maxLength={200}
          />
        </div>

        <div className="mb-3">
          <label className="ds-label" htmlFor="contact-priority">Priority</label>
          <select
            id="contact-priority" className="ds-select" value={priority}
            onChange={(e) => setPriority(e.target.value)}
          >
            {PRIORITIES.map((p) => (
              <option key={p.value} value={p.value}>{p.label}</option>
            ))}
          </select>
        </div>

        <div className="mb-4">
          <label className="ds-label" htmlFor="contact-message">Message</label>
          <textarea
            id="contact-message" className="ds-textarea w-full" value={body}
            onChange={(e) => setBody(e.target.value)}
            placeholder="Describe your question or issue…" maxLength={5000}
          />
        </div>

        {error && <div className="mb-3"><ErrorNote message={error} /></div>}

        {sent && !error && (
          <p className="text-xs text-muted mb-3">
            Sent. A platform admin will follow up by email if needed.
          </p>
        )}

        <button
          type="button" onClick={send} disabled={!canSend}
          className="btn btn-primary ds-focus"
        >
          <Send size={14} />
          {busy ? "Sending…" : "Send message"}
        </button>
      </Section>
    </>
  );
}
