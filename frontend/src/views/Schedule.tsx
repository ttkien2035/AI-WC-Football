import { useEffect, useMemo, useRef, useState } from "react";
import { api, type Match } from "../api";
import { Card, Flag } from "../components/ui";
import { useLang, useT } from "../i18n";

const GROUPS = "ABCDEFGHIJKL".split("");
type Filter = "all" | "group" | "ko";

export default function Schedule() {
  const t = useT();
  const { lang } = useLang();
  const [matches, setMatches] = useState<Match[]>([]);
  const [filter, setFilter] = useState<Filter>("all");
  const [groupPick, setGroupPick] = useState<string>("");
  const autoDefault = useRef(false);

  useEffect(() => {
    api.matches().then((d) => {
      setMatches(d.matches);
      // once the group stage is fully played, default the view to the KNOCKOUT
      // round (that's what's upcoming) — but only auto-set once, never override
      // a manual pick.
      if (!autoDefault.current) {
        autoDefault.current = true;
        const groupLeft = d.matches.some((m) => m.stage === "GROUP_STAGE" && m.status !== "FINISHED");
        const koExists = d.matches.some((m) => m.stage !== "GROUP_STAGE");
        if (!groupLeft && koExists) setFilter("ko");
      }
    }).catch(() => {});
  }, []);

  const filtered = useMemo(() => {
    let ms = matches;
    if (filter === "group") {
      ms = ms.filter((m) => m.stage === "GROUP_STAGE");
      if (groupPick) ms = ms.filter((m) => (m.group ?? "").endsWith(groupPick));
    } else if (filter === "ko") {
      ms = ms.filter((m) => m.stage !== "GROUP_STAGE");
    }
    return [...ms].sort((a, b) => a.utcDate.localeCompare(b.utcDate));
  }, [matches, filter, groupPick]);

  const byDay = useMemo(() => {
    const out: { day: string; list: Match[] }[] = [];
    for (const m of filtered) {
      const day = new Date(m.utcDate).toLocaleDateString(
        lang === "vi" ? "vi-VN" : "en-US",
        { weekday: "short", day: "numeric", month: "numeric" });
      if (out.length === 0 || out[out.length - 1].day !== day) {
        out.push({ day, list: [m] });
      } else {
        out[out.length - 1].list.push(m);
      }
    }
    return out;
  }, [filtered, lang]);

  if (matches.length === 0) {
    return <div className="h-96 animate-pulse rounded-2xl bg-slate-200/80 dark:bg-white/[0.1]" />;
  }

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        {(["all", "group", "ko"] as Filter[]).map((f) => (
          <button key={f} onClick={() => setFilter(f)}
            className={`rounded-full px-3.5 py-1.5 text-sm font-medium transition ${
              filter === f
                ? "bg-gradient-to-r from-emerald-600 to-emerald-500 text-white shadow-md shadow-emerald-600/40"
                : "bg-slate-200/80 text-slate-600 dark:bg-white/[0.07] dark:text-slate-300"}`}>
            {t(f === "all" ? "sched.all" : f === "group" ? "sched.group_stage" : "sched.knockout")}
          </button>
        ))}
        {filter === "group" && (
          <select value={groupPick} onChange={(e) => setGroupPick(e.target.value)}
            className="rounded-lg border border-slate-300 bg-white px-2 py-1.5 text-sm dark:border-slate-700 dark:bg-slate-800">
            <option value="">{t("sched.group_pick")}: {t("sched.all")}</option>
            {GROUPS.map((g) => <option key={g} value={g}>{t("sched.group_pick")} {g}</option>)}
          </select>
        )}
      </div>
      <p className="text-xs text-slate-400">{t("sched.note")}</p>

      {byDay.map(({ day, list }) => (
        <Card key={day} className="!p-3">
          <h3 className="mb-2 text-sm font-bold capitalize text-emerald-600 dark:text-emerald-400">
            📅 {day}
          </h3>
          <div className="divide-y divide-slate-100 dark:divide-white/10">
            {list.map((m) => <Row key={m.id} m={m} />)}
          </div>
        </Card>
      ))}
    </div>
  );
}

function Row({ m }: { m: Match }) {
  const t = useT();
  const live = ["IN_PLAY", "PAUSED", "LIVE"].includes(m.status);
  const done = m.status === "FINISHED";
  const time = new Date(m.utcDate).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  const stageLabel = m.stage === "GROUP_STAGE"
    ? `${t("stage.GROUP_STAGE")} ${(m.group ?? "").slice(-1)}`
    : t(`stage.${m.stage}`);
  const tbd = !m.home.tla;

  return (
    <div className={`flex items-center gap-2 py-2 text-sm ${
      m.stage === "FINAL" ? "rounded-lg bg-amber-50 px-2 dark:bg-amber-950/30" : ""}`}>
      <span className="w-12 shrink-0 text-xs font-semibold tabular-nums text-slate-400">{time}</span>
      <span className="w-20 shrink-0">
        <span className={`rounded px-1.5 py-0.5 text-[10px] font-semibold ${
          m.stage === "GROUP_STAGE"
            ? "bg-slate-200/80 text-slate-600 dark:bg-white/[0.1] dark:text-slate-300"
            : "bg-indigo-100 text-indigo-700 dark:bg-indigo-950/60 dark:text-indigo-300"}`}>
          {stageLabel}
        </span>
      </span>
      <span className="flex min-w-0 flex-1 items-center justify-center gap-2">
        {tbd ? (
          <span className="text-xs italic text-slate-400">{t("sched.tbd")}</span>
        ) : (
          <>
            <span className="flex min-w-0 flex-1 items-center justify-end gap-1.5 truncate font-medium">
              <span className="truncate">{m.home.name}</span>
              <Flag crest={m.home.crest} tla={m.home.tla} size={16} />
            </span>
            <span className={`shrink-0 rounded-md px-2 py-0.5 text-center text-xs font-bold tabular-nums ${
              live ? "bg-red-100 text-red-600 dark:bg-red-950/60 dark:text-red-300"
                : done ? "bg-slate-200/80 dark:bg-white/[0.1]"
                : "text-slate-400"}`}>
              {live || done ? `${m.score.home ?? 0}–${m.score.away ?? 0}` : "vs"}
              {live && m.minute_estimate != null && <span className="ml-1">{m.minute_estimate}'</span>}
            </span>
            <span className="flex min-w-0 flex-1 items-center gap-1.5 truncate font-medium">
              <Flag crest={m.away.crest} tla={m.away.tla} size={16} />
              <span className="truncate">{m.away.name}</span>
            </span>
          </>
        )}
      </span>
    </div>
  );
}
