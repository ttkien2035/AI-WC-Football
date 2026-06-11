/** Anonymous usage tracking — random UUID in localStorage, no PII.
 *  Fire-and-forget: failures are silently ignored. */
import { getVisitorId } from "./visitor";

export function track(t: string, d?: Record<string, string>) {
  try {
    const body = JSON.stringify({ v: getVisitorId(), t, d });
    if (navigator.sendBeacon) {
      navigator.sendBeacon("/api/track", new Blob([body], { type: "application/json" }));
    } else {
      fetch("/api/track", {
        method: "POST", body, keepalive: true,
        headers: { "Content-Type": "application/json" },
      }).catch(() => {});
    }
  } catch {
    /* analytics must never break the app */
  }
}
