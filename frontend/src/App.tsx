import { useEffect, useState } from "react";
import { Moon, Sun, Trophy, RefreshCw, Languages } from "lucide-react";
import { api, type Match } from "./api";
import { StatusDot, Flag } from "./components/ui";
import { useLang, useT } from "./i18n";
import Groups from "./views/Groups";
import Bracket from "./views/Bracket";
import MatchSim from "./views/MatchSim";
import TitleOdds from "./views/TitleOdds";
import Odds from "./views/Odds";
import Accuracy from "./views/Accuracy";
import Live from "./views/Live";

const TABS = [
  { id: "live", key: "tab.live", el: <Live /> },
  { id: "groups", key: "tab.groups", el: <Groups /> },
  { id: "bracket", key: "tab.bracket", el: <Bracket /> },
  { id: "match", key: "tab.match", el: <MatchSim /> },
  { id: "title", key: "tab.title", el: <TitleOdds /> },
  { id: "odds", key: "tab.odds", el: <Odds /> },
  { id: "accuracy", key: "tab.accuracy", el: <Accuracy /> },
];

export default function App() {
  const t = useT();
  const { lang, setLang } = useLang();
  const [tab, setTab] = useState("groups");
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
    <div className="mx-auto max-w-7xl px-4 pb-16">
      <header className="sticky top-0 z-10 -mx-4 mb-4 border-b border-slate-200 bg-gradient-to-r from-emerald-50 via-slate-100 to-sky-50 px-4 py-3 backdrop-blur dark:border-slate-800 dark:from-emerald-950/60 dark:via-slate-950 dark:to-sky-950/60">
        <div className="flex items-center justify-between">
          <h1 className="flex items-center gap-2 text-xl font-extrabold tracking-tight">
            <Trophy className="text-amber-500" size={24} />
            {t("app.title")}{" "}
            <span className="hidden bg-gradient-to-r from-emerald-500 to-sky-500 bg-clip-text text-transparent sm:inline">
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
              onClick={() => setLang(lang === "vi" ? "en" : "vi")}
              className="flex items-center gap-1 rounded-full px-2.5 py-1.5 text-xs font-bold hover:bg-slate-200 dark:hover:bg-slate-800"
              title="Tiếng Việt / English"
            >
              <Languages size={14} /> {lang === "vi" ? "VI" : "EN"}
            </button>
            <button
              onClick={() => fetch("/api/refresh", { method: "POST" }).then(() => location.reload())}
              title={t("app.refresh")}
              className="rounded-full p-2 hover:bg-slate-200 dark:hover:bg-slate-800"
            >
              <RefreshCw size={16} />
            </button>
            <button onClick={() => setDark(!dark)}
              className="rounded-full p-2 hover:bg-slate-200 dark:hover:bg-slate-800">
              {dark ? <Sun size={16} /> : <Moon size={16} />}
            </button>
          </div>
        </div>

        <nav className="mt-3 flex flex-wrap gap-1">
          {TABS.map((x) => (
            <button key={x.id} onClick={() => setTab(x.id)}
              className={`rounded-full px-4 py-1.5 text-sm font-medium transition ${
                tab === x.id
                  ? "bg-emerald-600 text-white shadow"
                  : "text-slate-500 hover:bg-slate-200 dark:text-slate-400 dark:hover:bg-slate-800"
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

      <footer className="mt-10 text-center text-[11px] text-slate-400">{t("app.footer")}</footer>
    </div>
  );
}
