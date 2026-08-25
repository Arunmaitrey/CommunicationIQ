"use client";
import { useEffect, useRef, useState } from "react";
import { AlertCircle, Loader2, Pause, Play } from "lucide-react";
import { ApiError, attemptApi, type ResponseMetrics } from "@/lib/api";

/** Annotated listen-back (DIAG-02).
 *
 *  A number tells a student they paused too much. This lets them hear it: the
 *  pauses are drawn as gaps on the timeline, the transcript follows the
 *  playhead word by word, fillers are marked where they fell, and tapping any
 *  word jumps the audio to it.
 *
 *  It is the student's own recording and nobody else's — there is no staff
 *  route to this audio, by design.
 */
export function ListenBack({ attemptId, item }: {
  attemptId: string;
  item: ResponseMetrics;
}) {
  const [url, setUrl] = useState<string>("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [playing, setPlaying] = useState(false);
  const [positionMs, setPositionMs] = useState(0);

  const audio = useRef<HTMLAudioElement | null>(null);

  useEffect(() => {
    let objectUrl = "";
    let live = true;
    attemptApi.audioBlobUrl(attemptId, item.response_id)
      .then((u) => {
        objectUrl = u;
        if (live) setUrl(u);
        else URL.revokeObjectURL(u);
      })
      .catch((err) => {
        if (live) setError(err instanceof ApiError ? err.detail : "Could not load the recording");
      })
      .finally(() => { if (live) setLoading(false); });
    return () => {
      live = false;
      // The blob stays in memory until it is revoked, and a report with eight
      // items would otherwise hold eight recordings open.
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [attemptId, item.response_id]);

  const duration = item.duration_ms ?? 0;

  function toggle() {
    const el = audio.current;
    if (!el) return;
    if (el.paused) { void el.play(); } else { el.pause(); }
  }

  function seekTo(ms: number) {
    const el = audio.current;
    if (!el) return;
    el.currentTime = ms / 1000;
    setPositionMs(ms);
    if (el.paused) void el.play();
  }

  if (loading) {
    return (
      <div className="flex items-center gap-2 text-[11px] text-muted py-3">
        <Loader2 size={13} className="animate-spin" /> Loading your recording…
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex items-start gap-2 text-[11px] text-muted py-3">
        <AlertCircle size={13} className="shrink-0 mt-0.5" style={{ color: "var(--rag-amber)" }} />
        <span>{error}</span>
      </div>
    );
  }

  const fillerAt = new Map<number, string>();
  for (const event of item.disfluencies) fillerAt.set(event.start_ms, event.type);

  return (
    <div className="pt-3">
      <audio
        ref={audio}
        src={url}
        onPlay={() => setPlaying(true)}
        onPause={() => setPlaying(false)}
        onEnded={() => { setPlaying(false); setPositionMs(0); }}
        onTimeUpdate={(e) => setPositionMs(e.currentTarget.currentTime * 1000)}
        preload="metadata"
      />

      <div className="flex items-center gap-3 mb-3">
        <button onClick={toggle} className="btn btn-soft btn-sm ds-focus" aria-label={playing ? "Pause" : "Play"}>
          {playing ? <Pause size={13} /> : <Play size={13} />}
          {playing ? "Pause" : "Play back"}
        </button>
        <span className="text-[11px] text-muted tabular-nums">
          {(positionMs / 1000).toFixed(1)}s / {(duration / 1000).toFixed(1)}s
        </span>
      </div>

      {/* The timeline. Silence before the first word is the response delay;
          gaps inside it are pauses. They are different problems with different
          fixes, so they are drawn differently. */}
      <div
        className="wave ds-inset mb-3"
        style={{ height: 40, cursor: duration ? "pointer" : "default" }}
        onClick={(e) => {
          if (!duration) return;
          const box = e.currentTarget.getBoundingClientRect();
          seekTo(((e.clientX - box.left) / box.width) * duration);
        }}
      >
        {item.onset_ms != null && item.onset_ms > 0 && duration > 0 && (
          <span
            className="absolute top-0 bottom-0"
            title={`${(item.onset_ms / 1000).toFixed(1)}s before you started`}
            style={{
              left: 0,
              width: `${Math.min(100, (item.onset_ms / duration) * 100)}%`,
              background: "color-mix(in srgb, var(--muted) 18%, transparent)",
            }}
          />
        )}
        {duration > 0 && item.pauses.map((pause, i) => (
          <span
            key={i}
            className="wave-pause"
            title={`${(pause.ms / 1000).toFixed(1)}s pause`}
            style={{
              left: `${(pause.start_ms / duration) * 100}%`,
              width: `${Math.max(0.6, (pause.ms / duration) * 100)}%`,
            }}
          />
        ))}
        {duration > 0 && (
          <span className="wave-cursor" style={{ left: `${(positionMs / duration) * 100}%` }} />
        )}
      </div>

      {item.words.length > 0 ? (
        <p className="text-xs leading-7">
          {item.words.map((word, i) => {
            const current = positionMs >= word.start_ms && positionMs < word.end_ms;
            const filler = fillerAt.has(word.start_ms);
            return (
              <span
                key={`${word.start_ms}-${i}`}
                onClick={() => seekTo(word.start_ms)}
                className={`transcript-word ${filler ? "transcript-filler" : ""}`}
                style={current
                  ? { background: "color-mix(in srgb, var(--primary) 22%, transparent)",
                      fontWeight: 700 }
                  : undefined}
                title={filler
                  ? `${fillerAt.get(word.start_ms)} · tap to hear`
                  : `${(word.start_ms / 1000).toFixed(1)}s · tap to hear`}
              >
                {word.word}{" "}
              </span>
            );
          })}
        </p>
      ) : (
        <p className="text-[11px] text-muted">
          No transcript for this answer — nothing was recognised in the recording.
        </p>
      )}

      {item.word_errors.some((e) => describe(e)) && (
        <div className="mt-3 pt-3 border-t border-border">
          <div className="text-[10px] font-bold uppercase tracking-wide text-muted mb-1.5">
            Against the sentence you were given
          </div>
          <div className="flex flex-wrap gap-1.5">
            {item.word_errors.filter((e) => describe(e)).slice(0, 12).map((err, i) => (
              <span key={i} className="chip"
                    style={{ background: "color-mix(in srgb, var(--rag-red) 12%, transparent)",
                             color: "var(--rag-red)" }}>
                {/* Sentence Build reports one word_order error rather than a
                    pile of substitutions. The words were right; where they
                    went was not, and saying "you said 'request' where 'the'
                    was expected" describes a mistake nobody made.

                    The final branch used to be reached by every chip, because
                    this panel was fed per-word clarity scores that carry no
                    `kind`, no `expected` and no `heard`. It rendered
                    "undefined" -> "undefined", twelve times, under a heading
                    promising a comparison. `describe` refuses to do that. */}
                {describe(err)}
              </span>
            ))}
          </div>
          {item.word_errors.some((e) => e.kind === "word_order") && (
            <div className="text-[10px] text-muted mt-1.5 leading-relaxed">
              Asked for: {item.word_errors.find((e) => e.kind === "word_order")?.expected}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

/** One word-accuracy finding, in the candidate's terms.
 *
 *  Returns empty for anything that is not one. This panel was fed the wrong
 *  measurement for a long time -- per-word clarity scores, which have no
 *  `kind`, no `expected` and no `heard` -- and every chip fell through to the
 *  substitution template and rendered `"undefined" → "undefined"` under a
 *  heading promising a comparison against the sentence.
 *
 *  So the shape is checked rather than assumed. A finding that does not name
 *  what was expected or what was heard is not a finding this panel can
 *  describe, and showing nothing is strictly better than showing "undefined".
 */
export function describe(err: {
  kind?: string; expected?: string; heard?: string;
}): string {
  if (err.kind === "word_order") return "the words were right, the order was not";
  if (err.kind === "deletion" && err.expected) return `missed "${err.expected}"`;
  if (err.kind === "insertion" && err.heard) return `added "${err.heard}"`;
  if (err.expected && err.heard) return `"${err.expected}" → "${err.heard}"`;
  return "";
}
