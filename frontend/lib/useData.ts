"use client";
import { useCallback, useEffect, useState } from "react";
import { ApiError } from "@/lib/api";

interface State<T> {
  data: T | null;
  loading: boolean;
  error: string;
  reload: () => void;
}

/** Simple in-memory cache for navigation speed.
 *
 *  Caches responses for 30 seconds so navigating back to a page shows
 *  instantly rather than re-fetching. Cache is per-key (fetcher identity).
 */
const cache = new Map<string, { data: unknown; ts: number }>();
const CACHE_TTL_MS = 30_000;

/** One fetch hook for every screen.
 *
 *  Returns cached data instantly if available (under 30s old), then
 *  refreshes in the background. First load still shows a loading state.
 */
export function useData<T>(fetcher: () => Promise<T>, deps: unknown[] = []): State<T> {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [tick, setTick] = useState(0);

  // eslint-disable-next-line react-hooks/exhaustive-deps
  const run = useCallback(fetcher, deps);
  const cacheKey = run.toString();

  useEffect(() => {
    let live = true;

    // Check cache first for instant navigation
    const cached = cache.get(cacheKey);
    if (cached && Date.now() - cached.ts < CACHE_TTL_MS) {
      setData(cached.data as T);
      setLoading(false);
      setError("");
      // Still refresh in background
      run()
        .then((d) => { if (live) { setData(d); cache.set(cacheKey, { data: d, ts: Date.now() }); } })
        .catch(() => { /* keep cached data */ });
      return () => { live = false; };
    }

    setLoading(true);
    setError("");
    run()
      .then((d) => {
        if (live) {
          setData(d);
          cache.set(cacheKey, { data: d, ts: Date.now() });
        }
      })
      .catch((e) => {
        if (live && !(e instanceof ApiError && e.status === 401)) {
          setError(e instanceof ApiError ? e.detail : "Could not reach the server");
        }
      })
      .finally(() => { if (live) setLoading(false); });
    return () => { live = false; };
  }, [run, tick, cacheKey]);

  return { data, loading, error, reload: () => setTick((t) => t + 1) };
}
