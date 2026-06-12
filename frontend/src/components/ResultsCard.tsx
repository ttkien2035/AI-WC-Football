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
          <p className="mt-1.5 text-slate-400">
            {r.corners?.home != null &&
              `⛳ ${t("res.corners")}: ${r.home.tla} ${r.corners.home} – ${r.corners.away} ${r.away.tla}`}
            {r.stats?.possession?.home != null &&
              `  ·  ${t("res.possession")}: ${r.stats.possession.home}% – ${r.stats.possession.away}%`}
          </p>
        </div>
      )}
    </div>
  );
}
