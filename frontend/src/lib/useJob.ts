"use client";
/** Follow a background job the person started: ask about it until it is DONE or FAILED. Stops when the page is left. */
import { useEffect } from "react";
import { api, ApiError } from "./api";
import { JOB_POLL_MS } from "./ba";
import type { JobStatus } from "./types";

export function useJob(jobId: number | null, onDone: (job: JobStatus) => void, onFailed: (message: string) => void) {
  useEffect(() => {
    if (jobId === null) return;
    let alive = true;
    const t = setInterval(async () => {
      try {
        const j = await api<JobStatus>(`/jobs/${jobId}`);
        if (!alive) return;
        if (j.state === "DONE") onDone(j);
        else if (j.state === "FAILED") onFailed(j.error ? `It failed: ${j.error}` : "It failed.");
      } catch (e) {
        if (alive) onFailed(e instanceof ApiError ? e.message : "Something went wrong");
      }
    }, JOB_POLL_MS);
    return () => { alive = false; clearInterval(t); };
  }, [jobId, onDone, onFailed]);
}
