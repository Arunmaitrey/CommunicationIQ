"use client";
import { createContext, useCallback, useContext, useEffect, useState, ReactNode } from "react";
import { api, resetSessionExpiry, setToken, type SessionUser } from "@/lib/api";
import { IDENTITY_EVENT } from "@/components/ThemeProvider";

/** The signed-in account, kept where the theme can find it.
 *
 *  The identity is mirrored into localStorage under "commiq.identity" purely
 *  so ThemeProvider can key a theme per account without importing this file —
 *  the theme has to apply before any provider tree renders. */
const IDENTITY_KEY = "commiq.identity";

interface Ctx {
  user: SessionUser | null;
  loading: boolean;
  refresh: () => Promise<void>;
  signIn: (user: SessionUser, token: string) => void;
  signOut: () => void;
}

const RoleCtx = createContext<Ctx>({
  user: null, loading: true,
  refresh: async () => {}, signIn: () => {}, signOut: () => {},
});

function writeIdentity(user: SessionUser | null) {
  if (typeof window === "undefined") return;
  if (user) {
    localStorage.setItem(IDENTITY_KEY, JSON.stringify({ email: user.email, role: user.role }));
  } else {
    localStorage.removeItem(IDENTITY_KEY);
  }
  // A tab does not receive its own storage events, so the theme is told directly.
  window.dispatchEvent(new Event(IDENTITY_EVENT));
}

export function RoleProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<SessionUser | null>(null);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    try {
      const me = await api.me();
      setUser(me);
      writeIdentity(me);
    } catch {
      setUser(null);
      writeIdentity(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (typeof window === "undefined") return;
    if (!localStorage.getItem("commiq.token")) {
      setLoading(false);
      return;
    }
    void refresh();
  }, [refresh]);

  const signIn = (u: SessionUser, token: string) => {
    // A previous expiry in this page session latched the redirect off; a new
    // sign-in has to re-arm it or the next genuine expiry goes unnoticed.
    resetSessionExpiry();
    setToken(token);
    setUser(u);
    writeIdentity(u);
    setLoading(false);
  };

  const signOut = () => {
    setToken(null);
    setUser(null);
    writeIdentity(null);
    window.location.href = "/login";
  };

  return (
    <RoleCtx.Provider value={{ user, loading, refresh, signIn, signOut }}>
      {children}
    </RoleCtx.Provider>
  );
}

export const useRole = () => useContext(RoleCtx);
