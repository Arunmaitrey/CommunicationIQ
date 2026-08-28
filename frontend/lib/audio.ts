"use client";
/* =============================================================================
   Microphone capture.

   Captures raw PCM rather than using MediaRecorder, for two reasons: the
   scoring engine wants samples, not a container, and a live level meter needs
   the frames anyway. AudioWorklet where it exists, ScriptProcessorNode where
   it does not — the fallback matters, because "works on a ₹10,000 Android
   phone" is a hard requirement (ACC-02), not a nice-to-have.

   Known debt: uploads are 16 kHz mono WAV, about 32 KB per second. That is the
   right format for the engine and the wrong one for a hostel 3G connection.
   Opus upload with a decode at ingest belongs with the Tier-1 work.
   ============================================================================= */

export const TARGET_SAMPLE_RATE = 16000;

/** Worklet source, injected as a Blob so there is no static asset to serve. */
const WORKLET_SOURCE = `
class CaptureProcessor extends AudioWorkletProcessor {
  process(inputs) {
    const channel = inputs[0] && inputs[0][0];
    // The render quantum buffer is reused between calls — copy or the frames
    // arrive already overwritten.
    if (channel) this.port.postMessage(channel.slice(0));
    return true;
  }
}
registerProcessor('commiq-capture', CaptureProcessor);
`;

export class MicPermissionError extends Error {}
export class MicUnavailableError extends Error {}

export interface RecorderEvents {
  /** Called once per captured frame with the current input level in dBFS and
   *  the frame's real duration in milliseconds. The duration is NOT a fixed
   *  20 ms: an AudioWorklet delivers a 128-sample render quantum (~2.7 ms at
   *  48 kHz) while a ScriptProcessor delivers 4096 samples (~85 ms). Callers
   *  that pace on wall-clock time (adaptive advancement) must use frameMs, or
   *  their clock runs many times too fast on the worklet path. */
  onLevel?: (dbfs: number, frameMs: number) => void;
}

/** A live microphone, held open across a whole attempt.
 *
 *  Opened once and reused: asking for the device between every item costs a
 *  second of setup on a budget handset, and a student would hear it as the
 *  app being slow at the exact moment they are trying to answer.
 */
export class MicRecorder {
  private context: AudioContext;
  private stream: MediaStream;
  private source: MediaStreamAudioSourceNode;
  private node: AudioWorkletNode | ScriptProcessorNode | null = null;
  private chunks: Float32Array[] = [];
  private capturing = false;
  private events: RecorderEvents;

  readonly sampleRate: number;

  private constructor(context: AudioContext, stream: MediaStream, events: RecorderEvents) {
    this.context = context;
    this.stream = stream;
    this.events = events;
    this.sampleRate = context.sampleRate;
    this.source = context.createMediaStreamSource(stream);
  }

  static async open(events: RecorderEvents = {}): Promise<MicRecorder> {
    if (typeof navigator === "undefined" || !navigator.mediaDevices?.getUserMedia) {
      // The overwhelmingly common cause on a phone is a plain-HTTP origin:
      // browsers do not expose getUserMedia outside a secure context, and the
      // failure otherwise reads as a broken product rather than a missing
      // certificate.
      if (typeof window !== "undefined" && !window.isSecureContext) {
        throw new MicUnavailableError(
          "This page is not on a secure connection, so the browser will not " +
          "allow microphone access. Open it over HTTPS or on localhost.");
      }
      throw new MicUnavailableError("This browser cannot record audio.");
    }

    let stream: MediaStream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          // Echo cancellation and noise suppression are left ON. They are what
          // the student will have on during a real remote test, and turning
          // them off would score a cleaner signal than the one that actually
          // gets sent to a recruiter.
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
          channelCount: 1,
        },
      });
    } catch (err) {
      const name = (err as DOMException)?.name;
      if (name === "NotAllowedError" || name === "SecurityError") {
        throw new MicPermissionError("Microphone access was blocked.");
      }
      throw new MicUnavailableError("No microphone was found.");
    }

    const Ctor = window.AudioContext ?? (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext;
    const context = new Ctor();
    if (context.state === "suspended") await context.resume();

    const recorder = new MicRecorder(context, stream, events);
    await recorder.attach();
    return recorder;
  }

  private async attach() {
    const handleFrame = (frame: Float32Array) => {
      if (this.capturing) this.chunks.push(frame);
      // Real duration of this frame, from the audio clock: sample count over
      // the context rate. Passing this (not a fixed 20 ms) is what keeps a
      // wall-clock pacer honest across the worklet and script-processor paths.
      const frameMs = (frame.length / this.sampleRate) * 1000;
      this.events.onLevel?.(rmsDbfs(frame), frameMs);
    };

    if (this.context.audioWorklet) {
      try {
        const url = URL.createObjectURL(
          new Blob([WORKLET_SOURCE], { type: "application/javascript" }),
        );
        await this.context.audioWorklet.addModule(url);
        URL.revokeObjectURL(url);

        const node = new AudioWorkletNode(this.context, "commiq-capture");
        node.port.onmessage = (e) => handleFrame(e.data as Float32Array);
        this.source.connect(node);
        // A worklet with no downstream connection is not pulled by the graph
        // in some engines. Routing it to a muted gain keeps it running without
        // the student hearing themselves.
        const sink = this.context.createGain();
        sink.gain.value = 0;
        node.connect(sink).connect(this.context.destination);
        this.node = node;
        return;
      } catch {
        // Fall through to the older path rather than failing the attempt.
      }
    }

    const processor = this.context.createScriptProcessor(4096, 1, 1);
    processor.onaudioprocess = (e) => handleFrame(new Float32Array(e.inputBuffer.getChannelData(0)));
    this.source.connect(processor);
    processor.connect(this.context.destination);
    this.node = processor;
  }

  /** Begin keeping frames. Levels are reported whether or not this is on. */
  start() {
    this.chunks = [];
    this.capturing = true;
  }

  /** Stop keeping frames and return what was captured as a 16 kHz mono WAV. */
  /** The samples behind the last `stop()`, at TARGET_SAMPLE_RATE.
   *
   *  Kept so the runner can ask "was anything actually said?" before
   *  uploading, without decoding the WAV it just encoded. Read-only by
   *  convention: this is the audio that was sent, and nothing may alter it —
   *  the server's own VAD scores these exact bytes.
   */
  lastCapture: Float32Array = new Float32Array(0);

  stop(): Blob {
    this.capturing = false;
    const captured = concat(this.chunks);
    this.chunks = [];
    const resampled = resample(captured, this.sampleRate, TARGET_SAMPLE_RATE);
    this.lastCapture = resampled;
    return encodeWav(resampled, TARGET_SAMPLE_RATE);
  }

  close() {
    try {
      this.node?.disconnect();
      this.source.disconnect();
      this.stream.getTracks().forEach((t) => t.stop());
      void this.context.close();
    } catch {
      /* closing a closed context is not an error worth surfacing */
    }
  }
}

// -- signal helpers ---------------------------------------------------------

export function rmsDbfs(frame: Float32Array): number {
  let sum = 0;
  for (let i = 0; i < frame.length; i++) sum += frame[i] * frame[i];
  const rms = Math.sqrt(sum / Math.max(1, frame.length));
  return rms <= 1e-9 ? -90 : Math.max(-90, 20 * Math.log10(rms));
}

/** dBFS to a 0–1 bar height. -60 dB is the bottom of the meter. */
export function levelToFraction(dbfs: number): number {
  return Math.max(0, Math.min(1, (dbfs + 60) / 60));
}

function concat(chunks: Float32Array[]): Float32Array {
  const total = chunks.reduce((n, c) => n + c.length, 0);
  const out = new Float32Array(total);
  let offset = 0;
  for (const chunk of chunks) {
    out.set(chunk, offset);
    offset += chunk.length;
  }
  return out;
}

function resample(input: Float32Array, from: number, to: number): Float32Array {
  if (from === to || input.length === 0) return input;
  const ratio = from / to;
  const length = Math.floor(input.length / ratio);
  const out = new Float32Array(length);
  for (let i = 0; i < length; i++) {
    const position = i * ratio;
    const index = Math.floor(position);
    const frac = position - index;
    const a = input[index] ?? 0;
    const b = input[index + 1] ?? a;
    out[i] = a + (b - a) * frac;
  }
  return out;
}

export function encodeWav(samples: Float32Array, sampleRate: number): Blob {
  const buffer = new ArrayBuffer(44 + samples.length * 2);
  const view = new DataView(buffer);

  const ascii = (offset: number, text: string) => {
    for (let i = 0; i < text.length; i++) view.setUint8(offset + i, text.charCodeAt(i));
  };

  ascii(0, "RIFF");
  view.setUint32(4, 36 + samples.length * 2, true);
  ascii(8, "WAVE");
  ascii(12, "fmt ");
  view.setUint32(16, 16, true);           // PCM header size
  view.setUint16(20, 1, true);            // format: PCM
  view.setUint16(22, 1, true);            // mono
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate * 2, true); // byte rate
  view.setUint16(32, 2, true);            // block align
  view.setUint16(34, 16, true);           // bits per sample
  ascii(36, "data");
  view.setUint32(40, samples.length * 2, true);

  let offset = 44;
  for (let i = 0; i < samples.length; i++) {
    const clamped = Math.max(-1, Math.min(1, samples[i]));
    view.setInt16(offset, clamped * 0x7fff, true);
    offset += 2;
  }

  return new Blob([buffer], { type: "audio/wav" });
}

/* ---------------------------------------------------------------------------
   Voice selection for the prompt reader.

   The old reader took the first voice matching the language, which on most
   devices is the flat, robotic default — and it read voices synchronously,
   so on the first prompt getVoices() was often still empty and it fell back
   to the system default anyway. This picks a *good* voice: a natural/neural
   cloud voice where one exists, female by default (most students found the
   default male system voice harsh), matched to the accent, and it waits for
   the voice list to actually load before choosing. The student can override
   the choice, and their choice is remembered.
--------------------------------------------------------------------------- */

const VOICE_PREF_KEY = "commiq-voice";

// Name fragments that mark a voice as female or as higher quality. Heuristic
// and case-insensitive — voice names are not standardised across platforms,
// but these cover the common macOS / Chrome / Edge sets.
const FEMALE_HINTS = [
  "female", "samantha", "victoria", "karen", "moira", "tessa", "fiona",
  "serena", "allison", "ava", "susan", "zoe", "zira", "aria", "jenny",
  "michelle", "sonia", "libby", "natasha", "neerja", "heera", "kajal",
  "clara", "hazel", "linda", "emily",
];
const MALE_HINTS = [
  "male", "daniel", "alex", "fred", "david", "guy", "mark", "ryan", "rishi",
  "oliver", "george", "arthur", "thomas", "gordon",
];
const QUALITY_HINTS = ["natural", "neural", "online", "google", "enhanced", "premium"];

// macOS ships a set of novelty voices (singing, robotic, joke). They are real
// SpeechSynthesisVoices but nobody wants a passage read by "Bad News", so they
// are kept out of the picker and never chosen as the default.
const NOVELTY = [
  "albert", "bad news", "bahh", "bells", "boing", "bubbles", "cellos",
  "good news", "jester", "organ", "trinoids", "whisper", "wobble", "zarvox",
  "junior", "grandma", "grandpa", "ralph", "kathy", "fred", "eddy", "flo",
  "rocko", "sandy", "shelley", "superstar", "deranged", "hysterical",
];

function isNovelty(v: SpeechSynthesisVoice): boolean {
  const n = v.name.toLowerCase();
  return NOVELTY.some((h) => n === h || n.startsWith(h + " ") || n.startsWith(h + "("));
}

function wantedLang(accent: string): string {
  return accent === "us" ? "en-US" : accent === "uk" ? "en-GB" : "en-IN";
}

/** Resolve once the browser's voice list is actually populated. */
function loadVoices(): Promise<SpeechSynthesisVoice[]> {
  return new Promise((resolve) => {
    if (typeof window === "undefined" || !window.speechSynthesis) {
      resolve([]);
      return;
    }
    const now = window.speechSynthesis.getVoices();
    if (now.length) {
      resolve(now);
      return;
    }
    // Voices load asynchronously on first use; wait for the event, with a
    // timeout so a device that never fires it still speaks (with a default).
    let done = false;
    const finish = () => {
      if (done) return;
      done = true;
      resolve(window.speechSynthesis.getVoices());
    };
    window.speechSynthesis.addEventListener("voiceschanged", finish, { once: true });
    setTimeout(finish, 500);
  });
}

function scoreVoice(v: SpeechSynthesisVoice, lang: string): number {
  const name = v.name.toLowerCase();
  let score = 0;
  if (v.lang === lang) score += 100;
  else if (v.lang.replace("_", "-").startsWith(lang.slice(0, 2))) score += 45;
  if (QUALITY_HINTS.some((h) => name.includes(h))) score += 30;
  // Female is a strong preference here: enough that a female voice in a nearby
  // English accent is chosen over the harsh male voice that happens to match
  // the exact locale (which is what students were getting).
  if (FEMALE_HINTS.some((h) => name.includes(h))) score += 50;
  if (MALE_HINTS.some((h) => name.includes(h))) score -= 30;
  if (!v.localService) score += 5;   // cloud voices are usually the natural ones
  return score;
}

/** The English voices a student may choose between, best first. */
export async function englishVoices(): Promise<SpeechSynthesisVoice[]> {
  const voices = await loadVoices();
  return voices
    .filter((v) => v.lang.toLowerCase().startsWith("en") && !isNovelty(v))
    .sort((a, b) => scoreVoice(b, "en-IN") - scoreVoice(a, "en-IN"));
}

export function getVoicePreference(): string {
  if (typeof window === "undefined") return "";
  try { return window.localStorage.getItem(VOICE_PREF_KEY) || ""; }
  catch { return ""; }
}

export function setVoicePreference(voiceURI: string): void {
  if (typeof window === "undefined") return;
  try {
    if (voiceURI) window.localStorage.setItem(VOICE_PREF_KEY, voiceURI);
    else window.localStorage.removeItem(VOICE_PREF_KEY);
  } catch { /* storage disabled — the default picker still works this session */ }
}

async function pickVoice(lang: string): Promise<SpeechSynthesisVoice | null> {
  const voices = await loadVoices();
  if (!voices.length) return null;
  const preferred = getVoicePreference();
  if (preferred) {
    const chosen = voices.find((v) => v.voiceURI === preferred);
    if (chosen) return chosen;   // the student's own choice always wins
  }
  let best: SpeechSynthesisVoice | null = null;
  let bestScore = -Infinity;
  for (const v of voices) {
    if (isNovelty(v)) continue;
    const sc = scoreVoice(v, lang);
    if (sc > bestScore) { bestScore = sc; best = v; }
  }
  return best;
}

/** Speak a prompt with the best available voice.
 *
 *  A stand-in for real prompt audio (SIM-06). It waits for the voice list to
 *  load, then prefers a natural, female English voice matched to the accent —
 *  or whichever voice the student picked. An Indian-English voice is preferred
 *  for the default so a student practising for an Indian drive is not trained
 *  only on an American one.
 */
/** Un-park the speech engine from inside a user gesture (a click), so the
 *  prompt that follows a network round-trip still speaks. Chrome is far more
 *  willing to start speech when resume() was last called during a gesture. */
export function primeSpeech(): void {
  try { window.speechSynthesis?.resume(); } catch { /* not available; speak() copes */ }
}

/** Play a real audio clip (the server-rendered prompt) and resolve when it
 *  ends. Returns false if it could not be played -- a decode error, or an
 *  autoplay block -- so the caller can fall back to the browser voice. Unlike
 *  speech synthesis this is deterministic and cannot be parked by the browser.
 */
export async function playAudioUrl(url: string): Promise<boolean> {
  if (typeof window === "undefined" || !url) return false;
  return new Promise<boolean>((resolve) => {
    const audio = new Audio(url);
    let settled = false;
    let guard: ReturnType<typeof setTimeout>;
    const done = (ok: boolean) => {
      if (settled) return;
      settled = true;
      clearTimeout(guard);
      resolve(ok);
    };
    audio.onended = () => done(true);
    audio.onerror = () => done(false);
    // Once the clip's length is known, cap the wait at just past it, so a
    // stuck element can never hold the runner open.
    audio.onloadedmetadata = () => {
      const ms = (Number.isFinite(audio.duration) ? audio.duration : 12) * 1000 + 2000;
      clearTimeout(guard);
      guard = setTimeout(() => done(true), ms);
    };
    guard = setTimeout(() => done(true), 30_000);
    // The Play Audio click is the user gesture; a decode/autoplay failure
    // rejects here and drops us to the browser-voice fallback.
    audio.play().catch(() => done(false));
  });
}

export async function speak(text: string, accent = "indian"): Promise<void> {
  const ss = typeof window !== "undefined" ? window.speechSynthesis : undefined;
  if (!ss || !text) return;
  const voice = await pickVoice(wantedLang(accent));
  return new Promise((resolve) => {
    const utterance = new SpeechSynthesisUtterance(text);
    if (voice) utterance.voice = voice;
    utterance.lang = voice?.lang ?? wantedLang(accent);
    // Slightly slower and a touch higher than default reads as clearer and
    // warmer without sounding sped-up or cartoonish.
    utterance.rate = 0.95;
    utterance.pitch = 1.05;

    // Resolve exactly once, however the utterance ends.
    let settled = false;
    const done = () => { if (!settled) { settled = true; clearTimeout(guard); resolve(); } };
    utterance.onend = done;
    utterance.onerror = done;

    // Chrome parks the speech engine after periods of inactivity and after a
    // getUserMedia session starts; speak() then silently does nothing until
    // resume() is called. cancel() clears any utterance left stuck by a
    // previous item, and resume() un-parks the engine before we queue ours.
    ss.cancel();
    ss.resume();
    ss.speak(utterance);

    // Safety net: if neither onend nor onerror ever fires -- a documented
    // Chrome hang, and the case where the platform has no usable voice -- the
    // runner must not sit on "Playing..." forever. Advance after a duration
    // generous enough for the sentence to have finished if it did play.
    const guard = setTimeout(done, Math.max(4000, text.length * 90));
  });
}

/** The short tone that means "speak now". */
export async function beep(durationMs = 180, frequency = 880): Promise<void> {
  if (typeof window === "undefined") return;
  const Ctor = window.AudioContext ?? (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext;
  const ctx = new Ctor();
  const osc = ctx.createOscillator();
  const gain = ctx.createGain();
  osc.frequency.value = frequency;
  osc.type = "sine";
  // Ramped, not switched: a square edge on a cheap phone speaker clicks.
  gain.gain.setValueAtTime(0.0001, ctx.currentTime);
  gain.gain.exponentialRampToValueAtTime(0.25, ctx.currentTime + 0.02);
  gain.gain.exponentialRampToValueAtTime(0.0001, ctx.currentTime + durationMs / 1000);
  osc.connect(gain).connect(ctx.destination);
  osc.start();
  osc.stop(ctx.currentTime + durationMs / 1000);
  await new Promise((r) => setTimeout(r, durationMs + 40));
  await ctx.close();
}
