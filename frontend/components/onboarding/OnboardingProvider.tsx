"use client";
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { api } from "@/lib/api";
import { useRole } from "@/components/RoleProvider";
import { tourStepsFor, type TourStep } from "./tourSteps";

interface OnboardingCtx {
  /** Whether there's any tour content for this account's role. */
  available: boolean;
  steps: TourStep[];
  welcomeOpen: boolean;
  tourActive: boolean;
  stepIndex: number;
  startTour: () => void;
  skipTour: () => void;
  nextStep: () => void;
  prevStep: () => void;
  finishTour: () => void;
  dismissWelcome: () => void;
  /** Reopens the tour on demand — from Settings or the header help menu.
   *  Does not touch onboarding_completed on its own; finishing or skipping
   *  the replay marks it complete again, which is a harmless no-op for an
   *  account that was already onboarded. */
  restartTour: () => void;
}

const Ctx = createContext<OnboardingCtx | null>(null);

export function OnboardingProvider({ children }: { children: ReactNode }) {
  const { user, loading, refresh } = useRole();
  const steps = useMemo(() => tourStepsFor(user?.role), [user?.role]);
  const available = steps.length > 0;

  const [welcomeOpen, setWelcomeOpen] = useState(false);
  const [tourActive, setTourActive] = useState(false);
  const [stepIndex, setStepIndex] = useState(0);

  // Auto-show the welcome screen exactly once per account: the first time a
  // fresh SessionUser with onboarding_completed === false loads. Waiting on
  // `loading` avoids a flash before we know who's signed in.
  useEffect(() => {
    if (loading || !user) return;
    if (available && !user.onboarding_completed) {
      setWelcomeOpen(true);
    }
  }, [loading, user, available]);

  const markComplete = useCallback(() => {
    // The save has to land before the session re-fetch, or refresh() can
    // read back the pre-save onboarding_completed=false and the auto-show
    // effect above reopens the welcome modal right after closing it.
    // Best-effort otherwise: a failed save shouldn't trap the user in
    // onboarding UI they've already dismissed — worst case they see the
    // welcome screen again next login, which is annoying but never blocking.
    void (async () => {
      try {
        await api.completeOnboarding();
      } catch {
        /* see comment above */
      }
      await refresh();
    })();
  }, [refresh]);

  const startTour = useCallback(() => {
    setWelcomeOpen(false);
    setStepIndex(0);
    setTourActive(true);
  }, []);

  const finishTour = useCallback(() => {
    setTourActive(false);
    setWelcomeOpen(false);
    markComplete();
  }, [markComplete]);

  const skipTour = useCallback(() => {
    finishTour();
  }, [finishTour]);

  const nextStep = useCallback(() => {
    setStepIndex((i) => {
      if (i + 1 >= steps.length) {
        finishTour();
        return i;
      }
      return i + 1;
    });
  }, [steps.length, finishTour]);

  const prevStep = useCallback(() => {
    setStepIndex((i) => Math.max(0, i - 1));
  }, []);

  const dismissWelcome = useCallback(() => {
    setWelcomeOpen(false);
    markComplete();
  }, [markComplete]);

  const restartTour = useCallback(() => {
    setWelcomeOpen(false);
    setStepIndex(0);
    setTourActive(true);
  }, []);

  return (
    <Ctx.Provider value={{
      available, steps, welcomeOpen, tourActive, stepIndex,
      startTour, skipTour, nextStep, prevStep, finishTour, dismissWelcome, restartTour,
    }}>
      {children}
    </Ctx.Provider>
  );
}

export function useOnboarding(): OnboardingCtx {
  const ctx = useContext(Ctx);
  if (!ctx) {
    throw new Error("useOnboarding must be used within OnboardingProvider");
  }
  return ctx;
}
