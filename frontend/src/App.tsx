import { useEffect, useState } from "react";
import { Moon, Sun, Trophy, RefreshCw, Languages, ShieldCheck } from "lucide-react";
import { api, adminToken, type Match } from "./api";
import { StatusDot, Flag } from "./components/ui";
import { useLang, useT } from "./i18n";
import { track } from "./track";
import Groups from "./views/Groups";
import Bracket from "./views/Bracket";
import MatchSim from "./views/MatchSim";
import TitleOdds from "./views/TitleOdds";
import Odds from "./views/Odds";
import Accuracy from "./views/Accuracy";
import Live from "./views/Live";
import Schedule from "./views/Schedule";
import Pipeline from "./views/Pipeline";
import ChatWidget from "./components/ChatWidget";

export default function App() {
  const t = useT();
  const { lang, setLang } = useLang();
  const [tab, setTab] = useState("groups");
  const [isAdmin, setIsAdmin] = useState(false);

  // validate stored admin token once on boot
  useEffect(() => {
    if (adminToken.get()) {
      api.pipelineStatus().then(() => setIsAdmin(true)).catch(() => adminToken.clear());
    }
    track("visit", { lang: (localStorage.getItem("lang") as string) || "vi" });
  }, []);

  const switchTab = (id: string) => {
    setTab(id);
    track("tab", { tab: id });
  };

  const adminLogin = async () => {
    if (isAdmin) { setTab("pipeline"); return; }
    const token = prompt(t("pl.token_prompt"));
    if (!token) return;
    adminToken.set(token.trim());
    try {
      await api.pipelineStatus();
      setIsAdmin(true);
      setTab("pipeline");
    } catch {
      adminToken.clear();
      alert(t("pl.token_bad"));
    }
  };

  const adminLogout = () => {
    adminToken.clear();
    setIsAdmin(false);
    setTab("groups");
  };

  const TABS = [
    { id: "live", key: "tab.live", el: <Live /> },
    { id: "schedule", key: "tab.schedule", el: <Schedule /> },
    { id: "groups", key: "tab.groups", el: <Groups /> },
    { id: "bracket", key: "tab.bracket", el: <Bracket /> },
    { id: "match", key: "tab.match", el: <MatchSim /> },
    { id: "title", key: "tab.title", el: <TitleOdds /> },
    { id: "odds", key: "tab.odds", el: <Odds /> },
    { id: "accuracy", key: "tab.accuracy", el: <Accuracy /> },
    ...(isAdmin ? [{ id: "pipeline", key: "tab.pipeline", el: <Pipeline onLogout={adminLogout} /> }] : []),
  ];
  const [dark, setDark] = useState(() => localStorage.getItem("theme") !== "light");
  const [live, setLive] = useState<Match[]>([]);
  const [today, setToday] = useState<Match[]>([]);
  const [sources, setSources] = useState<Record<string, { ok: boolean }>>({});

  useEffect(() => {
    document.documentElement.classList.toggle("dark", dark);
    localStorage.setItem("theme", dark ? "dark" : "light");
  }, [dark]);

  useEffect(() => {
    const poll = () => {
      api.live().then((d) => { setLive(d.live); setToday(d.today); }).catch(() => {});
      api.sources().then(setSources).catch(() => {});
    };
    poll();
    const i = setInterval(poll, 60_000);
    return () => clearInterval(i);
  }, []);

  return (
    <div className="mx-auto max-w-7xl px-3 pb-28 sm:px-4 sm:pb-20">
      <header className="sticky top-0 z-10 -mx-4 mb-4 border-b border-slate-200/70 bg-white/70 px-4 py-3 backdrop-blur-xl dark:border-white/10 dark:bg-[#060913]/75">
        <div className="flex items-center justify-between">
          <h1 className="flex items-center gap-2 text-xl font-extrabold tracking-tight">
            <Trophy className="text-amber-500 drop-shadow-[0_0_8px_rgba(245,158,11,0.6)]" size={24} />
            {t("app.title")}{" "}
            <span className="title-gradient hidden sm:inline">
              {t("app.subtitle")}
            </span>
            {live.length > 0 && (
              <span className="ml-2 flex items-center gap-1 rounded-full bg-red-500 px-2 py-0.5 text-[11px] font-bold text-white">
                <span className="h-1.5 w-1.5 animate-ping rounded-full bg-white" />
                {live.length} LIVE
              </span>
            )}
          </h1>
          <div className="flex items-center gap-2">
            <div className="hidden items-center gap-2 text-[11px] text-slate-500 lg:flex">
              {Object.entries(sources).map(([k, v]) => (
                <span key={k} className="flex items-center gap-1">
                  <StatusDot ok={v.ok} /> {k.replace(/_/g, "-")}
                </span>
              ))}
            </div>
            <button
              onClick={() => {
                const next = lang === "vi" ? "en" : "vi";
                setLang(next);
                track("lang", { lang: next });
              }}
              className="flex items-center gap-1 rounded-full px-2.5 py-1.5 text-xs font-bold hover:bg-slate-200 dark:hover:bg-slate-800"
              title="Tiếng Việt / English"
            >
              <Languages size={14} /> {lang === "vi" ? "VI" : "EN"}
            </button>
            {isAdmin && (
              <button
                onClick={() =>
                  fetch("/api/refresh", {
                    method: "POST",
                    headers: { "X-Admin-Token": adminToken.get() ?? "" },
                  }).then(() => location.reload())}
                title={t("app.refresh")}
                className="rounded-full p-2 hover:bg-slate-200 dark:hover:bg-slate-800"
              >
                <RefreshCw size={16} />
              </button>
            )}
            <button onClick={() => setDark(!dark)}
              className="rounded-full p-2 hover:bg-slate-200 dark:hover:bg-slate-800">
              {dark ? <Sun size={16} /> : <Moon size={16} />}
            </button>
            <button onClick={adminLogin} title={t("pl.admin_only")}
              className={`rounded-full p-2 hover:bg-slate-200 dark:hover:bg-slate-800 ${
                isAdmin ? "text-emerald-500" : "text-slate-300 dark:text-slate-700"}`}>
              <ShieldCheck size={16} />
            </button>
          </div>
        </div>

        <nav className="-mx-3 mt-3 flex gap-1 overflow-x-auto px-3 pb-0.5 sm:mx-0 sm:flex-wrap sm:overflow-visible sm:px-0">
          {TABS.map((x) => (
            <button key={x.id} onClick={() => switchTab(x.id)}
              className={`shrink-0 rounded-full px-3.5 py-1.5 text-sm font-medium transition sm:shrink ${
                tab === x.id
                  ? "bg-gradient-to-r from-emerald-600 to-emerald-500 text-white shadow-md shadow-emerald-600/40"
                  : "text-slate-500 hover:bg-slate-200/80 dark:text-slate-400 dark:hover:bg-white/10"
              }`}>
              {t(x.key)}
            </button>
          ))}
        </nav>

        {today.length > 0 && (
          <div className="mt-2 flex items-center gap-2 overflow-x-auto pb-1">
            <span className="shrink-0 text-[10px] font-bold uppercase tracking-wider text-slate-400">
              {t("app.today")}
            </span>
            {today.map((m) => {
              const isLive = ["IN_PLAY", "PAUSED", "LIVE"].includes(m.status);
              const done = m.status === "FINISHED";
              return (
                <span key={m.id}
                  className={`flex shrink-0 items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium ${
                    isLive ? "bg-red-100 text-red-700 dark:bg-red-950/60 dark:text-red-300"
                      : "bg-white/70 text-slate-600 dark:bg-slate-900/70 dark:text-slate-300"}`}>
                  <Flag crest={m.home.crest} tla={m.home.tla} size={14} />
                  {m.home.tla}
                  <b className="tabular-nums">
                    {isLive || done
                      ? `${m.score.home ?? 0}–${m.score.away ?? 0}`
                      : new Date(m.utcDate).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
                  </b>
                  {m.away.tla}
                  <Flag crest={m.away.crest} tla={m.away.tla} size={14} />
                  {isLive && m.minute_estimate != null && <span className="text-[10px]">{m.minute_estimate}'</span>}
                </span>
              );
            })}
          </div>
        )}
      </header>

      <main>{TABS.find((x) => x.id === tab)?.el}</main>

      <ChatWidget />

      <footer className="mt-10 text-center text-[11px] text-slate-400">
        <p>{t("app.footer")}</p>
        <p className="mt-1.5 font-medium">
          ⚡ Powered by{" "}
          <a href="https://github.com/ttkien2035" target="_blank" rel="noreferrer"
             className="font-bold text-emerald-500 hover:underline">
            ttkien2035
          </a>
        </p>
      </footer>
    </div>
  );
}
