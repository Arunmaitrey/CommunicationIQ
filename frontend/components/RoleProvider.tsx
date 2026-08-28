"use client";
import { createContext, useCallback, useContext, useEffect, useState, ReactNode } from "react";
import { useRouter } from "next/navigation";
import { api, resetSessionExpiry, setToken, type SessionUser } from "@/lib/api";
import { IDENTITY_EVENT } from "@/components/ThemeProvider";

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
  window.dispatchEvent(new Event(IDENTITY_EVENT));
}

export function RoleProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<SessionUser | null>(null);
  const [loading, setLoading] = useState(true);
  const router = useRouter();

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
    const cached = localStorage.getItem(IDENTITY_KEY);
    if (cached) {
      try {
        const parsed = JSON.parse(cached);
        setUser({ ...parsed, id: "", email: parsed.email, full_name: "", role: parsed.role, scope: "" } as SessionUser);
      } catch { /* ignore */ }
    }
    const id = setTimeout(() => setLoading(false), 4000);
    void refresh().finally(() => clearTimeout(id));
  }, [refresh]);

  const signIn = (u: SessionUser, token: string) => {
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
    router.replace("/");
  };

  return (
    <RoleCtx.Provider value={{ user, loading, refresh, signIn, signOut }}>
      {children}
    </RoleCtx.Provider>
  );
}

export const useRole = () => useContext(RoleCtx);
