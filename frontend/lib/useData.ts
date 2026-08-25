"use client";
import { useCallback, useEffect, useState } from "react";
import { ApiError } from "@/lib/api";

interface State<T> {
  data: T | null;
  loading: boolean;
  error: string;
  reload: () => void;
}

/** One fetch hook for every screen.
 *
 *  Deliberately plain — no cache, no revalidation. A readiness dashboard read
 *  once per navigation is correct behaviour for this product; a stale-while-
 *  revalidate layer would be inventing a problem we do not have yet.
 */
export function useData<T>(fetcher: () => Promise<T>, deps: unknown[] = []): State<T> {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [tick, setTick] = useState(0);

  // eslint-disable-next-line react-hooks/exhaustive-deps
  const run = useCallback(fetcher, deps);

  useEffect(() => {
    let live = true;
    setLoading(true);
    setError("");
    run()
      .then((d) => { if (live) setData(d); })
      .catch((e) => {
        // A 401 has already navigated to sign-in; showing an error underneath
        // it would just flash red on the way out.
        if (live && !(e instanceof ApiError && e.status === 401)) {
          setError(e instanceof ApiError ? e.detail : "Could not reach the server");
        }
      })
      .finally(() => { if (live) setLoading(false); });
    return () => { live = false; };
  }, [run, tick]);

  return { data, loading, error, reload: () => setTick((t) => t + 1) };
}
