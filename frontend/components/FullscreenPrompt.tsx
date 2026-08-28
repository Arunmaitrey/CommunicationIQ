"use client";
import { Maximize2 } from "lucide-react";

/**
 * Fullscreen intro screen shown before starting a practice or exam session.
 * Asks the user to enter fullscreen mode for the best experience.
 */
export function FullscreenPrompt({ onStart }: { onStart: (fullscreen: boolean) => void }) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center" style={{ background: "var(--bg)" }}>
      <div className="max-w-sm text-center space-y-4 p-6">
        <div className="w-12 h-12 rounded-full mx-auto flex items-center justify-center"
             style={{ background: "color-mix(in srgb, var(--primary) 12%, transparent)" }}>
          <Maximize2 size={24} style={{ color: "var(--primary)" }} />
        </div>
        <h2 className="text-base font-bold">Ready to begin</h2>
        <p className="text-xs text-muted leading-relaxed">
          This session works best in fullscreen mode. It hides browser tabs and
          distractions so you can focus.
        </p>
        <div className="flex flex-col gap-2">
          <button
            onClick={() => {
              document.documentElement.requestFullscreen()
                .then(() => onStart(true))
                .catch(() => onStart(false));
            }}
            className="btn btn-primary w-full ds-focus"
          >
            <Maximize2 size={15} />
            Enter fullscreen and start
          </button>
          <button
            onClick={() => onStart(false)}
            className="btn btn-ghost w-full ds-focus text-muted"
          >
            Start without fullscreen
          </button>
        </div>
        <p className="text-[10px] text-muted">
          You can toggle fullscreen at any time during the session.
        </p>
      </div>
    </div>
  );
}
