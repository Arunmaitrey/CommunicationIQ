"use client";
import { useEffect, useState } from "react";
import { Volume2 } from "lucide-react";
import {
  englishVoices, getVoicePreference, setVoicePreference, speak,
} from "@/lib/audio";

/** Choose the voice the prompt reader uses, and hear it.
 *
 *  The device default is often the harsh system voice; this lets a student
 *  pick a better one (a natural, female voice is preferred by default) and
 *  preview it. The choice is stored in localStorage and used everywhere the
 *  app speaks — listening practice and the test runner alike — so it is set
 *  once and remembered.
 */
export function VoicePicker({ accent = "indian", sample }: {
  accent?: string; sample?: string;
}) {
  const [voices, setVoices] = useState<SpeechSynthesisVoice[]>([]);
  const [uri, setUri] = useState<string>("");

  useEffect(() => {
    let live = true;
    englishVoices().then((vs) => {
      if (!live) return;
      setVoices(vs);
      setUri(getVoicePreference());
    });
    return () => { live = false; };
  }, []);

  if (voices.length <= 1) return null;   // nothing to choose between

  const preview = () => {
    void speak(sample ?? "This is the voice that will read your passage.", accent);
  };

  return (
    <div className="flex items-center justify-center gap-2 flex-wrap">
      <span className="text-[11px] text-muted">Voice</span>
      <select
        value={uri}
        onChange={(e) => {
          setUri(e.target.value);
          setVoicePreference(e.target.value);
        }}
        className="ds-input ds-focus text-xs py-1"
        style={{ width: "auto", maxWidth: "16rem" }}
      >
        <option value="">Recommended</option>
        {voices.map((v) => (
          <option key={v.voiceURI} value={v.voiceURI}>
            {v.name} ({v.lang})
          </option>
        ))}
      </select>
      <button type="button" onClick={preview}
              className="btn btn-ghost btn-sm ds-focus">
        <Volume2 size={13} /> Preview
      </button>
    </div>
  );
}
