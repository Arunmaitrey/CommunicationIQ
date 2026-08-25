"use client";
import { useState } from "react";
import { AlertCircle, CheckCircle2, Plus, Settings2 } from "lucide-react";
import { RequireAuth } from "@/components/RequireAuth";
import { Badge, ErrorNote, PageHeader, Section, Skeleton } from "@/components/ui";
import {
  ApiError, api, operatorApi,
  type CapabilityRow, type NarrationSettings, type ProviderRow, type TenantRow,
} from "@/lib/api";
import { PLATFORM_ROLES } from "@/lib/roles";
import { useData } from "@/lib/useData";

export default function ProvidersPage() {
  return (
    <RequireAuth roles={PLATFORM_ROLES}>
      <Providers />
    </RequireAuth>
  );
}

const CAPABILITY_LABEL: Record<string, string> = {
  asr: "Transcription (ASR)",
  vad: "Voice activity detection",
  alignment: "Forced alignment",
  pronunciation: "Pronunciation scoring",
  fluency: "Fluency & prosody",
  disfluency: "Disfluency detection",
  intelligibility: "Intelligibility",
  l1_id: "L1 / accent identification",
  grammar: "Grammar errors",
  content_relevance: "Content relevance",
  tts: "Prompt synthesis",
  storage: "Storage",
  notification: "Notifications",
  payment: "Payments",
};

// "Heuristic" describes an engine tier, not a storage backend — labelling the
// local filesystem provider that way was accurate about the number and wrong
// about the meaning.
const TIER_LABEL = ["Tier 0", "Tier 1", "Tier 2"];
const TIER_HINT = ["no model — heuristic or built-in", "local open model", "vendor API"];

const MODES = ["live", "shadow", "canary"] as const;

const BLANK_PROVIDER = {
  capability: "", provider_key: "", name: "", tier: 1,
  version: "0.1.0", entrypoint: "", active: true,
};

function Providers() {
  const { data, loading, error, reload } = useData(() => api.platformCapabilities());
  const tenants = useData(() => api.platformTenants());
  const [problem, setProblem] = useState("");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState("");
  const [adding, setAdding] = useState<string | null>(null);
  const [draft, setDraft] = useState({ ...BLANK_PROVIDER });

  async function run(what: string, fn: () => Promise<unknown>, ok = "") {
    setBusy(what);
    setProblem("");
    setNote("");
    try {
      await fn();
      reload();
      if (ok) setNote(ok);
      return true;
    } catch (err) {
      setProblem(err instanceof ApiError ? err.detail : "That did not work");
      return false;
    } finally {
      setBusy("");
    }
  }

  async function repoint(cap: CapabilityRow, providerId: string) {
    const others = cap.providers.filter((p) => p.id !== providerId && p.active);
    await run("repoint", () => operatorApi.configureCapability(cap.capability, {
      primary_provider_id: providerId,
      fallback_provider_id: others[0]?.id ?? null,
      mode: cap.mode || "live",
      timeout_ms: cap.timeout_ms || 8000,
    }), "Provider switched.");
  }

  if (loading) return <Skeleton rows={8} />;
  if (error) return <ErrorNote message={error} />;

  const configured = (data ?? []).filter((c) => c.configured).length;

  return (
    <>
      <PageHeader
        title="Capabilities & providers"
        sub="Every pluggable capability, the contract it must satisfy, and what currently serves it. Switching a provider is a configuration write — never a deployment."
      />

      <div className="ds-card p-4 mb-4 text-xs text-muted leading-relaxed">
        {configured} of {(data ?? []).length} capabilities have a provider configured.
        Capabilities with none are listed anyway: an unconfigured capability is a fact
        worth seeing, not a row to hide. Registered-but-inactive providers are the
        Tier-0 and Tier-1 implementations arriving in M1 and M2 — their contracts
        exist today, their code does not.
      </div>

      <AiNarrationCard />

      {problem && <div className="mb-4"><ErrorNote message={problem} /></div>}
      {note && (
        <div className="ds-card p-3 mb-4 text-xs" style={{ borderColor: "var(--rag-green)" }}>
          {note}
        </div>
      )}

      <div className="space-y-3">
        {(data ?? []).map((cap) => (
          <CapabilityCard
            key={cap.capability}
            cap={cap}
            tenants={tenants.data ?? []}
            busy={busy}
            adding={adding === cap.capability}
            draft={draft}
            onDraft={setDraft}
            onOpenAdd={() => {
              setAdding(adding === cap.capability ? null : cap.capability);
              setDraft({ ...BLANK_PROVIDER, capability: cap.capability });
            }}
            onAdd={async () => {
              const ok = await run("add", () => operatorApi.registerProvider(draft),
                                   "Provider registered.");
              if (ok) setAdding(null);
            }}
            onRepoint={repoint}
            onRun={run}
          />
        ))}
      </div>
    </>
  );
}

function CapabilityCard({ cap, tenants, busy, adding, draft, onDraft, onOpenAdd,
                         onAdd, onRepoint, onRun }: {
  cap: CapabilityRow;
  tenants: TenantRow[];
  busy: string;
  adding: boolean;
  draft: typeof BLANK_PROVIDER;
  onDraft: (d: typeof BLANK_PROVIDER) => void;
  onOpenAdd: () => void;
  onAdd: () => Promise<void>;
  onRepoint: (cap: CapabilityRow, providerId: string) => Promise<void>;
  onRun: (what: string, fn: () => Promise<unknown>, ok?: string) => Promise<boolean>;
}) {
  const [tuning, setTuning] = useState(false);
  const [config, setConfig] = useState({
    primary_provider_id: cap.providers.find((p) => p.role === "primary")?.id ?? "",
    fallback_provider_id: cap.providers.find((p) => p.role === "fallback")?.id ?? "",
    shadow_provider_id: cap.providers.find((p) => p.role === "shadow")?.id ?? "",
    mode: cap.mode || "live",
    canary_percent: 0,
    timeout_ms: cap.timeout_ms || 8000,
    tenant_id: "",
  });

  return (
    <Section
      compact
      title={CAPABILITY_LABEL[cap.capability] ?? cap.capability}
      action={
        <div className="flex items-center gap-2">
          {cap.configured
            ? <Badge tone="var(--rag-green)"><CheckCircle2 size={10} /> {cap.mode}</Badge>
            : <Badge tone="var(--muted)"><AlertCircle size={10} /> not configured</Badge>}
          <button className="btn btn-ghost btn-sm ds-focus" onClick={() => setTuning(!tuning)}>
            <Settings2 size={12} /> Configure
          </button>
          <button className="btn btn-ghost btn-sm ds-focus" onClick={onOpenAdd}>
            <Plus size={12} /> Provider
          </button>
        </div>
      }
    >
      <div className="text-[11px] text-muted mb-2">
        Contract v{cap.contract_version}
        {cap.configured && (
          <>
            {" · primary "}<strong className="text-text">{cap.primary}</strong>
            {cap.fallback && <> · fallback {cap.fallback}</>}
            {cap.shadow && <> · shadow {cap.shadow}</>}
            {" · timeout "}{cap.timeout_ms}ms
          </>
        )}
      </div>

      {cap.providers.length === 0 ? (
        <div className="text-[11px] text-muted italic">No provider registered yet.</div>
      ) : (
        <div className="space-y-1">
          {cap.providers.map((p) => (
            <div key={p.id} className="flex items-center gap-2 text-[11px] py-1 border-b border-border last:border-0">
              <span className="mic-dot" style={{
                background: p.active ? "var(--rag-green)" : "var(--muted)",
              }} />
              <span className="font-medium flex-1">{p.name}</span>
              <span className="text-muted" title={TIER_HINT[p.tier]}>{TIER_LABEL[p.tier] ?? `Tier ${p.tier}`}</span>
              <span className="text-muted">v{p.version}</span>
              {p.role !== "unassigned" && <Badge tone="var(--primary)">{p.role}</Badge>}
              {p.calls_24h > 0 && (
                <span className="text-muted">
                  {p.calls_24h} calls · {p.p50_latency_ms}ms · {Math.round(p.error_rate * 100)}% err
                </span>
              )}
              {/* Switching provider is a configuration write, not a deploy —
                  which is the entire reason the abstraction exists. */}
              {p.active && p.role !== "primary" && (
                <button onClick={() => void onRepoint(cap, p.id)}
                        className="btn btn-ghost btn-sm ds-focus">
                  Make primary
                </button>
              )}
              <button
                className="btn btn-ghost btn-sm ds-focus"
                disabled={busy !== "" || (p.role === "primary" && p.active)}
                title={p.role === "primary" && p.active
                  ? "Point the capability elsewhere before disabling its primary"
                  : ""}
                onClick={() => void onRun("toggle",
                  () => operatorApi.setProviderActive(p.id, !p.active),
                  p.active ? "Provider disabled." : "Provider enabled.")}
              >
                {p.active ? "Disable" : "Enable"}
              </button>
            </div>
          ))}
        </div>
      )}

      {adding && (
        <div className="ds-inset p-3 mt-3">
          <div className="text-[11px] font-bold mb-2">
            Register a provider for {CAPABILITY_LABEL[cap.capability] ?? cap.capability}
          </div>
          <div className="grid md:grid-cols-3 gap-2">
            <PField label="Key" hint="Short identifier, unique per capability.">
              <input className="ds-input w-full" value={draft.provider_key}
                     onChange={(e) => onDraft({ ...draft, provider_key: e.target.value })}
                     placeholder="deepgram" />
            </PField>
            <PField label="Display name">
              <input className="ds-input w-full" value={draft.name}
                     onChange={(e) => onDraft({ ...draft, name: e.target.value })}
                     placeholder="Deepgram Nova-3" />
            </PField>
            <PField label="Version">
              <input className="ds-input w-full" value={draft.version}
                     onChange={(e) => onDraft({ ...draft, version: e.target.value })} />
            </PField>
            <PField label="Tier">
              <select className="ds-input w-full" value={draft.tier}
                      onChange={(e) => onDraft({ ...draft, tier: Number(e.target.value) })}>
                {TIER_LABEL.map((l, i) => (
                  <option key={i} value={i}>{l} — {TIER_HINT[i]}</option>
                ))}
              </select>
            </PField>
            <div className="md:col-span-2">
              <PField label="Entrypoint"
                      hint="module:attribute. Checked on save — an unimportable path is refused here rather than failing inside a student's attempt.">
                <input className="ds-input w-full font-mono text-[11px]"
                       value={draft.entrypoint}
                       onChange={(e) => onDraft({ ...draft, entrypoint: e.target.value })}
                       placeholder="app.engine.providers.tier2.deepgram:DeepgramASR" />
              </PField>
            </div>
          </div>
          <div className="flex gap-2 mt-2">
            <button className="btn btn-primary btn-sm ds-focus"
                    disabled={busy !== "" || !draft.provider_key.trim()
                              || !draft.name.trim() || !draft.entrypoint.trim()}
                    onClick={() => void onAdd()}>
              {busy === "add" ? "Registering…" : "Register"}
            </button>
            <button className="btn btn-ghost btn-sm ds-focus" onClick={onOpenAdd}>
              Cancel
            </button>
          </div>
        </div>
      )}

      {tuning && (
        <div className="ds-inset p-3 mt-3">
          <div className="text-[11px] font-bold mb-2">Routing</div>
          <div className="grid md:grid-cols-3 gap-2">
            <PField label="Primary">
              <select className="ds-input w-full" value={config.primary_provider_id}
                      onChange={(e) => setConfig({ ...config, primary_provider_id: e.target.value })}>
                <option value="">— choose —</option>
                {cap.providers.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
              </select>
            </PField>
            <PField label="Fallback" hint="Used when the primary errors or times out.">
              <select className="ds-input w-full" value={config.fallback_provider_id}
                      onChange={(e) => setConfig({ ...config, fallback_provider_id: e.target.value })}>
                <option value="">None</option>
                {cap.providers.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
              </select>
            </PField>
            <PField label="Shadow" hint="Runs alongside; its output is recorded, never served.">
              <select className="ds-input w-full" value={config.shadow_provider_id}
                      onChange={(e) => setConfig({ ...config, shadow_provider_id: e.target.value })}>
                <option value="">None</option>
                {cap.providers.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
              </select>
            </PField>
            <PField label="Mode">
              <select className="ds-input w-full" value={config.mode}
                      onChange={(e) => setConfig({ ...config, mode: e.target.value })}>
                {MODES.map((m) => <option key={m} value={m}>{m}</option>)}
              </select>
            </PField>
            {config.mode === "canary" && (
              <PField label="Canary %">
                <input className="ds-input w-full" type="number" min={0} max={100}
                       value={config.canary_percent}
                       onChange={(e) => setConfig({ ...config, canary_percent: Number(e.target.value) })} />
              </PField>
            )}
            <PField label="Timeout (ms)">
              <input className="ds-input w-full" type="number" min={100} max={120000}
                     value={config.timeout_ms}
                     onChange={(e) => setConfig({ ...config, timeout_ms: Number(e.target.value) })} />
            </PField>
            <PField label="Scope"
                    hint="A tenant override applies to that customer only; everyone else keeps the default.">
              <select className="ds-input w-full" value={config.tenant_id}
                      onChange={(e) => setConfig({ ...config, tenant_id: e.target.value })}>
                <option value="">Global default</option>
                {tenants.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
              </select>
            </PField>
          </div>
          <div className="flex gap-2 mt-2">
            <button className="btn btn-primary btn-sm ds-focus"
                    disabled={busy !== "" || !config.primary_provider_id}
                    onClick={() => void onRun("config",
                      () => operatorApi.configureCapability(cap.capability, {
                        ...config,
                        fallback_provider_id: config.fallback_provider_id || null,
                        shadow_provider_id: config.shadow_provider_id || null,
                        tenant_id: config.tenant_id || null,
                      }), "Routing saved.")}>
              {busy === "config" ? "Saving…" : "Save routing"}
            </button>
            <button className="btn btn-ghost btn-sm ds-focus" onClick={() => setTuning(false)}>
              Cancel
            </button>
          </div>
        </div>
      )}
    </Section>
  );
}

function PField({ label, hint, children }: {
  label: string; hint?: string; children: React.ReactNode;
}) {
  return (
    <label className="block">
      <span className="block text-[10px] font-bold uppercase tracking-wider text-muted mb-1">
        {label}
      </span>
      {children}
      {hint && <span className="block text-[10px] text-muted mt-1 leading-relaxed">{hint}</span>}
    </label>
  );
}


// --------------------------------------------------------------------------
// AI narration — provider, models and keys, operator-configurable.
// --------------------------------------------------------------------------

const NARRATION_PROVIDER_LABEL: Record<string, string> = {
  anthropic: "Anthropic (Claude)",
  nvidia: "NVIDIA NIM (build.nvidia.com)",
  opensource: "Self-hosted / OpenAI-compatible",
  echo: "Echo (no model — development only)",
};

/** Curated starting points; the field also accepts any model id NIM serves. */
const NVIDIA_MODELS = [
  "nvidia/llama-3.1-nemotron-70b-instruct",
  "nvidia/llama-3.3-nemotron-super-49b-v1",
  "meta/llama-3.1-70b-instruct",
  "meta/llama-3.3-70b-instruct",
  "mistralai/mixtral-8x22b-instruct-v0.1",
];

function SecretInput({ label, masked, value, onChange, onClear }: {
  label: string;
  masked: { set: boolean; last4: string };
  value: string;
  onChange: (v: string) => void;
  onClear: () => void;
}) {
  return (
    <label className="block text-xs">
      <span className="text-muted">{label}</span>
      <div className="flex gap-2 mt-1">
        <input
          type="password"
          className="ds-inset px-2 py-1.5 flex-1 bg-transparent"
          value={value}
          placeholder={masked.set ? `configured ····${masked.last4} — type to replace` : "not set"}
          onChange={(e) => onChange(e.target.value)}
          autoComplete="new-password"
        />
        {masked.set && (
          <button type="button" className="btn btn-ghost text-[11px] ds-focus"
                  onClick={onClear}
                  title="Remove the stored key and fall back to the environment">
            Clear
          </button>
        )}
      </div>
    </label>
  );
}

function AiNarrationCard() {
  const { data, loading, error, reload } = useData(() => api.narrationSettings());
  const [draft, setDraft] = useState<Record<string, string>>({});
  const [keys, setKeys] = useState<Record<string, string>>({});
  const [clears, setClears] = useState<Record<string, boolean>>({});
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState("");
  const [problem, setProblem] = useState("");

  if (loading) return <div className="ds-card p-4 mb-4"><Skeleton rows={3} /></div>;
  if (error || !data) return <div className="mb-4"><ErrorNote message={error || "Could not load AI settings"} /></div>;

  const value = (name: keyof NarrationSettings & string) =>
    draft[name] ?? String((data as unknown as Record<string, unknown>)[name] ?? "");
  const set = (name: string) => (v: string) => setDraft((d) => ({ ...d, [name]: v }));
  const provider = value("narration_provider");

  async function save() {
    setBusy(true); setProblem(""); setNote("");
    try {
      const body: Record<string, unknown> = { ...draft };
      // Keys: blank input = leave unchanged (null); Clear pressed = "".
      for (const [name, v] of Object.entries(keys)) if (v) body[name] = v;
      for (const [name, on] of Object.entries(clears)) if (on && !keys[name]) body[name] = "";
      await operatorApi.updateNarrationSettings(body);
      setDraft({}); setKeys({}); setClears({});
      setNote("Saved and applied. New narrations use this configuration immediately.");
      reload();
    } catch (err) {
      setProblem(err instanceof ApiError ? err.detail : "That did not work");
    } finally {
      setBusy(false);
    }
  }

  const dirty = Object.keys(draft).length > 0 || Object.values(keys).some(Boolean)
    || Object.values(clears).some(Boolean);

  return (
    <Section title="AI narration">
      <p className="text-xs text-muted leading-relaxed mb-3">
        Which model explains scores to students. Deterministic scoring is
        unaffected — the narrator only writes the explanation, and a validator
        rejects anything ungrounded.
      </p>
      <div className="ds-card p-4 mb-4 space-y-4">
        <div className="grid gap-3 sm:grid-cols-2">
          <label className="block text-xs">
            <span className="text-muted">Provider</span>
            <select className="ds-inset px-2 py-1.5 w-full mt-1 bg-transparent"
                    value={provider}
                    onChange={(e) => set("narration_provider")(e.target.value)}>
              {data.providers.map((p) => (
                <option key={p} value={p}>{NARRATION_PROVIDER_LABEL[p] ?? p}</option>
              ))}
            </select>
          </label>
          <label className="block text-xs">
            <span className="text-muted">Narration enabled</span>
            <select className="ds-inset px-2 py-1.5 w-full mt-1 bg-transparent"
                    value={value("narration_enabled") === "true" || data.narration_enabled && draft.narration_enabled === undefined ? "true" : String(value("narration_enabled"))}
                    onChange={(e) => set("narration_enabled")(e.target.value)}>
              <option value="true">On</option>
              <option value="false">Off</option>
            </select>
          </label>
        </div>

        {provider === "nvidia" && (
          <div className="grid gap-3 sm:grid-cols-2">
            <label className="block text-xs">
              <span className="text-muted">NVIDIA model</span>
              <input list="nvidia-models" className="ds-inset px-2 py-1.5 w-full mt-1 bg-transparent"
                     value={value("nvidia_model")}
                     onChange={(e) => set("nvidia_model")(e.target.value)} />
              <datalist id="nvidia-models">
                {NVIDIA_MODELS.map((m) => <option key={m} value={m} />)}
              </datalist>
            </label>
            <label className="block text-xs">
              <span className="text-muted">NVIDIA base URL</span>
              <input className="ds-inset px-2 py-1.5 w-full mt-1 bg-transparent"
                     value={value("nvidia_base_url")}
                     onChange={(e) => set("nvidia_base_url")(e.target.value)} />
            </label>
            <SecretInput label="NVIDIA API key" masked={data.nvidia_api_key}
                         value={keys.nvidia_api_key ?? ""}
                         onChange={(v) => setKeys((k) => ({ ...k, nvidia_api_key: v }))}
                         onClear={() => setClears((c) => ({ ...c, nvidia_api_key: true }))} />
            {clears.nvidia_api_key && !keys.nvidia_api_key && (
              <div className="text-[11px] text-muted self-end pb-2">Key will be removed on save.</div>
            )}
          </div>
        )}

        {provider === "anthropic" && (
          <div className="grid gap-3 sm:grid-cols-2">
            <label className="block text-xs">
              <span className="text-muted">Model</span>
              <input className="ds-inset px-2 py-1.5 w-full mt-1 bg-transparent"
                     value={value("narration_model")}
                     onChange={(e) => set("narration_model")(e.target.value)} />
            </label>
            <SecretInput label="Anthropic API key" masked={data.anthropic_api_key}
                         value={keys.anthropic_api_key ?? ""}
                         onChange={(v) => setKeys((k) => ({ ...k, anthropic_api_key: v }))}
                         onClear={() => setClears((c) => ({ ...c, anthropic_api_key: true }))} />
          </div>
        )}

        {provider === "opensource" && (
          <div className="grid gap-3 sm:grid-cols-2">
            <label className="block text-xs">
              <span className="text-muted">Model</span>
              <input className="ds-inset px-2 py-1.5 w-full mt-1 bg-transparent"
                     value={value("oss_model")}
                     onChange={(e) => set("oss_model")(e.target.value)} />
            </label>
            <label className="block text-xs">
              <span className="text-muted">Base URL (OpenAI-compatible)</span>
              <input className="ds-inset px-2 py-1.5 w-full mt-1 bg-transparent"
                     value={value("oss_base_url")}
                     onChange={(e) => set("oss_base_url")(e.target.value)} />
            </label>
            <SecretInput label="API key (optional for local servers)" masked={data.oss_api_key}
                         value={keys.oss_api_key ?? ""}
                         onChange={(v) => setKeys((k) => ({ ...k, oss_api_key: v }))}
                         onClear={() => setClears((c) => ({ ...c, oss_api_key: true }))} />
          </div>
        )}

        {provider === "echo" && (
          <p className="text-[11px] text-muted">
            Echo builds a grounded explanation locally with no model call — for
            development and tests only.
          </p>
        )}

        {problem && <ErrorNote message={problem} />}
        {note && <div className="text-xs" style={{ color: "var(--rag-green)" }}>{note}</div>}

        <div className="flex items-center gap-3">
          <button className="btn btn-primary ds-focus" disabled={!dirty || busy}
                  onClick={() => void save()}>
            {busy ? "Saving…" : "Save & apply"}
          </button>
          {data.overridden.length > 0 && (
            <span className="text-[11px] text-muted">
              Overriding environment: {data.overridden.join(", ")}
            </span>
          )}
        </div>
      </div>
    </Section>
  );
}
