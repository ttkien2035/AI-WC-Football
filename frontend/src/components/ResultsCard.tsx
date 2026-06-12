import { useEffect, useState } from "react";
import { api, type ResultMatch } from "../api";
import { Card, Flag } from "../components/ui";
import { useT } from "../i18n";

export default function ResultsCard({ limit = 6 }: { limit?: number }) {
  const t = useT();
  const [results, setResults] = useState<ResultMatch[] | null>(null);

  useEffect(() => {
    api.results(limit).then((d) => setResults(d.results)).catch(() => setResults([]));
  }, [limit]);

  if (!results || results.length === 0) return null;

  return (
    <Card>
      <h3 className="mb-2 text-sm font-semibold">🏁 {t("res.heading")}</h3>
      <div className="space-y-3">
        {results.map((r) => <ResultRow key={r.id} r={r} />)}
      </div>
    </Card>
  );
}

function ResultRow({ r }: { r: ResultMatch }) {
  const t = useT();
  const [openDetail, setOpenDetail] = useState(false);
  const score = r.score?.home != null ? `${r.score.home}–${r.score.away}` : "–";
  return (
    <div className="rounded-xl bg-slate-100/80 p-2.5 dark:bg-white/[0.07]">
      <button onClick={() => setOpenDetail(!openDetail)}
        className="flex w-full items-center justify-between text-sm">
        <span className="flex items-center gap-2 font-semibold">
          <Flag crest={r.home.crest} tla={r.home.tla} size={18} /> {r.home.name}
          <span className="rounded-md bg-slate-200/80 px-2 py-0.5 font-bold tabular-nums dark:bg-white/[0.1]">
            {score}
          </span>
          {r.away.name} <Flag crest={r.away.crest} tla={r.away.tla} size={18} />
        </span>
        <span className="text-xs text-slate-400">
          {r.ht_score?.home != null && `HT ${r.ht_score.home}–${r.ht_score.away} · `}
          {new Date(r.date).toLocaleDateString()} {openDetail ? "▲" : "▼"}
        </span>
      </button>
      {openDetail && (
        <div className="mt-2 border-t border-slate-200/60 pt-2 text-xs dark:border-white/10">
          {r.incidents.length > 0 && (
            <div className="space-y-0.5">
              {r.incidents.map((i, k) => (
                <p key={k} className="tabular-nums">
                  <span className="inline-block w-12 text-right text-slate-400">
                    {i.minute}{(i as any).minute_ex ? `+${(i as any).minute_ex}` : ""}'
                  </span>{" "}
                  {i.type === "goal" ? "⚽" : i.type === "red" ? "🟥" : "🟨"}{" "}
                  <b>{i.side === "home" ? r.home.tla : r.away.tla}</b> {i.player ?? ""}
                  {i.penalty && " (pen)"}{i.own_goal && " (OG)"}
                </p>
              ))}
            </div>
          )}
          {r.stats && <StatBars stats={r.stats} home={r.home.tla} away={r.away.tla} />}
        </div>
      )}
    </div>
  );
}

const STAT_ORDER = ["possession", "shots_on", "shots_off", "shots_blocked",
  "corners", "crosses", "fouls", "offsides", "throw_ins", "yellows", "reds"];

export function StatBars({ stats, home, away }: {
  stats: Record<string, { home: number | null; away: number | null }>;
  home: string | null; away: string | null;
}) {
  const t = useT();
  const rows = STAT_ORDER.filter(
    (k) => stats[k] && stats[k].home != null && stats[k].away != null);
  const hasXg = stats.xg && stats.xg.home != null && stats.xg.away != null;
  if (rows.length === 0 && !hasXg) return null;
  const fmt = (k: string, v: number) =>
    k === "xg" ? v.toFixed(1) : `${v}${k === "possession" ? "%" : ""}`;
  return (
    <div className="mt-2 border-t border-slate-200/60 pt-2 dark:border-white/10">
      <p className="mb-1 text-[10px] font-semibold uppercase tracking-wide text-slate-400">
        {t("res.stats")}
      </p>
      <div className="flex justify-between px-1 text-[10px] font-bold text-slate-400">
        <span>{home}</span><span>{away}</span>
      </div>
      {hasXg && (
        <div className="my-1 rounded-md bg-emerald-50 px-1.5 py-1 dark:bg-emerald-950/30">
          <div className="flex justify-between text-xs font-bold tabular-nums">
            <span className="text-emerald-600 dark:text-emerald-400">{stats.xg.home!.toFixed(1)}</span>
            <span className="text-[10px] font-semibold text-slate-500 dark:text-slate-400">{t("stat.xg")}</span>
            <span className="text-emerald-600 dark:text-emerald-400">{stats.xg.away!.toFixed(1)}</span>
          </div>
          <div className="mt-0.5 flex h-1.5 overflow-hidden rounded-full bg-slate-200/70 dark:bg-white/10">
            <div className="bg-emerald-500" style={{ width: `${(stats.xg.home! / ((stats.xg.home! + stats.xg.away!) || 1)) * 100}%` }} />
            <div className="bg-sky-500 flex-1" />
          </div>
        </div>
      )}
      {rows.map((k) => {
        const h = stats[k].home ?? 0, a = stats[k].away ?? 0;
        const tot = h + a || 1;
        const pct = k === "possession" ? h : Math.round((h / tot) * 100);
        return (
          <div key={k} className="my-0.5">
            <div className="flex justify-between text-[11px] tabular-nums">
              <span className="font-semibold">{fmt(k, h)}</span>
              <span className="text-slate-400">{t(`stat.${k}`)}</span>
              <span className="font-semibold">{fmt(k, a)}</span>
            </div>
            <div className="flex h-1 overflow-hidden rounded-full bg-slate-200/70 dark:bg-white/10">
              <div className="bg-emerald-500" style={{ width: `${pct}%` }} />
              <div className="bg-sky-500" style={{ width: `${100 - pct}%` }} />
            </div>
          </div>
        );
      })}
    </div>
  );
}
