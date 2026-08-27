"use client";
import { useCallback, useEffect, useState } from "react";
import { ApiError } from "@/lib/api";

interface State<T> {
  data: T | null;
  loading: boolean;
  error: string;
  reload: () => void;
}

const cache = new Map<unknown, { data: unknown; ts: number }>();
const CACHE_TTL_MS = 30_000;

export function useData<T>(fetcher: () => Promise<T>, deps: unknown[] = []): State<T> {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [tick, setTick] = useState(0);

  const run = useCallback(fetcher, deps);
  const cacheKey = run;

  useEffect(() => {
    let live = true;

    const cached = cache.get(cacheKey);
    if (cached && Date.now() - cached.ts < CACHE_TTL_MS) {
      setData(cached.data as T);
      setLoading(false);
      setError("");
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
