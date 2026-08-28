const getStorageKey = (examId) => `proctor_state:${examId || 'unknown_exam'}`;

export const readPersistedState = (examId) => {
  try {
    const raw = window.sessionStorage.getItem(getStorageKey(examId));
    return raw ? JSON.parse(raw) : null;
  } catch (error) {
    return null;
  }
};

export const writePersistedState = (examId, state) => {
  try {
    window.sessionStorage.setItem(getStorageKey(examId), JSON.stringify(state));
  } catch (error) {
    // storage unavailable (quota/private mode) — proctoring still works,
    // it just won't survive a reload.
  }
};

export const clearPersistedState = (examId) => {
  try {
    window.sessionStorage.removeItem(getStorageKey(examId));
  } catch (error) {
    // ignore
  }
};
