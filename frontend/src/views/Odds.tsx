import { useEffect, useState } from "react";
import { api, type OddsRow } from "../api";
import { Card, Flag } from "../components/ui";
import { useT } from "../i18n";

const fmt = (v: number | null | undefined) => (v == null ? "–" : v.toFixed(2));

export default function Odds() {
  const t = useT();
  const [data, setData] = useState<Awaited<ReturnType<typeof api.odds>> | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    api.odds().then(setData).catch((e) => setErr(String(e)));
  }, []);

  if (err) return <p className="text-red-500">Failed: {err}</p>;
  if (!data) return <div className="h-96 animate-pulse rounded-2xl bg-slate-200 dark:bg-slate-800" />;

  const noMarket = data.source === "disabled";

  return (
    <div className="space-y-4">
      {noMarket && (
        <div className="rounded-xl border border-amber-300 bg-amber-50 p-3 text-sm text-amber-800 dark:border-amber-700 dark:bg-amber-950/40 dark:text-amber-200">
          {t("odds.no_key")}
        </div>
      )}
      {data.quota && (
        <p className="text-xs text-slate-400">{t("odds.quota", { n: data.quota.remaining })}</p>
      )}
      {data.matches.map((r) => (
        <Card key={r.match_id}>
          <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
            <div className="flex items-center gap-2 font-semibold">
              <Flag crest={r.home.crest} tla={r.home.tla} />
              {r.home.name} <span className="text-slate-400">vs</span> {r.away.name}
              <Flag crest={r.away.crest} tla={r.away.tla} />
            </div>
            <span className="text-xs text-slate-400">
              {new Date(r.utcDate).toLocaleString()} · {r.group ?? r.stage}
            </span>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full min-w-[640px] text-sm tabular-nums">
              <thead>
                <tr className="text-left text-[11px] uppercase text-slate-400">
                  <th className="py-1 pr-2">{t("odds.bet")}</th>
                  <th>1 ({r.home.tla})</th><th>X</th><th>2 ({r.away.tla})</th>
                  <th>{t("odds.ou")}</th><th>{t("odds.ah")}</th><th>{t("odds.corners")}</th>
                </tr>
              </thead>
              <tbody>
                {r.market?.h2h && (
                  <tr className="border-t border-slate-100 dark:border-slate-800">
                    <td className="py-1.5 pr-2 font-medium">{t("odds.market")}</td>
                    <td className={r.value?.home ? "font-bold text-emerald-500" : ""}>{fmt(r.market.h2h.home)}</td>
                    <td className={r.value?.draw ? "font-bold text-emerald-500" : ""}>{fmt(r.market.h2h.draw)}</td>
                    <td className={r.value?.away ? "font-bold text-emerald-500" : ""}>{fmt(r.market.h2h.away)}</td>
                    <td>
                      {r.market.totals
                        ? `${r.market.totals.point}: ${fmt(r.market.totals.over)}/${fmt(r.market.totals.under)}`
                        : "–"}
                    </td>
                    <td>
                      {r.market.spreads
                        ? `${r.market.spreads.point > 0 ? "+" : ""}${r.market.spreads.point}: ${fmt(r.market.spreads.home)}/${fmt(r.market.spreads.away)}`
                        : "–"}
                    </td>
                    <td>
                      {r.market.corners_totals?.length
                        ? r.market.corners_totals.slice(0, 2).map((c) =>
                            `${c.point}: ${fmt(c.over)}/${fmt(c.under)}`).join("  ")
                        : "–"}
                    </td>
                  </tr>
                )}
                <tr className="border-t border-slate-100 dark:border-slate-800">
                  <td className="py-1.5 pr-2 font-medium text-sky-600 dark:text-sky-400">
                    {t("odds.model")}
                  </td>
                  <td>{fmt(r.fair.h2h.home)}</td>
                  <td>{fmt(r.fair.h2h.draw)}</td>
                  <td>{fmt(r.fair.h2h.away)}</td>
                  <td>O {fmt(r.fair.over25)} / U {fmt(r.fair.under25)}</td>
                  <td className="text-slate-400">—</td>
                  <td>~{r.fair.expected_corners.toFixed(1)} · O9.5 {fmt(r.fair.corners_over_95)}</td>
                </tr>
              </tbody>
            </table>
          </div>
          {r.value && Object.keys(r.value).length > 0 && (
            <p className="mt-1 text-xs font-medium text-emerald-500">
              ⚡ {t("odds.value", {
                v: Object.entries(r.value).map(([k, v]) => `${k} +${(v * 100).toFixed(1)}pt`).join(", "),
              })}
            </p>
          )}
        </Card>
      ))}
      <p className="text-center text-[11px] text-slate-400">
        {t("odds.footer", { ml: data.ml ? "✓" : "✗" })}
      </p>
    </div>
  );
}
