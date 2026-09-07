export interface PersistedProctorState {
  locked: boolean;
  violationCount: number;
  lastViolationType?: string;
  lastViolationAt?: number;
}

const getStorageKey = (examId?: string, candidateId?: string) =>
  `proctor_state:${candidateId || "unknown_candidate"}:${examId || "unknown_exam"}`;

export const readPersistedState = (
  examId?: string,
  candidateId?: string,
): PersistedProctorState | null => {
  try {
    const raw = window.sessionStorage.getItem(getStorageKey(examId, candidateId));
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
};

export const writePersistedState = (
  examId: string | undefined,
  candidateId: string | undefined,
  state: PersistedProctorState,
): void => {
  try {
    window.sessionStorage.setItem(getStorageKey(examId, candidateId), JSON.stringify(state));
  } catch {
    // storage unavailable (quota/private mode) — proctoring still works,
    // it just won't survive a reload.
  }
};

export const clearPersistedState = (examId?: string, candidateId?: string): void => {
  try {
    window.sessionStorage.removeItem(getStorageKey(examId, candidateId));
  } catch {
    // ignore
  }
};
