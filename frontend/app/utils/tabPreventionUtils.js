// Tab switching prevention utilities for tests
import React from 'react';
let isTabPreventionActive = false;
let visibilityHandler = null;
let blurHandler = null;
let beforeUnloadHandler = null;
let contextMenuHandler = null;
let keyHandler = null;
let focusHandler = null;

// Violation tracking
let violationCount = 0;
let autoSubmitCallback = null;
const MAX_VIOLATIONS_BEFORE_SUBMIT = 3;

// Record a violation and trigger auto-submit when threshold is reached
const recordViolation = () => {
  violationCount += 1;
  const remaining = MAX_VIOLATIONS_BEFORE_SUBMIT - violationCount;

  if (violationCount >= MAX_VIOLATIONS_BEFORE_SUBMIT && autoSubmitCallback) {
    showAutoSubmitBanner();
    setTimeout(() => {
      autoSubmitCallback();
    }, 2000);
  } else {
    showTabSwitchWarning(remaining);
  }
};

// Show final auto-submit banner
const showAutoSubmitBanner = () => {
  const existingWarning = document.getElementById('tab-switch-warning');
  if (existingWarning) existingWarning.remove();

  const banner = document.createElement('div');
  banner.id = 'tab-switch-warning';
  banner.innerHTML = `
    <div style="
      position: fixed;
      top: 0; left: 0; right: 0; bottom: 0;
      background: rgba(0,0,0,0.85);
      color: white;
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      z-index: 99999;
      font-family: sans-serif;
      text-align: center;
      padding: 40px;
    ">
      <div style="font-size: 64px; margin-bottom: 20px;">🚫</div>
      <h1 style="font-size: 28px; font-weight: 700; margin-bottom: 12px; color: #ef4444;">Test Auto-Submitted</h1>
      <p style="font-size: 18px; color: #d1d5db; max-width: 480px; line-height: 1.6;">
        You have switched tabs or left the test window ${MAX_VIOLATIONS_BEFORE_SUBMIT} times.<br/>
        Your test has been automatically submitted.
      </p>
      <p style="margin-top: 20px; font-size: 14px; color: #9ca3af;">Please wait...</p>
    </div>
  `;
  document.body.appendChild(banner);
};

// Show warning message when user tries to switch tabs
const showTabSwitchWarning = (remaining) => {
  const existingWarning = document.getElementById('tab-switch-warning');
  if (existingWarning) {
    existingWarning.remove();
  }

  const remainingText = remaining > 0
    ? ` (${remaining} warning${remaining !== 1 ? 's' : ''} left before auto-submit)`
    : '';

  const warning = document.createElement('div');
  warning.id = 'tab-switch-warning';
  warning.innerHTML = `
    <div style="
      position: fixed;
      top: 0;
      left: 0;
      right: 0;
      background: linear-gradient(135deg, #ef4444 0%, #dc2626 100%);
      color: white;
      padding: 12px 20px;
      text-align: center;
      z-index: 9999;
      font-weight: 600;
      font-size: 16px;
      box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
      animation: slideDown 0.3s ease-out;
    ">
      ⚠️ Warning: Tab switching is not allowed during the test!${remainingText}
    </div>
    <style>
      @keyframes slideDown {
        from { transform: translateY(-100%); opacity: 0; }
        to { transform: translateY(0); opacity: 1; }
      }
    </style>
  `;
  
  document.body.appendChild(warning);
  
  // Auto-remove warning after 3 seconds
  setTimeout(() => {
    if (warning && warning.parentNode) {
      warning.style.animation = 'slideDown 0.3s ease-out reverse';
      setTimeout(() => {
        if (warning && warning.parentNode) {
          warning.remove();
        }
      }, 300);
    }
  }, 3000);
};

// Prevent tab switching by blocking visibility change
// onAutoSubmit: optional callback invoked after MAX_VIOLATIONS_BEFORE_SUBMIT violations
export const preventTabSwitching = (onAutoSubmit = null) => {
  if (isTabPreventionActive) return;
  
  isTabPreventionActive = true;
  violationCount = 0;
  autoSubmitCallback = onAutoSubmit;

  // Handle visibility change (tab switching)
  visibilityHandler = () => {
    if (document.hidden) {
      recordViolation();
      
      // Force focus back to the current tab after a short delay
      setTimeout(() => {
        window.focus();
        if (navigator.locks) {
          navigator.locks.request('test-focus', () => {});
        }
      }, 100);
    }
  };

  // Handle window blur (user clicked outside)
  blurHandler = () => {
    recordViolation();
    setTimeout(() => {
      window.focus();
    }, 100);
  };

  // Handle window focus (user came back)
  focusHandler = () => {
    // Clear any existing warnings when user returns
    const existingWarning = document.getElementById('tab-switch-warning');
    if (existingWarning) {
      existingWarning.remove();
    }
  };

  // Handle before unload (refresh, close, navigate away)
  beforeUnloadHandler = (e) => {
    e.preventDefault();
    e.returnValue = 'Are you sure you want to leave? Your test progress will be lost.';
    return e.returnValue;
  };

  // Handle context menu (right-click)
  contextMenuHandler = (e) => {
    e.preventDefault();
    return false;
  };

  // Handle keyboard shortcuts that could lead to tab switching
  keyHandler = (e) => {
    // Block Ctrl+Tab, Ctrl+W, Alt+Tab, F11, Esc
    if (
      (e.ctrlKey && e.key === 'Tab') ||
      (e.ctrlKey && e.key === 'w') ||
      (e.altKey && e.key === 'Tab') ||
      e.key === 'F11' ||
      (e.key === 'Escape' && !e.target.closest('.modal-content'))
    ) {
      e.preventDefault();
      recordViolation();
      return false;
    }

    // Block Ctrl+Shift+T (reopen closed tab)
    if (e.ctrlKey && e.shiftKey && e.key === 'T') {
      e.preventDefault();
      return false;
    }

    // Block Windows key + Tab
    if (e.metaKey && e.key === 'Tab') {
      e.preventDefault();
      return false;
    }
  };

  // Add all event listeners
  document.addEventListener('visibilitychange', visibilityHandler);
  window.addEventListener('blur', blurHandler);
  window.addEventListener('focus', focusHandler);
  window.addEventListener('beforeunload', beforeUnloadHandler);
  document.addEventListener('contextmenu', contextMenuHandler);
  document.addEventListener('keydown', keyHandler);

  // Prevent drag and drop
  document.addEventListener('dragover', (e) => e.preventDefault());
  document.addEventListener('drop', (e) => e.preventDefault());

  // Try to use Page Visibility API more aggressively
  if ('wakeLock' in navigator) {
    navigator.wakeLock.request('screen').catch(() => {
      // Wake lock failed, but that's okay
    });
  }
};

// Remove tab switching prevention
export const allowTabSwitching = () => {
  if (!isTabPreventionActive) return;
  
  isTabPreventionActive = false;
  violationCount = 0;
  autoSubmitCallback = null;

  // Remove all event listeners
  if (visibilityHandler) {
    document.removeEventListener('visibilitychange', visibilityHandler);
    visibilityHandler = null;
  }
  
  if (blurHandler) {
    window.removeEventListener('blur', blurHandler);
    blurHandler = null;
  }
  
  if (focusHandler) {
    window.removeEventListener('focus', focusHandler);
    focusHandler = null;
  }
  
  if (beforeUnloadHandler) {
    window.removeEventListener('beforeunload', beforeUnloadHandler);
    beforeUnloadHandler = null;
  }
  
  if (contextMenuHandler) {
    document.removeEventListener('contextmenu', contextMenuHandler);
    contextMenuHandler = null;
  }
  
  if (keyHandler) {
    document.removeEventListener('keydown', keyHandler);
    keyHandler = null;
  }

  // Remove any existing warning
  const existingWarning = document.getElementById('tab-switch-warning');
  if (existingWarning) {
    existingWarning.remove();
  }

  // Release wake lock if it was acquired
  if ('wakeLock' in navigator) {
    // Wake lock is automatically released when the page is hidden
  }
};

// Check if tab prevention is currently active
export const isTabPreventionEnabled = () => isTabPreventionActive;

// Get current violation count
export const getViolationCount = () => violationCount;

// Custom hook for React components
// onAutoSubmit: called after MAX_VIOLATIONS_BEFORE_SUBMIT violations
export const useTabPrevention = (shouldPrevent = true, onAutoSubmit = null) => {
  React.useEffect(() => {
    if (shouldPrevent) {
      preventTabSwitching(onAutoSubmit);
    } else {
      allowTabSwitching();
    }

    return () => {
      allowTabSwitching();
    };
  }, [shouldPrevent]);
};
