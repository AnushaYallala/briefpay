"use client";
/** Load one API resource with the states every screen needs (SPEC 11.2): loading, error, data, and the "server is waking up" notice. */
import { useCallback, useEffect, useRef, useState } from "react";
import { api, ApiError } from "./api";
import { watchSlow } from "./wake";

export type Loaded<T> = { data: T | null; error: ApiError | null; loading: boolean; slow: boolean; reload: () => void };

export function useApi<T>(path: string | null, refreshKey?: unknown): Loaded<T> {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [loading, setLoading] = useState<boolean>(path !== null);
  const [slow, setSlow] = useState(false);
  const [tick, setTick] = useState(0);
  const latest = useRef(0);

  useEffect(() => {
    if (path === null) return;
    const mine = ++latest.current;
    const ctl = new AbortController();
    setLoading(true);
    setError(null);
    setSlow(false);
    watchSlow(api<T>(path, { signal: ctl.signal }), () => latest.current === mine && setSlow(true))
      .then((d) => latest.current === mine && (setData(d), setLoading(false), setSlow(false)))
      .catch((e: unknown) => {
        if (latest.current !== mine || (e instanceof DOMException && e.name === "AbortError")) return;
        setError(e instanceof ApiError ? e : new ApiError(0, "UNKNOWN", String(e)));
        setLoading(false);
        setSlow(false);
      });
    return () => ctl.abort();
  }, [path, tick, refreshKey]);

  const reload = useCallback(() => setTick((t) => t + 1), []);
  return { data, error, loading, slow, reload };
}
