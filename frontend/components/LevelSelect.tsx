"use client";
import { BookOpen, Headphones, Mic, PenLine, Zap } from "lucide-react";

export type DifficultyLevel = "" | "easy" | "medium" | "hard";

interface LevelSelectProps {
  skill: "reading" | "listening" | "quiz" | "writing" | "speaking";
  onSelect: (level: DifficultyLevel) => void;
}

const SKILL_CONFIG = {
  reading: { icon: BookOpen, title: "Reading Practice", desc: "Workplace text — emails, notices, reports. Comprehension and reading speed." },
  listening: { icon: Headphones, title: "Listening Practice", desc: "Hear a passage once, then answer questions about it." },
  quiz: { icon: Zap, title: "Quiz", desc: "Grammar, vocabulary and error-spotting — 10 items at a time." },
  writing: { icon: PenLine, title: "Writing Practice", desc: "Real workplace tasks — emails, status reports, summaries." },
  speaking: { icon: Mic, title: "Speaking Practice", desc: "Read aloud, repeat, answer — scored on fluency and pronunciation." },
};

const LEVELS = [
  { value: "" as DifficultyLevel, label: "All Levels", color: "var(--primary)", desc: "Mixed difficulty" },
  { value: "easy" as DifficultyLevel, label: "Easy", color: "var(--rag-green)", desc: "Beginner-friendly" },
  { value: "medium" as DifficultyLevel, label: "Medium", color: "var(--rag-amber)", desc: "Standard difficulty" },
  { value: "hard" as DifficultyLevel, label: "Hard", color: "var(--rag-red)", desc: "Challenging" },
];

export function LevelSelect({ skill, onSelect }: LevelSelectProps) {
  const config = SKILL_CONFIG[skill];
  const Icon = config.icon;

  return (
    <div className="max-w-lg mx-auto space-y-6 py-8">
      {/* Skill header */}
      <div className="text-center space-y-3">
        <div className="w-14 h-14 rounded-full mx-auto flex items-center justify-center"
             style={{ background: "color-mix(in srgb, var(--primary) 12%, transparent)" }}>
          <Icon size={28} style={{ color: "var(--primary)" }} />
        </div>
        <h2 className="text-lg font-bold">{config.title}</h2>
        <p className="text-xs text-muted leading-relaxed">{config.desc}</p>
      </div>

      {/* Difficulty selection */}
      <div className="ds-card p-5 space-y-4">
        <div className="text-sm font-bold">Choose difficulty level</div>
        <p className="text-xs text-muted">
          Select a difficulty or start with all levels mixed together.
          Each set contains 10 questions.
        </p>
        <div className="grid grid-cols-2 gap-3">
          {LEVELS.map((level) => (
            <button
              key={level.value}
              onClick={() => onSelect(level.value)}
              className="p-4 text-left rounded-lg transition-all ds-focus hover:scale-[1.02]"
              style={{
                border: `2px solid ${level.color}`,
                background: `color-mix(in srgb, ${level.color} 8%, var(--surface))`,
              }}
            >
              <div className="text-sm font-bold" style={{ color: level.color }}>
                {level.label}
              </div>
              <div className="text-[11px] text-muted mt-1">{level.desc}</div>
            </button>
          ))}
        </div>
        <div className="text-[10px] text-muted text-center pt-2">
          10 questions per set · Timer active · Camera &amp; mic required
        </div>
      </div>
    </div>
  );
}
