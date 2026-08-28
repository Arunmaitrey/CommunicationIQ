"use client";
import { createContext, useCallback, useContext, useEffect, useState, useRef, ReactNode } from "react";
import { usePathname } from "next/navigation";
import { LOADING_SHOW, LOADING_HIDE } from "@/lib/api";

interface LoadingCtx {
  loading: boolean;
  show: () => void;
  hide: () => void;
}

const LoadingCtx = createContext<LoadingCtx>({
  loading: false,
  show: () => {},
  hide: () => {},
});

export function useLoading() {
  return useContext(LoadingCtx);
}

export function LoadingProvider({ children }: { children: ReactNode }) {
  const [loading, setLoading] = useState(false);
  const countRef = useRef(0);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const pathname = usePathname();
  const prevPathRef = useRef(pathname);

  const show = useCallback(() => {
    countRef.current++;
    if (timerRef.current) clearTimeout(timerRef.current);
    setLoading(true);
    timerRef.current = setTimeout(() => {
      countRef.current = 0;
      setLoading(false);
    }, 8000);
  }, []);

  const hide = useCallback(() => {
    countRef.current = Math.max(0, countRef.current - 1);
    if (countRef.current === 0) {
      if (timerRef.current) clearTimeout(timerRef.current);
      setLoading(false);
    }
  }, []);

  // Listen to API loading events
  useEffect(() => {
    const onShow = () => show();
    const onHide = () => hide();
    window.addEventListener(LOADING_SHOW, onShow);
    window.addEventListener(LOADING_HIDE, onHide);
    return () => {
      window.removeEventListener(LOADING_SHOW, onShow);
      window.removeEventListener(LOADING_HIDE, onHide);
    };
  }, [show, hide]);

  // Auto-show on route changes
  useEffect(() => {
    if (prevPathRef.current !== pathname) {
      prevPathRef.current = pathname;
      setLoading(true);
      const t = setTimeout(() => setLoading(false), 400);
      return () => clearTimeout(t);
    }
  }, [pathname]);

  return (
    <LoadingCtx.Provider value={{ loading, show, hide }}>
      {children}
      {loading && (
        <div className="loading-overlay" role="status" aria-label="Loading">
          <div className="loading-overlay__spinner" />
          <div className="loading-overlay__text">Loading...</div>
        </div>
      )}
    </LoadingCtx.Provider>
  );
}
