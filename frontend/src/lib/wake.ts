/** The free host sleeps when idle and takes about a minute to wake (SPEC 14.5): say so instead of looking broken. */
export const SLOW_AFTER_MS = 4000;

/** Runs `onSlow` once if `work` is still pending after `ms`; always cleans its timer. Returns the work's own result or error. */
export async function watchSlow<T>(work: Promise<T>, onSlow: () => void, ms = SLOW_AFTER_MS): Promise<T> {
  const timer = setTimeout(onSlow, ms);
  try {
    return await work;
  } finally {
    clearTimeout(timer);
  }
}
