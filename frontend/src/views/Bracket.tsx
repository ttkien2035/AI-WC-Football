import { useEffect, useState } from "react";
import { api, type BracketEntry, pct } from "../api";
import { Card } from "../components/ui";
import { useLang, useT } from "../i18n";

type BracketData = Awaited<ReturnType<typeof api.bracket>>;

const ROUNDS: { key: string; nos: number[] }[] = [
  { key: "bracket.r32", nos: [73, 74, 75, 76, 77, 78, 79, 80, 81, 82, 83, 84, 85, 86, 87, 88] },
  { key: "bracket.r16", nos: [89, 90, 91, 92, 93, 94, 95, 96] },
  { key: "bracket.qf", nos: [97, 98, 99, 100] },
  { key: "bracket.sf", nos: [101, 102] },
  { key: "bracket.final", nos: [104] },
];

function slotLabel(routing: BracketData["routing"], no: number): string {
  for (const stage of Object.values(routing)) {
    const pair = stage[no];
    if (pair) {
      const fmt = (s: string | number) =>
        typeof s === "string" && s.startsWith("3:") ? `3rd(${s.slice(2)})` :
        typeof s === "number" ? `W${s}` : String(s);
      return `${fmt(pair[0])} vs ${fmt(pair[1])}`;
    }
  }
  return "";
}

function MatchCard({ no, entry, label, when }: {
  no: number; entry?: BracketEntry; label: string;
  when?: { date: string; city: string };
}) {
  const { lang } = useLang();
  const top = entry?.winner_top?.slice(0, 3) ?? [];
  const h = entry?.home_top?.[0];
  const a = entry?.away_top?.[0];
  const dateStr = when
    ? new Date(when.date + "T12:00:00Z").toLocaleDateString(
        lang === "vi" ? "vi-VN" : "en-US", { day: "numeric", month: "short" })
    : null;
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-2.5 text-xs shadow-sm dark:border-slate-800 dark:bg-slate-900">
      <div className="mb-1 flex justify-between text-[10px] text-slate-400">
        <span>M{no}</span>
        <span>{label}</span>
      </div>
      {when && (
        <div className="mb-1 text-[10px] font-medium text-sky-600 dark:text-sky-400">
          📅 {dateStr} · {when.city}
        </div>
      )}
      <div className="mb-1.5 flex items-center justify-between font-semibold">
        <span>{h ? `${h.tla} ${pct(h.p, 0)}` : "TBD"}</span>
        <span className="text-slate-400">vs</span>
        <span>{a ? `${a.tla} ${pct(a.p, 0)}` : "TBD"}</span>
      </div>
      <div className="flex gap-1">
        {top.map((w) => (
          <span
            key={w.tla}
            className="rounded-full bg-emerald-100 px-1.5 py-0.5 text-[10px] font-medium text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300"
            title={`Most likely winner: ${w.tla} ${pct(w.p)}`}
          >
            {w.tla} {pct(w.p, 0)}
          </span>
        ))}
      </div>
    </div>
  );
}

export default function Bracket() {
  const t = useT();
  const [data, setData] = useState<BracketData | null>(null);

  useEffect(() => {
    api.bracket().then(setData);
  }, []);

  if (!data) return <div className="h-96 animate-pulse rounded-2xl bg-slate-200 dark:bg-slate-800" />;

  return (
    <Card className="overflow-x-auto">
      <p className="mb-3 text-xs text-slate-500 dark:text-slate-400">
        {t("bracket.note", { runs: data.meta.runs.toLocaleString() })}
      </p>
      <div className="flex min-w-[1100px] gap-4">
        {ROUNDS.map((round) => (
          <div key={round.key} className="flex flex-1 flex-col">
            <h3 className="mb-2 text-center text-xs font-bold uppercase tracking-wider text-slate-400">
              {t(round.key)}
            </h3>
            <div className="flex flex-1 flex-col justify-around gap-2">
              {round.nos.map((no) => (
                <MatchCard key={no} no={no} entry={data.sim?.[no]}
                  label={slotLabel(data.routing, no)}
                  when={data.schedule?.[no]} />
              ))}
            </div>
          </div>
        ))}
      </div>
    </Card>
  );
}
