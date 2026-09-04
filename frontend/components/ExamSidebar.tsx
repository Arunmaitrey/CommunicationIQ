"use client";
import { ReactNode, useEffect, useRef, useState } from "react";
import { AlertTriangle, Check, HelpCircle, X } from "lucide-react";

/**
 * Professional exam sidebar — matches the standard exam interface pattern:
 *
 * Top bar:
 *   - Section tabs (Section 1, Section 2)
 *   - Time Left display
 *   - Instructions button (? icon)
 *   - Marks info
 *
 * Right sidebar panel:
 *   - Legend: Answered (green), Not Answered (red), Not Visited (grey),
 *     Marked for Review (purple), Answered & Marked for Review
 *   - Question grid with numbered boxes
 *   - Current question highlighted
 *   - Clickable to navigate
 *
 * Used for ALL practice modes: reading, listening, quiz, writing, speaking.
 */

export interface ExamQuestionStatus {
  id: string;
  index: number; // 1-based
  answered: boolean;
  selectedOption: number | null;
  markedForReview?: boolean;
}

interface ExamSidebarProps {
  questions: ExamQuestionStatus[];
  currentIndex: number;
  totalQuestions: number;
  sectionTitle?: string;
  companyLabel?: string;
  timeRemaining?: string;
  totalSecondsRemaining?: number;
  onNavigate: (index: number) => void;
  children: ReactNode;
  showInstructions?: boolean;
  onToggleInstructions?: () => void;
  instructions?: string;
  collapsed?: boolean;
  onEndExam?: () => void;
}

function playWarningSound(frequency: number = 800, duration: number = 200) {
  try {
    const ctx = new (window.AudioContext || (window as any).webkitAudioContext)();
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.connect(gain);
    gain.connect(ctx.destination);
    osc.frequency.value = frequency;
    osc.type = "sine";
    gain.gain.setValueAtTime(0.3, ctx.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.01, ctx.currentTime + duration / 1000);
    osc.start(ctx.currentTime);
    osc.stop(ctx.currentTime + duration / 1000);
    osc.onended = () => ctx.close();
  } catch {}
}

export function ExamSidebar({
  questions,
  currentIndex,
  totalQuestions,
  sectionTitle,
  companyLabel,
  timeRemaining,
  totalSecondsRemaining,
  onNavigate,
  children,
  showInstructions = false,
  onToggleInstructions,
  instructions,
  collapsed = false,
  onEndExam,
}: ExamSidebarProps) {
  const answeredCount = questions.filter((q) => q.answered).length;
  const notVisited = questions.filter((q) => !q.answered && q.index - 1 > currentIndex).length;
  const markedCount = questions.filter((q) => q.markedForReview).length;
  const [warningLevel, setWarningLevel] = useState<"none" | "10min" | "5min" | "1min">("none");
  const lastWarningRef = useRef<"none" | "10min" | "5min" | "1min">("none");

  useEffect(() => {
    if (totalSecondsRemaining === undefined) return;
    let newLevel: "none" | "10min" | "5min" | "1min" = "none";
    if (totalSecondsRemaining <= 60) newLevel = "1min";
    else if (totalSecondsRemaining <= 300) newLevel = "5min";
    else if (totalSecondsRemaining <= 600) newLevel = "10min";

    if (newLevel !== lastWarningRef.current && newLevel !== "none") {
      lastWarningRef.current = newLevel;
      if (newLevel === "10min") playWarningSound(600, 150);
      else if (newLevel === "5min") { playWarningSound(800, 200); setTimeout(() => playWarningSound(800, 200), 250); }
      else if (newLevel === "1min") { playWarningSound(1000, 300); setTimeout(() => playWarningSound(1000, 300), 350); setTimeout(() => playWarningSound(1000, 300), 700); }
    }
    setWarningLevel(newLevel);
  }, [totalSecondsRemaining]);

  const getTimerStyle = () => {
    if (warningLevel === "1min") return { background: "var(--rag-red)", color: "#fff" };
    if (warningLevel === "5min") return { background: "color-mix(in srgb, var(--rag-amber) 20%, var(--surface))", color: "var(--rag-amber)", border: "1.5px solid var(--rag-amber)" };
    if (warningLevel === "10min") return { background: "color-mix(in srgb, var(--rag-amber) 10%, var(--surface))", color: "var(--rag-amber)" };
    return {};
  };

  // Collapsed mode — minimal top bar for practice
  if (collapsed) {
    return (
      <div className="min-h-[calc(100vh-80px)]">
        <div className="sticky top-0 z-40 flex items-center justify-between px-4 py-2 border-b border-border bg-surface/95 backdrop-blur-sm" style={{ boxShadow: '0 2px 8px rgba(0,0,0,0.06)' }}>
          <div className="flex items-center gap-3">
            <span className="text-xs font-bold">{currentIndex + 1} / {totalQuestions}</span>
            <div className="flex gap-1">
              {questions.map((q, i) => (
                <span key={q.id} className="rounded-full transition-all" style={{
                  width: i === currentIndex ? 10 : 8, height: i === currentIndex ? 10 : 8,
                  background: q.answered ? "var(--rag-green)" : i === currentIndex ? "var(--primary)" : "var(--surface-2)",
                  border: q.answered || i === currentIndex ? "none" : "1.5px solid var(--border)",
                }} />
              ))}
            </div>
            {sectionTitle && <span className="text-[10px] font-semibold text-muted uppercase tracking-wider hidden sm:inline">{sectionTitle}</span>}
            {companyLabel && (
              <span className="text-[10px] font-semibold px-2 py-0.5 rounded-full hidden sm:inline-block" style={{
                background: companyLabel.startsWith("Company") ? "color-mix(in srgb, var(--secondary) 14%, transparent)" : "color-mix(in srgb, var(--primary) 14%, transparent)",
                color: companyLabel.startsWith("Company") ? "var(--secondary)" : "var(--primary)",
              }}>{companyLabel}</span>
            )}
          </div>
          <div className="flex items-center gap-3">
            {onToggleInstructions && (
              <button onClick={onToggleInstructions} className="w-7 h-7 rounded-full flex items-center justify-center transition-colors" style={{ background: showInstructions ? "var(--primary)" : "var(--surface-2)", color: showInstructions ? "#fff" : "var(--muted)" }} title="Instructions">
                <HelpCircle size={14} />
              </button>
            )}
            {timeRemaining && (
              <span className={`text-sm font-bold tabular-nums px-2 py-1 rounded ${warningLevel === "1min" ? "countdown-critical" : warningLevel === "5min" ? "countdown-warn" : ""}`} style={getTimerStyle()}>
                {timeRemaining}
              </span>
            )}
            {onEndExam && (
              <button onClick={onEndExam} className="text-[10px] font-semibold px-3 py-1 rounded-lg" style={{ background: "color-mix(in srgb, var(--rag-red) 10%, var(--surface))", color: "var(--rag-red)" }}>
                End Exam
              </button>
            )}
          </div>
        </div>
        {showInstructions && instructions && (
          <div className="mx-4 mt-2 p-3 rounded-lg text-[11px] text-muted leading-relaxed" style={{ background: "color-mix(in srgb, var(--primary) 8%, var(--surface-2))" }}>
            {instructions}
          </div>
        )}
        {warningLevel !== "none" && (
          <div className="mx-4 mt-2 p-2 rounded-lg flex items-center gap-2 text-[11px] font-semibold" style={{
            background: warningLevel === "1min" ? "color-mix(in srgb, var(--rag-red) 15%, var(--surface))" : "color-mix(in srgb, var(--rag-amber) 15%, var(--surface))",
            color: warningLevel === "1min" ? "var(--rag-red)" : "var(--rag-amber)",
            border: `1.5px solid ${warningLevel === "1min" ? "var(--rag-red)" : "var(--rag-amber)"}`,
          }}>
            <AlertTriangle size={14} />
            <span>{warningLevel === "1min" && "Less than 1 minute remaining!"}{warningLevel === "5min" && "5 minutes remaining!"}{warningLevel === "10min" && "10 minutes remaining"}</span>
          </div>
        )}
        <div className="p-6">{children}</div>
      </div>
    );
  }

  // Full sidebar mode — professional exam interface (fullscreen overlay)
  return (
    <div className="fixed inset-0 z-50 flex bg-surface">
      {/* Main content area (left) */}
      <div className="flex-1 min-w-0 flex flex-col">
        {/* Top bar */}
        <div className="sticky top-0 z-40 border-b border-border bg-surface/95 backdrop-blur-sm">
          <div className="flex items-center justify-between px-4 py-2">
            <div className="flex items-center gap-4">
              {sectionTitle && (
                <div className="flex items-center gap-2">
                  <span className="text-xs font-bold px-3 py-1 rounded" style={{ background: "var(--primary)", color: "#fff" }}>
                    {sectionTitle}
                  </span>
                </div>
              )}
              {companyLabel && (
                <span className="text-[10px] font-semibold px-2 py-0.5 rounded-full" style={{
                  background: companyLabel.startsWith("Company") ? "color-mix(in srgb, var(--secondary) 14%, transparent)" : "color-mix(in srgb, var(--primary) 14%, transparent)",
                  color: companyLabel.startsWith("Company") ? "var(--secondary)" : "var(--primary)",
                }}>{companyLabel}</span>
              )}
            </div>
            <div className="flex items-center gap-3">
              {timeRemaining && (
                <div className="flex items-center gap-2">
                  <span className="text-[10px] text-muted font-semibold">Time Left</span>
                  <span className={`text-sm font-bold tabular-nums px-3 py-1 rounded ${warningLevel === "1min" ? "countdown-critical" : warningLevel === "5min" ? "countdown-warn" : ""}`} style={getTimerStyle()}>
                    {timeRemaining}
                  </span>
                </div>
              )}
              {onToggleInstructions && (
                <button onClick={onToggleInstructions} className="flex items-center gap-1.5 text-[10px] font-semibold px-2 py-1 rounded transition-colors" style={{ background: showInstructions ? "var(--primary)" : "var(--surface-2)", color: showInstructions ? "#fff" : "var(--muted)" }} title="Instructions">
                  <HelpCircle size={12} /> Instructions
                </button>
              )}
              {onEndExam && (
                <button onClick={onEndExam} className="text-[10px] font-semibold px-3 py-1 rounded-lg" style={{ background: "color-mix(in srgb, var(--rag-red) 10%, var(--surface))", color: "var(--rag-red)" }}>
                  End Exam
                </button>
              )}
            </div>
          </div>
          {showInstructions && instructions && (
            <div className="px-4 pb-3">
              <div className="p-3 rounded-lg text-[11px] text-muted leading-relaxed" style={{ background: "color-mix(in srgb, var(--primary) 8%, var(--surface-2))" }}>
                {instructions}
              </div>
            </div>
          )}
          {warningLevel !== "none" && (
            <div className="px-4 pb-2">
              <div className="p-2 rounded-lg flex items-center gap-2 text-[11px] font-semibold" style={{
                background: warningLevel === "1min" ? "color-mix(in srgb, var(--rag-red) 15%, var(--surface))" : "color-mix(in srgb, var(--rag-amber) 15%, var(--surface))",
                color: warningLevel === "1min" ? "var(--rag-red)" : "var(--rag-amber)",
                border: `1.5px solid ${warningLevel === "1min" ? "var(--rag-red)" : "var(--rag-amber)"}`,
              }}>
                <AlertTriangle size={14} />
                <span>{warningLevel === "1min" && "Less than 1 minute remaining!"}{warningLevel === "5min" && "5 minutes remaining!"}{warningLevel === "10min" && "10 minutes remaining"}</span>
              </div>
            </div>
          )}
        </div>

        {/* Question content */}
        <div className="flex-1 overflow-y-auto thin-scroll p-6 pt-8">{children}</div>
      </div>

      {/* Right sidebar panel */}
      <div className="w-60 shrink-0 border-l border-border bg-surface flex flex-col h-full">
        {/* Legend */}
        <div className="p-3 border-b border-border space-y-1.5">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-1.5">
              <span className="w-4 h-4 rounded flex items-center justify-center" style={{ background: "var(--rag-green)" }}>
                <Check size={10} color="#fff" />
              </span>
              <span className="text-[10px] font-semibold">Answered</span>
            </div>
            <span className="text-[10px] font-bold" style={{ color: "var(--rag-green)" }}>{answeredCount}</span>
          </div>
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-1.5">
              <span className="w-4 h-4 rounded" style={{ background: "var(--rag-red)" }} />
              <span className="text-[10px] font-semibold">Not Answered</span>
            </div>
            <span className="text-[10px] font-bold" style={{ color: "var(--rag-red)" }}>{totalQuestions - answeredCount}</span>
          </div>
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-1.5">
              <span className="w-4 h-4 rounded" style={{ background: "var(--surface-2)", border: "1.5px solid var(--border)" }} />
              <span className="text-[10px] font-semibold">Not Visited</span>
            </div>
            <span className="text-[10px] font-bold text-muted">{notVisited}</span>
          </div>
          {markedCount > 0 && (
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-1.5">
                <span className="w-4 h-4 rounded" style={{ background: "var(--secondary)" }} />
                <span className="text-[10px] font-semibold">Marked for Review</span>
              </div>
              <span className="text-[10px] font-bold" style={{ color: "var(--secondary)" }}>{markedCount}</span>
            </div>
          )}
        </div>

        {/* Section label */}
        <div className="px-3 py-2 border-b border-border">
          <span className="text-[10px] font-bold uppercase tracking-wider" style={{ color: "var(--primary)" }}>
            {sectionTitle || "Section 1"}
          </span>
        </div>

        {/* Question grid */}
        <div className="flex-1 p-3 overflow-y-auto thin-scroll">
          <div className="text-[10px] font-semibold text-muted mb-2">Choose a Question</div>
          <div className="grid grid-cols-4 gap-1.5">
            {questions.map((q) => {
              const isCurrent = q.index - 1 === currentIndex;
              const isAnswered = q.answered;
              const isFuture = q.index - 1 > currentIndex;

              return (
                <button
                  key={q.id}
                  onClick={() => {
                    if (isFuture) onNavigate(q.index - 1);
                  }}
                  disabled={!isFuture}
                  className="relative w-full aspect-square rounded flex items-center justify-center text-[11px] font-bold transition-all"
                  style={{
                    background: isCurrent
                      ? "var(--rag-red)"
                      : isAnswered
                      ? "var(--rag-green)"
                      : "var(--surface-2)",
                    color: isCurrent || isAnswered ? "#fff" : "var(--muted)",
                    border: isCurrent ? "2px solid var(--rag-red)" : isAnswered ? "none" : "1.5px solid var(--border)",
                    cursor: isFuture ? "pointer" : "default",
                    boxShadow: isCurrent ? "0 2px 8px rgba(0,0,0,0.15)" : "none",
                  }}
                >
                  {isAnswered && !isCurrent ? (
                    <Check size={11} />
                  ) : (
                    q.index
                  )}
                </button>
              );
            })}
          </div>
        </div>

        {/* Marks info */}
        <div className="p-3 border-t border-border text-center">
          <div className="text-[9px] text-muted">
            Marks for correct answer: <span className="font-bold" style={{ color: "var(--rag-green)" }}>1.0</span>
            {" | "}
            Negative Marks: <span className="font-bold" style={{ color: "var(--rag-red)" }}>0.0</span>
          </div>
        </div>
      </div>
    </div>
  );
}
