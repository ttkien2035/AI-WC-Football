import { useEffect, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { Loader2, Send, Sparkles, X, Zap } from "lucide-react";
import { api } from "../api";
import { useLang, useT } from "../i18n";
import { getVisitorId } from "../visitor";

type ToolStep = { name: string; label: string; done: boolean };
type Msg = { role: "user" | "bot"; text: string; tools: ToolStep[] };

/** markdown-lite: **bold**, bullet lines, newlines */
function Md({ text }: { text: string }) {
  const lines = text.split("\n");
  return (
    <>
      {lines.map((ln, i) => {
        const bullet = /^\s*[*•-]\s+/.test(ln);
        const html = ln
          .replace(/^\s*[*•-]\s+/, "")
          .split(/(\*\*[^*]+\*\*)/g)
          .map((seg, j) =>
            seg.startsWith("**") && seg.endsWith("**")
              ? <b key={j}>{seg.slice(2, -2)}</b>
              : <span key={j}>{seg}</span>);
        return bullet
          ? <div key={i} className="ml-1 flex gap-1.5"><span>•</span><span>{html}</span></div>
          : <div key={i} className={ln.trim() === "" ? "h-1.5" : ""}>{html}</div>;
      })}
    </>
  );
}

export default function ChatWidget() {
  const t = useT();
  const { lang } = useLang();
  const [open, setOpen] = useState(false);
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [remaining, setRemaining] = useState<number | null>(null);
  const [liveNow, setLiveNow] = useState(false);
  const [followups, setFollowups] = useState<string[]>([]);
  const [todayMatch, setTodayMatch] = useState<string | null>(null);
  const [enabled, setEnabled] = useState(true);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    fetch(`/api/chat/quota?v=${getVisitorId()}`)
      .then((r) => r.json())
      .then((d) => { setRemaining(d.remaining); setLiveNow(d.live_now); setEnabled(d.enabled); })
      .catch(() => {});
    api.live().then((d) => {
      const m = d.live[0] ?? d.today.find((x) => x.status === "TIMED");
      if (m?.home.tla) setTodayMatch(`${m.home.tla} vs ${m.away.tla}`);
    }).catch(() => {});
  }, []);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: 99999, behavior: "smooth" });
  }, [msgs, streaming]);

  const send = async (text: string) => {
    if (!text.trim() || streaming || (remaining ?? 0) <= 0) return;
    setFollowups([]);
    const history = msgs.slice(-6).map((m) => ({ role: m.role, text: m.text }));
    setMsgs((p) => [...p, { role: "user", text, tools: [] },
                          { role: "bot", text: "", tools: [] }]);
    setInput("");
    setStreaming(true);
    try {
      const res = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ v: getVisitorId(), message: text, history, lang }),
      });
      if (!res.ok || !res.body) throw new Error(String(res.status));
      const reader = res.body.getReader();
      const dec = new TextDecoder();
      let buf = "";
      for (;;) {
        const { done, value } = await reader.read();
        if (done) break;
        buf += dec.decode(value, { stream: true });
        const lines = buf.split("\n");
        buf = lines.pop() ?? "";
        for (const line of lines) {
          if (!line.trim()) continue;
          let ev: any;
          try { ev = JSON.parse(line); } catch { continue; }
          setMsgs((prev) => {
            const out = [...prev];
            const bot = { ...out[out.length - 1] };
            if (ev.type === "tool") {
              bot.tools = [...bot.tools.map((x) => ({ ...x, done: true })),
                           { name: ev.name, label: lang === "vi" ? ev.label_vi : ev.label_en, done: false }];
            } else if (ev.type === "delta") {
              bot.tools = bot.tools.map((x) => ({ ...x, done: true }));
              bot.text += ev.text;
            } else if (ev.type === "done") {
              bot.tools = bot.tools.map((x) => ({ ...x, done: true }));
              setRemaining(ev.remaining);
              setFollowups(ev.followups ?? []);
            } else if (ev.type === "error") {
              bot.text = ev.code === "quota" ? t("chat.quota_out") : t("chat.error");
              if (ev.code === "quota") setRemaining(0);
            }
            out[out.length - 1] = bot;
            return out;
          });
        }
      }
    } catch {
      setMsgs((prev) => {
        const out = [...prev];
        out[out.length - 1] = { ...out[out.length - 1], text: t("chat.error") };
        return out;
      });
    } finally {
      setStreaming(false);
    }
  };

  if (!enabled) return null;

  const chips = msgs.length === 0
    ? [
        todayMatch && t("chat.chip_deep", { m: todayMatch }),
        t("chat.chip_value"),
        t("chat.chip_title"),
        todayMatch && t("chat.chip_whatif", { m: todayMatch }),
      ].filter(Boolean) as string[]
    : followups;

  return (
    <>
      {/* FAB */}
      <motion.button
        onClick={() => setOpen(!open)}
        whileHover={{ scale: 1.08 }} whileTap={{ scale: 0.92 }}
        className="fixed bottom-5 right-5 z-50 flex h-14 w-14 items-center justify-center rounded-full bg-gradient-to-br from-emerald-500 to-sky-500 text-2xl shadow-lg shadow-emerald-500/30"
        title={t("chat.title")}
      >
        {open ? <X className="text-white" size={22} /> : "⚽"}
        {!open && liveNow && (
          <span className="absolute -right-0.5 -top-0.5 h-3.5 w-3.5 animate-pulse rounded-full border-2 border-white bg-red-500" />
        )}
        {!open && (
          <Sparkles size={14} className="absolute -left-1 -top-1 text-amber-300" />
        )}
      </motion.button>

      {/* Panel */}
      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ opacity: 0, y: 24, scale: 0.96 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 24, scale: 0.96 }}
            transition={{ duration: 0.18 }}
            className="fixed bottom-[5.5rem] right-4 z-50 flex h-[560px] max-h-[75vh] w-[380px] max-w-[93vw] flex-col overflow-hidden rounded-2xl border border-slate-200 bg-white/95 shadow-2xl backdrop-blur dark:border-slate-700 dark:bg-slate-900/95"
          >
            {/* header */}
            <div className="flex items-center justify-between bg-gradient-to-r from-emerald-600 to-sky-600 px-4 py-3 text-white">
              <span className="flex items-center gap-1.5 text-sm font-bold">
                ⚽ {t("chat.title")} <Sparkles size={14} className="text-amber-300" />
              </span>
              <span className="flex items-center gap-0.5" title={`${remaining ?? "?"}/5`}>
                {[...Array(5)].map((_, i) => (
                  <Zap key={i} size={13}
                    className={i < (remaining ?? 0) ? "text-amber-300" : "text-white/25"}
                    fill={i < (remaining ?? 0) ? "currentColor" : "none"} />
                ))}
              </span>
            </div>

            {/* messages */}
            <div ref={scrollRef} className="flex-1 space-y-3 overflow-y-auto p-3 text-sm">
              <div className="rounded-2xl rounded-tl-sm bg-slate-100 p-3 dark:bg-slate-800">
                <Md text={liveNow ? t("chat.greeting_live") : t("chat.greeting")} />
              </div>
              {msgs.map((m, i) => (
                <div key={i} className={m.role === "user" ? "flex justify-end" : ""}>
                  <div className={m.role === "user"
                    ? "max-w-[85%] rounded-2xl rounded-tr-sm bg-emerald-600 p-2.5 text-white"
                    : "max-w-[92%] rounded-2xl rounded-tl-sm bg-slate-100 p-3 dark:bg-slate-800"}>
                    {m.tools.length > 0 && (
                      <div className="mb-1.5 space-y-0.5">
                        {m.tools.map((s, j) => (
                          <p key={j} className="flex items-center gap-1.5 text-[11px] italic text-slate-400">
                            {s.done ? "✓" : <Loader2 size={11} className="animate-spin" />} {s.label}
                          </p>
                        ))}
                      </div>
                    )}
                    {m.text
                      ? <Md text={m.text} />
                      : m.role === "bot" && (
                          <span className="flex items-center gap-1.5 text-slate-400">
                            <Loader2 size={13} className="animate-spin" /> {t("chat.thinking")}
                          </span>
                        )}
                    {m.role === "bot" && streaming && i === msgs.length - 1 && m.text && (
                      <span className="ml-0.5 inline-block h-3.5 w-1.5 animate-pulse bg-emerald-500 align-middle" />
                    )}
                  </div>
                </div>
              ))}
              {(remaining ?? 1) <= 0 && !streaming && (
                <div className="rounded-2xl bg-amber-50 p-3 text-amber-800 dark:bg-amber-950/40 dark:text-amber-200">
                  {t("chat.quota_out")}
                </div>
              )}
            </div>

            {/* chips */}
            {chips.length > 0 && (remaining ?? 0) > 0 && !streaming && (
              <div className="flex flex-wrap gap-1.5 px-3 pb-1.5">
                {chips.map((c, i) => (
                  <button key={i} onClick={() => send(c)}
                    className="rounded-full border border-emerald-300 bg-emerald-50 px-2.5 py-1 text-[11px] font-medium text-emerald-700 hover:bg-emerald-100 dark:border-emerald-800 dark:bg-emerald-950/40 dark:text-emerald-300">
                    {c}
                  </button>
                ))}
              </div>
            )}

            {/* input */}
            <div className="border-t border-slate-200 p-2.5 dark:border-slate-700">
              <div className="flex gap-2">
                <input
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && send(input)}
                  placeholder={t("chat.placeholder")}
                  disabled={streaming || (remaining ?? 0) <= 0}
                  className="flex-1 rounded-xl border border-slate-300 bg-white px-3 py-2 text-sm outline-none focus:border-emerald-500 disabled:opacity-50 dark:border-slate-700 dark:bg-slate-800"
                />
                <button onClick={() => send(input)}
                  disabled={streaming || !input.trim() || (remaining ?? 0) <= 0}
                  className="rounded-xl bg-emerald-600 px-3 text-white hover:bg-emerald-500 disabled:opacity-40">
                  <Send size={16} />
                </button>
              </div>
              <p className="mt-1 text-center text-[9px] text-slate-400">{t("chat.disclaimer")}</p>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </>
  );
}
