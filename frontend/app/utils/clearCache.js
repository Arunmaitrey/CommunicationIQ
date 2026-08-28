export const clearQuestionCache = () => {
  try {
    // Clear localStorage items related to questions
    const keysToRemove = [];
    for (let i = 0; i < localStorage.length; i++) {
      const key = localStorage.key(i);
      if (key && (key.includes('question') || key.includes('reading') || key.includes('questionnaire'))) {
        keysToRemove.push(key);
      }
    }
    keysToRemove.forEach(key => localStorage.removeItem(key));
    
    // Clear sessionStorage items related to questions
    const sessionKeysToRemove = [];
    for (let i = 0; i < sessionStorage.length; i++) {
      const key = sessionStorage.key(i);
      if (key && (key.includes('question') || key.includes('reading') || key.includes('questionnaire'))) {
        sessionKeysToRemove.push(key);
      }
    }
    sessionKeysToRemove.forEach(key => sessionStorage.removeItem(key));
    
    console.log('🧹 Cleared question cache:', keysToRemove.length + sessionKeysToRemove.length, 'items removed');
  } catch (error) {
    console.error('Error clearing cache:', error);
  }
};

export const forceRefresh = () => {
  clearQuestionCache();
  // Force a hard refresh
  window.location.reload(true);
};
