// const getStorageKey = (examId) => `proctor_state:${examId || 'unknown_exam'}`;

// export const readPersistedState = (examId) => {
//   try {
//     const raw = window.sessionStorage.getItem(getStorageKey(examId));
//     return raw ? JSON.parse(raw) : null;
//   } catch (error) {
//     return null;
//   }
// };

// export const writePersistedState = (examId, state) => {
//   try {
//     window.sessionStorage.setItem(getStorageKey(examId), JSON.stringify(state));
//   } catch (error) {
//     // storage unavailable (quota/private mode) — proctoring still works,
//     // it just won't survive a reload.
//   }
// };

// export const clearPersistedState = (examId) => {
//   try {
//     window.sessionStorage.removeItem(getStorageKey(examId));
//   } catch (error) {
//     // ignore
//   }
// };
const getStorageKey = (examId, candidateId) =>
  `proctor_state:${candidateId || 'unknown_candidate'}:${examId || 'unknown_exam'}`;

export const readPersistedState = (examId, candidateId) => {
  try {
    const raw = window.sessionStorage.getItem(getStorageKey(examId, candidateId));
    return raw ? JSON.parse(raw) : null;
  } catch (error) {
    return null;
  }
};

export const writePersistedState = (examId, candidateId, state) => {
  try {
    window.sessionStorage.setItem(getStorageKey(examId, candidateId), JSON.stringify(state));
  } catch (error) {
    // storage unavailable (quota/private mode) — proctoring still works,
    // it just won't survive a reload.
  }
};

export const clearPersistedState = (examId, candidateId) => {
  try {
    window.sessionStorage.removeItem(getStorageKey(examId, candidateId));
  } catch (error) {
    // ignore
  }
};
