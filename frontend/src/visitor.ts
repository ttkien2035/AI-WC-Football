/** Anonymous visitor id — crypto.randomUUID() only exists in secure contexts
 *  (HTTPS/localhost), so plain-HTTP deployments need a fallback. */
export function getVisitorId(): string {
  try {
    let v = localStorage.getItem("visitor_id");
    if (!v) {
      v = typeof crypto !== "undefined" && "randomUUID" in crypto
        ? crypto.randomUUID()
        : "v-" + Date.now().toString(36) + "-" +
          Array.from({ length: 4 }, () => Math.random().toString(36).slice(2, 8)).join("");
      localStorage.setItem("visitor_id", v);
    }
    return v;
  } catch {
    return "v-anon";
  }
}
